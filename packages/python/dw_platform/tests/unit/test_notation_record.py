"""A customer's notation record (Sales ticket 37): learned by code from a
person's confirmation, and read by `settle` only where the document itself
says nothing."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from dw_platform.domain.notation import (
    KIND_VALUES,
    UNSTATED,
    Learned,
    Notation,
    day_and_month,
    learned,
    notation_of,
    read_currency,
    read_number,
    record_of,
    settle,
)

pytestmark = pytest.mark.unit

COMMA = record_of([("decimal_mark", ",")])
POINT = record_of([("decimal_mark", ".")])


def _number(text: str) -> Callable[[Notation], Decimal | None]:
    return lambda notation: read_number(text, notation)


# ------------------------------------------------------------- settle --


def test_a_record_settles_what_the_document_leaves_open() -> None:
    read = settle(_number("1.500"), notation_of("SL 1.500 m"), COMMA)
    assert read.value == Decimal(1500)
    assert read.by_record and not read.contradicts_record


def test_without_a_record_the_value_is_left_for_a_person() -> None:
    read = settle(_number("1.500"), notation_of("SL 1.500 m"))
    assert read.value is None and not read.by_record and not read.contradicts_record


def test_a_document_that_agrees_settles_by_itself() -> None:
    document = notation_of("1.500 m; 2.250,50 USD")
    read = settle(_number("1.500"), document, COMMA)
    assert read.value == Decimal(1500) and not read.by_record


def test_a_document_that_contradicts_the_record_goes_to_a_person() -> None:
    # "2,250.50" settles the decimal point; the record says comma.
    document = notation_of("1,500 m; 2,250.50 USD")
    read = settle(_number("1,500"), document, COMMA)
    assert read.value is None and read.contradicts_record


def test_the_weak_evidence_of_a_point_is_not_overruled_either() -> None:
    # "0.95" reads "2,000" as 2000 by itself; the record would read 2.
    document = notation_of("2,000 m at USD 0.95")
    read = settle(_number("2,000"), document, COMMA)
    assert read.value is None and read.contradicts_record


def test_a_value_that_reads_by_itself_is_never_touched() -> None:
    read = settle(_number("1200"), UNSTATED, COMMA)
    assert read.value == Decimal(1200) and not read.by_record


def test_a_record_settles_a_date_order() -> None:
    record = record_of([("date_order", "month_first")])
    read = settle(lambda n: day_and_month(5, 11, n), notation_of("ship 05/11/2026"), record)
    assert read.value == (11, 5) and read.by_record


def test_a_date_against_the_record_puts_every_date_to_a_person() -> None:
    record = record_of([("date_order", "month_first")])
    document = notation_of("ship 25/11/2026, then 05/12/2026")
    assert settle(lambda n: day_and_month(25, 11, n), document, record).contradicts_record
    assert settle(lambda n: day_and_month(5, 12, n), document, record).contradicts_record


def test_a_record_names_what_a_bare_symbol_means() -> None:
    record = record_of([("dollar_sign", "SGD")])
    read = settle(lambda n: read_currency("$", n), notation_of("$ 1,200.00"), record)
    assert read.value == "SGD" and read.by_record
    named = notation_of("prices in USD: $ 1,200.00")
    assert settle(lambda n: read_currency("$", n), named, record).contradicts_record


def test_a_record_of_one_symbol_says_nothing_of_another() -> None:
    record = record_of([("dollar_sign", "USD")])
    assert settle(lambda n: read_currency("¥", n), UNSTATED, record).value is None


def test_two_values_of_one_kind_settle_nothing() -> None:
    both = record_of([("decimal_mark", ","), ("decimal_mark", ".")])
    assert settle(_number("1.500"), UNSTATED, both).value is None


def test_a_record_refuses_a_value_its_kind_does_not_hold() -> None:
    with pytest.raises(ValueError, match="dollar_sign"):
        record_of([("dollar_sign", "JPY")])


# ------------------------------------------------------------ learned --


def test_a_grouping_confirmed_teaches_the_decimal_mark() -> None:
    assert learned(_number("1.200"), Decimal(1200)) == Learned("decimal_mark", ",")
    assert learned(_number("1.200"), Decimal("1.2")) == Learned("decimal_mark", ".")
    assert learned(_number("1,200"), Decimal(1200)) == Learned("decimal_mark", ".")


def test_words_that_read_by_themselves_teach_nothing() -> None:
    assert learned(_number("1200"), Decimal(1200)) is None
    assert learned(_number("1.250,50"), Decimal("1250.50")) is None


def test_a_value_the_person_corrected_teaches_nothing() -> None:
    # Neither reading of "1.200" is 1500: Sales corrected the value itself.
    assert learned(_number("1.200"), Decimal(1500)) is None


def test_a_date_confirmed_teaches_the_order() -> None:
    def parse(n: Notation) -> tuple[int, int] | None:
        return day_and_month(5, 11, n)

    assert learned(parse, (5, 11)) == Learned("date_order", "day_first")
    assert learned(parse, (11, 5)) == Learned("date_order", "month_first")
    assert learned(lambda n: day_and_month(25, 11, n), (25, 11)) is None


def test_a_symbol_confirmed_teaches_its_currency() -> None:
    assert learned(lambda n: read_currency("$", n), "HKD") == Learned("dollar_sign", "HKD")
    assert learned(lambda n: read_currency("¥", n), "CNY") == Learned("yen_sign", "CNY")
    assert learned(lambda n: read_currency("USD", n), "USD") is None


def test_what_is_learned_is_what_a_record_reads_back() -> None:
    lesson = learned(_number("1.200"), Decimal(1200))
    assert lesson is not None
    assert settle(_number("1.500"), UNSTATED, lesson.notation).value == Decimal(1500)


def test_every_kind_value_is_a_record() -> None:
    for kind, values in KIND_VALUES.items():
        for value in values:
            assert record_of([(kind, value)]) != UNSTATED
    assert POINT.decimal_mark == "."


def test_words_the_notation_left_open_are_told_from_words_that_are_no_value() -> None:
    assert settle(_number("1.500"), UNSTATED).unsettled
    assert not settle(_number("abc"), UNSTATED).unsettled
    assert not settle(_number("1500"), UNSTATED).unsettled
    contradicted = settle(_number("1,500"), notation_of("2,250.50"), COMMA)
    assert contradicted.unsettled and contradicted.contradicts_record
