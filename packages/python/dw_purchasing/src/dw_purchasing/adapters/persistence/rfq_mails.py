"""DW2's queue of RFQ mails in PostgreSQL (migration da6950544c81).

`SqlRfqMails` implements `RfqMailsPort` for the API and the
`purchasing_outbound` lane. Each call is one short transaction bound to the
scope it is asked about, its audit event inside it; RLS keeps one workspace's
mails from another.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.rule_versions import ContextScope
from dw_platform.domain.audit import AuditEvent
from dw_purchasing.adapters.persistence.store import AuditFactory, metadata
from dw_purchasing.application.rfq_mail import MailError, RfqMail

_TS = sa.TIMESTAMP(timezone=True)

rfq_mails = sa.Table(
    "rfq_mails",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("case_id", UUID(as_uuid=True), nullable=False),
    sa.Column("supplier_code", sa.Text, nullable=False),
    sa.Column("mailbox", sa.Text, nullable=False),
    sa.Column("recipients", JSONB, nullable=False),
    sa.Column("subject", sa.Text, nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("error", sa.Text),
    sa.Column("queued_by", UUID(as_uuid=True), nullable=False),
    sa.Column("queued_at", _TS, nullable=False),
    sa.Column("written_at", _TS),
    sa.Column("settled_at", _TS),
)

_R = rfq_mails
ALREADY_SENT = "thư hỏi giá cho nhà cung cấp này đã được gửi hoặc đang gửi"


def _bound(scope: ContextScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


def _mail(row: Any) -> RfqMail:
    return RfqMail(
        mail_id=row.id,
        case_id=row.case_id,
        supplier_code=row.supplier_code,
        mailbox=row.mailbox,
        recipients=tuple(row.recipients),
        subject=row.subject,
        body=row.body,
        status=row.status,
        error=row.error,
        queued_by=row.queued_by,
        queued_at=row.queued_at,
        written_at=row.written_at,
        settled_at=row.settled_at,
    )


@dataclass(frozen=True)
class SqlRfqMails:
    """Implements `RfqMailsPort`."""

    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    async def add(self, mail: RfqMail, event: AuditEvent) -> None:
        scope = TenantScope(tenant_id=event.tenant_id.value, workspace_id=event.workspace_id.value)
        try:
            async with tenant_session(self.session_factory, scope) as session:
                await session.execute(
                    sa.insert(_R).values(
                        id=mail.mail_id,
                        tenant_id=scope.tenant_id,
                        workspace_id=scope.workspace_id,
                        case_id=mail.case_id,
                        supplier_code=mail.supplier_code,
                        mailbox=mail.mailbox,
                        recipients=list(mail.recipients),
                        subject=mail.subject,
                        body=mail.body,
                        status="queued",
                        queued_by=mail.queued_by,
                        queued_at=mail.queued_at,
                    )
                )
                await self.audit(session).append(event)
        except IntegrityError as refused:
            if "uq_rfq_mails_case_id_supplier_code_active" not in str(refused.orig):
                raise
            raise ConflictError(ALREADY_SENT, details={"rule": "already_sent"}) from None

    async def of_case(self, scope: ContextScope, case_id: uuid.UUID) -> Sequence[RfqMail]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            rows = await session.execute(
                sa.select(_R).where(_R.c.case_id == case_id).order_by(_R.c.queued_at, _R.c.id)
            )
            return [_mail(row) for row in rows]

    async def get(self, scope: ContextScope, mail_id: uuid.UUID) -> RfqMail | None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            row = (await session.execute(sa.select(_R).where(_R.c.id == mail_id))).first()
        return None if row is None else _mail(row)

    async def pending(self, scope: ContextScope) -> Sequence[RfqMail]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            rows = await session.execute(
                sa.select(_R)
                .where(_R.c.status.in_(("queued", "written")))
                .order_by(_R.c.queued_at, _R.c.id)
            )
            return [_mail(row) for row in rows]

    async def written(self, scope: ContextScope, mail_id: uuid.UUID, *, at: datetime) -> bool:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            done = await session.scalar(
                sa.update(_R)
                .where(_R.c.id == mail_id, _R.c.status == "queued")
                .values(status="written", written_at=at)
                .returning(_R.c.id)
            )
        return done is not None

    async def settle(
        self,
        scope: ContextScope,
        mail_id: uuid.UUID,
        *,
        status: Literal["sent", "failed", "stalled"],
        error: MailError | None,
        at: datetime,
        event: AuditEvent,
    ) -> bool:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            done = await session.scalar(
                sa.update(_R)
                .where(_R.c.id == mail_id, _R.c.status.in_(("queued", "written")))
                .values(status=status, error=error, settled_at=at)
                .returning(_R.c.id)
            )
            if done is None:
                return False
            await self.audit(session).append(event)
        return True
