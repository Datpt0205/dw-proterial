"""Ticket 28 against real Postgres (migration 64d50dbc1d00): an order's
confirmation sent and the customer's agreement (`sales.order_cases`
`confirmation`, `agreement`).

An order whose confirmation left with a customer's term of silence reads
back as the domain left it, and the follow-up lane reads the instant silence
counts from it, in its own workspace only; once agreed it reads back again
and is owed nothing; and an agreement or a confirmation the domain would not
write is refused whoever writes.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sales_harness import T0, OrderRun, World, user
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import CaseEvent
from dw_sales.application.followups import LOADED
from dw_sales.application.ports import SalesScope
from dw_sales.domain.orders import Actor, ImpliedTerm, OrderCase, OrderStatus

pytestmark = pytest.mark.integration

AN_ID, DIEU_ID = uuid.UUID(int=0xA1), uuid.UUID(int=0xD1)
HANOI = ZoneInfo("Asia/Ho_Chi_Minh")
# Far after every sample's arrival: only the confirmation can load the order.
LATER = T0 + timedelta(days=3650)
_NOT_LEFT = " WHERE status NOT IN ('confirmation_sent', 'confirmed')"


def _m01(order_run: OrderRun) -> OrderCase:
    case = order_run.outcomes["M01"].case
    assert case is not None
    return order_run.latest()[case.case_id]


async def _save(uow: SqlSalesUnitOfWorkFactory, order_run: OrderRun, *cases: OrderCase) -> None:
    async with uow(order_run.scope) as work:
        for before, after in pairwise(cases):
            event = CaseEvent(action="order.customer_agreed", actor=user(AN_ID), occurred_at=T0)
            await work.orders.save(after, expected_version=before.case_version, event=event)
        await work.commit()


def _sent(case: OrderCase, term: ImpliedTerm | None) -> list[OrderCase]:
    """M01 walked in the domain to its confirmation sent, every step on the way."""
    an, dieu = Actor(user_id=AN_ID), Actor(user_id=DIEU_ID)
    walk = [case, case.start_review()]
    walk.append(walk[-1].prepare(an, T0))
    walk.append(walk[-1].record_bravo_entry("SO26-1001", an, T0, entry_compared=True))
    if walk[-1].awaits_cross_check:
        walk.append(walk[-1].cross_check(dieu, T0))
    last = walk[-1]
    dates = {line.line_no: [date(2026, 12, 4)] * line.deliveries for line in last.lines}
    walk.append(last.confirm(an, T0, dates, last.confirmation_sent(T0, term, HANOI)))
    return walk


async def _implied(
    uow: SqlSalesUnitOfWorkFactory, scope: SalesScope
) -> dict[uuid.UUID, datetime | None]:
    async with uow(scope) as work:
        return {
            c.case_id: c.implied_from
            for c in await work.followups.cases(LOADED, received_since=LATER)
        }


async def test_the_confirmation_and_the_agreement_read_back_and_the_lane_reads_the_term(
    small_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    case = _m01(small_run)
    walk = _sent(case, ImpliedTerm(days=3))
    sent = walk[-1]
    assert sent.status is OrderStatus.CONFIRMATION_SENT and sent.confirmation is not None
    await _save(uow, small_run, *walk)

    async with uow(world.alpha) as work:
        stored = await work.orders.get(case.case_id)
    assert stored is not None and stored.case == sent
    assert (await _implied(uow, world.alpha))[case.case_id] == sent.confirmation.implied_from
    for other in (world.alpha_other, world.beta):
        assert case.case_id not in await _implied(uow, other)

    agreed = sent.agreed("implied", Actor(user_id=AN_ID), LATER)
    await _save(uow, small_run, sent, agreed)
    async with uow(world.alpha) as work:
        stored = await work.orders.get(case.case_id)
    assert stored is not None and stored.case == agreed
    assert stored.case.agreement is not None and stored.case.agreement.how == "implied"
    assert case.case_id not in await _implied(uow, world.alpha)


async def test_a_confirmation_with_no_term_is_never_loaded_for_silence(
    small_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    case = _m01(small_run)
    await _save(uow, small_run, *_sent(case, None))
    assert case.case_id not in await _implied(uow, world.alpha)


@pytest.mark.parametrize(
    "assignment",
    [
        # An agreement on an order that is not agreed.
        """agreement = '{"how": "accepted"}'::jsonb""",
        # A confirmation before the confirmation left.
        """confirmation = '{"sent_at": "2026-10-05T03:00:00+00:00"}'::jsonb""",
    ],
)
async def test_what_the_domain_would_not_write_is_refused(
    migrator: AsyncEngine, small_run: OrderRun, assignment: str
) -> None:
    async with migrator.begin() as connection:
        found = await connection.scalar(
            sa.text("SELECT count(*) FROM sales.order_cases" + _NOT_LEFT)
        )
    assert found  # a check over no row proves nothing
    with pytest.raises(IntegrityError):
        async with migrator.begin() as connection:
            await connection.execute(
                sa.text(f"UPDATE sales.order_cases SET {assignment}" + _NOT_LEFT)
            )


@pytest.mark.parametrize(
    "agreement",
    ["""'{"how": "silently"}'::jsonb""", "'[]'::jsonb", "NULL"],
)
async def test_an_agreed_order_names_how_from_the_closed_set(
    migrator: AsyncEngine,
    small_run: OrderRun,
    uow: SqlSalesUnitOfWorkFactory,
    agreement: str,
) -> None:
    case = _m01(small_run)
    walk = _sent(case, None)
    await _save(uow, small_run, *walk, walk[-1].agreed("accepted", Actor(user_id=AN_ID), T0))
    with pytest.raises(IntegrityError):
        async with migrator.begin() as connection:
            await connection.execute(
                sa.text(f"UPDATE sales.order_cases SET agreement = {agreement} WHERE id = :id"),
                {"id": case.case_id},
            )


async def test_a_term_with_an_unknown_day_count_is_refused(
    migrator: AsyncEngine, small_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    case = _m01(small_run)
    await _save(uow, small_run, *_sent(case, ImpliedTerm(days=3)))
    with pytest.raises(IntegrityError):
        async with migrator.begin() as connection:
            await connection.execute(
                sa.text(
                    "UPDATE sales.order_cases SET confirmation = jsonb_set(confirmation,"
                    " '{term,day_count}', to_jsonb('lunar'::text)) WHERE id = :id"
                ),
                {"id": case.case_id},
            )
