"""`OutboundMailStorePort` on PostgreSQL (`sales.outbound_mails`, migration
`c42ed45c73a2`), and the workspaces with a mail pending for the worker's
`sales_outbound` lane (`sales.outbound_scopes_pending()`, ids only)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.application.case_store import OutboundError, OutboundMail, OutboundStatus
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind

_M = tables.outbound_mails
_SCOPES = sa.text("SELECT tenant_id, workspace_id FROM sales.outbound_scopes_pending()")
_PENDING = ("queued", "written")


def _mail(row: RowMapping) -> OutboundMail:
    return OutboundMail(
        mail_id=row["id"],
        case_kind=CaseKind(row["case_kind"]),
        case_id=row["case_id"],
        artifact_id=row["artifact_id"],
        requested_by=row["requested_by"],
        mailbox=row["mailbox"],
        status=row["status"],
        queued_at=row["queued_at"],
        settled_at=row["settled_at"],
        error=row["error"],
    )


@dataclass(frozen=True)
class SqlOutboundMails:
    """Implements `OutboundMailStorePort`."""

    session: AsyncSession
    scope: SalesScope

    def _mine(self) -> tuple[sa.ColumnElement[bool], ...]:
        return (
            _M.c.tenant_id == self.scope.tenant_id.value,
            _M.c.workspace_id == self.scope.workspace_id.value,
        )

    async def add(self, mail: OutboundMail) -> OutboundMail:
        row = (
            (
                await self.session.execute(
                    pg_insert(_M)
                    .values(
                        id=mail.mail_id,
                        **scope_values(self.scope),
                        case_kind=mail.case_kind.value,
                        case_id=mail.case_id,
                        artifact_id=mail.artifact_id,
                        requested_by=mail.requested_by,
                        mailbox=mail.mailbox,
                        status=mail.status,
                        queued_at=mail.queued_at,
                    )
                    .on_conflict_do_nothing()
                    .returning(*_M.c)
                )
            )
            .mappings()
            .first()
        )
        if row is not None:
            return _mail(row)
        held = (
            (
                await self.session.execute(
                    sa.select(_M).where(
                        *self._mine(),
                        _M.c.artifact_id == mail.artifact_id,
                        _M.c.status.in_(("queued", "written", "sent")),
                    )
                )
            )
            .mappings()
            .one()
        )
        return _mail(held)

    async def get(self, mail_id: uuid.UUID) -> OutboundMail | None:
        row = (
            (await self.session.execute(sa.select(_M).where(*self._mine(), _M.c.id == mail_id)))
            .mappings()
            .first()
        )
        return None if row is None else _mail(row)

    async def for_case(self, case_kind: CaseKind, case_id: uuid.UUID) -> Sequence[OutboundMail]:
        rows = await self.session.execute(
            sa.select(_M)
            .where(*self._mine(), _M.c.case_kind == case_kind.value, _M.c.case_id == case_id)
            .order_by(_M.c.queued_at.desc(), _M.c.id)
        )
        return [_mail(r) for r in rows.mappings()]

    async def pending(self) -> Sequence[OutboundMail]:
        rows = await self.session.execute(
            sa.select(_M)
            .where(*self._mine(), _M.c.status.in_(_PENDING))
            .order_by(_M.c.queued_at, _M.c.id)
        )
        return [_mail(r) for r in rows.mappings()]

    async def settle(
        self,
        mail_id: uuid.UUID,
        status: OutboundStatus,
        at: datetime,
        error: OutboundError | None = None,
    ) -> bool:
        pending = status in _PENDING
        done = await self.session.execute(
            sa.update(_M)
            .where(*self._mine(), _M.c.id == mail_id, _M.c.status.in_(_PENDING))
            .values(status=status, settled_at=None if pending else at, error=error)
        )
        return bool(done.rowcount)  # type: ignore[attr-defined]


@dataclass(frozen=True)
class SqlOutboundScopes:
    """The workspaces with a mail pending, for the worker's lane."""

    session_factory: async_sessionmaker[AsyncSession]

    async def scopes(self) -> Sequence[SalesScope]:
        async with self.session_factory() as session:
            rows = (await session.execute(_SCOPES)).all()
        return [SalesScope(TenantId(t), WorkspaceId(w)) for t, w in rows]
