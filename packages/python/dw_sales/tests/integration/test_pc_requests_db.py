"""Ticket 07 against real Postgres (migration 91f83937dbf1): the wait on PC
(`sales.order_cases.pc_request`) and PC's answer per line
(`sales.order_lines.pc_answer`).

A case asked of PC and a line PC split read back as the domain left them; the
follow-up lane reads the start of the wait from the stored request, in its
own workspace only; once every line asked is answered the request is gone, so
no reminder is owed; a `waiting_pc` delivery is a record the CHECK admits;
and a request or an answer that is not an object is refused whoever writes.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import pytest
import sqlalchemy as sa
from sales_harness import T0, OrderRun, World, user
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.persistence.orders import SqlOrderCaseLookup
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.adapters.reader_client import ClientPoReaders, ClientQuoteForms
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.case_store import CaseEvent
from dw_sales.application.followups import LOADED, FollowupKey, SentFollowup
from dw_sales.application.order_intake import OrderIntake
from dw_sales.domain.orders import Actor, OrderCase
from dw_sales.testing.followups import platform_zone

pytestmark = pytest.mark.integration

AN_ID = uuid.UUID(int=0xA1)
POLICIES = Path(__file__).resolve().parents[5] / "configs" / "policies"
NOV_20, DEC_12 = date(2026, 11, 20), date(2026, 12, 12)


def _intake(order_run: OrderRun, app_sessions: async_sessionmaker[AsyncSession]) -> OrderIntake:
    scope = order_run.scope
    return OrderIntake(
        catalog=MockSalesCatalog.load(scope),
        inbox=MockInbox.load(scope),
        reader=ClientPoReaders(InProcessReaderTransport()),
        quote_forms=ClientQuoteForms(InProcessReaderTransport()),
        zones=platform_zone(),
        rules=PlatformOrderRules(load_order_rules(POLICIES / "sales_order_rules@1.13.0.yaml")),
        cases=SqlOrderCaseLookup(app_sessions),
        new_case_id=uuid.uuid4,
    )


def _m01(order_run: OrderRun) -> OrderCase:
    case = order_run.outcomes["M01"].case
    assert case is not None
    return order_run.latest()[case.case_id]


async def _save(uow: SqlSalesUnitOfWorkFactory, order_run: OrderRun, *cases: OrderCase) -> None:
    async with uow(order_run.scope) as work:
        for before, after in pairwise(cases):
            event = CaseEvent(action="order.pc_asked", actor=user(AN_ID), occurred_at=T0)
            await work.orders.save(after, expected_version=before.case_version, event=event)
        await work.commit()


async def test_the_wait_and_a_split_read_back_and_the_lane_reads_the_wait(
    small_run: OrderRun,
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
) -> None:
    case = _m01(small_run)
    an = Actor(user_id=AN_ID)
    reviewing = case.start_review()
    asked = reviewing.ask_pc(an, T0)
    whole = asked.line(1).effective.quantity
    intake = _intake(small_run, app_sessions)
    split = await intake.take_pc_answer(
        small_run.scope, asked, 1, [(whole - 1, NOV_20), (Decimal(1), DEC_12)], an, T0
    )
    await _save(uow, small_run, case, reviewing, asked)

    async with uow(world.alpha) as work:
        stored = await work.orders.get(case.case_id)
        waiting = {c.case_id: c for c in await work.followups.cases(LOADED, received_since=T0)}
    assert stored is not None and stored.case == asked
    assert waiting[case.case_id].pc_asked_at == T0
    for other in (world.alpha_other, world.beta):
        async with uow(other) as work:
            assert case.case_id not in {
                c.case_id for c in await work.followups.cases(LOADED, received_since=T0)
            }

    await _save(uow, small_run, asked, split)
    async with uow(world.alpha) as work:
        stored = await work.orders.get(case.case_id)
    assert stored is not None and stored.case == split
    line = stored.case.line(1)
    assert line.pc_answer is not None and line.deliveries == 2

    answered = split
    for other_line in split.lines[1:]:
        answered = await intake.take_pc_answer(
            small_run.scope,
            answered,
            other_line.line_no,
            [(other_line.effective.quantity, NOV_20)],
            an,
            T0,
        )
    if answered is not split:
        await _save(uow, small_run, split, answered)
    assert answered.pc_request is None
    async with uow(world.alpha) as work:
        again = {c.case_id: c for c in await work.followups.cases(LOADED, received_since=T0)}
    assert again[case.case_id].pc_asked_at is None


async def test_a_waiting_pc_delivery_is_a_record_the_check_admits(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    key = FollowupKey("waiting_pc", "remind", str(uuid.uuid4()), T0 - timedelta(hours=24))
    async with uow(world.alpha) as work:
        assert await work.followups.record(SentFollowup(key, 1, T0))
        await work.commit()


@pytest.mark.parametrize(
    ("table", "column"), [("order_cases", "pc_request"), ("order_lines", "pc_answer")]
)
async def test_a_request_or_an_answer_that_is_not_an_object_is_refused(
    migrator: AsyncEngine, small_run: OrderRun, table: str, column: str
) -> None:
    with pytest.raises(IntegrityError):
        async with migrator.begin() as connection:
            await connection.execute(sa.text(f"UPDATE sales.{table} SET {column} = '[]'::jsonb"))
