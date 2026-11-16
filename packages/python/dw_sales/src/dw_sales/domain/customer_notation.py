"""How one customer writes its numbers, dates and bare currency symbols, as
Sales' confirmations settled it (ticket 37).

The platform owns the reading (`dw_platform.domain.notation`): a document
fixes its own notation where its values show it, and a value it leaves open
("1.200 m", "05/11/2026", a bare "$") goes to a person. A customer writes one
way, and Sales knows it the first time they confirm such a value. So:

- **Code learns** (`order_lesson`, `quote_lessons`): when Sales confirms or
  types a value whose words did not read by themselves, the one notation
  under which the words read as the value Sales kept (`notation.learned`)
  is that customer's, for that kind. A value Sales corrected to something
  neither reading gives teaches nothing; no model is asked.
- **One entry per customer and kind** (`NotationEntry`): the value, and the
  evidence it rests on (the case, the field, the words as written, the
  value confirmed, who and when), or that a person set it on the customer's
  master data.
- **Readers consult it** through `notation.settle`: it settles what a
  document leaves open, never what a document says, and a document that
  says otherwise goes to a person.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_platform.domain.notation import (
    KIND_VALUES,
    Learned,
    Notation,
    NotationKind,
    learned,
    record_of,
)
from dw_sales.domain.catalog import CustomerCode
from dw_sales.domain.orders import OrderCase, value_with_correction
from dw_sales.domain.quotes import FindingCorrected, QuoteCase, QuoteFindingCode, RequestedItem
from dw_sales.domain.rfq_reading import parse_currency, parse_price, written_date

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

NotationSource = Literal["confirmed", "set"]
NotationCaseKind = Literal["order", "quote"]
# The fields a confirmation can teach from: a number, a date, a currency.
_ORDER_FIELDS = frozenset(
    {"quantity", "unit_price", "amount", "requested_date", "po_date", "currency"}
)
_QUOTE_FIELDS = frozenset({"quantity", "needed_by", "quote_due", "currency"})


class NotationEntry(BaseModel):
    """One kind of one customer's notation (module docstring).

    ``confirmed``: learned from a value Sales confirmed, naming the case and
    field, the words as written and the value kept. ``set``: a person chose
    it on the customer's master data, and nothing else is named.
    """

    model_config = _FROZEN

    customer_code: CustomerCode
    kind: NotationKind
    value: str = Field(min_length=1, max_length=16)
    source: NotationSource
    case_kind: NotationCaseKind | None = None
    case_id: uuid.UUID | None = None
    field: str | None = Field(default=None, pattern=r"^[a-z_]{1,32}$")
    written: str | None = Field(default=None, min_length=1, max_length=300)
    confirmed: str | None = Field(default=None, min_length=1, max_length=64)
    by: uuid.UUID
    at: AwareDatetime

    @model_validator(mode="after")
    def _holds_its_evidence(self) -> Self:
        if self.value not in KIND_VALUES[self.kind]:
            raise ValueError(f"{self.kind} holds no such value")
        evidence = (self.case_kind, self.case_id, self.field, self.written, self.confirmed)
        if self.source == "confirmed" and any(part is None for part in evidence):
            raise ValueError("a learned notation names the value that settled it")
        if self.source == "set" and any(part is not None for part in evidence):
            raise ValueError("a notation a person set names no case")
        return self


def customer_record(entries: Iterable[NotationEntry]) -> Notation:
    """The customer's record as `notation.settle` reads it."""
    return record_of((entry.kind, entry.value) for entry in entries)


@dataclass(frozen=True, slots=True)
class Lesson:
    """What one confirmation taught: the field, the words, the value kept."""

    field: str
    written: str
    confirmed: str
    learned: Learned


def lesson(field: str, written: str, kept: object) -> Lesson | None:
    """What Sales keeping ``kept`` for the words ``written`` teaches, read by
    Sales' own parsers: a number as one number among words (``1.200 m``), a
    date by its day and month, a currency among the three DW1 prices in."""
    found: Learned | None = None
    if isinstance(kept, Decimal):
        found = learned(lambda n: parse_price(written, n), kept)
    elif isinstance(kept, date):
        found = learned(lambda n: _month_day(written, n), (kept.month, kept.day))
    elif isinstance(kept, str):
        found = learned(lambda n: parse_currency(written, n), kept)
    if found is None:
        return None
    return Lesson(field, written[:300], _text(kept), found)


def _month_day(written: str, notation: Notation) -> tuple[int, int] | None:
    found = written_date(written, notation)
    return None if found is None else (found[1], found[2])


def _text(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")[:64]
    return str(value)[:64]


def order_lesson(
    before: OrderCase, after: OrderCase, finding_key: str, field: str
) -> Lesson | None:
    """What Sales' value for ``field`` of a `value_uncertain` (``after``'s
    correction) teaches, against the words it was read from."""
    if field not in _ORDER_FIELDS:
        return None
    finding = before.finding(finding_key)
    correction = (
        after.header_correction(field)
        if finding.line_no is None
        else after.line(finding.line_no).correction(field)
    )
    if correction is None:
        return None
    holder: Any = before.header if finding.line_no is None else before.line(finding.line_no).po_line
    written = getattr(holder.anchors, field).quote
    kept = getattr(value_with_correction(holder, correction), field)
    return lesson(field, written, kept) if written else None


def quote_lessons(before: QuoteCase, after: QuoteCase) -> list[Lesson]:
    """What one decision on a request teaches: each value a model read that
    Sales confirmed by it, and each value the request left open that Sales
    typed (`rfq_incomplete`), against the words it was read from."""
    lessons: list[Lesson] = []
    earlier = {
        (f.line_no, c.field)
        for f in before.findings
        if f.code is QuoteFindingCode.VALUE_UNCERTAIN
        for c in f.confirmed
    }
    was_open = {f.key for f in before.findings if f.is_open}
    document = before.request.document
    for finding in after.findings:
        if finding.code is QuoteFindingCode.VALUE_UNCERTAIN:
            for confirmation in finding.confirmed:
                if (finding.line_no, confirmation.field) in earlier:
                    continue
                if confirmation.field not in _QUOTE_FIELDS:
                    continue
                holder: Any = (
                    document if finding.line_no is None else document.item(finding.line_no)
                )
                written = getattr(holder, confirmation.field).source.quote
                kept_holder: Any = (
                    after.request.document
                    if finding.line_no is None
                    else after.request.document.item(finding.line_no)
                )
                kept = getattr(kept_holder, confirmation.field).value
                found = lesson(confirmation.field, written, kept) if written else None
                if found is not None:
                    lessons.append(found)
        elif (
            finding.code is QuoteFindingCode.RFQ_INCOMPLETE
            and finding.line_no is not None
            and finding.key in was_open
            and not finding.is_open
        ):
            lessons += _typed(document.item(finding.line_no), finding.disposition)
    return lessons


def _typed(item: RequestedItem, disposition: object) -> list[Lesson]:
    """The values Sales typed for a line whose words the request's notation
    did not settle (`RequestedItem.unsettled`, anchored at those words);
    never a value the customer did not state, anchored at the line."""
    if not isinstance(disposition, FindingCorrected):
        return []
    typed = {"quantity": disposition.quantity, "needed_by": disposition.needed_by}
    lessons: list[Lesson] = []
    for field in item.unsettled:
        kept = typed[field]
        written = getattr(item, field).source.quote
        found = lesson(field, written, kept) if kept is not None and written else None
        if found is not None:
            lessons.append(found)
    return lessons
