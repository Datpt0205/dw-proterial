"""Ticket 27 against real Postgres: a customer's change requests on an order
(`sales.change_requests`) and a line's confirmed changes
(`sales.order_lines.changes`), migration c7d0730fcccd.

A request reads back as the domain left it, once per mail and case; two are
never open on one case together (the partial unique index, whoever writes);
a save on a version that moved on is refused; another workspace or tenant
finds none of it; `dw_app` may not delete one, and a row whose record names
another state is refused. A confirmed change is stored on its line beside
the value as read.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sales_harness import T0, OrderRun, World, user
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.persistence.orders import SqlOrderCaseLookup
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.adapters.reader_client import ClientPoReaders, ClientQuoteForms
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.case_store import CaseEvent
from dw_sales.application.order_intake import OrderIntake
from dw_sales.domain.anchors import MessageText
from dw_sales.domain.change_requests import ChangeRequest, ChangeRequestState, person_line
from dw_sales.domain.orders import Actor, AppliedChange, OrderCase
from dw_sales.domain.rfq_reading import text_digest
from dw_sales.testing.followups import platform_zone

pytestmark = pytest.mark.integration

AN_ID = uuid.UUID(int=0xA1)
POLICIES = Path(__file__).resolve().parents[5] / "configs" / "policies"
TEXT = "RE: PO NRV-PO-26-0457\n\nLine 3 to 18/12/2026, please."


def _m04(order_run: OrderRun) -> OrderCase:
    """M04's order as the run left it (later mail may have moved it on)."""
    case = order_run.outcomes["M04"].case
    assert case is not None
    return order_run.latest()[case.case_id]


def _request(
    case: OrderCase,
    message_id: str = "R1",
    state: ChangeRequestState = "open",
    minutes: int = 0,
) -> ChangeRequest:
    return ChangeRequest(
        request_id=uuid.uuid4(),
        case_id=case.case_id,
        # The mail's number is the request's place on the case: R1 first.
        number=int(message_id[1:]),
        message_id=message_id,
        text=MessageText(text=TEXT, sha256=text_digest(TEXT)),
        opened_by=AN_ID,
        opened_at=T0 + timedelta(minutes=minutes),
        state=state,
        lines=(person_line(case, 3, "requested_date", "2026-12-18"),),
    )


async def test_a_request_reads_back_once_per_mail_and_in_its_workspace_only(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    case = _m04(order_run)
    first = _request(case)
    async with uow(world.alpha) as work:
        await work.change_requests.add(first)
        await work.commit()

    async with uow(world.alpha) as work:
        assert await work.change_requests.for_case(case.case_id) == [first]
    with pytest.raises(ConflictError) as again:
        async with uow(world.alpha) as work:
            await work.change_requests.add(_request(case, state="queued"))
    assert again.value.details["rule"] == "change_request_exists"
    for other in (world.alpha_other, world.beta):
        async with uow(other) as work:
            assert await work.change_requests.for_case(case.case_id) == []


async def test_two_requests_are_never_open_on_one_case(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    """ADR 0010 decision 4, held by the store whoever writes: a second open
    one is refused; queued, it is kept, and it opens only once the first is
    no longer open."""
    case = _m04(order_run)
    first, second = _request(case), _request(case, "R2", state="queued", minutes=5)
    async with uow(world.alpha) as work:
        await work.change_requests.add(first)
        await work.commit()
    with pytest.raises(ConflictError) as both:
        async with uow(world.alpha) as work:
            await work.change_requests.add(_request(case, "R3"))
    assert both.value.details["rule"] == "change_request_open"

    async with uow(world.alpha) as work:
        await work.change_requests.add(second)
        await work.commit()
    with pytest.raises(ConflictError):
        async with uow(world.alpha) as work:
            await work.change_requests.save(second.opened(), expected_version=second.version)
    closed = first.rejected(1, "Khách gọi lại", AN_ID, T0)
    async with uow(world.alpha) as work:
        await work.change_requests.save(closed, expected_version=first.version)
        await work.change_requests.save(second.opened(), expected_version=second.version)
        await work.commit()

    async with uow(world.alpha) as work:
        states = [r.state for r in await work.change_requests.for_case(case.case_id)]
    assert states == ["closed", "open"]


async def test_a_save_on_a_version_that_moved_on_is_refused(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    case = _m04(order_run)
    request = _request(case)
    async with uow(world.alpha) as work:
        await work.change_requests.add(request)
        await work.commit()
    decided = request.rejected(1, "Không đổi", AN_ID, T0)
    async with uow(world.alpha) as work:
        await work.change_requests.save(decided, expected_version=request.version)
        await work.commit()

    with pytest.raises(ConflictError) as stale:
        async with uow(world.alpha) as work:
            await work.change_requests.save(
                request.confirmed(1, AN_ID, T0), expected_version=request.version
            )
    assert stale.value.details["rule"] == "stale_change_request"


async def test_the_application_may_not_delete_and_a_record_names_its_own_state(
    order_run: OrderRun, migrator: AsyncEngine, world: World
) -> None:
    case = _m04(order_run)
    async with migrator.connect() as conn:
        held = {
            row.verb
            for row in await conn.execute(
                sa.text(
                    "SELECT v.verb"
                    " FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) AS v(verb)"
                    " WHERE has_table_privilege('dw_app', 'sales.change_requests', v.verb)"
                )
            )
        }
    assert held == {"SELECT", "INSERT", "UPDATE"}
    request = _request(case)
    with pytest.raises(DBAPIError):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.change_requests (id, tenant_id, workspace_id, case_id,"
                    " message_id, state, version, opened_by, opened_at, record)"
                    " VALUES (:id, :t, :w, :c, 'R1', 'closed', 1, :by, now(), :record)"
                ),
                {
                    "id": request.request_id,
                    "t": world.alpha.tenant_id.value,
                    "w": world.alpha.workspace_id.value,
                    "c": case.case_id,
                    "by": AN_ID,
                    "record": request.model_dump_json(),
                },
            )


async def test_a_confirmed_change_reads_back_on_its_line_beside_the_value_as_read(
    order_run: OrderRun,
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    case = _m04(order_run)
    scope = order_run.scope
    intake = OrderIntake(
        catalog=MockSalesCatalog.load(scope),
        inbox=MockInbox.load(scope),
        reader=ClientPoReaders(InProcessReaderTransport()),
        quote_forms=ClientQuoteForms(InProcessReaderTransport()),
        zones=platform_zone(),
        rules=PlatformOrderRules(load_order_rules(POLICIES / "sales_order_rules@1.13.0.yaml")),
        cases=SqlOrderCaseLookup(app_sessions),
        new_case_id=uuid.uuid4,
    )
    an = Actor(user_id=AN_ID)
    reviewing = case.start_review()
    change = AppliedChange(
        field="requested_date", value="2026-12-18", request_id=uuid.uuid4(), by=AN_ID, at=T0
    )
    changed = await intake.take_change(scope, reviewing, 3, change, an)
    async with uow(scope) as work:
        for before, after in ((case, reviewing), (reviewing, changed)):
            event = CaseEvent(action="order.change_confirmed", actor=user(AN_ID), occurred_at=T0)
            await work.orders.save(after, expected_version=before.case_version, event=event)
        await work.commit()

    async with uow(scope) as work:
        stored = await work.orders.get(case.case_id)
    assert stored is not None and stored.case == changed
    line = stored.case.line(3)
    assert (line.po_line.requested_date, line.effective.requested_date) == (
        date(2026, 12, 4),
        date(2026, 12, 18),
    )
    assert line.changes == (change,)
