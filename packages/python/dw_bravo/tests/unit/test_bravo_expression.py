"""Bravo's expression language: what it evaluates, and what it refuses to guess."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

import pytest

from dw_bravo.expression import (
    UNKNOWN,
    RuleRefusedError,
    UndecidableError,
    UnsupportedSyntaxError,
    condition,
    evaluate,
    round_decimal,
)

pytestmark = pytest.mark.unit


class FakeScope:
    """A row and its document, as plain dicts."""

    def __init__(
        self,
        row: dict[str, object],
        parent: dict[str, object] | None = None,
        tables: dict[str, list[dict[str, object]]] | None = None,
        trigger: str | None = None,
    ) -> None:
        self.row = {k.lower(): v for k, v in row.items()}
        self.parent = parent or {}
        self.tables = tables or {}
        self.trigger = trigger

    def column(self, name: str) -> object:
        if name.lower() not in self.row:
            raise UndecidableError(f"{name} is not in hand")
        return self.row[name.lower()]

    def parent_column(self, name: str) -> object:
        return self.parent[name]

    def table_rows(self, table: str) -> Sequence[FakeScope]:
        return [FakeScope(r, self.parent, self.tables) for r in self.tables[table]]

    def updated_column(self) -> str | None:
        return self.trigger

    def session(self, function: str, argument: object) -> object:
        known: dict[tuple[str, object], object] = {
            ("USER", "Id"): Decimal(7),
            ("GETDATE", None): datetime(2026, 1, 10),
        }
        return known.get((function, argument), UNKNOWN)


def ev(text: str, **row: object) -> object:
    return evaluate(text, FakeScope(row))


def test_arithmetic_precedence_and_decimal_exactness() -> None:
    assert ev("1 + 2 * 3") == Decimal(7)
    assert ev("Q9 % (Box * Len)", Q9=Decimal(12200), Box=Decimal(1), Len=Decimal(6100)) == 0
    assert ev("12345 / 26194") == Decimal(12345) / Decimal(26194)


def test_null_propagates_through_arithmetic_and_comparison() -> None:
    assert ev("A * 2", A=None) is None
    assert ev("A = 1", A=None) is None
    assert ev("ISNULL(A, 0) = 0", A=None) is True


def test_empty_is_null_blank_zero_or_false() -> None:
    for value in (None, "", Decimal(0), False):
        assert ev("EMPTY(A)", A=value) is True
    for present in ("x", Decimal(1), True, datetime(2026, 1, 1)):
        assert ev("Empty(A)", A=present) is False


def test_iif_evaluates_only_the_branch_taken() -> None:
    # The untaken branch reads a column not in hand and is never touched.
    assert ev("IIF(A IS NULL, True, Missing > 1)", A=None) is True


def test_in_like_and_is_null() -> None:
    assert ev("T IN ('Mass','Sample')", T="Mass") is True
    assert ev("T NOT IN ('Mass')", T="Sample") is True
    assert ev("N NOT LIKE '%check con%'", N="please check con lan") is False
    assert ev("A IS NOT NULL", A="x") is True


def test_parent_child_and_aggregates() -> None:
    rows = [{"Q": Decimal(2), "G": "A", "Id": 1}, {"Q": Decimal(3), "G": "B", "Id": 2}]
    scope = FakeScope({"G": "A"}, parent={"Type": "Mass"}, tables={"Detail": rows})
    assert evaluate("Parent.Type", scope) == "Mass"
    assert evaluate("SUM(Detail.Q)", scope) == Decimal(5)
    assert evaluate("SUM(Child(Detail).Q)", scope) == Decimal(5)
    assert evaluate("SUMIF(Detail.Q, G='{=G}')", scope) == Decimal(2)
    assert evaluate("VLOOKUP(Child(Detail), Id, Q=MAX(Q))", scope) == 2
    assert evaluate("Exists(Detail)", scope) is True


def test_template_substitution_reads_the_current_row() -> None:
    scope = FakeScope({"G": "A", "CreatedBy": Decimal(7)})
    assert evaluate("'{=ISNULL(G,'')}' = G", scope) is True
    assert evaluate("{=USER('Id')} = CreatedBy", scope) is True


def test_dateadd_by_day_only() -> None:
    assert ev("DateAdd(day, 5, D)", D=datetime(2026, 1, 1)) == datetime(2026, 1, 6)
    with pytest.raises(UnsupportedSyntaxError):
        ev("DateAdd(month, 1, D)", D=datetime(2026, 1, 1))


def test_unknown_syntax_and_functions_refuse() -> None:
    with pytest.raises(UnsupportedSyntaxError):
        ev("A ? B", A=1, B=2)
    with pytest.raises(UnsupportedSyntaxError):
        ev("SOUNDEX(A)", A="x")
    with pytest.raises(UnsupportedSyntaxError):
        ev("EMPTY(A, 0)", A=None)


def test_charindex_refuses_because_its_base_is_unmeasured() -> None:
    with pytest.raises(RuleRefusedError, match="CHARINDEX"):
        ev("CHARINDEX(',7,', L) >= 0", L=",7,")


def test_a_value_not_in_hand_refuses_and_is_never_null() -> None:
    with pytest.raises(UndecidableError):
        ev("EMPTY(A)", A=UNKNOWN)
    with pytest.raises(UndecidableError):
        ev("Missing = 1")


def test_case_only_difference_refuses() -> None:
    assert ev("T = 'Mass'", T="Mass") is True
    with pytest.raises(RuleRefusedError, match="case"):
        ev("T = 'mass'", T="Mass")


def test_rounding_refuses_only_on_the_half() -> None:
    assert round_decimal(Decimal("5749.738"), Decimal(2), "x") == Decimal("5749.74")
    assert round_decimal(Decimal("0.471291"), Decimal(5), "x") == Decimal("0.47129")
    with pytest.raises(RuleRefusedError, match="half"):
        round_decimal(Decimal("2.5"), Decimal(0), "x")


def test_a_null_condition_does_not_hold() -> None:
    assert condition("A = 1", FakeScope({"A": None})) is False
    assert condition(None, FakeScope({})) is True


def test_and_false_is_folded_so_the_disabled_part_is_never_read() -> None:
    # `EMPTY(x, 0)` is unknown syntax; behind `AND False` it is never evaluated.
    assert condition("!Empty(M, 0) AND False", FakeScope({})) is False


def test_mismatched_types_refuse() -> None:
    with pytest.raises(RuleRefusedError):
        ev("G = 0", G="A")
    with pytest.raises(RuleRefusedError):
        ev("1 / 0")
