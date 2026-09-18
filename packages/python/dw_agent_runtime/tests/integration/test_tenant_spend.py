"""Integration: what a tenant has spent today, against real SQL.

Written after the first version of `spend_since` summed a column that does not
exist. `worker_runs` has no `cost_usd`; cost is recorded per model CALL in
`platform.model_usage_ledger`. Neither mypy nor ruff said anything, because
SQLAlchemy resolves `table.c.<name>` at runtime — the query was a clean type
check and an AttributeError in production.

Three things only a database can answer: that the column is there, that SUM over
no rows is zero rather than NULL, and that one tenant's spend is invisible to
another.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from runtime_harness import TENANT_B, RuntimeUrls, make_run_context
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_agent_runtime.adapters.run_store import SqlWorkerRunStore
from dw_agent_runtime.adapters.runtime_tables import model_usage_ledger

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

# Every test gets its own day. The database is shared and every test writes as
# the same tenant, so a fixed window would make each one read its neighbours'
# rows — green alone, wrong together, and wrong in the direction that hides an
# over-count. Isolating on the filter under test keeps each assertion its own.
_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
_days = itertools.count()


def a_day() -> datetime:
    return _EPOCH + timedelta(days=next(_days))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def store(
    urls: RuntimeUrls,
) -> AsyncIterator[tuple[SqlWorkerRunStore, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine(urls.app, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SqlWorkerRunStore(sessions, stale_run_after_seconds=3600), sessions
    finally:
        await engine.dispose()


async def _spend(
    sessions: async_sessionmaker[AsyncSession],
    *,
    tenant: uuid.UUID,
    workspace: uuid.UUID,
    cost: Decimal | None,
    at: datetime,
) -> None:
    async with sessions() as session, session.begin():
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)}
        )
        await session.execute(
            sa.insert(model_usage_ledger).values(
                id=uuid.uuid4(),
                tenant_id=tenant,
                workspace_id=workspace,
                run_id=uuid.uuid4(),
                worker_id="demo_approval",
                task="chat",
                provider="mock",
                model="mock",
                input_tokens=10,
                output_tokens=5,
                cost_usd=cost,
                created_at=at,
            )
        )


async def test_a_tenant_that_has_spent_nothing_reads_as_zero_not_null(
    store: tuple[SqlWorkerRunStore, async_sessionmaker[AsyncSession]],
) -> None:
    """SUM over no rows is NULL, and NULL compared against a cap is neither above
    nor below it — which reads as "under quota" and makes the cap absent exactly
    when the table is empty."""
    runs, _ = store
    fresh = uuid.uuid4()

    assert await runs.spend_since(fresh, a_day()) == Decimal(0)


async def test_todays_calls_are_summed(
    store: tuple[SqlWorkerRunStore, async_sessionmaker[AsyncSession]],
) -> None:
    runs, sessions = store
    context = make_run_context()
    day_start = a_day()
    for cost in (Decimal("1.50"), Decimal("2.25")):
        await _spend(
            sessions,
            tenant=context.tenant_id,
            workspace=context.workspace_id,
            cost=cost,
            at=day_start + timedelta(hours=1),
        )

    assert await runs.spend_since(context.tenant_id, day_start) == Decimal("3.75")


async def test_yesterdays_calls_are_not_counted(
    store: tuple[SqlWorkerRunStore, async_sessionmaker[AsyncSession]],
) -> None:
    runs, sessions = store
    context = make_run_context()
    day_start = a_day()
    await _spend(
        sessions,
        tenant=context.tenant_id,
        workspace=context.workspace_id,
        cost=Decimal("9.00"),
        at=day_start - timedelta(minutes=1),
    )

    assert await runs.spend_since(context.tenant_id, day_start) == Decimal(0)


async def test_an_unpriced_call_does_not_break_the_sum(
    store: tuple[SqlWorkerRunStore, async_sessionmaker[AsyncSession]],
) -> None:
    """Cost is NULL when nobody priced the route — a different claim from free,
    and it must not turn the whole day's total into NULL."""
    runs, sessions = store
    context = make_run_context()
    day_start = a_day()
    await _spend(
        sessions,
        tenant=context.tenant_id,
        workspace=context.workspace_id,
        cost=None,
        at=day_start + timedelta(hours=1),
    )
    await _spend(
        sessions,
        tenant=context.tenant_id,
        workspace=context.workspace_id,
        cost=Decimal("2.00"),
        at=day_start + timedelta(hours=2),
    )

    assert await runs.spend_since(context.tenant_id, day_start) == Decimal("2.00")


async def test_one_tenants_spend_is_invisible_to_another(
    store: tuple[SqlWorkerRunStore, async_sessionmaker[AsyncSession]],
) -> None:
    """A quota that could read another tenant's ledger would stop the wrong
    customer, and tell them a number they have no way to explain."""
    runs, sessions = store
    context = make_run_context()
    day_start = a_day()
    await _spend(
        sessions,
        tenant=context.tenant_id,
        workspace=context.workspace_id,
        cost=Decimal("5.00"),
        at=day_start + timedelta(hours=1),
    )

    assert await runs.spend_since(TENANT_B, day_start) == Decimal(0)
