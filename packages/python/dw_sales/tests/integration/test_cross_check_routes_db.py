"""Ticket 81 against real Postgres, migration d533225350dd: what the
cross-check lane did with each order version (`sales.order_cross_check_routes`),
the rule's stamp and the pass's read-back on `sales.order_cases`, and where
a read-back came from (`sales.order_bravo_read_backs.source`).

A version is routed once and decided once; another workspace or tenant finds
none of it; `dw_app` may not delete a route; a route the gate applied names
no exception, an undo is only a pass's, and the stamp is on only where a
cross-check is required, whoever writes. A case's stamp reads back as saved.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from sales_harness import T0, OrderRun, World
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_kernel.errors import ConflictError
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import CaseEvent, EventActor
from dw_sales.application.cross_check_on_match import CrossCheckRoute
from dw_sales.domain.cross_check_on_match import ON_MATCH_BASIS, OnMatchException
from dw_sales.domain.orders import OrderCase

pytestmark = pytest.mark.integration


def _m04(order_run: OrderRun) -> OrderCase:
    case = order_run.outcomes["M04"].case
    assert case is not None
    return order_run.latest()[case.case_id]


def _route(case: OrderCase, **values: object) -> CrossCheckRoute:
    return CrossCheckRoute.model_validate(
        {
            "case_id": case.case_id,
            "case_version": case.case_version,
            "basis": ON_MATCH_BASIS,
            "route": "person",
            "exceptions": (),
            "routed_at": T0,
            **values,
        }
    )


async def test_a_version_is_routed_once_decided_once_and_in_its_workspace_only(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    case = _m04(order_run)
    route = _route(case, exceptions=(OnMatchException.FINDING,))
    async with uow(world.alpha) as work:
        await work.cross_check_routes.add(route)
        await work.commit()
    with pytest.raises(ConflictError):
        async with uow(world.alpha) as work:
            await work.cross_check_routes.add(route)

    decided_at = T0 + timedelta(hours=1)
    async with uow(world.alpha) as work:
        assert await work.cross_check_routes.decide(
            case.case_id, case.case_version, "returned", decided_at
        )
        assert not await work.cross_check_routes.decide(
            case.case_id, case.case_version, "kept", decided_at
        )
        await work.commit()
    async with uow(world.alpha) as work:
        stored = await work.cross_check_routes.get(case.case_id, case.case_version)
        decided = list(await work.cross_check_routes.outcomes(ON_MATCH_BASIS))
    assert stored is not None
    assert (stored.outcome, stored.exceptions) == ("returned", (OnMatchException.FINDING,))
    assert [r.case_id for r in decided] == [case.case_id]
    for other in (world.alpha_other, world.beta):
        async with uow(other) as work:
            assert await work.cross_check_routes.get(case.case_id, case.case_version) is None
            assert list(await work.cross_check_routes.outcomes(ON_MATCH_BASIS)) == []
            assert not await work.cross_check_routes.decide(
                case.case_id, case.case_version, "kept", decided_at
            )


async def test_an_open_pass_is_found_to_take_back(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    case = _m04(order_run)
    async with uow(world.alpha) as work:
        await work.cross_check_routes.add(_route(case, route="applied"))
        await work.commit()
    async with uow(world.alpha) as work:
        passed = await work.cross_check_routes.passed(case.case_id)
        assert passed is not None and passed.route == "applied"
        await work.cross_check_routes.decide(case.case_id, case.case_version, "undone", T0)
        await work.commit()
    async with uow(world.alpha) as work:
        assert await work.cross_check_routes.passed(case.case_id) is None


async def test_the_application_may_not_delete_and_the_checks_hold_whoever_writes(
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
                    " WHERE has_table_privilege('dw_app', 'sales.order_cross_check_routes',"
                    " v.verb)"
                )
            )
        }
    assert held == {"SELECT", "INSERT", "UPDATE"}
    insert = sa.text(
        "INSERT INTO sales.order_cross_check_routes (tenant_id, workspace_id, case_id,"
        " case_version, basis, route, exceptions, outcome, routed_at, decided_at)"
        " VALUES (:t, :w, :c, :v, :b, :route, CAST(:x AS jsonb), :o, now(), :d)"
    )
    base = {
        "t": world.alpha.tenant_id.value,
        "w": world.alpha.workspace_id.value,
        "c": case.case_id,
        "b": ON_MATCH_BASIS,
        "o": None,
        "d": None,
    }
    refused = (
        # The gate applied an order an exception kept a person's.
        {"v": 90, "route": "applied", "x": '["finding"]'},
        # An undo is only a pass's.
        {"v": 91, "route": "person", "x": "[]", "o": "undone", "d": T0},
        # A decision has its time, and only a decision.
        {"v": 92, "route": "person", "x": "[]", "o": "kept"},
        {"v": 93, "route": "elsewhere", "x": "[]"},
    )
    for values in refused:
        with pytest.raises(DBAPIError):
            async with migrator.begin() as conn:
                await conn.execute(insert, {**base, **values})
    # The stamp is on only where a cross-check is required.
    with pytest.raises(DBAPIError):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    "UPDATE sales.order_cases SET cross_check_on_match = true,"
                    " cross_check_required = false WHERE id = :c"
                ),
                {"c": case.case_id},
            )
    # A read-back's source is one of two.
    with pytest.raises(DBAPIError):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.order_bravo_read_backs (tenant_id, workspace_id, case_id,"
                    " case_version, po_no, so_no, differences, rows_read, file_sha256, read_by,"
                    " read_at, source) VALUES (:t, :w, :c, 1, 'PO', 'SO', '[]', 1, :sha, :c,"
                    " now(), 'mail')"
                ),
                {**base, "sha": "0" * 64},
            )


async def test_a_cases_stamp_reads_back_as_saved(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    case = _m04(order_run)
    assert case.cross_check_required is True
    stamped = OrderCase.model_validate({**dict(case.reassigned()), "cross_check_on_match": True})
    event = CaseEvent(
        action="order.reassigned", actor=EventActor.person(uuid.UUID(int=0xA1)), occurred_at=T0
    )
    async with uow(world.alpha) as work:
        await work.orders.save(stamped, expected_version=case.case_version, event=event)
        await work.commit()
    async with uow(world.alpha) as work:
        found = await work.orders.get(case.case_id)
        waiting = await work.orders.awaiting_on_match()
    assert found is not None and found.case.cross_check_on_match is True
    # In review, not in Bravo: nothing for the lane to read.
    assert [s.case.case_id for s in waiting] == []
