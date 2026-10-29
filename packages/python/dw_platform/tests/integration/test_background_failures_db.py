"""Integration: a failed outbox event waits before its next attempt, one that
spent them is found across tenants for the alarm, and an administrator sees
and sends back only their own workspace's (2026-10-29)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.background_failures_repo import SqlStalledEvents
from dw_platform.adapters.persistence.outbox_drain import SqlOutboxDrain
from dw_platform.adapters.persistence.uow import SqlPlatformUnitOfWorkFactory
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.outbox import OutboxEvent

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
WAITING_TYPE = "test.outbox.waiting.v1"
STOPPED_TYPE = "test.outbox.stopped.v1"


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at


@pytest.fixture
async def sessions(db_urls: DatabaseUrls) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(db_urls.app)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def migrator(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.migrator)
    yield engine
    await engine.dispose()


def _context(tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> AccessContext:
    return AccessContext(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        principal_id=uuid.uuid4(),
        roles=frozenset({"member"}),
        scopes=frozenset(),
        plan_id="professional",
    )


async def _announce(
    sessions: async_sessionmaker[AsyncSession], context: AccessContext, event_type: str
) -> OutboxEvent:
    event = OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        event_type=event_type,
        schema_version="1.0",
        aggregate_id=uuid.uuid4(),
        occurred_at=NOW,
        actor_id=context.principal_id,
    )
    async with SqlPlatformUnitOfWorkFactory(sessions)(context) as uow:
        await uow.outbox.add(event)
        await uow.commit()
    return event


async def _stop(drain: SqlOutboxDrain, event: OutboxEvent, attempts: int) -> None:
    for _ in range(attempts):
        (claimed,) = await drain.claim_batch(
            event_types=[event.event_type], limit=10, max_attempts=attempts
        )
        assert claimed.id == event.id
        await drain.record_failure(event.id, error="RuntimeError: Key (price)=(9)", retry_at=NOW)


def _audit(context: AccessContext, event_id: uuid.UUID) -> AuditEvent:
    return AuditEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action="platform.outbox.requeued",
        resource_type="outbox_event",
        resource_id=str(event_id),
        occurred_at=NOW,
    )


async def test_a_failed_event_is_not_claimed_again_before_its_time(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    context = _context(uuid.uuid4(), uuid.uuid4())
    event = await _announce(sessions, context, WAITING_TYPE)
    clock = Clock(NOW)
    drain = SqlOutboxDrain(sessions, clock)

    await drain.claim_batch(event_types=[WAITING_TYPE], limit=10, max_attempts=5)
    await drain.record_failure(
        event.id, error="RuntimeError: reader down", retry_at=NOW + timedelta(seconds=30)
    )

    clock.at = NOW + timedelta(seconds=29)
    assert await drain.claim_batch(event_types=[WAITING_TYPE], limit=10, max_attempts=5) == []
    clock.at = NOW + timedelta(seconds=30)
    (again,) = await drain.claim_batch(event_types=[WAITING_TYPE], limit=10, max_attempts=5)
    assert (again.id, again.attempts) == (event.id, 2)


async def test_a_stopped_event_is_found_for_the_alarm_and_sent_back_by_its_workspace(
    sessions: async_sessionmaker[AsyncSession], migrator: AsyncEngine
) -> None:
    tenant = uuid.uuid4()
    mine, other_workspace = _context(tenant, uuid.uuid4()), _context(tenant, uuid.uuid4())
    other_tenant = _context(uuid.uuid4(), mine.workspace_id)
    drain = SqlOutboxDrain(sessions, Clock(NOW))
    event = await _announce(sessions, mine, STOPPED_TYPE)
    await _stop(drain, event, attempts=3)

    # The alarm finds it across tenants; the drain no longer claims it.
    assert event.id in {e.id for e in await drain.exhausted(max_attempts=3, limit=1000)}
    assert await drain.claim_batch(event_types=[STOPPED_TYPE], limit=10, max_attempts=3) == []

    page = SqlStalledEvents(sessions)
    (shown,) = [e for e in await page.stalled(mine, max_attempts=3) if e.id == event.id]
    assert (shown.attempts, shown.error_kind) == (3, "RuntimeError")
    # Another workspace of the tenant, or another tenant, sees nothing of it
    # and cannot send it back.
    assert event.id not in {e.id for e in await page.stalled(other_workspace, max_attempts=3)}
    assert event.id not in {e.id for e in await page.stalled(other_tenant, max_attempts=3)}
    for stranger in (other_workspace, other_tenant):
        assert not await page.requeue(
            stranger, event_id=event.id, max_attempts=3, audit=_audit(stranger, event.id)
        )

    assert await page.requeue(mine, event_id=event.id, max_attempts=3, audit=_audit(mine, event.id))

    async with migrator.connect() as conn:
        row = (
            await conn.execute(
                sa.select(tables.outbox_events).where(tables.outbox_events.c.id == event.id)
            )
        ).one()
        audited = await conn.scalar(
            sa.select(sa.func.count()).where(
                tables.audit_events.c.action == "platform.outbox.requeued",
                tables.audit_events.c.resource_id == str(event.id),
            )
        )
    assert (row.attempts, row.next_attempt_at, row.last_error) == (0, None, None)
    assert audited == 1
    (back,) = await drain.claim_batch(event_types=[STOPPED_TYPE], limit=10, max_attempts=3)
    assert back.id == event.id
