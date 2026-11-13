"""How a document writes numbers, dates and money: the one rule both contexts
read by (hardcode audit 2026-11-13, findings 8, 9 and 20)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from dw_platform.domain.notation import (
    UNSTATED,
    Notation,
    day_and_month,
    is_ambiguous_number,
    notation_of,
    read_currency,
    read_number,
)

pytestmark = pytest.mark.unit


# ------------------------------------------------------------- numbers --


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1200", Decimal(1200)),
        ("1 200", Decimal(1200)),
        ("1\u00a0200,5", Decimal("1200.5")),
        ("1.250.000", Decimal(1250000)),
        ("1,250,000", Decimal(1250000)),
        ("1.250,50", Decimal("1250.50")),
        ("1,250.00", Decimal("1250.00")),
        ("12,5", Decimal("12.5")),
        ("0.42", Decimal("0.42")),
        ("0,042", Decimal("0.042")),
        ("1250.000", Decimal("1250.000")),
        ("-1,5", Decimal("-1.5")),
        # One separator, three digits after: thousands or a decimal, unknown.
        ("1.250", None),
        ("1,250", None),
        ("12.500", None),
        # Malformed: no reading.
        ("1,2,3", None),
        ("1.2.3", None),
        ("1,234.567,89", None),
        ("0.250,5", None),
        ("abc", None),
        ("", None),
    ],
)
def test_a_number_reads_by_itself_only_when_it_reads_one_way(
    text: str, value: Decimal | None
) -> None:
    assert read_number(text) == value


def test_an_ambiguous_grouping_reads_as_the_document_settles_it() -> None:
    comma = Notation(decimal_marks=frozenset({","}))
    dot = Notation(decimal_marks=frozenset({"."}))
    both = Notation(decimal_marks=frozenset({",", "."}))

    assert read_number("1.250", comma) == Decimal(1250)
    assert read_number("1,250", comma) == Decimal("1.250")
    assert read_number("1,250", dot) == Decimal(1250)
    assert read_number("1.250", dot) == Decimal("1.250")
    # A document that writes both ways settles nothing.
    assert read_number("1.250", both) is None
    assert is_ambiguous_number("1.250") and not is_ambiguous_number("1.250,5")


@pytest.mark.parametrize(
    ("document", "marks"),
    [
        ("Đơn giá 12,5 USD", {","}),
        ("Trọng lượng 0,042 kg/m", {","}),
        ("Tổng 1.250,50", {","}),
        ("Total 1,250.00", {"."}),
        ("合計\uff1a1,635.00 USD", {"."}),
        ("1.250.000 đồng", {","}),
        ("1,250,000 VND", {"."}),
        # A dot before one or two digits fixes nothing: technical sizes are
        # written so in every locale, beside quantities grouped "6.100" by a
        # writer whose decimal mark is the comma (the Vietnamese PO fixture).
        ("6.100 m, đơn giá 0.0420, cáp 0.75 mm2", set()),
        ("1.250 m", set()),
        # Inside a code, a date or a range, a number shows nothing.
        ("mã A1.250,5 · 15.11.2026 · 1,5-2,5 mm", set()),
        ("1.250,50 và 1,250.00", {",", "."}),
    ],
)
def test_a_document_fixes_its_decimal_mark_only_by_a_number_that_shows_it(
    document: str, marks: set[str]
) -> None:
    assert notation_of(document).decimal_marks == marks


def test_a_vietnamese_mail_with_a_comma_decimal_reads_its_thousands() -> None:
    mail = "Giao 1.250 m, đơn giá 12,5 USD/m"
    assert read_number("1.250", notation_of(mail)) == Decimal(1250)
    # The same quantity beside a technical size only: refused, for a person.
    assert read_number("1.250", notation_of("Giao 1.250 m cáp 0.75 mm2")) is None


# --------------------------------------------------------------- dates --


@pytest.mark.parametrize(
    ("document", "orders"),
    [
        ("giao ngày 25/11/2026", {"day_first"}),
        ("deliver 11/15/2026", {"month_first"}),
        ("05/11/2026 và 06/11/2026", set()),
        ("giao 25/11", {"day_first"}),
        ("25.11.2026", {"day_first"}),
        # Without a year, only a slash counts: a size and a range are not dates.
        ("cáp 25.5 kg, 13-15 ngày", set()),
        ("ISO 2026-11-15, R8.11.15", set()),
        ("25/11/2026 hoặc 11/15/2026", {"day_first", "month_first"}),
    ],
)
def test_a_document_fixes_its_date_order_only_by_a_date_that_shows_it(
    document: str, orders: set[str]
) -> None:
    assert notation_of(document).date_orders == orders


def test_a_numeric_date_is_never_swapped_silently() -> None:
    day_first = notation_of("ngày đặt 25/10/2026")
    month_first = notation_of("ordered 10/25/2026")
    conflict = day_first | month_first

    # A number over 12 says which is the day, whatever else.
    assert day_and_month(25, 11) == (25, 11)
    assert day_and_month(11, 15) == (15, 11)
    # Both at most 12: the document decides, and without one nothing is read.
    assert day_and_month(5, 11) is None
    assert day_and_month(5, 11, day_first) == (5, 11)
    assert day_and_month(5, 11, month_first) == (11, 5)
    # The same number twice is the same date either way.
    assert day_and_month(5, 5) == (5, 5)
    # A date that contradicts its document is not read; nor any in a document
    # whose dates contradict each other.
    assert day_and_month(11, 15, day_first) is None
    assert day_and_month(25, 11, month_first) is None
    assert day_and_month(25, 11, conflict) is None
    assert day_and_month(5, 11, conflict) is None


# ------------------------------------------------------------ currency --


@pytest.mark.parametrize(
    ("span", "document", "code"),
    [
        ("USD", "", "USD"),
        ("us$", "", "USD"),
        ("VNĐ", "", "VND"),
        ("đồng", "", "VND"),
        ("₫", "", "VND"),
        ("€", "", "EUR"),
        ("円", "", "JPY"),
        ("SGD", "", "SGD"),
        # A bare symbol is no currency by itself...
        ("$", "", None),
        ("¥", "", None),
        ("$", "Price 0.42 $/m", None),
        # ...unless the document names the one ISO code it stands for.
        ("$", "All prices in USD.", "USD"),
        ("$", "Giá tính bằng SGD", "SGD"),
        ("¥", "通貨\uff1aJPY", "JPY"),
        ("¥", "单价 CNY", "CNY"),
        ("¥", "日本円でお願いします", "JPY"),
        # Two it could stand for: unknown.
        ("$", "USD or SGD", None),
        # A code inside a longer word is not named.
        ("$", "USDT wallet", None),
        ("nonsense", "USD", None),
    ],
)
def test_a_currency_is_read_from_the_one_table(span: str, document: str, code: str | None) -> None:
    assert read_currency(span, notation_of(document)) == code


def test_documents_read_together_combine_their_evidence() -> None:
    mail, file = notation_of("prices in USD"), notation_of("Total 1,250.00")
    together = mail | file
    assert together.currencies == {"USD"} and together.decimal_mark == "."
    assert UNSTATED | UNSTATED == UNSTATED


def test_a_decimal_point_settles_a_comma_as_thousands_and_never_a_dot_as_a_decimal() -> None:
    """An English request writes "2,000 m" beside "USD 0.95": the comma is
    thousands. A Vietnamese one writes "6.100 m" beside "0.0420": the point
    says nothing about the dot that groups the quantity."""
    english = notation_of("2,000 m - target USD 0.95")
    vietnamese = notation_of("6.100 m, đơn giá 0.0420")

    assert english.decimal_points and english.decimal_mark is None
    assert read_number("2,000", english) == Decimal(2000)
    assert read_number("6.100", vietnamese) is None
    # Anything stronger said either way wins over a decimal point.
    assert read_number("1,250", notation_of("0.75 mm2, đơn giá 12,5")) == Decimal("1.250")
    assert read_number("1,250", notation_of("0.75 mm2, 1.250,5 và 1,250.5")) is None
