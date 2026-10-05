"""Offboarding a tenant exports and purges its sales cases, every workspace.

`SqlTenantOffboarding` binds only `app.tenant_id` for the platform's tables.
The `sales` policies also narrow by workspace, so a tenant-only session sees
none of these rows; the offboarding pass binds each of the tenant's
workspaces in turn for them. Without that, export would hand over no sales
data and purge would leave it all in place, with both reporting success.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sales_harness import World, run_mailbox
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.offboarding import SqlTenantOffboarding
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory

pytestmark = pytest.mark.integration

_CASE_TABLES = (
    "order_cases",
    "order_revisions",
    "order_lines",
    "order_findings",
    "messages",
)


async def _held(engine: AsyncEngine, table: str, tenant: object) -> int:
    async with engine.connect() as conn:
        count = await conn.scalar(
            sa.text(f"SELECT count(*) FROM sales.{table} WHERE tenant_id = :t"), {"t": tenant}
        )
    return int(count or 0)


async def test_a_tenants_sales_cases_are_exported_and_purged_in_every_workspace(
    world: World,
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
) -> None:
    first = await run_mailbox(uow, app_sessions, world.alpha, frozenset({"M01", "M02"}))
    second = await run_mailbox(uow, app_sessions, world.alpha_other, frozenset({"M05"}))
    await run_mailbox(uow, app_sessions, world.beta, frozenset({"M01", "M02"}))
    alpha = world.alpha.tenant_id.value
    beta = world.beta.tenant_id.value
    expected = {o.case.case_id for run in (first, second) for o in run.outcomes.values() if o.case}
    assert len(expected) == 3

    offboarding = SqlTenantOffboarding(app_sessions)
    exported = {(t.schema, t.table): t.rows for t in await offboarding.export_rows(alpha)}
    assert {row["id"] for row in exported[("sales", "order_cases")]} == expected
    assert {row["workspace_id"] for row in exported[("sales", "order_cases")]} == {
        world.alpha.workspace_id.value,
        world.alpha_other.workspace_id.value,
    }
    assert {row["tenant_id"] for rows in exported.values() for row in rows} <= {alpha}
    assert len(exported[("sales", "case_events")]) >= 3

    await offboarding.purge_rows(alpha)

    for table in _CASE_TABLES:
        assert await _held(migrator, table, alpha) == 0, table
        assert await _held(migrator, table, beta) > 0, f"{table}: the other tenant's rows went"
    # The case event log is append-only, like the audit log: exported, kept
    # for its retention term (ticket 12), never purged by the application.
    assert await _held(migrator, "case_events", alpha) >= 3
