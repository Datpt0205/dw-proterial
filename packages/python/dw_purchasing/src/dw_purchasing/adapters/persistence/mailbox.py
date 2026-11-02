"""DW2's stored mailbox in PostgreSQL (migration 32c1f04b76d6).

`SqlPurchasingMailbox` is the mailbox once real mail arrives: the
`purchasing_mail_drop` lane writes it (`MailStorePort`) and every service
reads it (`InboxPort`), in the API and the worker alike. Each call is one
short transaction bound to the scope it is asked about; RLS keeps one
workspace's mail from another, and nothing here names a tenant beyond
binding the scope.

A message is stored whole, as its model dumps it, and read back through the
same model: no field is named here twice. Its attachments' bytes are kept
beside it for the steps that will read them (the Excel PR form, a scanned
request); nothing reads them yet, and a file the lane has handled is not read
again, so what is not kept now is lost.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import ContextScope
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.messages import InboundMessage
from dw_purchasing.adapters.persistence.store import AuditFactory, metadata
from dw_purchasing.application.mail_drop import MailFile

_TS = sa.TIMESTAMP(timezone=True)

mailbox_messages = sa.Table(
    "mailbox_messages",
    metadata,
    sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("message_id", sa.Text, primary_key=True),
    sa.Column("received_at", _TS, primary_key=True),
    sa.Column("sender_address", sa.Text, nullable=False),
    sa.Column("internet_message_id", sa.Text),
    sa.Column("source_name", sa.Text, nullable=False),
    sa.Column("message", JSONB, nullable=False),
    sa.Column("stored_at", _TS, nullable=False, server_default=sa.func.now()),
)

mailbox_attachments = sa.Table(
    "mailbox_attachments",
    metadata,
    sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("message_id", sa.Text, primary_key=True),
    sa.Column("received_at", _TS, primary_key=True),
    sa.Column("attachment_id", sa.Text, primary_key=True),
    sa.Column("content", sa.LargeBinary, nullable=False),
    sa.Column("stored_at", _TS, nullable=False, server_default=sa.func.now()),
)

# Every file the drop lane handled and what became of it, so a restart does
# not parse the folder's history again.
mailbox_files = sa.Table(
    "mailbox_files",
    metadata,
    sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("source_name", sa.Text, primary_key=True),
    sa.Column("handled_at", _TS, primary_key=True, server_default=sa.func.now()),
    sa.Column("outcome", sa.Text, nullable=False),
    sa.Column("message_id", sa.Text),
    sa.Column("reason", sa.Text),
)

_M = mailbox_messages
_A = mailbox_attachments
_F = mailbox_files


def _bound(scope: ContextScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


def _keys(scope: ContextScope) -> dict[str, Any]:
    return {"tenant_id": scope.tenant_id.value, "workspace_id": scope.workspace_id.value}


@dataclass(frozen=True)
class SqlPurchasingMailbox:
    """Implements `InboxPort` and `MailStorePort` over the stored mailbox."""

    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    # ------------------------------------------------------------ InboxPort --

    async def list_messages(self, context: AccessContext) -> Sequence[InboundMessage]:
        async with tenant_session(self.session_factory, _bound(ContextScope.of(context))) as s:
            documents = await s.scalars(
                sa.select(_M.c.message).order_by(_M.c.received_at, _M.c.message_id)
            )
            return [InboundMessage.model_validate(document) for document in documents]

    async def get_message(self, context: AccessContext, message_id: str) -> InboundMessage | None:
        async with tenant_session(self.session_factory, _bound(ContextScope.of(context))) as s:
            document = await s.scalar(sa.select(_M.c.message).where(_M.c.message_id == message_id))
        return None if document is None else InboundMessage.model_validate(document)

    # -------------------------------------------------------- MailStorePort --

    async def handled_sources(self, scope: ContextScope) -> frozenset[str]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            return frozenset(await session.scalars(sa.select(_F.c.source_name)))

    async def refuse(self, scope: ContextScope, *, source: str, reason: str) -> None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            await session.execute(
                sa.insert(_F).values(
                    **_keys(scope), source_name=source, outcome="refused", reason=reason
                )
            )

    async def store(
        self, scope: ContextScope, mail: MailFile, *, source: str, event: AuditEvent
    ) -> bool:
        message = mail.message
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            # One writer per mail at a time: two files of one mail, read by
            # two workers at once, would both find the other absent.
            key = message.internet_message_id or message.message_id
            await session.execute(
                sa.select(
                    sa.func.pg_advisory_xact_lock(sa.func.hashtextextended("purchasing:" + key, 0))
                )
            )
            stored = (
                None
                if message.internet_message_id is None
                else await session.scalar(
                    sa.select(_M.c.message_id).where(
                        _M.c.internet_message_id == message.internet_message_id,
                        _M.c.sender_address == message.sender.address,
                    )
                )
            )
            inserted = (
                None
                if stored is not None
                else await session.scalar(
                    insert(_M)
                    .values(
                        **_keys(scope),
                        message_id=message.message_id,
                        received_at=message.received_at,
                        sender_address=message.sender.address,
                        internet_message_id=message.internet_message_id,
                        source_name=source,
                        message=message.model_dump(mode="json"),
                    )
                    .on_conflict_do_nothing()
                    .returning(_M.c.message_id)
                )
            )
            await session.execute(
                sa.insert(_F).values(
                    **_keys(scope),
                    source_name=source,
                    outcome="stored" if inserted is not None else "duplicate",
                    message_id=stored or message.message_id,
                )
            )
            if inserted is None:
                return False
            if message.attachments:
                await session.execute(
                    sa.insert(_A),
                    [
                        {
                            **_keys(scope),
                            "message_id": message.message_id,
                            "received_at": message.received_at,
                            "attachment_id": attachment.attachment_id,
                            "content": mail.contents[attachment.attachment_id],
                        }
                        for attachment in message.attachments
                    ],
                )
            await self.audit(session).append(event)
        return True
