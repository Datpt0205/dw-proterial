"""An order after it is drafted (DW02 function 5, `domain.tracking`): the
number Bravo gave it, the supplier's confirmation held to the order line by
line, and what was received against what is due."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from dw_purchasing.domain.orders import PoDraft, PoLine
from dw_purchasing.domain.tracking import (
    ConfirmedLine,
    OrderTracking,
    Receipt,
    differences,
    due_lines,
    received,
)

pytestmark = pytest.mark.unit

AT = datetime(2026, 11, 4, 8, 0, tzinfo=UTC)
BUYER = uuid.UUID(int=0xB0B)


def _order() -> PoDraft:
    lines = (
        PoLine(
            line_no=1,
            item_code="DC-200",
            description="Dao cắt cáp DC-200",
            quantity=Decimal(4),
            unit="cái",
            unit_price=Decimal(350000),
            amount=Decimal(1400000),
            need_by=date(2026, 11, 20),
        ),
        PoLine(
            line_no=3,
            item_code="BK-1700",
            description="Băng keo cách điện",
            quantity=Decimal(120),
            unit="cuộn",
            unit_price=Decimal(18000),
            amount=Decimal(2160000),
            need_by=None,
        ),
    )
    return PoDraft(
        po_ref="PR-2611-004-01",
        supplier_code="NCC-KIM",
        supplier_name="Kimura Tools",
        currency="VND",
        lines=lines,
        total=Decimal(3560000),
    )


def _confirmed(line_no: int, quantity: str, price: str, on: date | None) -> ConfirmedLine:
    return ConfirmedLine(
        line_no=line_no, quantity=Decimal(quantity), unit_price=Decimal(price), delivery_on=on
    )


def test_a_confirmation_matching_the_order_has_no_difference() -> None:
    lines = (
        _confirmed(1, "4", "350000", date(2026, 11, 18)),
        _confirmed(3, "120", "18000", date(2026, 11, 25)),
    )
    assert differences(_order(), lines) == ()


def test_each_difference_names_its_line_and_what_differs() -> None:
    lines = (
        # Fewer, dearer, and later than the line is needed.
        _confirmed(1, "3", "360000", date(2026, 11, 22)),
    )
    found = {(d.line_no, d.field): (d.ordered, d.confirmed) for d in differences(_order(), lines)}
    assert found == {
        (1, "quantity"): ("4", "3"),
        (1, "unit_price"): ("350000", "360000"),
        (1, "delivery_on"): ("2026-11-20", "2026-11-22"),
        # Line 3 not confirmed at all.
        (3, "missing"): ("120", None),
    }


def test_a_line_the_order_does_not_hold_is_a_difference() -> None:
    lines = (
        _confirmed(1, "4", "350000", None),
        _confirmed(3, "120", "18000", None),
        _confirmed(9, "1", "1", None),
    )
    assert [(d.line_no, d.field) for d in differences(_order(), lines)] == [(9, "not_ordered")]


def test_a_date_confirmed_for_a_line_with_no_need_by_is_no_difference() -> None:
    lines = (
        _confirmed(1, "4", "350000", date(2026, 11, 20)),
        _confirmed(3, "120", "18000", date(2027, 1, 30)),
    )
    assert differences(_order(), lines) == ()


def _tracking(**changes: object) -> OrderTracking:
    return OrderTracking.model_validate({"po_ref": "PR-2611-004-01", **changes})


def _receipt(line_no: int, quantity: str, on: date) -> Receipt:
    return Receipt(
        line_no=line_no,
        quantity=Decimal(quantity),
        received_on=on,
        recorded_by=BUYER,
        recorded_at=AT,
    )


def test_what_is_due_reads_the_confirmed_date_else_the_need_by() -> None:
    order = _order()
    tracking = _tracking()
    # Line 1 needed by 20/11; line 3 has no date, so nothing is due for it.
    assert due_lines(order, tracking, today=date(2026, 11, 21)) == [1]
    assert due_lines(order, tracking, today=date(2026, 11, 20)) == []


def test_a_line_received_in_full_is_not_due() -> None:
    order = _order()
    partly = _tracking(receipts=[_receipt(1, "3", date(2026, 11, 19))])
    assert received(partly, 1) == Decimal(3)
    assert due_lines(order, partly, today=date(2026, 11, 21)) == [1]
    full = _tracking(
        receipts=[_receipt(1, "3", date(2026, 11, 19)), _receipt(1, "1", date(2026, 11, 21))]
    )
    assert due_lines(order, full, today=date(2026, 11, 30)) == []


def test_bravo_s_number_is_a_code_and_is_stamped_with_who_typed_it() -> None:
    with pytest.raises(ValidationError):
        _tracking(bravo_no="PO 2611/1; DROP")
    with pytest.raises(ValidationError):
        _tracking(bravo_no="PO26110001")  # who recorded it, and when, go with it
    held = _tracking(bravo_no="PO26110001", bravo_by=BUYER, bravo_at=AT)
    assert held.bravo_no == "PO26110001"


def test_a_receipt_is_more_than_nothing() -> None:
    with pytest.raises(ValidationError):
        _receipt(1, "0", date(2026, 11, 19))


# ------------------------------------------------- reading a confirmation --

MAIL = (
    "Kimura Tools xác nhận đơn hàng PR-2611-004-01:\n"
    "- DC-200 Dao cắt cáp: 4 cái, đơn giá 350.000, giao ngày 18/11/2026\n"
    "- BK-1700 Băng keo: 100 cuộn, giao ngày 25/11/2026\n"
    "Ghi chú: giá chưa gồm VAT 8%."
)
ORDERED = {"DC-200": 1, "BK-1700": 3}


def _line(span: str, code: str | None, **values: str | None) -> dict[str, str | None]:
    return {
        "line_span": span,
        "item_code_span": code,
        "quantity_span": values.get("quantity"),
        "unit_price_span": values.get("price"),
        "delivery_date_span": values.get("on"),
    }


def _read(*lines: dict[str, str | None], text: str = MAIL):  # type: ignore[no-untyped-def]
    from dw_purchasing.domain.confirmation_reading import (
        ModelConfirmation,
        read_confirmation_mail,
    )

    answer = ModelConfirmation.model_validate({"lines": list(lines)})
    return read_confirmation_mail(text, answer, ordered=ORDERED, received_on=date(2026, 11, 5))


FIRST = _line(
    "DC-200 Dao cắt cáp: 4 cái, đơn giá 350.000, giao ngày 18/11/2026",
    "DC-200",
    quantity="4 cái",
    price="350.000",
    on="18/11/2026",
)
SECOND = _line(
    "BK-1700 Băng keo: 100 cuộn, giao ngày 25/11/2026",
    "BK-1700",
    quantity="100 cuộn",
    on="25/11/2026",
)


def test_a_confirmation_is_read_line_by_line_by_the_order_s_codes() -> None:
    verdict = _read(FIRST, SECOND)
    assert verdict.not_read is None
    assert verdict.lines == (
        ConfirmedLine(
            line_no=1,
            quantity=Decimal(4),
            unit_price=Decimal(350000),
            delivery_on=date(2026, 11, 18),
        ),
        ConfirmedLine(
            line_no=3, quantity=Decimal(100), unit_price=None, delivery_on=date(2026, 11, 25)
        ),
    )
    # What it says against the order: 100 of 120 rolls.
    assert [(d.line_no, d.field) for d in differences(_order(), verdict.lines)] == [(3, "quantity")]


@pytest.mark.parametrize(
    ("line", "why"),
    [
        # A value the line does not hold.
        ({**FIRST, "unit_price_span": "0"}, "line_unreadable"),
        # A value of another line: in the mail, not in this line.
        ({**FIRST, "quantity_span": "100 cuộn"}, "line_unreadable"),
        # A line the mail does not hold.
        ({**FIRST, "line_span": "DC-200 Dao cắt cáp: 4 cái, giá 0"}, "line_unreadable"),
        # No value at all.
        (
            {**FIRST, "quantity_span": None, "unit_price_span": None, "delivery_date_span": None},
            "line_unreadable",
        ),
        # No code: which line it is is the order's, by code.
        ({**FIRST, "item_code_span": None}, "line_unreadable"),
        # A value that is no number.
        ({**FIRST, "quantity_span": "Dao"}, "line_unreadable"),
    ],
)
def test_a_line_code_cannot_find_refuses_the_mail(line: dict[str, str | None], why: str) -> None:
    verdict = _read(line, SECOND)
    assert (verdict.lines, verdict.not_read) == ((), why)


def test_an_item_the_order_does_not_hold_is_not_read() -> None:
    text = MAIL + "\n- GT-C5 Găng tay: 10 đôi"
    extra = _line("GT-C5 Găng tay: 10 đôi", "GT-C5", quantity="10 đôi")
    assert _read(FIRST, extra, text=text).not_read == "item_not_ordered"


def test_one_item_twice_and_no_line_are_not_read() -> None:
    again = {**SECOND, "item_code_span": "DC-200", "line_span": SECOND["line_span"]}
    assert _read(FIRST, {**again, "item_code_span": "BK-1700"}, FIRST).not_read == (
        "line_unreadable"
    )
    assert _read().not_read == "no_lines"


async def test_a_case_follows_only_the_orders_it_drafted_each_once() -> None:
    """Held by the aggregate: tracking a `po_ref` the case never drafted,
    or one twice, is no case."""
    from pathlib import Path

    from dw_purchasing.domain.cases import PurchaseCase
    from dw_purchasing.testing.flows import orders_drafted, sourcing_world
    from dw_purchasing.testing.world import caller

    world = sourcing_world(Path(__file__).resolve().parents[5])
    case = await world.service.case(caller(), await orders_drafted(world))
    assert case.po is not None
    order = case.po.orders[0]
    followed = case.model_copy(update={"tracking": (_tracking(po_ref=order.po_ref),)})
    assert PurchaseCase.model_validate(followed.model_dump()) == followed
    for tracking in (
        (_tracking(po_ref="PR-0000-001-01"),),
        (_tracking(po_ref=order.po_ref), _tracking(po_ref=order.po_ref)),
    ):
        with pytest.raises(ValidationError, match="followed once"):
            PurchaseCase.model_validate({**case.model_dump(), "tracking": tracking})
