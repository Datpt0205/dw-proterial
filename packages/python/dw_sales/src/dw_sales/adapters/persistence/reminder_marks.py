"""`ReminderMarkStorePort` on PostgreSQL (`sales.reminder_marks`, migration
4bcfa82060fc; tickets 47 and 48).

One transaction per use, bound to the caller's tenant, workspace **and
user**: the table's policy reads all three, so another person's marks are
never read or written, and the statements name the three again. A mark goes
with its notification (`ON DELETE CASCADE`), so nothing here prunes.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_sales.adapters.persistence import tables
from dw_sales.application.today import Mark, ReminderMark, ReminderMarkStorePort
from dw_sales.domain.followups import Followup

_M = tables.reminder_marks


@dataclass(frozen=True)
class SqlReminderMarkStore:
    """Implements `ReminderMarkStorePort` inside one bound transaction."""

    db: AsyncSession
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID

    def _mine(self) -> tuple[sa.ColumnElement[bool], ...]:
        return (
            _M.c.tenant_id == self.tenant_id,
            _M.c.workspace_id == self.workspace_id,
            _M.c.user_id == self.user_id,
        )

    async def marks(self) -> Sequence[ReminderMark]:
        rows = await self.db.execute(
            sa.select(_M.c.notification_id, _M.c.followup, _M.c.mark, _M.c.until, _M.c.marked_at)
            .where(*self._mine())
            .order_by(_M.c.marked_at, _M.c.notification_id)
        )
        return [
            ReminderMark(
                notification_id=r.notification_id,
                followup=Followup(r.followup),
                mark=Mark(r.mark),
                until=r.until,
                marked_at=r.marked_at,
            )
            for r in rows
        ]

    async def put(self, mark: ReminderMark) -> None:
        values = {"mark": mark.mark.value, "until": mark.until, "marked_at": mark.marked_at}
        await self.db.execute(
            pg_insert(_M)
            .values(
                notification_id=mark.notification_id,
                user_id=self.user_id,
                tenant_id=self.tenant_id,
                workspace_id=self.workspace_id,
                followup=mark.followup.value,
                **values,
            )
            .on_conflict_do_update(constraint="pk_reminder_marks", set_=values)
        )


@dataclass(frozen=True)
class SqlReminderMarkStoreFactory:
    """`ReminderMarkStoreFactory`: one transaction per use, bound to the caller."""

    session_factory: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def __call__(self, context: AccessContext) -> AsyncIterator[ReminderMarkStorePort]:
        async with tenant_session(
            self.session_factory, TenantScope.from_access_context(context)
        ) as session:
            yield SqlReminderMarkStore(
                session, context.tenant_id, context.workspace_id, context.principal_id
            )
