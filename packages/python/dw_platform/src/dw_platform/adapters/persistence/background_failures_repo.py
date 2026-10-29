"""`StalledEventsPort` on PostgreSQL: the caller's workspace's outbox events
that spent their attempts, under the tenant's RLS, and sending one back to the
queue with its audit row in the same transaction."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_platform.application.background_failures import StalledEvent, error_kind
from dw_platform.domain.audit import AuditEvent

_E = tables.outbox_events


def _stopped(context: AccessContext, max_attempts: int) -> tuple[sa.ColumnElement[bool], ...]:
    return (
        _E.c.workspace_id == context.workspace_id,
        _E.c.processed_at.is_(None),
        _E.c.attempts >= max_attempts,
    )


@dataclass(frozen=True)
class SqlStalledEvents:
    session_factory: async_sessionmaker[AsyncSession]

    async def stalled(self, context: AccessContext, *, max_attempts: int) -> list[StalledEvent]:
        async with tenant_session(
            self.session_factory, TenantScope.from_access_context(context)
        ) as session:
            rows = await session.execute(
                sa.select(
                    _E.c.id, _E.c.event_type, _E.c.occurred_at, _E.c.attempts, _E.c.last_error
                )
                .where(*_stopped(context, max_attempts))
                .order_by(_E.c.occurred_at)
            )
            return [
                StalledEvent(
                    id=row.id,
                    event_type=row.event_type,
                    occurred_at=row.occurred_at,
                    attempts=row.attempts,
                    error_kind=error_kind(row.last_error),
                )
                for row in rows
            ]

    async def requeue(
        self, context: AccessContext, *, event_id: uuid.UUID, max_attempts: int, audit: AuditEvent
    ) -> bool:
        async with tenant_session(
            self.session_factory, TenantScope.from_access_context(context)
        ) as session:
            found = await session.scalar(
                sa.update(_E)
                .where(_E.c.id == event_id, *_stopped(context, max_attempts))
                .values(attempts=0, next_attempt_at=None, last_error=None)
                .returning(_E.c.id)
            )
            if found is None:
                return False
            await SqlAuditRepository(session).append(audit)
            return True
