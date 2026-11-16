"""How a document writes its numbers, dates and money: one answer for every context.

Hardcode audit 2026-11-13, findings 8, 9 and 20. Sales and Purchasing both read
values a model located in a customer's or a supplier's words, and each had its
own parser: "1.250" was 1250 in two of them and refused in a third, a date was
always day first ("05/11/2026" became 5 November for a writer who meant 11
May, and "11/15/2026" was silently swapped), and "$" was always USD while
SGD, HKD and others exist. One question, one owner: both contexts read through
this module (docs/adr/0013: what a second context shares moves to the
platform), and a context keeps only a stricter rule of its own on top (which
currencies it prices in, which units it takes).

**A document fixes its own notation** (`notation_of`), from the values in it
that can only be read one way; no tenant or customer setting guesses it:

- *Decimal mark.* A number with both separators shows both (``1.250,50``,
  ``1,250.00``); a run of groups shows the grouping one (``1.250.000``); a
  comma before other than three digits is a decimal comma (``12,5``,
  ``0,042``). A decimal point (``0.95``, ``0.0420``) counts for less: it
  settles a comma as thousands (``2,000 m`` beside ``USD 0.95``), never a dot
  as a decimal, because technical sizes and prices are written ``0.75`` in
  every locale, beside quantities grouped ``6.100`` by a writer whose decimal
  mark is the comma (the Vietnamese PO in `evals/fixtures/cases/sales_po_body.json`
  wrote exactly that).
- *Date order.* A numeric date whose first number is over 12 is day first
  (``25/11/2026``); one whose second number is over 12 is month first
  (``11/15/2026``). Dates are counted when they carry a year, or are written
  with a slash: ``1.5`` and ``10-12`` are a size and a range far more often
  than they are a date.
- *Currency.* The ISO codes and unambiguous names the document writes
  (``USD``, ``US$``, ``円``), for a bare symbol to be read by.

Evidence pointing both ways fixes nothing (for dates it is a conflict, and
every numeric date of that document goes to a person).

**A customer's record** (Sales ticket 37) is what that customer's earlier
documents settled, learned by code from a person's confirmation of a value
the document left ambiguous (`learned`: the one notation under which the
words read as the value confirmed), one entry per kind (`NotationKind`) and
held as a `Notation` of its own (`record_of`). `settle` reads a value by the
document's own evidence together with the record, and says which settled it:

- the document says nothing on that kind: the record settles it
  (``by_record``);
- the document agrees with the record: the document settles it, as before;
- the document says otherwise: the two together fix nothing, the value is
  not read, and a person reads it (``contradicts_record``).

So the record never changes a value the document reads by itself: it only
settles one the document left open, and a value the document reads one way
(even by the weak evidence of a decimal point) that the record would read
another is a contradiction, not read.

**Reading a value** (`read_number`, `day_and_month`, `read_currency`) never
guesses: "1.250" or "1,250" (one separator, exactly three digits after, a
first group of one to three digits not starting with 0) is ambiguous, and is
read only where the document fixed its decimal mark; "05/11/2026" is read only
where the document fixed its date order, and a date that contradicts it is not
read; a bare "$" or "¥" is a currency only where the document names exactly
one ISO code it can stand for. Anything else is None: the value is left for a
person, never guessed.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Final, Literal

DecimalMark = Literal[".", ","]
DateOrder = Literal["day_first", "month_first"]


@dataclass(frozen=True, slots=True)
class Notation:
    """What one document's own unambiguous values say about how it writes
    the ambiguous ones. Sets of evidence, so two documents read together (a
    value found in both) combine with ``|``."""

    decimal_marks: frozenset[DecimalMark] = frozenset()
    date_orders: frozenset[DateOrder] = frozenset()
    currencies: frozenset[str] = frozenset()
    # A decimal point written where it can only be one (``0.95``): weaker
    # evidence than `decimal_marks` (module docstring).
    decimal_points: bool = False

    def __or__(self, other: Notation) -> Notation:
        return Notation(
            self.decimal_marks | other.decimal_marks,
            self.date_orders | other.date_orders,
            self.currencies | other.currencies,
            self.decimal_points or other.decimal_points,
        )

    @property
    def decimal_mark(self) -> DecimalMark | None:
        """The decimal mark, when the document shows exactly one."""
        return next(iter(self.decimal_marks)) if len(self.decimal_marks) == 1 else None

    @property
    def date_order(self) -> DateOrder | None:
        """The date order, when the document shows exactly one."""
        return next(iter(self.date_orders)) if len(self.date_orders) == 1 else None

    @property
    def dates_conflict(self) -> bool:
        """The document's dates are written both ways: none of them is read."""
        return len(self.date_orders) > 1


# A document nothing is known of: only what reads one way by itself is read.
UNSTATED: Final = Notation()


# ------------------------------------------------------------- numbers --

# Spaces a writer groups thousands with: plain, no-break, thin, narrow no-break.
_SPACES: Final = " \u00a0\u2009\u202f"
_SPACE_GROUPED: Final = re.compile(rf"\d{{1,3}}(?:[{_SPACES}]\d{{3}})+(?:[.,]\d+)?")
_DIGITS_AND_MARKS: Final = re.compile(r"\d+(?:[.,]\d+)*")


def _grouped(whole: str, mark: str) -> bool:
    """Whether ``whole`` is digits grouped in threes by ``mark``: ``1.250.000``."""
    return re.fullmatch(rf"[1-9]\d{{0,2}}(?:{re.escape(mark)}\d{{3}})+", whole) is not None


def _ambiguous(whole: str, fraction: str) -> bool:
    """One separator with exactly three digits after it and a first group
    that could lead a grouping: ``1.250``, ``12,500``; not ``0.042``."""
    return len(fraction) == 3 and 1 <= len(whole) <= 3 and whole[0] != "0"


def _decimal(text: str) -> Decimal | None:
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def read_number(text: str, notation: Notation = UNSTATED) -> Decimal | None:
    """A number as people write it, or None when it is no number or when its
    grouping is ambiguous and ``notation`` does not settle it (module
    docstring). ``1200``, ``1 200``, ``1.250.000``, ``1.250,50``,
    ``1,250.00``, ``12,5`` and ``0.42`` read by themselves; a leading ``-`` is
    kept (a caller that wants a positive value says so)."""
    value = text.strip()
    sign = ""
    if value.startswith("-"):
        sign, value = "-", value[1:]
    if _SPACE_GROUPED.fullmatch(value):
        value = "".join(c for c in value if c not in _SPACES)
    if not _DIGITS_AND_MARKS.fullmatch(value):
        return None
    marks = {c for c in value if c in ".,"}
    if not marks:
        return _decimal(sign + value)
    if len(marks) == 2:
        decimal = value[max(value.rfind("."), value.rfind(","))]
        group = "," if decimal == "." else "."
        whole, fraction = value.rsplit(decimal, 1)
        if decimal in whole or not _grouped(whole, group):
            return None
        return _decimal(f"{sign}{whole.replace(group, '')}.{fraction}")
    mark = marks.pop()
    pieces = value.split(mark)
    if len(pieces) > 2:
        return _decimal(sign + value.replace(mark, "")) if _grouped(value, mark) else None
    whole, fraction = pieces
    if _ambiguous(whole, fraction):
        settled = notation.decimal_mark
        if settled is None and mark == "," and notation.decimal_points:
            # Only with nothing stronger said either way (module docstring).
            settled = None if notation.decimal_marks else "."
        if settled is None:
            return None
        return _decimal(sign + (f"{whole}.{fraction}" if settled == mark else whole + fraction))
    return _decimal(f"{sign}{whole}.{fraction}")


def is_ambiguous_number(text: str) -> bool:
    """Whether ``text`` is a number only a document's decimal mark can read
    (``1.250``): what a caller tells a person instead of "not a number"."""
    settled = Notation(decimal_marks=frozenset({"."}))
    return read_number(text) is None and read_number(text, settled) is not None


def _mark_shown(token: str) -> DecimalMark | None:
    """The decimal mark a number token shows by itself (module docstring)."""
    marks = {c for c in token if c in ".,"}
    if len(marks) == 2:
        if read_number(token) is None:
            return None
        return "." if token.rfind(".") > token.rfind(",") else ","
    mark = marks.pop()
    pieces = token.split(mark)
    if len(pieces) > 2:
        if not _grouped(token, mark):
            return None
        return "," if mark == "." else "."
    whole, fraction = pieces
    if mark == "," and not _ambiguous(whole, fraction):
        return ","
    return None


def _point_shown(token: str) -> bool:
    """A lone decimal point that can only be one: ``0.95``, ``0.0420``."""
    pieces = token.split(".")
    return "," not in token and len(pieces) == 2 and not _ambiguous(*pieces)


# A number with a separator, standing alone: not inside a code (``A1.250``),
# a date (``1.5/2``), a range (``1,5-2,5``) or a time or ratio (``1.5:2``),
# which would show nothing. After a label's colon it stands alone (``合計:1,635.00``).
_NUMBER_TOKEN: Final = re.compile(r"(?<![\w.,/\-])\d+(?:[.,]\d+)+(?![/:\-]\d)")


# --------------------------------------------------------------- dates --

# A numeric date with a year, separated one way: `25/11/2026`, `11.15.26`.
_DATED: Final = re.compile(
    r"(?<![\w./\-])(\d{1,2})([/.\-])(\d{1,2})\2(\d{4}|\d{2})(?![\d]|[./\-]\d)"
)
# A numeric date without a year, only with a slash: `25/11`.
_SLASHED: Final = re.compile(r"(?<![\w./\-])(\d{1,2})/(\d{1,2})(?![\d]|[./\-]\d)")


def _order_shown(first: int, second: int) -> DateOrder | None:
    if 13 <= first <= 31 and 1 <= second <= 12:
        return "day_first"
    if 13 <= second <= 31 and 1 <= first <= 12:
        return "month_first"
    return None


def day_and_month(first: int, second: int, notation: Notation = UNSTATED) -> tuple[int, int] | None:
    """The day and the month of a numeric date written ``first/second``, or
    None when it is not settled: a number over 12 says which is the day, and
    must not contradict the document; two numbers both at most 12 (and not
    equal) take the document's order, and are not read without one; a
    document whose dates conflict has none read."""
    if notation.dates_conflict:
        return None
    if first == second:
        return first, second
    shown = _order_shown(first, second)
    if shown is not None and notation.date_order not in (None, shown):
        return None
    order = shown or notation.date_order
    if order is None:
        return None
    return (first, second) if order == "day_first" else (second, first)


# ------------------------------------------------------------ currency --

# The one table of currency names (finding 20). An ISO code, or a name or a
# symbol that stands for exactly one currency.
_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "USD": "USD",
        "US$": "USD",
        "US DOLLAR": "USD",
        "US DOLLARS": "USD",
        "ĐÔ LA MỸ": "USD",
        "VND": "VND",
        "VNĐ": "VND",
        "ĐỒNG": "VND",
        "Đ": "VND",
        "₫": "VND",
        "JPY": "JPY",
        "YEN": "JPY",
        "円": "JPY",
        "日本円": "JPY",
        "EUR": "EUR",
        "€": "EUR",
        "SGD": "SGD",
        "S$": "SGD",
        "HKD": "HKD",
        "HK$": "HKD",
        "CNY": "CNY",
        "RMB": "CNY",
        "THB": "THB",
        "AUD": "AUD",
        "CAD": "CAD",
        "TWD": "TWD",
        "NT$": "TWD",
        "KRW": "KRW",
        "GBP": "GBP",
    }
)
# A symbol several currencies write: none of them until the document names one.
_SYMBOLS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "$": frozenset({"USD", "SGD", "HKD", "AUD", "CAD", "TWD"}),
        "¥": frozenset({"JPY", "CNY"}),
    }
)


def _key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).upper().split()).strip(" .:")


def read_currency(text: str, notation: Notation = UNSTATED) -> str | None:
    """The ISO code ``text`` names: a code or an unambiguous name or symbol by
    itself; a bare ``$`` or ``¥`` only when the document names exactly one ISO
    code it can stand for; else None."""
    key = _key(text)
    if key in _NAMES:
        return _NAMES[key]
    named = _SYMBOLS.get(key, frozenset()) & notation.currencies
    return next(iter(named)) if len(named) == 1 else None


def _narrow_letter(char: str) -> bool:
    return char.isalnum() and unicodedata.east_asian_width(char) not in ("W", "F")


def _named(folded: str, name: str) -> bool:
    """Whether ``name`` stands in ``folded`` as a word of its own: an edge
    that is a letter is not joined to another (``USD`` is not in ``USDT``)."""
    start = folded.find(name)
    while start >= 0:
        end = start + len(name)
        left = _narrow_letter(name[0]) and start > 0 and folded[start - 1].isalpha()
        right = _narrow_letter(name[-1]) and end < len(folded) and folded[end].isalpha()
        if not left and not right:
            return True
        start = folded.find(name, start + 1)
    return False


# ------------------------------------------------------------ document --


def notation_of(text: str) -> Notation:
    """What ``text``, one document read whole, fixes about its notation
    (module docstring)."""
    normal = unicodedata.normalize("NFKC", text)
    marks: set[DecimalMark] = set()
    points = False
    for token in _NUMBER_TOKEN.finditer(normal):
        mark = _mark_shown(token.group(0))
        if mark is not None:
            marks.add(mark)
        points = points or _point_shown(token.group(0))
    orders: set[DateOrder] = set()
    for match in _DATED.finditer(normal):
        order = _order_shown(int(match.group(1)), int(match.group(3)))
        if order is not None:
            orders.add(order)
    for match in _SLASHED.finditer(normal):
        order = _order_shown(int(match.group(1)), int(match.group(2)))
        if order is not None:
            orders.add(order)
    folded = normal.upper()
    currencies = frozenset(code for name, code in _NAMES.items() if _named(folded, name))
    return Notation(frozenset(marks), frozenset(orders), currencies, points)


# ---------------------------------------------------- a customer's record --

NotationKind = Literal["decimal_mark", "date_order", "dollar_sign", "yen_sign"]

# What each kind of a customer's record may hold: the decimal mark, the date
# order, and the ISO code a bare ``$`` or ``¥`` stands for (`_SYMBOLS`).
KIND_VALUES: Final[Mapping[NotationKind, frozenset[str]]] = MappingProxyType(
    {
        "decimal_mark": frozenset({".", ","}),
        "date_order": frozenset({"day_first", "month_first"}),
        "dollar_sign": _SYMBOLS["$"],
        "yen_sign": _SYMBOLS["¥"],
    }
)


def record_of(entries: Iterable[tuple[NotationKind, str]]) -> Notation:
    """A customer's record, one ``(kind, value)`` per kind, as the evidence
    it stands for: the decimal mark and date order its documents use, and
    the ISO code its bare symbols mean (named, as a document naming ``USD``
    settles ``$``). A value no kind holds is refused (ValueError); two values
    of one kind fix nothing, as two ways in one document do."""
    marks: set[DecimalMark] = set()
    orders: set[DateOrder] = set()
    currencies: set[str] = set()
    for kind, value in entries:
        if value not in KIND_VALUES[kind]:
            raise ValueError(f"{kind} holds no {value!r}")
        if kind == "decimal_mark":
            marks.add("." if value == "." else ",")
        elif kind == "date_order":
            orders.add("day_first" if value == "day_first" else "month_first")
        else:
            currencies.add(value)
    return Notation(frozenset(marks), frozenset(orders), frozenset(currencies))


@dataclass(frozen=True, slots=True)
class Settled[T]:
    """A value read by a document's evidence and its writer's record (module
    docstring): ``by_record`` when only the record settles it;
    ``contradicts_record`` when the document reads it one way and the record
    another, so it is not read and a person reads it."""

    value: T | None
    by_record: bool = False
    contradicts_record: bool = False
    # Not read, though some notation reads the words: a value the notation
    # left open (or the record contradicts), not words that are no value.
    unsettled: bool = False


def settle[T](
    parse: Callable[[Notation], T | None], document: Notation, record: Notation = UNSTATED
) -> Settled[T]:
    """``parse`` (a reader's own parser of one span, given a notation) read
    by ``document``'s evidence and the writer's ``record``: the one answer
    every reader of a customer's words uses (module docstring)."""
    own = parse(document)
    if own is None:
        value = parse(document | record)
        if value is not None:
            return Settled(value, by_record=True)
        return Settled(None, unsettled=any(parse(c.notation) is not None for c in _CANDIDATES))
    if parse(document | record) == own:
        return Settled(own)
    return Settled(None, contradicts_record=True, unsettled=True)


@dataclass(frozen=True, slots=True)
class Learned:
    """One kind of a writer's notation, as a person's confirmation settled it."""

    kind: NotationKind
    value: str

    @property
    def notation(self) -> Notation:
        return record_of([(self.kind, self.value)])


_CANDIDATES: Final = tuple(
    Learned(kind, value) for kind, values in KIND_VALUES.items() for value in sorted(values)
)


def learned[T](parse: Callable[[Notation], T | None], confirmed: T) -> Learned | None:
    """What a person's confirmation that the words ``parse`` reads stand for
    ``confirmed`` settles about how their writer writes: the one kind and
    value under which they read as ``confirmed``. None where the words read
    by themselves (they settle nothing), where no notation reads them as the
    value confirmed (the person corrected the value, not its reading), or
    where more than one does. Code compares; nothing is guessed."""
    if parse(UNSTATED) is not None:
        return None
    hits = [c for c in _CANDIDATES if parse(c.notation) == confirmed]
    return hits[0] if len(hits) == 1 else None
