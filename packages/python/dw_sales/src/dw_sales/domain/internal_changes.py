"""Proterial's own change of a confirmed order, read from the mail of PC's
that Sales pastes (ticket 10, the BA's 6.1B; "Internal change" in
CONTEXT.md).

After the confirmation, PC may move the dates of many lines at once, split
lines over several dates, or cut lines, for overcapacity, NG or short stock.
Sales pastes PC's mail into "Thay đổi nội bộ"; a model copies, per line, the
words naming it and, per delivery, the words of its quantity and of its date
(`ModelInternalChange`). It is read the way item 7 reads PC's dates
(`application.pc_dates`), and every value is code's:

- **The words are the paste's**: each span is in the pasted text, whole
  (never inside a longer number, date or code). A span that is not, and the
  change it carries, is dropped and counted.
- **The line is code's**: from a customer item code or PRV code of the order
  in the line's words, else the one whole number in them
  (`change_requests.named_line`). Words naming no line of the order are
  refused and shown as such, never matched to the nearest line. The model is
  shown no line of the order, so it cannot pick one either.
- **Each value is parsed** through the paste's own notation
  (`change_requests.parse_asked`, `rfq_reading.written_date`): a date or a
  quantity the paste leaves open (``03/04``, ``1.200`` with nothing beside
  them to settle it), a quantity in another unit than the line's, or a
  delivery with no quantity on a line split in several, makes the line a
  person's to fill. The customer's notation record is not read: PC is not
  the customer, and a customer's US dates would misread PC's.
- Several mentions of one line (a split pasted as one row per delivery)
  are its deliveries, in the order the model gives them.

Nothing is stored: what is read fills the form, and the person applies the
lines (`OrderCase.internal_change`), the one door that changes the order.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from dw_platform.domain.notation import Notation, notation_of
from dw_sales.domain.change_requests import named_line, parse_asked, same_unit
from dw_sales.domain.orders import OrderCase, OrderLine
from dw_sales.domain.spans import FoldedText

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The most lines one model answer holds (about 40 tokens each), and the most
# deliveries of one line in it.
MAX_MODEL_LINES: Final = 60
MAX_MODEL_DELIVERIES: Final = 20
_Span = Annotated[str, Field(min_length=1, max_length=200)]

# Why a line read is not ready to apply as it stands: words naming no line of
# the order (refused); a value a person must give; more than the order's
# quantity (Proterial cuts, never raises); new quantities for schedules the
# PO prints (PC moves their dates only).
ReadProblem = Literal["no_such_line", "unread", "quantity_raised", "printed_schedules"]


class ModelInternalDelivery(BaseModel):
    """One delivery as the model copies it: the words of its quantity (none
    for a line delivered at once, whose quantity is the line's) and of its
    date."""

    model_config = _FROZEN

    quantity_span: _Span | None = None
    date_span: _Span


class ModelInternalLine(BaseModel):
    """One line PC changes: the words naming it first, so the model finds
    the line before it reads its deliveries."""

    model_config = _FROZEN

    line_span: _Span
    deliveries: tuple[ModelInternalDelivery, ...] = Field(
        min_length=1, max_length=MAX_MODEL_DELIVERIES
    )


class ModelInternalChange(BaseModel):
    """What one call returns: flat and closed, every key required."""

    model_config = _FROZEN

    lines: tuple[ModelInternalLine, ...] = Field(max_length=MAX_MODEL_LINES)


@dataclass(frozen=True, slots=True)
class ReadDelivery:
    """A delivery as code read it: a value None where the paste does not
    settle it; the words it rests on."""

    quantity: Decimal | None
    day: date | None
    quantity_words: str | None
    date_words: str


@dataclass(frozen=True, slots=True)
class ReadLine:
    """A line as code read it. ``line_no`` None: the words name no line of
    the order (``no_such_line``). ``quantity``: what the deliveries add up
    to, where every one was read."""

    line_no: int | None
    words: str
    deliveries: tuple[ReadDelivery, ...]
    problem: ReadProblem | None

    @property
    def quantity(self) -> Decimal | None:
        found = [d.quantity for d in self.deliveries]
        if not found or any(q is None for q in found):
            return None
        return sum((q for q in found if q is not None), Decimal(0))


@dataclass(frozen=True, slots=True)
class InternalReading:
    """The lines read, in the order's line order, the refused after them;
    and how many changes the model gave whose words are not in the paste."""

    lines: tuple[ReadLine, ...] = ()
    dropped: int = 0


def _written(folded: FoldedText, words: str) -> bool:
    return bool(folded.occurrences(words, bounded=True))


def read_internal(
    case: OrderCase, text: str, answer: ModelInternalChange, today: date
) -> InternalReading:
    """What code keeps of a model's reading of ``text``, the pasted mail
    NFKC-normalised (module docstring). Never raises on the model's answer."""
    folded = FoldedText(text)
    notation = notation_of(text)
    held = {line.line_no: line for line in case.lines}
    grouped: dict[int, tuple[str, list[ReadDelivery | None]]] = {}
    refused: list[ReadLine] = []
    dropped = 0
    for item in answer.lines:
        words = item.line_span.strip()
        if not _written(folded, words):
            dropped += 1
            continue
        line_no = named_line(case, words)
        if line_no is None or line_no not in held:
            refused.append(ReadLine(None, words, (), "no_such_line"))
            continue
        line = held[line_no]
        read = [
            _delivery(d, line, folded, notation, today, alone=len(item.deliveries) == 1)
            for d in item.deliveries
        ]
        first, earlier = grouped.get(line_no, (words, []))
        grouped[line_no] = (first, [*earlier, *read])
    lines = [_line(held[no], *grouped[no]) for no in sorted(grouped)]
    return InternalReading(tuple(lines + refused), dropped)


def _delivery(
    asked: ModelInternalDelivery,
    line: OrderLine,
    folded: FoldedText,
    notation: Notation,
    today: date,
    *,
    alone: bool,
) -> ReadDelivery | None:
    """One delivery, or None where its words are not the paste's: the line
    is then a person's to fill (`_line`)."""
    date_words = asked.date_span.strip()
    quantity_words = None if asked.quantity_span is None else asked.quantity_span.strip()
    if not _written(folded, date_words) or (
        quantity_words is not None and not _written(folded, quantity_words)
    ):
        return None
    when = parse_asked("requested_date", date_words, today, notation)
    day = None if when is None else date.fromisoformat(when[0])
    quantity: Decimal | None = line.effective.quantity if quantity_words is None and alone else None
    if quantity_words is not None:
        how_much = parse_asked("quantity", quantity_words, today, notation)
        if how_much is not None and (how_much[1] is None or same_unit(how_much[1], line)):
            quantity = Decimal(how_much[0])
    return ReadDelivery(quantity, day, quantity_words, date_words)


def _line(line: OrderLine, words: str, read: Sequence[ReadDelivery | None]) -> ReadLine:
    """The line with its deliveries, and what keeps it from being applied as
    read (`ReadProblem`), checked as `OrderCase.internal_change` will."""
    deliveries = tuple(d for d in read if d is not None)
    if len(deliveries) != len(read) or any(d.day is None or d.quantity is None for d in deliveries):
        return ReadLine(line.line_no, words, deliveries, "unread")
    found = ReadLine(line.line_no, words, deliveries, None)
    po = line.effective
    total = found.quantity
    assert total is not None  # every quantity read
    if total > po.quantity:
        return ReadLine(line.line_no, words, deliveries, "quantity_raised")
    quantities = tuple(d.quantity for d in deliveries)
    if po.prints_schedules and quantities != tuple(s.quantity for s in po.schedules):
        return ReadLine(line.line_no, words, deliveries, "printed_schedules")
    return found


__all__ = [
    "MAX_MODEL_DELIVERIES",
    "MAX_MODEL_LINES",
    "InternalReading",
    "ModelInternalChange",
    "ModelInternalDelivery",
    "ModelInternalLine",
    "ReadDelivery",
    "ReadLine",
    "ReadProblem",
    "read_internal",
]
