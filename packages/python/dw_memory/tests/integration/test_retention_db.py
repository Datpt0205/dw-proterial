"""Retention against real Postgres: what goes, what stays, and what must never go.

`retention_policy` was a column every row wrote and nothing read. These prove it
is now load-bearing — and prove the two cases where deleting would be the bug:
a class held for a legal obligation, and a class this build has never heard of.

Against a database because the sweep runs under `app.worker_drain`, and whether
that GUC actually opens the rows is a question only the policy engine answers.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from runtime_harness import RuntimeUrls
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_memory import tables
from dw_memory.retention import RetentionClass, RetentionPolicy, SqlMemoryRetention

pytestmark = pytest.mark.integration

TENANT = uuid.UUID(int=0xEE00)
OTHER_TENANT = uuid.UUID(int=0xEE01)
WORKSPACE = uuid.UUID(int=0xEE02)
NOW = datetime(2026, 9, 18, tzinfo=UTC)


@dataclass(frozen=True)
class _Clock:
    def now(self) -> datetime:
        return NOW


def _policy(**overrides: object) -> RetentionPolicy:
    fields: dict[str, object] = {
        "schema_version": "1.0",
        "policy_id": "retention",
        "policy_version": "1.0.0",
        "classes": {
            "default": RetentionClass(days=730, description="thường"),
            "ephemeral": RetentionClass(days=30, description="ngắn"),
            "legal_hold": RetentionClass(days=None, description="giữ vô hạn"),
        },
        "batch_limit": 1000,
    }
    fields.update(overrides)
    return RetentionPolicy.model_validate(fields)


@pytest.fixture
async def sweep(
    urls: RuntimeUrls,
) -> AsyncIterator[tuple[SqlMemoryRetention, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine(urls.app, poolclass=NullPool)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield SqlMemoryRetention(sessions, _policy(), _Clock()), sessions
    finally:
        await engine.dispose()


async def _memory(
    sessions: async_sessionmaker[AsyncSession],
    *,
    retention: str,
    age_days: int,
    tenant: uuid.UUID = TENANT,
) -> uuid.UUID:
    memory_id, run_id = uuid.uuid4(), uuid.uuid4()
    async with sessions() as session, session.begin():
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)}
        )
        # A real run: `fk_items_created_by_run_id_worker_runs` refuses a memory
        # that names a run nobody made. Another Mốc 4 constraint catching the
        # fixture rather than the code.
        await session.execute(
            sa.text(
                "INSERT INTO platform.worker_runs"
                " (id, thread_id, tenant_id, workspace_id, worker_id, worker_version,"
                "  graph_version, requested_by)"
                " VALUES (:r, :r, :t, :w, 'demo', '1.0.0', '1.0.0', gen_random_uuid())"
            ),
            {"r": run_id, "t": tenant, "w": WORKSPACE},
        )
        await session.execute(
            sa.insert(tables.items).values(
                memory_id=memory_id,
                tenant_id=tenant,
                workspace_id=WORKSPACE,
                worker_id="demo",
                memory_type="semantic",
                subject_refs=[],
                content="x",
                structured_facts={},
                # Non-empty: `ck_items_provenance_refs` refuses a memory that
                # cites nothing, which is the constraint doing its job. Shaped
                # like a real ref but pointing nowhere — retention never walks it,
                # and `item_evidence` is what ties a citation to a real row.
                provenance_refs=[{"evidence_id": str(uuid.uuid4())}],
                confidence=0.9,
                classification="internal",
                valid_from=NOW - timedelta(days=age_days),
                retention_policy=retention,
                memory_schema_version="1.0.0",
                created_by_run_id=run_id,
                created_at=NOW - timedelta(days=age_days),
            )
        )
    return memory_id


async def _alive(sessions: async_sessionmaker[AsyncSession], memory_id: uuid.UUID) -> bool:
    async with sessions() as session, session.begin():
        await session.execute(sa.text("SELECT set_config('app.worker_drain', 'on', true)"))
        found = await session.execute(
            sa.select(tables.items.c.memory_id).where(tables.items.c.memory_id == memory_id)
        )
        return found.first() is not None


async def test_a_memory_past_its_term_is_deleted(
    sweep: tuple[SqlMemoryRetention, async_sessionmaker[AsyncSession]],
) -> None:
    pruner, sessions = sweep
    old = await _memory(sessions, retention="ephemeral", age_days=40)

    await pruner.prune()

    assert not await _alive(sessions, old)


async def test_a_memory_inside_its_term_is_kept(
    sweep: tuple[SqlMemoryRetention, async_sessionmaker[AsyncSession]],
) -> None:
    pruner, sessions = sweep
    recent = await _memory(sessions, retention="ephemeral", age_days=10)

    await pruner.prune()

    assert await _alive(sessions, recent)


async def test_legal_hold_is_never_swept_however_old(
    sweep: tuple[SqlMemoryRetention, async_sessionmaker[AsyncSession]],
) -> None:
    """A class with no term is not "a very long term". Deleting something held
    for a legal obligation is the one mistake here that cannot be undone."""
    pruner, sessions = sweep
    ancient = await _memory(sessions, retention="legal_hold", age_days=10_000)

    await pruner.prune()

    assert await _alive(sessions, ancient)


async def test_the_sweep_only_touches_classes_the_policy_names(
    sweep: tuple[SqlMemoryRetention, async_sessionmaker[AsyncSession]],
) -> None:
    """A row naming a class this build has never heard of is kept.

    Named for what actually protects it: `prune` iterates the classes IN the
    policy and deletes by exact match, so an unknown name is never asked about.
    A mutation proved that — making `cutoff_for` fall back to `default` changed
    nothing here, because `cutoff_for` is never called with this name. The guard
    inside it is defence for a caller that does not exist yet, and it has its own
    unit test rather than a claim on this one.
    """
    pruner, sessions = sweep
    unknown = await _memory(sessions, retention="from_a_later_release", age_days=10_000)

    await pruner.prune()

    assert await _alive(sessions, unknown)


async def test_the_sweep_reaches_every_tenant(
    sweep: tuple[SqlMemoryRetention, async_sessionmaker[AsyncSession]],
) -> None:
    """A sweep scoped to one tenant would need a list of tenants to iterate, and
    getting that list is the cross-tenant read the scoping exists to prevent."""
    pruner, sessions = sweep
    mine = await _memory(sessions, retention="ephemeral", age_days=40)
    theirs = await _memory(sessions, retention="ephemeral", age_days=40, tenant=OTHER_TENANT)

    await pruner.prune()

    assert not await _alive(sessions, mine)
    assert not await _alive(sessions, theirs)


async def test_the_batch_ceiling_bounds_one_pass(
    urls: RuntimeUrls,
    sweep: tuple[SqlMemoryRetention, async_sessionmaker[AsyncSession]],
) -> None:
    """A DELETE holding a year of rows locks the table while somebody is using
    it. The sweep runs hourly; what it misses this hour goes next hour."""
    _pruner, sessions = sweep
    ids = [await _memory(sessions, retention="ephemeral", age_days=40) for _ in range(3)]
    engine = create_async_engine(urls.app, poolclass=NullPool)
    try:
        small = SqlMemoryRetention(
            async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
            _policy(batch_limit=2),
            _Clock(),
        )
        await small.prune()
    finally:
        await engine.dispose()

    survivors = [i for i in ids if await _alive(sessions, i)]
    assert len(survivors) == 1, "the ceiling must bound one pass, not be ignored"
