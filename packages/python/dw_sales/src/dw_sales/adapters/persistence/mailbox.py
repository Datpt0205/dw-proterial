"""DW1's stored mailbox in PostgreSQL (ticket 43, migration e544ff20fad6).

`SqlMailbox` is the mailbox once real mail arrives: the `sales_mail_drop`
lane writes it (`MailStorePort`) and every service reads it (`InboxPort`),
in the API and the worker alike. Each call is one short transaction bound to
the scope it is asked about; RLS keeps one workspace's mail from another, and
nothing here names a tenant beyond binding the scope.

A message is stored whole, as its model dumps it, and read back through the
same model: no field is named here twice. An attachment's bytes are held to
the description the message carries (`AttachmentContent`) every time they
are read.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.adapters.persistence.uow import AuditFactory
from dw_sales.application.mail_drop import MailFile
from dw_sales.application.ports import SalesScope
from dw_sales.domain.messages import AttachmentContent, InboundMessage

_M = tables.mailbox_messages
_A = tables.mailbox_attachments
_F = tables.mailbox_files


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


@dataclass(frozen=True)
class SqlMailbox:
    """Implements `InboxPort` and `MailStorePort` over the stored mailbox."""

    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    # ------------------------------------------------------------ InboxPort --

    async def list_messages(self, scope: SalesScope) -> Sequence[InboundMessage]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            documents = await session.scalars(
                sa.select(_M.c.message).order_by(_M.c.received_at, _M.c.message_id)
            )
            return [InboundMessage.model_validate(document) for document in documents]

    async def get_message(self, scope: SalesScope, message_id: str) -> InboundMessage | None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            return await _message(session, message_id)

    async def read_attachment(
        self, scope: SalesScope, message_id: str, attachment_id: str
    ) -> AttachmentContent | None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            message = await _message(session, message_id)
            attachment = None if message is None else message.attachment(attachment_id)
            if message is None or attachment is None:
                return None
            data = await session.scalar(
                sa.select(_A.c.content).where(
                    _A.c.message_id == message_id,
                    _A.c.received_at == message.received_at,
                    _A.c.attachment_id == attachment_id,
                )
            )
        if data is None:
            return None
        return AttachmentContent(attachment=attachment, data=data)

    # -------------------------------------------------------- MailStorePort --

    async def handled_sources(self, scope: SalesScope) -> frozenset[str]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            return frozenset(await session.scalars(sa.select(_F.c.source_name)))

    async def leave_out(self, scope: SalesScope, *, source: str) -> None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            await session.execute(
                sa.insert(_F).values(**scope_values(scope), source_name=source, outcome="left_out")
            )

    async def store(
        self, scope: SalesScope, mail: MailFile, *, source: str, event: AuditEvent
    ) -> bool:
        message = mail.message
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            # One writer per mail at a time: two files of one mail, read by
            # two workers at once, would both find the other absent.
            key = message.internet_message_id or message.message_id
            await session.execute(
                sa.select(sa.func.pg_advisory_xact_lock(sa.func.hashtextextended(key, 0)))
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
                        **scope_values(scope),
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
            if inserted is None:
                await session.execute(
                    sa.insert(_F).values(
                        **scope_values(scope),
                        source_name=source,
                        outcome="duplicate",
                        message_id=stored or message.message_id,
                    )
                )
                return False
            await session.execute(
                sa.insert(_F).values(
                    **scope_values(scope),
                    source_name=source,
                    outcome="stored",
                    message_id=message.message_id,
                )
            )
            if message.attachments:
                await session.execute(
                    sa.insert(_A),
                    [
                        {
                            **scope_values(scope),
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


async def _message(session: AsyncSession, message_id: str) -> InboundMessage | None:
    document = await session.scalar(sa.select(_M.c.message).where(_M.c.message_id == message_id))
    return None if document is None else InboundMessage.model_validate(document)
