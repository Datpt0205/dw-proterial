"""Ticket 09 against real Postgres (migration ae1388cdd714): the quote cases
opened from an order (`sales.order_cases.quote_links`), the order a quote
case was opened from (in `sales.quote_cases.body`), and the lookup the
order's checks read the quote cases through (`SqlQuoteCaseLookup.quotes`).

A link and a `from_order` read back as the domain left them; the lookup
reads a quote case in its own workspace only, never another workspace's or
another tenant's under the same id; and a `quote_links` that is not an array
is refused whoever writes.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sales_harness import T0, OrderRun, QuoteRun, World, user
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_sales.adapters.persistence.quotes import SqlQuoteCaseLookup
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import CaseEvent
from dw_sales.domain.orders import OrderCase, QuoteLink
from dw_sales.domain.quotes import FromOrder

pytestmark = pytest.mark.integration

AN_ID = uuid.UUID(int=0xA1)


def _m01(order_run: OrderRun) -> OrderCase:
    case = order_run.outcomes["M01"].case
    assert case is not None
    return order_run.latest()[case.case_id]


async def test_a_link_and_its_lookup_read_back_in_their_own_workspace_only(
    small_run: OrderRun,
    quote_run: QuoteRun,
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
) -> None:
    order = _m01(small_run)
    quote = quote_run.steps[-1]
    # The stored order linked to the stored quote: the columns, not the flow
    # (the flow's tests are `test_order_quotes.py`).
    reviewing = order.start_review()
    linked = reviewing.model_validate(
        {
            **dict(reviewing),
            "case_version": reviewing.case_version + 1,
            "quote_links": (QuoteLink(quote_case_id=quote.case_id, lines=(1,), by=AN_ID, at=T0),),
        }
    )
    stamped = quote.model_copy(
        update={
            "from_order": FromOrder(case_id=order.case_id, po_no=order.header.po_no),
            "case_version": quote.case_version + 1,
        }
    )
    event = CaseEvent(action="order.quote_opened", actor=user(AN_ID), occurred_at=T0)
    async with uow(world.alpha) as work:
        await work.orders.save(reviewing, expected_version=order.case_version, event=event)
        await work.orders.save(linked, expected_version=reviewing.case_version, event=event)
        opened = CaseEvent(action="quote.opened_from_order", actor=user(AN_ID), occurred_at=T0)
        await work.quotes.save(stamped, expected_version=quote.case_version, event=opened)
        await work.commit()

    async with uow(world.alpha) as work:
        stored_order = await work.orders.get(order.case_id)
        stored_quote = await work.quotes.get(quote.case_id)
    assert stored_order is not None and stored_order.case.quote_links == linked.quote_links
    assert stored_quote is not None and stored_quote.case.from_order == stamped.from_order

    lookup = SqlQuoteCaseLookup(app_sessions)
    (found,) = await lookup.quotes(world.alpha, [quote.case_id, uuid.uuid4()])
    assert found.case_id == quote.case_id
    for other in (world.alpha_other, world.beta):
        assert await lookup.quotes(other, [quote.case_id]) == []


async def test_quote_links_that_are_not_an_array_are_refused(
    migrator: AsyncEngine, small_run: OrderRun
) -> None:
    with pytest.raises(IntegrityError):
        async with migrator.begin() as connection:
            await connection.execute(
                sa.text("UPDATE sales.order_cases SET quote_links = '{}'::jsonb")
            )
