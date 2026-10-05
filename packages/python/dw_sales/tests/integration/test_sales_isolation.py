"""Tenant AND workspace isolation of the `sales` schema, as the application role.

Every policy narrows by `app.tenant_id` and `app.workspace_id`. Each negative
below is checked against rows that are really there (read back as the
migrator), so a zero is isolation and not an empty table.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sales_harness import DW1, OrderRun, World
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.errors import NotFoundError
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence.orders import SqlOrderCaseLookup
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import CaseEvent
from dw_sales.application.ports import SalesScope
from dw_sales.domain.orders import OrderCase

pytestmark = pytest.mark.integration

_TABLES = (
    "order_cases",
    "order_revisions",
    "order_lines",
    "order_findings",
    "quote_cases",
    "messages",
    "artifacts",
    "source_served",
    "worker_state",
    "case_events",
    "case_events_default",
)


@asynccontextmanager
async def bound(
    sessions: async_sessionmaker[AsyncSession], scope: SalesScope
) -> AsyncIterator[AsyncSession]:
    async with tenant_session(
        sessions, TenantScope(scope.tenant_id.value, scope.workspace_id.value)
    ) as session:
        yield session


def _a_case(small_run: OrderRun) -> OrderCase:
    case = small_run.outcomes["M01"].case
    assert case is not None
    return case


@pytest.fixture(params=["other tenant", "other workspace of the same tenant"])
def outsider(request: pytest.FixtureRequest, world: World) -> SalesScope:
    return world.beta if request.param == "other tenant" else world.alpha_other


async def test_an_outsider_reads_none_of_the_cases(
    small_run: OrderRun,
    outsider: SalesScope,
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
) -> None:
    case = _a_case(small_run)
    async with uow(outsider) as work:
        assert await work.orders.get(case.case_id) is None
        assert await work.messages.get("M01") is None
    lookup = SqlOrderCaseLookup(app_sessions)
    assert await lookup.cases_for_po(outsider, case.customer_code, case.header.po_no) == []
    assert await lookup.cases_for_po(small_run.scope, case.customer_code, case.header.po_no)

    async with bound(app_sessions, outsider) as session:
        seen = {
            table: (await session.execute(sa.text(f"SELECT count(*) FROM sales.{table}"))).scalar()
            for table in _TABLES
        }
    assert set(seen.values()) == {0}, seen
    async with migrator.connect() as conn:
        held = await conn.scalar(
            sa.text("SELECT count(*) FROM sales.order_lines WHERE tenant_id = :t"),
            {"t": small_run.scope.tenant_id.value},
        )
    assert held, "the owner's rows are there: the zeros above are isolation"


async def test_an_outsider_cannot_change_a_case(
    small_run: OrderRun,
    outsider: SalesScope,
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    case = _a_case(small_run)
    reviewing = case.start_review()
    event = CaseEvent(
        action="order.review_started", actor=DW1, occurred_at=datetime(2026, 10, 3, tzinfo=UTC)
    )
    async with uow(outsider) as work:
        with pytest.raises(NotFoundError):
            await work.orders.save(reviewing, expected_version=case.case_version, event=event)
    async with bound(app_sessions, outsider) as session:
        changed = await session.execute(
            sa.text(
                "UPDATE sales.order_cases"
                " SET assigned_to = '00000000-0000-0000-0000-0000000000b9' WHERE id = :id"
            ),
            {"id": case.case_id},
        )
        deleted = await session.execute(
            sa.text("DELETE FROM sales.order_cases WHERE id = :id"), {"id": case.case_id}
        )
    assert (changed.rowcount, deleted.rowcount) == (0, 0)  # type: ignore[attr-defined]
    async with uow(small_run.scope) as work:
        stored = await work.orders.get(case.case_id)
    assert stored is not None and stored.case == case and stored.origin.assigned_to is None


async def test_an_outsider_cannot_write_a_row_into_the_owners_scope(
    small_run: OrderRun,
    outsider: SalesScope,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """WITH CHECK, not only USING: a row naming another tenant's or another
    workspace's ids is refused on the way in."""
    owner = small_run.scope
    with pytest.raises(DBAPIError, match="row-level security"):
        async with bound(app_sessions, outsider) as session:
            await session.execute(
                sa.text(
                    "INSERT INTO sales.worker_state"
                    " (tenant_id, workspace_id, paused, changed_by, changed_at)"
                    " VALUES (:t, :w, true, '00000000-0000-0000-0000-0000000000b9', now())"
                ),
                {"t": owner.tenant_id.value, "w": owner.workspace_id.value},
            )
    with pytest.raises(DBAPIError, match="row-level security"):
        async with bound(app_sessions, outsider) as session:
            await session.execute(
                sa.text(
                    "INSERT INTO sales.case_events (id, tenant_id, workspace_id, case_kind,"
                    " case_id, case_version, action, to_status, actor_kind, actor_id,"
                    " occurred_at) VALUES (gen_random_uuid(), :t, :w, 'order', :c, 1,"
                    " 'order.probe', 'checked', 'user', 'dev|bao.pham', now())"
                ),
                {
                    "t": owner.tenant_id.value,
                    "w": owner.workspace_id.value,
                    "c": _a_case(small_run).case_id,
                },
            )


async def test_a_connection_that_never_scopes_itself_reads_nothing(
    small_run: OrderRun, sales_app_engine: AsyncEngine
) -> None:
    async with sales_app_engine.connect() as conn:
        for table in _TABLES:
            count = (await conn.execute(sa.text(f"SELECT count(*) FROM sales.{table}"))).scalar()
            assert count == 0, table


async def test_a_tenant_bound_without_a_workspace_reads_nothing(
    small_run: OrderRun, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A scope that names no workspace denies, rather than seeing every
    workspace of its tenant (`bind_tenant` binds the empty string)."""
    async with tenant_session(app_sessions, TenantScope(small_run.scope.tenant_id.value)) as s:
        assert (await s.execute(sa.text("SELECT count(*) FROM sales.order_cases"))).scalar() == 0


async def test_a_month_made_at_runtime_narrows_by_workspace_too(
    small_run: OrderRun,
    world: World,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
) -> None:
    """The partition maintenance copies the parent's policy, so a month made
    by the worker's lane is isolated per workspace exactly like the parent."""
    async with app_sessions() as session, session.begin():
        await session.execute(sa.text("SELECT platform.ensure_time_partitions(1)"))
    now = datetime.now(UTC)
    part = f"case_events_{now:%Y_%m}"
    async with migrator.connect() as conn:
        policy = await conn.scalar(
            sa.text("SELECT qual FROM pg_policies WHERE schemaname = 'sales' AND tablename = :p"),
            {"p": part},
        )
        forced = await conn.scalar(
            sa.text("SELECT relforcerowsecurity FROM pg_class WHERE relname = :p"), {"p": part}
        )
    assert policy is not None and "app.workspace_id" in policy and "app.tenant_id" in policy
    assert forced is True

    owner = small_run.scope
    async with bound(app_sessions, owner) as session:
        await session.execute(
            sa.text(
                "INSERT INTO sales.case_events (id, tenant_id, workspace_id, case_kind, case_id,"
                " case_version, action, to_status, actor_kind, actor_id, occurred_at)"
                " VALUES (gen_random_uuid(), :t, :w, 'order', :c, 1, 'order.probe', 'checked',"
                " 'user', 'dev|an.nguyen', now())"
            ),
            {
                "t": owner.tenant_id.value,
                "w": owner.workspace_id.value,
                "c": _a_case(small_run).case_id,
            },
        )
    async with bound(app_sessions, owner) as session:
        mine = (await session.execute(sa.text(f"SELECT count(*) FROM sales.{part}"))).scalar()
    async with bound(app_sessions, world.alpha_other) as session:
        theirs = (await session.execute(sa.text(f"SELECT count(*) FROM sales.{part}"))).scalar()
    # At least the probe; more when the golden run's fixed dates fall in this
    # month, since creating the month moves them out of the DEFAULT partition.
    assert mine is not None and mine >= 1
    assert theirs == 0
