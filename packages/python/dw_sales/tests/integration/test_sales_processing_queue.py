"""The processing queue against PostgreSQL (ticket 25, migration 0a78ca5e96d3):
what the database owns.

- One job per message per workspace: enqueueing an active job changes
  nothing, a finished one is queued again (the upsert).
- Two workers never claim one job (`FOR UPDATE SKIP LOCKED`), due jobs run
  oldest first and, at one instant, in the order queued (`seq`).
- A settlement names its claim: a job taken back since is not settled.
- The reaper's function returns a job a dead worker left running, or fails
  it `abandoned`, and touches nothing else.
- Row security: a workspace reads its own jobs only, and the one read that
  crosses tenants returns ids only.
- The CHECKs hold whatever writes the row.

Owed when Docker is back (ticket 25, "Post-reboot checks").
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_sales.adapters.persistence.processing import SqlProcessingQueue
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import Settlement
from dw_sales.application.processing import MAX_ATTEMPTS

pytestmark = pytest.mark.integration

AN = uuid.uuid4()
NOW = datetime(2026, 10, 14, 3, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def _empty_queue(migrator: AsyncEngine) -> None:
    """Every test starts on an empty queue. The claim and the reaper cross
    tenants by design, so a job an earlier test left queued or running is one
    this test claims or reaps (CI run 38513561151: a fourth job claimed, a
    job of another world reaped). The migrator is the one role past RLS."""
    async with migrator.begin() as conn:
        await conn.execute(sa.text("TRUNCATE sales.processing_jobs"))


async def _enqueue(
    uow: SqlSalesUnitOfWorkFactory, world: World, message_id: str, at: datetime = NOW
) -> uuid.UUID:
    async with uow(world.alpha) as work:
        job, queued = await work.jobs.enqueue(message_id, AN, at, uuid.uuid4())
        await work.commit()
    assert queued
    return job.job_id


async def test_an_active_job_is_queued_once_and_a_finished_one_again(
    uow: SqlSalesUnitOfWorkFactory, world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    first = await _enqueue(uow, world, "M01")
    async with uow(world.alpha) as work:
        again, queued = await work.jobs.enqueue("M01", uuid.uuid4(), NOW, uuid.uuid4())
        await work.commit()
    assert (again.job_id, queued, again.requested_by) == (first, False, AN)

    queue = SqlProcessingQueue(app_sessions)
    claimed = await queue.claim()
    assert claimed is not None and claimed.job.job_id == first
    async with uow(world.alpha) as work:
        assert await work.jobs.settle(claimed.job, Settlement.failed("error"), NOW)
        await work.commit()

    other = uuid.uuid4()
    async with uow(world.alpha) as work:
        requeued, queued = await work.jobs.enqueue("M01", other, NOW, uuid.uuid4())
        await work.commit()
    assert (requeued.job_id, queued, requeued.status, requeued.attempts) == (
        first,
        True,
        "queued",
        0,
    )
    # The failure is remembered until a round ends done.
    assert (requeued.requested_by, requeued.failures) == (other, 1)


async def test_two_workers_never_claim_one_job(
    uow: SqlSalesUnitOfWorkFactory, world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ids = [await _enqueue(uow, world, f"M0{n}") for n in (1, 2, 3)]
    queue = SqlProcessingQueue(app_sessions)

    claims = await asyncio.gather(*(queue.claim() for _ in range(4)))

    taken = [c.job.job_id for c in claims if c is not None]
    assert sorted(map(str, taken)) == sorted(map(str, ids))


async def test_jobs_queued_at_one_instant_run_in_the_order_queued(
    uow: SqlSalesUnitOfWorkFactory, world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ids = [await _enqueue(uow, world, f"M0{n}") for n in (3, 1, 2)]
    queue = SqlProcessingQueue(app_sessions)

    order = []
    for _ in ids:
        claimed = await queue.claim()
        assert claimed is not None
        order.append(claimed.job.job_id)

    assert order == ids


async def test_a_settlement_whose_claim_was_taken_back_writes_nothing(
    uow: SqlSalesUnitOfWorkFactory,
    world: World,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _enqueue(uow, world, "M01")
    queue = SqlProcessingQueue(app_sessions)
    first = await queue.claim()
    assert first is not None
    # The worker died: the reaper puts it back, another worker claims it.
    assert await queue.reap_stale(older_than=datetime.now(UTC) + timedelta(minutes=1))
    second = await queue.claim()
    assert second is not None and second.job.attempts == first.job.attempts + 1

    async with uow(world.alpha) as work:
        stale = await work.jobs.settle(first.job, Settlement.done(), NOW)
        current = await work.jobs.settle(second.job, Settlement.done(), NOW)
        await work.commit()

    assert (stale, current) == (False, True)


async def test_the_reaper_requeues_a_dead_workers_job_then_fails_it_abandoned(
    uow: SqlSalesUnitOfWorkFactory, world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    await _enqueue(uow, world, "M01")
    queue = SqlProcessingQueue(app_sessions)
    window = timedelta(minutes=15)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        claimed = await queue.claim()
        assert claimed is not None and claimed.job.attempts == attempt
        # A job inside its window is a healthy one: left alone.
        assert await queue.reap_stale(older_than=datetime.now(UTC) - window) == []
        assert await queue.reap_stale(older_than=datetime.now(UTC) + window) == [claimed.job.job_id]

    async with uow(world.alpha) as work:
        job = await work.jobs.get("M01")
    assert job is not None
    assert (job.status, job.error, job.attempts, job.failures) == (
        "failed",
        "abandoned",
        MAX_ATTEMPTS,
        1,
    )
    assert await queue.claim() is None


async def test_a_workspace_reads_its_own_jobs_and_the_due_scopes_are_ids(
    uow: SqlSalesUnitOfWorkFactory,
    world: World,
    sales_app_engine: AsyncEngine,
) -> None:
    await _enqueue(uow, world, "M01")

    async with uow(world.alpha_other) as work:
        assert await work.jobs.list_all() == []
    async with uow(world.beta) as work:
        assert await work.jobs.get("M01") is None
    async with sales_app_engine.connect() as conn:
        unscoped = await conn.execute(sa.text("SELECT count(*) FROM sales.processing_jobs"))
        assert unscoped.scalar_one() == 0
        due = (await conn.execute(sa.text("SELECT * FROM sales.processing_scopes_due()"))).all()
    assert (world.alpha.tenant_id.value, world.alpha.workspace_id.value) in [tuple(r) for r in due]
    assert all(len(row) == 2 for row in due)


@pytest.mark.parametrize(
    "change",
    [
        "error = 'whatever'",
        "status = 'running', claimed_at = NULL",
        "status = 'failed', error = NULL",
        "message_id = 'has a space'",
    ],
)
async def test_the_checks_hold_whatever_writes_the_row(
    uow: SqlSalesUnitOfWorkFactory, world: World, migrator: AsyncEngine, change: str
) -> None:
    job_id = await _enqueue(uow, world, "M01")

    with pytest.raises(IntegrityError):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(f"UPDATE sales.processing_jobs SET {change} WHERE id = :id"),
                {"id": job_id},
            )
