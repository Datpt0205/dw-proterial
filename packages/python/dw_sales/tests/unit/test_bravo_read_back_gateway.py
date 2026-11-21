"""Ticket 51: a case's SO read back from Bravo through the gateway on the
PIC's ask, compared with the paste sheet as approved, confirmed dates
included ("XN giao hàng" cleared by Bravo is a difference). Nothing is
stored when Bravo holds no SO, several, or did not answer."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from dw_kernel.errors import ConflictError, PermissionDeniedError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_sales.application.bravo_line_writes import BravoUnreachableError
from dw_sales.application.bravo_sales_orders import ReadBackService, prepared_rows
from dw_sales.application.ports import SalesScope
from dw_sales.domain.bravo_sales_orders import BravoSalesOrder, BravoSoRow, PreparedRow, compare
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN, CALLERS, DIEU, READER
from dw_sales.evals.world import SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
T0 = datetime(2026, 11, 21, 3, tzinfo=UTC)


def _rows(case: OrderCase, *, so: str = "SO26-1001", cleared: bool = False) -> BravoSalesOrder:
    rows = [
        BravoSoRow(
            row=n,
            so_no=so,
            customer_code=case.customer_code,
            po_no=r.po_no,
            po_line=r.line_no,
            item_code=r.prv_code,
            quantity=r.quantity,
            unit_price=r.unit_price,
            requested_date=r.requested_date,
            confirmed_date=None if cleared else r.confirmed_date,
        )
        for n, r in enumerate(prepared_rows(case), start=1)
    ]
    return BravoSalesOrder(
        customer_code=case.customer_code, po_no=case.header.po_no, rows=tuple(rows)
    )


@dataclasses.dataclass
class _Bravo:
    order: BravoSalesOrder | None
    down: bool = False
    asked: list[tuple[str, str]] = dataclasses.field(default_factory=list)

    async def by_customer_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> tuple[BravoSalesOrder, str] | None:
        self.asked.append((customer_code, po_no))
        if self.down:
            raise BravoUnreachableError("no answer")
        return None if self.order is None else (self.order, "d" * 64)


async def _uploaded() -> tuple[World, OrderCase]:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    seen = await world.process_each(DIEU, ["M01"])
    case_id = seen["M01"][0].case_id
    assert case_id is not None
    return world, await world.walk_to_uploaded(AN, case_id)


def _service(world: World, bravo: _Bravo | None) -> ReadBackService:
    return dataclasses.replace(
        world.services.read_backs, bravo=bravo, clock=FixedClock(T0), ids=Uuid4Generator()
    )


async def test_an_so_bravo_holds_as_prepared_is_read_back_equal() -> None:
    world, case = await _uploaded()
    bravo = _Bravo(_rows(case))

    view = await _service(world, bravo).read_from_bravo(
        AN.context(), case.case_id, case_version=case.case_version
    )

    assert bravo.asked == [(case.customer_code, case.header.po_no)]
    assert view.read_back is not None and view.read_back.equal
    assert view.read_back.file_sha256 == "d" * 64 and not view.stale


def test_a_confirmed_date_bravo_cleared_is_a_difference_only_where_it_was_read() -> None:
    prepared = PreparedRow(
        po_no="PO-1",
        line_no=1,
        prv_code="A",
        quantity=1,  # type: ignore[arg-type]
        unit_price=2,  # type: ignore[arg-type]
        requested_date=None,
        confirmed_date=date(2026, 12, 1),
    )
    held = BravoSalesOrder(
        customer_code="FG1",
        po_no="PO-1",
        rows=(
            BravoSoRow(
                row=1,
                so_no="SO-1",
                customer_code="FG1",
                po_no="PO-1",
                po_line=1,
                item_code="A",
                quantity=1,
                unit_price=2,  # type: ignore[arg-type]
            ),
        ),
    )

    assert [d.field for d in compare([prepared], held, confirmed_dates=True)] == ["confirmed_date"]
    # The Form 1 export carries no confirmed date: nothing is compared.
    assert compare([prepared], held) == ()


@pytest.mark.parametrize(
    "bravo",
    [_Bravo(None), _Bravo(None, down=True), None],
    ids=["no_so_in_bravo", "bravo_down", "no_gateway"],
)
async def test_nothing_is_stored_when_bravo_cannot_answer_for_one_so(bravo: _Bravo | None) -> None:
    world, case = await _uploaded()

    with pytest.raises(ConflictError):
        await _service(world, bravo).read_from_bravo(
            AN.context(), case.case_id, case_version=case.case_version
        )
    assert (await world.services.read_backs.latest(AN.context(), case.case_id)).read_back is None


async def test_a_po_under_several_sos_is_not_compared() -> None:
    world, case = await _uploaded()
    order = _rows(case)
    split = order.model_copy(
        update={"rows": (*order.rows, order.rows[0].model_copy(update={"so_no": "SO26-1002"}))}
    )

    with pytest.raises(ConflictError) as refused:
        await _service(world, _Bravo(split)).read_from_bravo(
            AN.context(), case.case_id, case_version=case.case_version
        )
    assert refused.value.details["rule"] == "several_sos"


async def test_a_reader_without_the_prepare_right_cannot_ask_bravo() -> None:
    world, case = await _uploaded()
    bravo = _Bravo(_rows(case))

    with pytest.raises(PermissionDeniedError):
        await _service(world, bravo).read_from_bravo(
            READER.context(), case.case_id, case_version=case.case_version
        )
    assert bravo.asked == []


async def test_a_read_back_asked_on_an_older_case_version_is_refused() -> None:
    world, case = await _uploaded()
    bravo = _Bravo(_rows(case))

    with pytest.raises(ConflictError) as refused:
        await _service(world, bravo).read_from_bravo(
            AN.context(), case.case_id, case_version=case.case_version - 1
        )
    assert refused.value.details["rule"] == "stale_case_version" and bravo.asked == []
