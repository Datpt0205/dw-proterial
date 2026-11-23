"""A case keeps the stage versions it opened with, in PostgreSQL (ticket 61, step 2).

The stamp is written when the case opens and read back with it; the database
refuses any UPDATE that changes it, from any role; and start-up reads, through
`sales.open_cases_by_stage()`, how many open cases each version still has,
counts only and across tenants, as the application role.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sales_harness import OrderRun
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_sales.adapters.assembly import refuse_orphaned_stage_pins
from dw_sales.adapters.persistence.stage_pins import open_cases_by_stage
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.stages import StageConfigError

pytestmark = pytest.mark.integration


async def test_a_case_reads_back_with_the_versions_it_opened_with(
    small_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    async with uow(small_run.scope) as work:
        for case_id in small_run.latest():
            stored = await work.orders.get(case_id)
            assert stored is not None
            assert stored.origin.stage_versions == {"write_bravo": "1.0.0"}


@pytest.mark.parametrize("as_migrator", [False, True])
async def test_no_role_moves_a_cases_stamp(
    small_run: OrderRun,
    sales_app_engine: AsyncEngine,
    migrator: AsyncEngine,
    as_migrator: bool,
) -> None:
    case_id = next(iter(small_run.latest()))
    engine = migrator if as_migrator else sales_app_engine
    with pytest.raises(IntegrityError, match="stage versions it was opened with"):
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("SELECT set_config('app.tenant_id', :t, true)"),
                {"t": str(small_run.scope.tenant_id.value)},
            )
            await conn.execute(
                sa.text("SELECT set_config('app.workspace_id', :w, true)"),
                {"w": str(small_run.scope.workspace_id.value)},
            )
            await conn.execute(
                sa.text(
                    'UPDATE sales.order_cases SET stage_versions = \'{"write_bravo": "9.9.9"}\''
                    " WHERE id = :id"
                ),
                {"id": case_id},
            )


async def test_open_cases_are_counted_per_version_for_the_application_role(
    small_run: OrderRun,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    counts = await open_cases_by_stage(app_sessions)
    assert counts[("write_bravo", "1.0.0")] >= len(small_run.latest())
    # The served versions cover every open case: start-up goes on.
    await refuse_orphaned_stage_pins(app_sessions)


async def test_start_up_is_refused_while_an_open_case_runs_on_a_dropped_version(
    small_run: OrderRun,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    uow: SqlSalesUnitOfWorkFactory,
) -> None:
    """A case stamped with a version no handler serves: written by the
    tables' owner with the trigger off inside one transaction, which no
    application role can do."""
    case_id = next(iter(small_run.latest()))
    async with migrator.begin() as conn:
        await conn.execute(sa.text(_TRIGGER_OFF))
        await conn.execute(
            sa.text(
                'UPDATE sales.order_cases SET stage_versions = \'{"write_bravo": "0.9.0"}\''
                " WHERE id = :id"
            ),
            {"id": case_id},
        )
        await conn.execute(sa.text(_TRIGGER_ON))
    try:
        # Read back as stored, never as today's default.
        async with uow(small_run.scope) as work:
            stored = await work.orders.get(case_id)
        assert stored is not None and stored.origin.stage_versions == {"write_bravo": "0.9.0"}
        with pytest.raises(StageConfigError, match=r"0\.9\.0 \(1 open\)"):
            await refuse_orphaned_stage_pins(app_sessions)
    finally:
        async with migrator.begin() as conn:
            await conn.execute(sa.text(_TRIGGER_OFF))
            await conn.execute(
                sa.text(
                    'UPDATE sales.order_cases SET stage_versions = \'{"write_bravo": "1.0.0"}\''
                    " WHERE id = :id"
                ),
                {"id": case_id},
            )
            await conn.execute(sa.text(_TRIGGER_ON))


_TRIGGER_OFF = "ALTER TABLE sales.order_cases DISABLE TRIGGER refuse_stage_versions_change"
_TRIGGER_ON = "ALTER TABLE sales.order_cases ENABLE TRIGGER refuse_stage_versions_change"
