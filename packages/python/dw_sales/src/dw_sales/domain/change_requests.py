"""A change a customer asks for on an order, confirmed line by line (dw_sales
ADR 0010 decisions 2 and 4, ticket 27; "Change request" in CONTEXT.md).

A customer asks by mail to pull a delivery in or push it out, or to raise or
cut a quantity: in a sentence, or as a table in the mail's HTML body (Box
B03: PO, line, item, quantity, the date as held and the date asked). The
body changes no value a person has not confirmed (ADR 0005 as amended), so
what the mail asks is a `ChangeRequest` on the order case: per line, the
field, the value the case holds, the value asked and where the mail says it.

**How a line is read** (all of it code's, but the words a model copies):

- *A table* is split by its markup (`mail_parts.newest_tables`) and each
  cell found in the newest part's text, in order, so its anchor is the
  cell's characters. A row is this order's when one of its cells is the
  case's PO number; its line is the case line whose customer item code (or
  PRV code) is one of its cells, a line number among its cells telling apart
  lines that share a code. Which column holds the date asked is decided by
  the values, never by a header's words: the date columns are those whose
  every cell reads as a date (and not as a number); the column whose every
  cell is the date the case holds is the held one; the one other date column
  is the date asked. Two candidates, or none, and the table gives no date: a
  person reads it. A quantity is never taken from a table: an id, a line
  number and a price column read as numbers too, and no value tells the
  asked quantity apart from them (a model or a person gives it).
- *Free text* is read by a model where the tenant's step is on and measured
  (`ModelChanges`): for each change, the words naming the line, the field
  from a closed set and the words of the value asked. Code finds both spans,
  whole and once, in the newest part; takes the line from a customer item
  code of the case inside the line's words, or else from the one number in
  them; and parses the value: a date through the mail's own notation, a
  quantity with the unit it is written in.
- *A person* types a line (line, field, value) where nothing was read, the
  model being off or the mail too loose; it has no anchor and says so.

**What blocks a confirmation** (`Blocked`, stamped when read, shown with
the line): the case has no such line; the quantity is written in another
unit than the line's (``km`` against ``m``: never converted, ADR 0010 and
the ticket's acceptance 3); the line prints several delivery schedules, and
one value cannot say which. Such a line is rejected with a reason.

A value equal to what the case holds is no change and makes no line; two
values for one line and field from one mail contradict each other and make
none (each counted as unread, for a person). One request is open on a case
at a time; one made while another is open waits behind it (``queued``),
never merged into it, and opens when the one before is closed.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_kernel.errors import ConflictError, DomainError
from dw_platform.domain.mail_parts import MailTable
from dw_platform.domain.notation import Notation, notation_of
from dw_sales.domain.anchors import MessageText, TextRange
from dw_sales.domain.orders import Note, OrderCase, OrderLine
from dw_sales.domain.rfq_reading import parse_date, parse_number, parse_uom
from dw_sales.domain.spans import FoldedText, word_char

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# What a change line may change: the BA's step 6.1A (pull in, push out, raise
# or cut a quantity). A price, the place or the transport are not values of
# a line DW1 holds, and stay a person's (ticket 27, recorded in its Done).
ChangeField = Literal["quantity", "requested_date"]
ChangeLineState = Literal["open", "confirmed", "rejected"]
ChangeRequestState = Literal["open", "queued", "closed"]
ReadBy = Literal["table", "model", "person"]
Blocked = Literal["no_such_line", "unit_differs", "printed_schedules"]
# The most lines one request holds: a mail asking more is a revised PO.
MAX_LINES: Final = 50
# The most changes one model answer holds (about 60 tokens each).
MAX_MODEL_CHANGES: Final = 10
_Span = Annotated[str, Field(min_length=1, max_length=200)]


def _decimal_text(value: Decimal) -> str:
    """A quantity as one text per value: ``2000.0`` and ``2000`` are one."""
    return format(value.normalize(), "f")


def _value_text(field: ChangeField, text: str) -> str:
    """``text`` as ``field``'s value in its one form, or ValueError."""
    if field == "requested_date":
        return date.fromisoformat(text).isoformat()
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("a quantity is a number") from None
    if not value.is_finite() or value <= 0:
        raise ValueError("a quantity is a number above zero")
    return _decimal_text(value)


class ChangeLine(BaseModel):
    """One value the customer asks to change on one line of the order."""

    model_config = _FROZEN

    # Its place in the request, from 1: what a decision names.
    seq: int = Field(ge=1, le=MAX_LINES)
    # The line the mail names, as the case numbers its lines.
    line_no: int = Field(ge=1, le=99_999)
    field: ChangeField
    # What the case held when the mail was read, in the field's one form (an
    # ISO date, a number); None where the case has no such line, or the line
    # was printed with no date.
    held: str | None = Field(max_length=40)
    # The value asked, in the same form.
    asked: str = Field(max_length=40)
    # The words the mail writes it with, or what the person typed.
    written: str = Field(min_length=1, max_length=200)
    # The unit written beside an asked quantity (``km``); None: none written,
    # the line's own.
    unit: str | None = Field(default=None, min_length=1, max_length=16)
    # Where the words are in the request's text; None only for a person's.
    anchor: TextRange | None
    read_by: ReadBy
    blocked: Blocked | None = None
    state: ChangeLineState = "open"
    decided_by: uuid.UUID | None = None
    decided_at: AwareDatetime | None = None
    # Why it was rejected: the person's words, kept here and never audited.
    reason: Note | None = None

    @model_validator(mode="after")
    def _a_line_says_what_it_is(self) -> Self:
        if (self.read_by == "person") != (self.anchor is None):
            raise ValueError("a line read from the mail names where, and only a person's has none")
        if _value_text(self.field, self.asked) != self.asked:
            raise ValueError("the asked value is not in its field's form")
        if self.held is not None and _value_text(self.field, self.held) != self.held:
            raise ValueError("the held value is not in its field's form")
        if self.asked == self.held:
            raise ValueError("a change asks for another value than the one held")
        if self.unit is not None and self.field != "quantity":
            raise ValueError("only a quantity is written with a unit")
        if (self.blocked == "unit_differs") and self.unit is None:
            raise ValueError("a unit that differs is a unit written")
        if self.blocked == "no_such_line" and self.held is not None:
            raise ValueError("a line the case does not have holds nothing")
        decided = self.state != "open"
        if decided != (self.decided_by is not None) or decided != (self.decided_at is not None):
            raise ValueError("a decided line names who decided it and when, an open one neither")
        if (self.state == "rejected") != (self.reason is not None):
            raise ValueError("a rejected line says why, and only a rejected one")
        if self.state == "confirmed" and self.blocked is not None:
            raise ValueError("a blocked line is not confirmed")
        return self

    @property
    def key(self) -> tuple[int, ChangeField]:
        return (self.line_no, self.field)

    @property
    def value(self) -> date | Decimal:
        """The asked value, typed."""
        return (
            date.fromisoformat(self.asked)
            if self.field == "requested_date"
            else Decimal(self.asked)
        )


ChangeOutcome = Literal["read", "unavailable"]


class ChangeReading(BaseModel):
    """The model call that read the request's free text, stamped on it: the
    prompt, profile and route, the rules whose switch asked for it, and its
    outcome (``unavailable``: no usable answer, and the lines are code's and
    a person's)."""

    model_config = _FROZEN

    prompt: str = Field(pattern=r"^[a-z][a-z0-9_.]*@\d+\.\d+\.\d+$")
    model_profile: str = Field(min_length=1, max_length=64)
    route: str = Field(min_length=1, max_length=64)
    rules: str = Field(pattern=r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$")
    outcome: ChangeOutcome


class ChangeRequest(BaseModel):
    """What one mail asks to change on one order case (module docstring)."""

    model_config = _FROZEN

    request_id: uuid.UUID
    case_id: uuid.UUID
    # Its place among the case's requests, from 1: the order they open in.
    number: int = Field(ge=1, le=9_999)
    # The customer's reply it was read from (linked to the case by its thread).
    message_id: str = Field(pattern=r"^[!-~]{1,512}$")
    # The mail's newest part as it was read: what anchors index into.
    text: MessageText
    opened_by: uuid.UUID
    opened_at: AwareDatetime
    state: ChangeRequestState
    # Taken by every change, so a decision made on an older one is refused.
    version: int = Field(default=1, ge=1)
    lines: tuple[ChangeLine, ...] = Field(default=(), max_length=MAX_LINES)
    # Rows and spans naming this order that code could not turn into a line.
    unread: int = Field(default=0, ge=0, le=999)
    # The model call, where one was made.
    reading: ChangeReading | None = None

    @model_validator(mode="after")
    def _request_is_consistent(self) -> Self:
        if [line.seq for line in self.lines] != list(range(1, len(self.lines) + 1)):
            raise ValueError("a request numbers its lines from 1, in order")
        live = [line.key for line in self.lines if line.state != "rejected"]
        if len(live) != len(set(live)):
            raise ValueError("a request asks one value per line and field")
        size = len(self.text.text)
        if any(line.anchor is not None and line.anchor.end > size for line in self.lines):
            raise ValueError("an anchor points past the request's text")
        settled = bool(self.lines) and all(line.state != "open" for line in self.lines)
        if (self.state == "closed") != settled:
            raise ValueError("a request is closed exactly when every line of it is decided")
        return self

    def line(self, seq: int) -> ChangeLine:
        for line in self.lines:
            if line.seq == seq:
                return line
        raise ConflictError(
            "the change request has no such line",
            details={"request_id": str(self.request_id), "line": seq, "rule": "no_such_change"},
        )

    def with_line(self, line: ChangeLine) -> ChangeRequest:
        """One more line, numbered after the others; refused once closed."""
        if self.state == "closed":
            raise ConflictError(
                "a closed change request takes no more lines",
                details={"request_id": str(self.request_id), "rule": "change_request_closed"},
            )
        if any(x.key == line.key and x.state != "rejected" for x in self.lines):
            raise ConflictError(
                "the request already asks this value of this line",
                details={
                    "request_id": str(self.request_id),
                    "line": line.line_no,
                    "field": line.field,
                    "rule": "change_asked_twice",
                },
            )
        numbered = line.model_copy(update={"seq": len(self.lines) + 1})
        return self._with(lines=(*self.lines, ChangeLine.model_validate(dict(numbered))))

    def confirmed(self, seq: int, by: uuid.UUID, at: AwareDatetime) -> ChangeRequest:
        """The line confirmed (`OrderCase.take_change` applies it)."""
        line = self._decidable(seq)
        if line.blocked is not None:
            raise ConflictError(
                "this change cannot be confirmed as read",
                details={
                    "request_id": str(self.request_id),
                    "line": seq,
                    "rule": line.blocked,
                },
            )
        return self._decided(line, state="confirmed", decided_by=by, decided_at=at)

    def rejected(self, seq: int, reason: str, by: uuid.UUID, at: AwareDatetime) -> ChangeRequest:
        return self._decided(
            self._decidable(seq), state="rejected", decided_by=by, decided_at=at, reason=reason
        )

    def opened(self) -> ChangeRequest:
        """A queued request, its turn come."""
        if self.state != "queued":
            raise ConflictError(
                "only a queued change request is opened",
                details={"request_id": str(self.request_id), "state": self.state},
            )
        return self._with(state="open")

    def _decidable(self, seq: int) -> ChangeLine:
        details: dict[str, object] = {"request_id": str(self.request_id), "line": seq}
        if self.state != "open":
            # A queued request waits for the one before it (ADR 0010 decision 4).
            raise ConflictError(
                f"a {self.state} change request is not decided",
                details={**details, "state": self.state, "rule": f"change_request_{self.state}"},
            )
        line = self.line(seq)
        if line.state != "open":
            raise ConflictError(
                "this change is already decided", details={**details, "rule": "change_decided"}
            )
        return line

    def _decided(self, line: ChangeLine, **changes: object) -> ChangeRequest:
        decided = ChangeLine.model_validate({**dict(line), **changes})
        lines = tuple(decided if x.seq == line.seq else x for x in self.lines)
        state: ChangeRequestState = (
            "closed" if all(x.state != "open" for x in lines) else self.state
        )
        return self._with(lines=lines, state=state)

    def _with(self, **changes: object) -> ChangeRequest:
        return ChangeRequest.model_validate({**dict(self), **changes, "version": self.version + 1})


def first_state(others: Iterable[ChangeRequest]) -> ChangeRequestState:
    """A new request's state: open, unless one of the case is open or queued,
    when it waits behind them (ADR 0010 decision 4: never merged)."""
    return "queued" if any(r.state != "closed" for r in others) else "open"


def next_to_open(requests: Sequence[ChangeRequest]) -> ChangeRequest | None:
    """The queued request whose turn has come: the oldest, once none is open."""
    if any(r.state == "open" for r in requests):
        return None
    queued = [r for r in requests if r.state == "queued"]
    return min(queued, key=lambda r: r.number, default=None)


# ------------------------------------------------------------- reading --


def held_value(
    case: OrderCase, line_no: int, field: ChangeField
) -> tuple[str | None, Blocked | None]:
    """What the case holds for ``field`` of line ``line_no``, as entered, and
    what blocks a change of it: no such line, or schedules printed apart."""
    line = next((x for x in case.lines if x.line_no == line_no), None)
    if line is None:
        return None, "no_such_line"
    entered = line.effective
    blocked: Blocked | None = "printed_schedules" if entered.prints_schedules else None
    if field == "quantity":
        return _decimal_text(entered.quantity), blocked
    day = entered.requested_date
    return (None if day is None else day.isoformat()), blocked


@dataclass(frozen=True, slots=True)
class ReadChanges:
    """The lines code accepted from one source, and how many places naming
    this order it could not turn into one."""

    lines: tuple[ChangeLine, ...] = ()
    unread: int = 0


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _same(cell: str, value: str) -> bool:
    return _nfkc(cell).strip().casefold() == _nfkc(value).strip().casefold()


def _line(
    case: OrderCase,
    line_no: int,
    field: ChangeField,
    asked: str,
    written: str,
    anchor: TextRange | None,
    read_by: ReadBy,
    unit: str | None = None,
) -> ChangeLine | None:
    """The change line, or None when the value asked is the one held."""
    held, blocked = held_value(case, line_no, field)
    if asked == held:
        return None
    if blocked is None and unit is not None and not same_unit(unit, case.line(line_no)):
        blocked = "unit_differs"
    return ChangeLine(
        seq=1,
        line_no=line_no,
        field=field,
        held=held,
        asked=asked,
        written=written[:200],
        unit=unit,
        anchor=anchor,
        read_by=read_by,
        blocked=blocked,
    )


def same_unit(unit: str, line: OrderLine) -> bool:
    """Whether ``unit`` is the line's: the same word, or metres both."""
    uom = line.effective.uom
    return _same(unit, uom) or (parse_uom(unit) == "m" and parse_uom(uom) == "m")


# A quantity as written: a number, then the unit it is written in, if any.
_QUANTITY: Final = re.compile(r"(?P<number>\d[\d.,\s]*?)\s*(?P<unit>[^\W\d_][^\s\d]{0,15}?)?\.?")


def parse_asked(
    field: ChangeField, span: str, received_on: date, notation: Notation
) -> tuple[str, str | None] | None:
    """The value ``span`` writes for ``field``, in its one form, with the unit
    written beside a quantity; None when it does not read as one. A date is
    never a bare number (``24.4`` reads as a date in some notations), and a
    quantity is never zero."""
    text = _nfkc(span).strip()
    if field == "requested_date":
        if parse_number(text, notation) is not None:
            return None
        day = parse_date(text, received_on, notation)
        return None if day is None else (day.isoformat(), None)
    match = _QUANTITY.fullmatch(text)
    if match is None:
        return None
    number = parse_number(match.group("number"), notation)
    if number is None or number <= 0:
        return None
    return _decimal_text(number), match.group("unit")


def _keyed(lines: Iterable[ChangeLine]) -> ReadChanges:
    """One value per line and field: a key asked twice by one source is a
    contradiction a person settles, so it makes no line and counts unread."""
    listed = list(lines)
    counts = Counter(line.key for line in listed)
    kept = tuple(line for line in listed if counts[line.key] == 1)
    return ReadChanges(numbered(kept), len(listed) - len(kept))


def merged(first: ReadChanges, second: ReadChanges) -> ReadChanges:
    """The table's lines, then the model's: one asking what the table asks of
    the same line and field is the same line; one asking another value for it
    makes neither (a person reads both)."""
    table = {line.key: line for line in first.lines}
    clash = {
        line.key
        for line in second.lines
        if line.key in table and table[line.key].asked != line.asked
    }
    lines = [line for line in first.lines if line.key not in clash]
    lines += [line for line in second.lines if line.key not in table]
    return ReadChanges(numbered(lines), first.unread + second.unread + 2 * len(clash))


def numbered(lines: Iterable[ChangeLine]) -> tuple[ChangeLine, ...]:
    """``lines`` numbered from 1, in order."""
    return tuple(
        ChangeLine.model_validate({**dict(line), "seq": seq})
        for seq, line in enumerate(lines, start=1)
    )


# ------------------------------------------------------------ the table --


@dataclass(frozen=True, slots=True)
class _Cell:
    text: str
    at: tuple[int, int] | None


def _located(text: str, table: MailTable, start: int) -> list[list[_Cell]] | None:
    """``table``'s cells with where each is in ``text`` (from ``start``):
    every non-empty cell, in order, separated from the one before by nothing
    but the part's own separators (spaces, ``|``, line ends). None when the
    table is not in the text so."""
    cells = [_nfkc(cell) for row in table for cell in row if cell]
    if not cells:
        return None
    at = text.find(cells[0], start)
    while at >= 0:
        places = _chained(text, cells, at)
        if places is not None:
            found = iter(places)
            return [
                [_Cell(_nfkc(cell), next(found) if cell else None) for cell in row] for row in table
            ]
        at = text.find(cells[0], at + 1)
    return None


def _chained(text: str, cells: Sequence[str], at: int) -> list[tuple[int, int]] | None:
    places: list[tuple[int, int]] = []
    position = at
    for index, cell in enumerate(cells):
        if index:
            while position < len(text) and text[position] in " |\n":
                position += 1
        if not text.startswith(cell, position):
            return None
        places.append((position, position + len(cell)))
        position += len(cell)
    return places


def _row_line(case: OrderCase, row: Sequence[_Cell]) -> OrderLine | None:
    """The case line a row names: by a customer item code or PRV code among
    its cells; among lines sharing that code, by a line number among them."""
    named = [
        line
        for line in case.lines
        if any(
            cell.text
            and (
                _same(cell.text, line.effective.customer_item_code)
                or (line.mapping.prv_code is not None and _same(cell.text, line.mapping.prv_code))
            )
            for cell in row
        )
    ]
    if len(named) <= 1:
        return named[0] if named else None
    numbers = {cell.text.strip() for cell in row}
    numbered_lines = [line for line in named if str(line.line_no) in numbers]
    return numbered_lines[0] if len(numbered_lines) == 1 else None


def _date_of(cell: _Cell, received_on: date, notation: Notation) -> date | None:
    asked = parse_asked("requested_date", cell.text, received_on, notation)
    return None if asked is None else date.fromisoformat(asked[0])


def table_changes(
    case: OrderCase, text: str, tables: Sequence[MailTable], received_on: date
) -> ReadChanges:
    """The dates a table in the mail asks for this order's lines (module
    docstring). ``text`` is the newest part, NFKC-normalised, the tables
    `mail_parts.newest_tables` of the same message."""
    notation = notation_of(text)
    po_no = case.effective_header.po_no
    lines: list[ChangeLine] = []
    unread = 0
    cursor = 0
    for table in tables:
        located = _located(text, table, cursor)
        if located is None:
            unread += sum(1 for row in table if any(_same(cell, po_no) for cell in row if cell))
            continue
        cursor = max(c.at[1] for row in located for c in row if c.at is not None)
        ours = [row for row in located if any(c.text and _same(c.text, po_no) for c in row)]
        resolved = [(row, line) for row in ours if (line := _row_line(case, row)) is not None]
        unread += len(ours) - len(resolved)
        asked_column = _asked_date_column(resolved, received_on, notation)
        if asked_column is None:
            unread += len(resolved) if _has_date_columns(resolved, received_on, notation) else 0
            continue
        for row, line in resolved:
            cell = row[asked_column] if asked_column < len(row) else None
            if cell is None or not cell.text or cell.at is None:
                continue
            day = _date_of(cell, received_on, notation)
            if day is None:  # a column of dates: every cell read as one
                continue
            change = _line(
                case,
                line.line_no,
                "requested_date",
                day.isoformat(),
                cell.text,
                TextRange(start=cell.at[0], end=cell.at[1]),
                "table",
            )
            if change is not None:
                lines.append(change)
    kept = _keyed(lines)
    return ReadChanges(kept.lines, unread + kept.unread)


def _date_columns(
    rows: Sequence[tuple[Sequence[_Cell], OrderLine]], received_on: date, notation: Notation
) -> list[int]:
    width = max((len(row) for row, _ in rows), default=0)
    columns: list[int] = []
    for column in range(width):
        cells = [row[column] for row, _ in rows if column < len(row) and row[column].text]
        if cells and all(_date_of(c, received_on, notation) is not None for c in cells):
            columns.append(column)
    return columns


def _has_date_columns(
    rows: Sequence[tuple[Sequence[_Cell], OrderLine]], received_on: date, notation: Notation
) -> bool:
    return bool(_date_columns(rows, received_on, notation))


def _asked_date_column(
    rows: Sequence[tuple[Sequence[_Cell], OrderLine]], received_on: date, notation: Notation
) -> int | None:
    """The one date column that is not the dates the case holds; None when
    there is none, or more than one (module docstring)."""
    if not rows:
        return None

    def holds(column: int) -> bool:
        checked = 0
        for row, line in rows:
            entered = line.effective
            if entered.prints_schedules or entered.requested_date is None:
                continue
            cell = row[column] if column < len(row) else None
            if cell is None or _date_of(cell, received_on, notation) != entered.requested_date:
                return False
            checked += 1
        return checked > 0

    candidates = [c for c in _date_columns(rows, received_on, notation) if not holds(c)]
    return candidates[0] if len(candidates) == 1 else None


# ------------------------------------------------------- the free text --


class ModelChange(BaseModel):
    """One change as a model gives it: the words naming the line, the field
    from the closed set, the words of the value asked. The line's words come
    first, so the model finds the line before it reads the value."""

    model_config = _FROZEN

    line_span: _Span
    field: ChangeField
    asked_span: _Span


class ModelChanges(BaseModel):
    """What one call returns: flat and closed, every key required."""

    model_config = _FROZEN

    changes: tuple[ModelChange, ...] = Field(max_length=MAX_MODEL_CHANGES)


_DIGITS: Final = re.compile(r"\d+")


def _numbers_in(span: str) -> list[int]:
    """The whole numbers ``span`` writes as tokens of their own: not part of
    a code (``AWG24``), a decimal (``1.5``) or a grouped number (``1,200``)."""
    found: list[int] = []
    for match in _DIGITS.finditer(span):
        start, end = match.span()
        before = span[start - 1] if start else ""
        after = span[end] if end < len(span) else ""
        if (before and (word_char(before) or before in ".,")) or (
            after and (word_char(after) or (after in ".," and span[end + 1 : end + 2].isdigit()))
        ):
            continue
        found.append(int(match.group()))
    return found


def named_line(case: OrderCase, span: str) -> int | None:
    """The line ``span`` names: a customer item code or PRV code of the case
    inside it (one line only; among lines sharing the code, the one whose
    number is a whole number in it), else the one whole number in it.
    The number may name no line of the case: the caller refuses it, never
    guesses (ticket 10 reads PC's mail, which names lines by PRV code)."""
    folded = FoldedText(span)
    coded = {
        line.line_no
        for line in case.lines
        if folded.occurrences(_nfkc(line.effective.customer_item_code), bounded=True)
        or (
            line.mapping.prv_code is not None
            and folded.occurrences(_nfkc(line.mapping.prv_code), bounded=True)
        )
    }
    numbers = _numbers_in(span)
    if len(coded) > 1:
        numbered = coded & set(numbers)
        return numbered.pop() if len(numbered) == 1 else None
    if coded:
        return coded.pop()
    return numbers[0] if len(numbers) == 1 else None


def model_changes(
    case: OrderCase, text: str, answer: ModelChanges, received_on: date
) -> ReadChanges:
    """What code accepts of a model's reading of ``text`` (the newest part,
    NFKC-normalised; module docstring). Never raises on the model's answer:
    a change whose words are not found once, whose line cannot be told, or
    whose value does not read is dropped and counted."""
    notation = notation_of(text)
    folded = FoldedText(text)
    lines: list[ChangeLine] = []
    unread = 0
    for change in answer.changes:
        named = folded.locate(_nfkc(change.line_span).strip(), bounded=True)
        place = folded.locate(_nfkc(change.asked_span).strip(), bounded=True)
        line_no = None if isinstance(named, str) else named_line(case, text[named[0] : named[1]])
        if isinstance(place, str) or line_no is None:
            unread += 1
            continue
        written = text[place[0] : place[1]]
        asked = parse_asked(change.field, written, received_on, notation)
        if asked is None:
            unread += 1
            continue
        line = _line(
            case,
            line_no,
            change.field,
            asked[0],
            written,
            TextRange(start=place[0], end=place[1]),
            "model",
            unit=asked[1],
        )
        if line is not None:
            lines.append(line)
    kept = _keyed(lines)
    return ReadChanges(kept.lines, unread + kept.unread)


# ------------------------------------------------------------ a person --


def person_line(case: OrderCase, line_no: int, field: ChangeField, value: str) -> ChangeLine:
    """A line a person typed: ``value`` in the field's one form (the screen's
    date and number pickers send it so). Refused for a line the case does not
    have (a person can see the lines), and for the value it holds."""
    details: dict[str, object] = {"case_id": str(case.case_id), "line": line_no, "field": field}
    try:
        asked = _value_text(field, value.strip())
    except ValueError:
        raise DomainError("the value is not one of this field", details=details) from None
    _, blocked = held_value(case, line_no, field)
    if blocked == "no_such_line":
        raise ConflictError(
            "the case has no such line", details={**details, "rule": "no_such_line"}
        )
    line = _line(case, line_no, field, asked, value.strip() or asked, None, "person")
    if line is None:
        raise ConflictError(
            "the case already holds this value", details={**details, "rule": "no_change"}
        )
    return line
