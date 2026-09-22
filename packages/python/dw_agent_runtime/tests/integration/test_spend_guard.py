"""Integration: the daily spend guard is tenant-scoped by construction.

The gate in langgraph_runner.py is exercised in unit tests against a fake
store (test_spend_quota.py). What only a real database can show is the
property the whole design exists for: tenant B never sees, and never
increments, tenant A's running total.

Each test uses its own date rather than one shared constant: `urls` is
session-scoped (one database for the whole file), and `(tenant_id,
spend_date)` is the primary key — sharing a date across tests would collide
on it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from runtime_harness import TENANT_A, TENANT_B, RuntimeUrls, make_run_context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_agent_runtime.adapters.spend_guard import (
    SqlSpendGuardRecorder,
    SqlSpendGuardRetention,
    SqlSpendGuardStore,
)
from dw_agent_runtime.model.gateway import ModelUsage
from dw_agent_runtime.ports import ModelRequest

pytestmark = pytest.mark.integration

_REQUEST = ModelRequest(task="agent_loop", prompt_id="demo", prompt_version="1.0.0")


@dataclass(frozen=True)
class _FrozenClock:
    day: date

    def now(self) -> datetime:
        return datetime(self.day.year, self.day.month, self.day.day, 12, 0, tzinfo=UTC)


def _usage(cost_usd: float) -> ModelUsage:
    return ModelUsage(
        provider="mock", model="mock", input_tokens=1, output_tokens=1, cost_usd=cost_usd
    )


@pytest.fixture
async def sessions(urls: RuntimeUrls) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(urls.app, poolclass=NullPool)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def test_recording_twice_the_same_day_accumulates(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    day = date(2026, 9, 22)
    recorder = SqlSpendGuardRecorder(session_factory=sessions, clock=_FrozenClock(day))
    store = SqlSpendGuardStore(session_factory=sessions)
    run_context = make_run_context(tenant=TENANT_A)

    await recorder.record(run_context, _REQUEST, _usage(1.5))
    await recorder.record(run_context, _REQUEST, _usage(2.25))

    assert await store.spend_today(TENANT_A, day) == Decimal("3.7500")


async def test_zero_cost_calls_do_not_create_a_row(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    day = date(2026, 9, 23)
    recorder = SqlSpendGuardRecorder(session_factory=sessions, clock=_FrozenClock(day))
    store = SqlSpendGuardStore(session_factory=sessions)

    await recorder.record(make_run_context(tenant=TENANT_A), _REQUEST, _usage(0.0))

    assert await store.spend_today(TENANT_A, day) == Decimal(0)


async def test_another_tenant_neither_sees_nor_increments_the_spend(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    day = date(2026, 9, 24)
    recorder = SqlSpendGuardRecorder(session_factory=sessions, clock=_FrozenClock(day))
    store = SqlSpendGuardStore(session_factory=sessions)

    await recorder.record(make_run_context(tenant=TENANT_A), _REQUEST, _usage(5.0))

    # B never sees A's spend...
    assert await store.spend_today(TENANT_B, day) == Decimal(0)

    # ...and B's own calls land in B's own row, not A's.
    await recorder.record(make_run_context(tenant=TENANT_B), _REQUEST, _usage(1.0))
    assert await store.spend_today(TENANT_A, day) == Decimal("5.0000")
    assert await store.spend_today(TENANT_B, day) == Decimal("1.0000")


async def test_rls_hides_the_row_even_from_a_query_with_no_tenant_filter(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The store's own WHERE clause already filters by tenant_id — this test
    does not go through it, on purpose. It proves the database itself refuses
    the row under `app.tenant_id=B`, so a future query that forgot the WHERE
    (or read the wrong variable) is still safe. A mutation check confirmed
    this test goes red when the policy predicate is replaced with `true` and
    the one above does not, because the store never relies on RLS to filter —
    it filters in the query and RLS is defense in depth.
    """
    day = date(2026, 9, 26)
    recorder = SqlSpendGuardRecorder(session_factory=sessions, clock=_FrozenClock(day))
    await recorder.record(make_run_context(tenant=TENANT_A), _REQUEST, _usage(5.0))

    async with sessions() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_B)}
        )
        rows = (
            await session.execute(
                text(
                    "SELECT tenant_id FROM platform.tenant_daily_spend_guard"
                    " WHERE spend_date = :day"
                ),
                {"day": day},
            )
        ).all()

    assert rows == []


async def test_retention_prunes_old_rows_and_keeps_recent_ones(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    today = date(2026, 9, 25)
    old_day = today - timedelta(days=40)
    async with sessions() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_A)}
        )
        await session.execute(
            text(
                "INSERT INTO platform.tenant_daily_spend_guard"
                " (tenant_id, spend_date, spend_usd, updated_at)"
                " VALUES (:tenant_id, :old_day, 9.0, now()), (:tenant_id, :today, 1.0, now())"
            ),
            {"tenant_id": str(TENANT_A), "old_day": old_day, "today": today},
        )

    await SqlSpendGuardRetention(session_factory=sessions, clock=_FrozenClock(today)).prune()

    store = SqlSpendGuardStore(session_factory=sessions)
    assert await store.spend_today(TENANT_A, old_day) == Decimal(0)
    assert await store.spend_today(TENANT_A, today) == Decimal("1.0000")
