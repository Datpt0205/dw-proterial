"""What code accepts of a model's reading of a request for quotation
(ticket 29, dw_sales ADR 0005): the parsers, and `verify_rfq`'s checks."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from dw_sales.domain.rfq_reading import (
    ModelRfqReading,
    TextPart,
    parse_currency,
    parse_date,
    parse_number,
    parse_price,
    parse_quantity,
    parse_uom,
    verify_rfq,
)

pytestmark = pytest.mark.unit

RECEIVED = date(2026, 10, 2)
SHA = hashlib.sha256(b"part").hexdigest()


# ---------------------------------------------------------------- parsers --


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1,200", Decimal(1200)),
        ("1.200", Decimal(1200)),
        ("1 200", Decimal(1200)),
        ("12,200", Decimal(12200)),
        ("1200", Decimal(1200)),
        ("0.42", Decimal("0.42")),
        ("0,42", Decimal("0.42")),
        ("1,2,3", None),
        ("1.200,5", None),
        ("", None),
    ],
)
def test_a_number_is_read_as_customers_write_it(text: str, value: Decimal | None) -> None:
    assert parse_number(text) == value


@pytest.mark.parametrize(
    ("span", "read"),
    [
        ("1,200 m", (Decimal(1200), True)),
        ("3.000 mét", (Decimal(3000), True)),
        ("4,000m", (Decimal(4000), True)),
        ("1500メートル", (Decimal(1500), True)),
        ("500", (Decimal(500), False)),
        ("5 reels", None),
        ("2 km", None),
        ("0 m", None),
    ],
)
def test_a_quantity_is_a_number_and_at_most_metres(
    span: str, read: tuple[Decimal, bool] | None
) -> None:
    assert parse_quantity(span) == read


@pytest.mark.parametrize(
    ("span", "uom"),
    [
        ("m", "m"),
        ("mét", "m"),
        ("meters", "m"),
        ("/m", "m"),
        ("pcs", None),
        ("reel", None),
        ("km", None),
    ],
)
def test_only_metres_is_a_unit_dw1_quotes_in(span: str, uom: str | None) -> None:
    assert parse_uom(span) == uom


@pytest.mark.parametrize(
    ("span", "day"),
    [
        ("2026-11-15", date(2026, 11, 15)),
        ("15/11/2026", date(2026, 11, 15)),
        ("15/11", date(2026, 11, 15)),
        ("ngày 05/12", date(2026, 12, 5)),
        ("15 Nov 2026", date(2026, 11, 15)),
        ("November 30, 2026", date(2026, 11, 30)),
        ("Nov 15", date(2026, 11, 15)),
        ("2026年12月4日", date(2026, 12, 4)),
        ("11月20日", date(2026, 11, 20)),
        ("15 tháng 11", date(2026, 11, 15)),
        # Only the other order makes a date.
        ("11/25/2026", date(2026, 11, 25)),
        # Without a year: the next one that is not long past.
        ("15/01", date(2027, 1, 15)),
        ("12月中旬", None),
        ("31/02", None),
        ("next week", None),
    ],
)
def test_a_date_is_read_as_customers_write_it(span: str, day: date | None) -> None:
    assert parse_date(span, RECEIVED) == day


@pytest.mark.parametrize(
    ("span", "currency"),
    [
        ("USD", "USD"),
        ("us$", "USD"),
        ("VNĐ", "VND"),
        ("đồng", "VND"),
        ("円", "JPY"),
        ("yen", "JPY"),
        ("EUR", None),
    ],
)
def test_a_currency_is_one_of_the_three_dw1_prices_in(span: str, currency: str | None) -> None:
    assert parse_currency(span) == currency


@pytest.mark.parametrize(
    ("span", "price"),
    [("USD 0.95", Decimal("0.95")), ("0,42 USD/m", Decimal("0.42")), ("0", None), ("1 or 2", None)],
)
def test_a_stated_price_is_one_number_above_zero(span: str, price: Decimal | None) -> None:
    assert parse_price(span) == price


# ---------------------------------------------------------- verification --

BODY = (
    "Yêu cầu báo giá\n\n"
    "1. Cáp 2C AWG24 BLK, 1.200 m, cần trước 15/11\n"
    "2. Dây điện AWG22 đỏ, 3.000 m, cần trước 30/11\n"
    "Giá tính bằng USD, hạn báo giá 20/10/2026."
)
LINE_1 = "1. Cáp 2C AWG24 BLK, 1.200 m, cần trước 15/11"
LINE_2 = "2. Dây điện AWG22 đỏ, 3.000 m, cần trước 30/11"
PART = TextPart("body", BODY, None, SHA)


def _item(**fields: Any) -> dict[str, Any]:
    return {
        "part": "body",
        "line_span": LINE_1,
        "description_span": "Cáp 2C AWG24 BLK",
        "customer_item_code_span": None,
        "quantity_span": "1.200 m",
        "uom_span": None,
        "required_date_span": "15/11",
        "target_price_span": None,
    } | fields


def _answer(*items: dict[str, Any], **header: Any) -> ModelRfqReading:
    return ModelRfqReading.model_validate(
        {"rfq_no_span": None, "quote_due_span": "20/10/2026", "currency_span": "USD"}
        | header
        | {"items": list(items)}
    )


def test_a_reading_code_accepts_is_every_value_parsed_from_its_place() -> None:
    verdict = verify_rfq([PART], _answer(_item()), RECEIVED)

    (item,) = verdict.items
    assert item.description.value == "Cáp 2C AWG24 BLK"
    assert (item.quantity and item.quantity.value) == Decimal(1200)
    assert (item.uom and item.uom.value) == "m"
    assert (item.needed_by and item.needed_by.value) == date(2026, 11, 15)
    assert verdict.currency is not None and verdict.currency.value == "USD"
    assert verdict.quote_due is not None and verdict.quote_due.value == date(2026, 10, 20)
    chars = item.quantity.anchor.chars if item.quantity else None
    assert chars is not None and BODY[chars.start : chars.end] == "1.200 m"
    assert not verdict.refused


@pytest.mark.parametrize(
    ("fields", "refusal"),
    [
        ({"part": "M38-A1#p1"}, "part_unknown"),
        ({"line_span": "1. Cáp 2C AWG24 BLK, 5.000 m"}, "line_not_found"),
        ({"description_span": "Dây điện AWG22 đỏ"}, "description_not_found"),
    ],
)
def test_an_item_whose_place_does_not_hold_is_not_read(
    fields: dict[str, Any], refusal: str
) -> None:
    verdict = verify_rfq([PART], _answer(_item(**fields)), RECEIVED)

    assert verdict.items == [] and verdict.refused[refusal] == 1


@pytest.mark.parametrize(
    ("fields", "refusal"),
    [
        # 24 of AWG24 is no token.
        ({"quantity_span": "24"}, "quantity_not_found"),
        # The other line's quantity is not inside this line.
        ({"quantity_span": "3.000 m"}, "quantity_not_found"),
        ({"required_date_span": "30/11"}, "needed_by_not_found"),
        # A number with no unit is no quantity: 5 reels is not 5 m.
        ({"quantity_span": "1.200", "line_span": LINE_1}, None),
    ],
)
def test_a_value_whose_span_does_not_hold_is_dropped_never_repaired(
    fields: dict[str, Any], refusal: str | None
) -> None:
    verdict = verify_rfq([PART], _answer(_item(**fields)), RECEIVED)

    (item,) = verdict.items
    if refusal is not None:
        assert verdict.refused[refusal] == 1
    if "quantity_span" in fields:
        assert item.quantity is None
    else:
        assert item.needed_by is None


def test_a_number_without_metres_is_no_quantity() -> None:
    verdict = verify_rfq([PART], _answer(_item(quantity_span="1.200")), RECEIVED)

    assert verdict.items[0].quantity is None
    assert verdict.refused["quantity_unit_unknown"] == 1


def test_a_line_read_twice_is_one_item() -> None:
    verdict = verify_rfq([PART], _answer(_item(), _item()), RECEIVED)

    assert len(verdict.items) == 1 and verdict.refused["line_repeated"] == 1


def test_the_request_values_are_found_anywhere_and_need_not_be_unique() -> None:
    twice = TextPart("body", "RFQ QRL-RFQ-2610-02\n\nRFQ QRL-RFQ-2610-02: 1) wire, USD", None, SHA)
    answer = _answer(
        _item(
            part="body",
            line_span="1) wire",
            description_span="wire",
            quantity_span=None,
            required_date_span=None,
        ),
        rfq_no_span="QRL-RFQ-2610-02",
        quote_due_span=None,
    )

    verdict = verify_rfq([twice], answer, RECEIVED)

    assert verdict.rfq_no is not None and verdict.rfq_no.value == "QRL-RFQ-2610-02"


def test_a_value_in_a_sheet_is_anchored_at_its_cell_and_never_across_cells() -> None:
    text = "Part | Description | Qty\nNRV-77-0031 | HOOK-UP WIRE AWG24 | 2500 | m"
    cells = (
        (0, 4, "RFQ!A1"),
        (7, 18, "RFQ!B1"),
        (21, 24, "RFQ!C1"),
        (25, 36, "RFQ!A2"),
        (39, 57, "RFQ!B2"),
        (60, 64, "RFQ!C2"),
        (67, 68, "RFQ!D2"),
    )
    sheet = TextPart("A1!RFQ", text, "M39-A1", SHA, cells=cells)
    line = "NRV-77-0031 | HOOK-UP WIRE AWG24 | 2500 | m"
    answer = _answer(
        {
            "part": "A1!RFQ",
            "line_span": line,
            "description_span": "HOOK-UP WIRE AWG24",
            "customer_item_code_span": "NRV-77-0031",
            "quantity_span": "2500 | m",
            "uom_span": "m",
            "required_date_span": None,
            "target_price_span": None,
        },
        currency_span=None,
    )

    verdict = verify_rfq([sheet], answer, RECEIVED)

    (item,) = verdict.items
    assert item.description.anchor.cell_ref == "RFQ!B2"
    assert item.customer_item_code is not None
    assert item.customer_item_code.anchor.cell_ref == "RFQ!A2"
    # "2500 | m" straddles two cells: no value of one field does.
    assert item.quantity is None and verdict.refused["quantity_unparsed"] == 1


def test_a_value_on_a_pdf_page_names_the_page_and_its_words() -> None:
    page = TextPart("M38-A1#p1", "1. NRV-77-0012 CABLE 4C - 2,000 m", "M38-A1", SHA, page=1)
    answer = _answer(
        _item(
            part="M38-A1#p1",
            line_span="1. NRV-77-0012 CABLE 4C - 2,000 m",
            description_span="CABLE 4C",
            quantity_span="2,000 m",
            required_date_span=None,
        ),
    )

    (item,) = verify_rfq([page], answer, RECEIVED).items

    anchor = item.quantity.anchor if item.quantity else None
    assert anchor is not None and (anchor.page, anchor.quote, anchor.boxes) == (1, "2,000 m", ())


def test_an_answer_outside_the_schema_is_no_answer() -> None:
    with pytest.raises(ValidationError):
        ModelRfqReading.model_validate({"items": [], "unit_price": 0})
    with pytest.raises(ValidationError):
        ModelRfqReading.model_validate({"items": [_item(quantity=1200)]})


def test_a_long_part_is_split_into_pieces_of_whole_lines_with_their_offsets() -> None:
    text = "\n".join(f"line {n} of the request" for n in range(60))
    part = TextPart("body", text, None, SHA)

    pieces = part.pieces(10_000, len)

    assert [p.part_id for p in pieces] == ["body", "body~2", "body~3"]
    assert "\n".join(p.text for p in pieces) == text
    second = pieces[1]
    anchor = second.anchor(0, 4)
    assert anchor is not None and anchor.chars is not None
    assert text[anchor.chars.start : anchor.chars.end] == "line"
    assert anchor.chars.start == second.base > 0
