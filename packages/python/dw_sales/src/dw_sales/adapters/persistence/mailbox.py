"""DW1's stored mailbox in PostgreSQL (ticket 43, migration e544ff20fad6).

`SqlMailbox` is the mailbox once real mail arrives: the `sales_mail_drop`
lane writes it (`MailStorePort`), "Tải PO lên" writes a person's upload into
it (`UploadStorePort`, ticket 18), and every service reads it (`InboxPort`),
in the API and the worker alike. Each call is one short transaction bound to
the scope it is asked about; RLS keeps one workspace's mail from another, and
nothing here names a tenant beyond binding the scope.

A message is stored whole, as its model dumps it, and read back through the
same model: no field is named here twice. An attachment's bytes are held to
the description the message carries (`AttachmentContent`) every time they
are read.

Each message is stored with its thread key (ticket 24), by
`threads.thread_key` over the messages already stored that its headers name,
in the transaction that stores it; a thread is read by `threads.thread_keys`
through `ix_mailbox_messages_thread_key`, never by listing the mailbox.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.messages import AttachmentContent, InboundMessage
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.adapters.persistence.uow import AuditFactory
from dw_sales.application.mail_drop import MailFile
from dw_sales.application.order_ports import PoUpload
from dw_sales.application.ports import SalesScope
from dw_sales.application.threads import KeyedMessage, thread_key, thread_keys

_M = tables.mailbox_messages
_A = tables.mailbox_attachments
_F = tables.mailbox_files


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


@dataclass(frozen=True)
class SqlMailbox:
    """Implements `InboxPort`, `MailStorePort`, `UploadStorePort` and
    `UploadLookupPort` over the stored mailbox."""

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

    # ---------------------------------------------------- ThreadMembersPort --

    async def thread_messages(
        self, scope: SalesScope, message: InboundMessage
    ) -> Sequence[InboundMessage]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            own = await session.scalar(
                sa.select(_M.c.thread_key).where(_M.c.message_id == message.message_id).limit(1)
            )
            named = [m.thread_key for m in await _named(session, message)]
            keys = thread_keys(own, named)
            if not keys:
                return []
            documents = await session.scalars(
                sa.select(_M.c.message)
                .where(_M.c.thread_key.in_(sorted(keys)))
                .order_by(_M.c.received_at, _M.c.message_id)
            )
            return [InboundMessage.model_validate(document) for document in documents]

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

    async def refuse(self, scope: SalesScope, *, source: str, reason: str) -> None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            await session.execute(
                sa.insert(_F).values(
                    **scope_values(scope), source_name=source, outcome="refused", reason=reason
                )
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
                        thread_key=thread_key(message, await _named(session, message)),
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
            await _store_attachments(session, scope, mail)
            await self.audit(session).append(event)
        return True

    # ------------------------------------------------------ UploadStorePort --

    async def store_upload(
        self, scope: SalesScope, mail: MailFile, upload: PoUpload, *, event: AuditEvent
    ) -> bool:
        message = mail.message
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            # Its id is its files' hash and its time is when it was uploaded,
            # so the key the primary key would catch differs on a second
            # upload: one writer per id, and the id looked for first.
            await session.execute(
                sa.select(
                    sa.func.pg_advisory_xact_lock(sa.func.hashtextextended(message.message_id, 0))
                )
            )
            if await session.scalar(
                sa.select(_M.c.message_id).where(_M.c.message_id == message.message_id)
            ):
                return False
            await session.execute(
                sa.insert(_M).values(
                    **scope_values(scope),
                    message_id=message.message_id,
                    received_at=message.received_at,
                    sender_address=message.sender.address,
                    internet_message_id=None,
                    source_name=message.attachments[0].name,
                    message=message.model_dump(mode="json"),
                    # Its own: an upload names no message it answers.
                    thread_key=thread_key(message, ()),
                    uploaded_by=upload.uploaded_by,
                    uploaded_for=upload.customer_code,
                )
            )
            await _store_attachments(session, scope, mail)
            await self.audit(session).append(event)
        return True

    async def upload_of(self, scope: SalesScope, message_id: str) -> PoUpload | None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            row = (
                await session.execute(
                    sa.select(_M.c.uploaded_for, _M.c.uploaded_by).where(
                        _M.c.message_id == message_id, _M.c.uploaded_by.is_not(None)
                    )
                )
            ).first()
        if row is None:
            return None
        return PoUpload(customer_code=row.uploaded_for, uploaded_by=row.uploaded_by)


async def _store_attachments(session: AsyncSession, scope: SalesScope, mail: MailFile) -> None:
    message = mail.message
    if not message.attachments:
        return
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


async def _named(session: AsyncSession, message: InboundMessage) -> list[KeyedMessage]:
    """The stored messages ``message``'s `In-Reply-To`/`References` name, in
    the scope the session is bound to (RLS), by the Message-ID index."""
    if not message.references:
        return []
    rows = await session.execute(
        sa.select(_M.c.message_id, _M.c.received_at, _M.c.thread_key).where(
            _M.c.internet_message_id.in_(list(message.references)),
            _M.c.message_id != message.message_id,
        )
    )
    return [KeyedMessage(row.message_id, row.received_at, row.thread_key) for row in rows]


async def _message(session: AsyncSession, message_id: str) -> InboundMessage | None:
    document = await session.scalar(sa.select(_M.c.message).where(_M.c.message_id == message_id))
    return None if document is None else InboundMessage.model_validate(document)
