"""Ticket 06 against real Postgres (migration 3d139b41fec1): the wait on
Design for a line no item fits (`sales.order_cases.design_requests`).

A case asked of Design reads back as the domain left it, in its own
workspace only; a case stored before the column existed reads as waiting on
nobody (the column's default); and a value that is not an array is refused
whoever writes.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sales_harness import T0, OrderRun, World, run_mailbox, user
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import CaseEvent
from dw_sales.domain.orders import Actor, MappingStatus

pytestmark = pytest.mark.integration

AN_ID = uuid.UUID(int=0xA1)
# M04's line 3: no item of the item master fits it (`code_unmapped`).
LINE = 3


@pytest.fixture
async def m04_run(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
) -> OrderRun:
    return await run_mailbox(uow, app_sessions, world.alpha, frozenset({"M04"}))


async def test_the_wait_on_design_reads_back_in_its_own_workspace_only(
    m04_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    outcome = m04_run.outcomes["M04"].case
    assert outcome is not None
    case = m04_run.latest()[outcome.case_id]
    assert case.design_requests == ()
    assert case.line(LINE).mapping.status is MappingStatus.UNMAPPED
    reviewing = case.start_review()
    asked = reviewing.ask_design(LINE, Actor(user_id=AN_ID), T0)

    async with uow(world.alpha) as work:
        stored = await work.orders.get(case.case_id)
    assert stored is not None and stored.case.design_requests == ()

    async with uow(m04_run.scope) as work:
        for before, after in ((case, reviewing), (reviewing, asked)):
            event = CaseEvent(action="order.design_asked", actor=user(AN_ID), occurred_at=T0)
            await work.orders.save(after, expected_version=before.case_version, event=event)
        await work.commit()

    async with uow(world.alpha) as work:
        stored = await work.orders.get(case.case_id)
    assert stored is not None and stored.case == asked
    ((request),) = stored.case.design_requests
    assert (request.line_no, request.by, request.at) == (LINE, AN_ID, T0)
    for other in (world.alpha_other, world.beta):
        async with uow(other) as work:
            assert await work.orders.get(case.case_id) is None


async def test_a_wait_that_is_not_an_array_is_refused(
    migrator: AsyncEngine, m04_run: OrderRun
) -> None:
    for value in ("'{}'::jsonb", "'null'::jsonb", "NULL"):
        with pytest.raises(IntegrityError):
            async with migrator.begin() as connection:
                await connection.execute(
                    sa.text(f"UPDATE sales.order_cases SET design_requests = {value}")
                )
