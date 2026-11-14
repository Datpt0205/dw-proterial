"""Ticket 29 against real Postgres (migration 0d1d0e4eb203): the update loop
of a customer's change on an order already in Bravo
(`sales.order_cases.update_loop`).

A confirmed order whose change waits on PC, then on the customer, reads back
as the domain left it; the follow-up lane reads the start of each wait from
the stored loop by its step, in its own workspace only, although the order
is `confirmed` and no status-watched follow-up loads it; once the customer
answers the loop is gone, so nothing is owed; and a loop that is not an
object, names an unknown step or sits on an order not in Bravo is refused
whoever writes.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from itertools import pairwise

import pytest
import sqlalchemy as sa
from sales_harness import T0, OrderRun, World, user
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import CaseEvent
from dw_sales.application.followups import LOADED
from dw_sales.domain.orders import Actor, AppliedChange, OrderCase, OrderStatus

pytestmark = pytest.mark.integration

AN_ID, DIEU_ID = uuid.UUID(int=0xA1), uuid.UUID(int=0xD1)
T1 = T0 + timedelta(hours=3)
# Far after every sample's arrival: only the loop can load the order.
LATER = T0 + timedelta(days=3650)
_IN_BRAVO = "('confirmed', 'change_review', 'uploaded_to_bravo', 'cross_checked')"


def _m01(order_run: OrderRun) -> OrderCase:
    case = order_run.outcomes["M01"].case
    assert case is not None
    return order_run.latest()[case.case_id]


async def _save(uow: SqlSalesUnitOfWorkFactory, order_run: OrderRun, *cases: OrderCase) -> None:
    async with uow(order_run.scope) as work:
        for before, after in pairwise(cases):
            event = CaseEvent(action="order.update_pc_asked", actor=user(AN_ID), occurred_at=T0)
            await work.orders.save(after, expected_version=before.case_version, event=event)
        await work.commit()


def _confirmed(case: OrderCase) -> list[OrderCase]:
    """M01 walked to `confirmed` in the domain: every step on the way."""
    an, dieu = Actor(user_id=AN_ID), Actor(user_id=DIEU_ID)
    walk = [case, case.start_review()]
    walk.append(walk[-1].prepare(an, T0))
    walk.append(walk[-1].record_bravo_entry("SO26-1001", an, T0, entry_compared=True))
    if walk[-1].awaits_cross_check:
        walk.append(walk[-1].cross_check(dieu, T0))
    last = walk[-1]
    dates = {line.line_no: [date(2026, 12, 4)] * line.deliveries for line in last.lines}
    walk.append(last.confirm(an, T0, dates))
    return walk


async def test_the_loop_reads_back_and_the_lane_reads_each_wait_from_it(
    small_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    case = _m01(small_run)
    walk = _confirmed(case)
    confirmed = walk[-1]
    assert confirmed.status is OrderStatus.CONFIRMED
    an = Actor(user_id=AN_ID)
    line = confirmed.lines[0]
    change = AppliedChange(
        field="requested_date", value="2026-11-20", request_id=uuid.uuid4(), by=AN_ID, at=T0
    )
    looping = confirmed.loop_change(line.line_no, change, an)
    asked = looping.loop_ask_pc(T0)
    await _save(uow, small_run, *walk, looping, asked)

    async with uow(world.alpha) as work:
        stored = await work.orders.get(case.case_id)
        waiting = {c.case_id: c for c in await work.followups.cases(LOADED, received_since=LATER)}
    assert stored is not None and stored.case == asked
    assert (waiting[case.case_id].pc_asked_at, waiting[case.case_id].customer_asked_at) == (
        T0,
        None,
    )
    for other in (world.alpha_other, world.beta):
        async with uow(other) as work:
            assert case.case_id not in {
                c.case_id for c in await work.followups.cases(LOADED, received_since=LATER)
            }

    quantity = line.effective.quantity
    answered = asked.loop_pc_answer(line.line_no, [(quantity, date(2026, 11, 20))], an, T1)
    sent = answered.loop_answer_sent(T1)
    await _save(uow, small_run, asked, answered, sent)
    async with uow(world.alpha) as work:
        stored = await work.orders.get(case.case_id)
        waiting = {c.case_id: c for c in await work.followups.cases(LOADED, received_since=LATER)}
    assert stored is not None and stored.case == sent
    assert (waiting[case.case_id].pc_asked_at, waiting[case.case_id].customer_asked_at) == (
        None,
        T1,
    )

    kept = sent.loop_answered("keep", T1)
    await _save(uow, small_run, sent, kept)
    async with uow(world.alpha) as work:
        stored = await work.orders.get(case.case_id)
        waiting = {c.case_id: c for c in await work.followups.cases(LOADED, received_since=LATER)}
    assert stored is not None and stored.case.update_loop is None
    assert stored.case.lines == confirmed.lines
    assert case.case_id not in waiting


@pytest.mark.parametrize(
    "loop",
    [
        "'[]'::jsonb",
        """'{"step": "nope"}'::jsonb""",
    ],
)
async def test_a_loop_that_is_not_one_the_domain_names_is_refused(
    migrator: AsyncEngine, small_run: OrderRun, loop: str
) -> None:
    with pytest.raises(IntegrityError):
        async with migrator.begin() as connection:
            await connection.execute(sa.text(f"UPDATE sales.order_cases SET update_loop = {loop}"))


async def test_a_loop_on_an_order_not_in_bravo_is_refused(
    migrator: AsyncEngine, small_run: OrderRun
) -> None:
    async with migrator.begin() as connection:
        before_bravo = await connection.scalar(
            sa.text("SELECT count(*) FROM sales.order_cases WHERE status NOT IN " + _IN_BRAVO)
        )
    assert before_bravo  # a check over no row proves nothing
    with pytest.raises(IntegrityError):
        async with migrator.begin() as connection:
            await connection.execute(
                sa.text(
                    'UPDATE sales.order_cases SET update_loop = \'{"step": "ask_pc"}\'::jsonb'
                    " WHERE status NOT IN " + _IN_BRAVO
                )
            )
