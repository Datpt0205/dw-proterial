"""Ticket 03: a sales order read back from Bravo, compared line by line with
the rows DW1 prepared for it. Every value here is synthetic."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from dw_sales.domain.bravo_sales_orders import (
    BravoSalesOrder,
    BravoSoRow,
    PreparedRow,
    compare,
)

pytestmark = pytest.mark.unit

PO = "VN-261109-0001"


def _prepared(
    line: int,
    *,
    code: str = "7600000034",
    qty: str = "40",
    price: str = "4.3285",
    requested: date | None = date(2026, 12, 1),
) -> PreparedRow:
    return PreparedRow(
        po_no=PO,
        line_no=line,
        prv_code=code,
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        requested_date=requested,
    )


def _bravo(
    line: int,
    *,
    code: str = "7600000034",
    qty: str = "40.000",
    price: str = "4.32850",
    requested: date | None = date(2026, 12, 1),
    so: str = "SO2611-000161",
    row: int = 4,
) -> BravoSoRow:
    return BravoSoRow(
        row=row,
        so_no=so,
        customer_code="FG0001",
        po_no=PO,
        po_line=line,
        item_code=code,
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        requested_date=requested,
    )


def _order(*rows: BravoSoRow) -> BravoSalesOrder:
    return BravoSalesOrder(customer_code="FG0001", po_no=PO, rows=rows)


def test_an_entry_equal_line_by_line_has_no_difference_and_names_its_so() -> None:
    order = _order(_bravo(1), _bravo(2, code="7600000035"))

    found = compare((_prepared(1), _prepared(2, code="7600000035")), order)

    assert found == ()
    assert order.so_no == "SO2611-000161"


def test_one_wrong_price_is_one_difference_on_that_line() -> None:
    """Acceptance 1."""
    found = compare((_prepared(1), _prepared(2)), _order(_bravo(1), _bravo(2, price="4.32860")))

    assert [(d.line_no, d.field) for d in found] == [(2, "unit_price")]


@pytest.mark.parametrize(
    ("bravo", "expected"),
    [
        (_order(_bravo(1)), [(2, "missing_row")]),  # a row Bravo's import skipped
        (_order(_bravo(1), _bravo(2), _bravo(3)), [(3, "extra_row")]),
        (_order(_bravo(1), _bravo(2, code="7600000099")), [(2, "item_code")]),
        (_order(_bravo(1), _bravo(2, qty="39")), [(2, "quantity")]),
        (_order(_bravo(1), _bravo(2, requested=date(2026, 12, 2))), [(2, "requested_date")]),
        (_order(_bravo(1), _bravo(2, requested=None)), [(2, "requested_date")]),
    ],
    ids=["skipped_row", "extra_row", "code", "quantity", "date", "no_date"],
)
def test_each_difference_names_its_line_and_field(
    bravo: BravoSalesOrder, expected: list[tuple[int, str]]
) -> None:
    found = compare((_prepared(1), _prepared(2)), bravo)

    assert [(d.line_no, d.field) for d in found] == expected


def test_a_line_delivered_twice_is_compared_row_by_row() -> None:
    prepared = (_prepared(1, qty="990"), _prepared(1, qty="10"))

    assert compare(prepared, _order(_bravo(1, qty="990"), _bravo(1, qty="10"))) == ()
    found = compare(prepared, _order(_bravo(1, qty="1000")))
    assert [(d.line_no, d.field) for d in found] == [(1, "quantity"), (1, "missing_row")]


def test_a_line_cancelled_whole_expects_no_row() -> None:
    prepared = (_prepared(1), _prepared(2, qty="0"))

    assert compare(prepared, _order(_bravo(1))) == ()
    found = compare(prepared, _order(_bravo(1), _bravo(2)))
    assert [(d.line_no, d.field) for d in found] == [(2, "extra_row")]


def test_a_po_under_two_sales_orders_is_not_compared() -> None:
    """B02 holds POs under two and four SOs: which one the paste made is not
    guessed."""
    order = _order(_bravo(1), _bravo(2, so="SO2611-000162"))

    assert order.so_no is None and order.so_numbers == ("SO2611-000161", "SO2611-000162")
    with pytest.raises(ValueError):
        compare((_prepared(1), _prepared(2)), order)
