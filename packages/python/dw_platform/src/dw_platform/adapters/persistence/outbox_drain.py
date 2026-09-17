"""The worker's side of the outbox: cross-tenant, one batch at a time.

This is the only place in the platform package that reads rows without a tenant
scope, and it says so out loud. A dispatcher drains every tenant's outbox on one
connection, so it sets ``app.worker_drain`` instead of ``app.tenant_id`` and
relies on the policy migration 0033 added.

Delivery is at-least-once by design: the attempt is counted when the row is
claimed, the effect runs outside this transaction, and ``mark_processed`` lands
afterwards. A process that dies between the two retries the event, which is why
every effect wired to this drain has to be idempotent. Marking first would give
at-most-once and lose the effect instead, and losing it is the worse failure -
nothing downstream would ever notice.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ports import UtcClock
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.repositories import outbox_from_row
from dw_platform.domain.outbox import OutboxEvent

# SET LOCAL semantics (third argument true) so the flag dies with the
# transaction. Session-wide it would ride the pooled connection back into the
# pool and hand the next caller a connection that can read every tenant.
_ENABLE_DRAIN = text("SELECT set_config('app.worker_drain', 'on', true)")

_ERROR_LIMIT = 2000


@dataclass(frozen=True)
class SqlOutboxDrain:
    """Implements ``OutboxDrainPort``."""

    session_factory: async_sessionmaker[AsyncSession]
    clock: UtcClock

    async def claim_batch(
        self, *, event_types: Sequence[str], limit: int, max_attempts: int
    ) -> list[OutboxEvent]:
        if not event_types:
            return []
        async with self.session_factory() as session, session.begin():
            await session.execute(_ENABLE_DRAIN)
            candidates = (
                await session.execute(
                    sa.select(tables.outbox_events.c.id)
                    .where(
                        tables.outbox_events.c.processed_at.is_(None),
                        tables.outbox_events.c.event_type.in_(list(event_types)),
                        tables.outbox_events.c.attempts < max_attempts,
                    )
                    .order_by(tables.outbox_events.c.occurred_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).scalars()
            claimed = list(candidates)
            if not claimed:
                return []
            rows = await session.execute(
                sa.update(tables.outbox_events)
                .where(tables.outbox_events.c.id.in_(claimed))
                .values(attempts=tables.outbox_events.c.attempts + 1)
                .returning(tables.outbox_events)
            )
            events = [outbox_from_row(row) for row in rows]
            # Ordering is lost by the UPDATE ... RETURNING, and the dispatcher
            # delivers in the order the events happened.
            events.sort(key=lambda event: event.occurred_at)
            return events

    async def mark_processed(self, event_id: uuid.UUID) -> None:
        async with self.session_factory() as session, session.begin():
            await session.execute(_ENABLE_DRAIN)
            await session.execute(
                sa.update(tables.outbox_events)
                .where(
                    tables.outbox_events.c.id == event_id,
                    tables.outbox_events.c.processed_at.is_(None),
                )
                .values(processed_at=self.clock.now(), last_error=None)
            )

    async def record_failure(self, event_id: uuid.UUID, *, error: str) -> None:
        async with self.session_factory() as session, session.begin():
            await session.execute(_ENABLE_DRAIN)
            await session.execute(
                sa.update(tables.outbox_events)
                .where(tables.outbox_events.c.id == event_id)
                .values(last_error=error[:_ERROR_LIMIT])
            )
