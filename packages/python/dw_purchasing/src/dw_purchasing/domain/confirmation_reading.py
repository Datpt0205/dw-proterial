"""A model's reading of a supplier's order confirmation, and what code accepts.

The rule DW2 reads a request and a quotation by (`domain.mail_reading`,
`domain.offer_reading`), applied to a confirmation: the model copies spans;
code finds each as a whole token run in what the model was shown, parses it,
and ties each line to a line of the order by the item code the order named.
Which order the mail confirms is decided by code before the model is asked
(`application.follow_up`), never by the model.

**What code checks** (`read_confirmation_mail`):

1. At least one line; each found once, as a whole token run.
2. In each line, the item code is found and is one the order holds; at
   least one of the quantity, the unit price and the delivery date is given,
   and each given is found in the line and parsed. A line that fails
   refuses the whole mail (``line_unreadable``), and so does an item
   confirmed twice. An item the order does not hold is ``item_not_ordered``.
3. A confirmation that names no line is not read (``no_lines``): what "we
   confirm your order" covers is for a buyer to judge.

What the confirmation then says against the order is `domain.tracking`'s
`differences`, not this module's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from dw_purchasing.domain.mail_reading import Span, fold, occurrences, parse_date, parse_quantity
from dw_purchasing.domain.tracking import ConfirmedLine

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
MAX_CONFIRMED_LINES: Final = 20


class ModelConfirmedLine(BaseModel):
    model_config = _FROZEN

    line_span: Span
    item_code_span: Span | None
    quantity_span: Span | None
    unit_price_span: Span | None
    delivery_date_span: Span | None


class ModelConfirmation(BaseModel):
    model_config = _FROZEN

    lines: tuple[ModelConfirmedLine, ...] = Field(max_length=MAX_CONFIRMED_LINES)


@dataclass(frozen=True, slots=True)
class ConfirmationVerdict:
    lines: tuple[ConfirmedLine, ...]
    not_read: str | None


def read_confirmation_mail(
    text: str,
    answer: ModelConfirmation,
    *,
    ordered: Mapping[str, int],
    received_on: date,
) -> ConfirmationVerdict:
    """What code accepts of one confirmation. ``ordered`` maps each item code
    the order holds to its line."""
    folded = fold(text)
    ordered_folded = {fold(code): line_no for code, line_no in ordered.items()}
    if not answer.lines:
        return ConfirmationVerdict((), "no_lines")
    read: list[ConfirmedLine] = []
    seen_spans: set[str] = set()
    for line in answer.lines:
        span = fold(line.line_span)
        if span in seen_spans or len(occurrences(folded, span)) != 1:
            return ConfirmationVerdict((), "line_unreadable")
        seen_spans.add(span)
        values = (line.quantity_span, line.unit_price_span, line.delivery_date_span)
        if line.item_code_span is None or all(v is None for v in values):
            return ConfirmationVerdict((), "line_unreadable")
        if any(
            v is not None and not occurrences(span, fold(v)) for v in (line.item_code_span, *values)
        ):
            return ConfirmationVerdict((), "line_unreadable")
        line_no = ordered_folded.get(fold(line.item_code_span))
        if line_no is None:
            return ConfirmationVerdict((), "item_not_ordered")
        if any(r.line_no == line_no for r in read):
            return ConfirmationVerdict((), "line_unreadable")
        quantity = parse_quantity(line.quantity_span) if line.quantity_span else None
        price = parse_quantity(line.unit_price_span) if line.unit_price_span else None
        on = (
            parse_date(line.delivery_date_span, received_on=received_on)
            if line.delivery_date_span
            else None
        )
        parsed = (
            (line.quantity_span, quantity),
            (line.unit_price_span, price),
            (line.delivery_date_span, on),
        )
        if any(given is not None and value is None for given, value in parsed):
            return ConfirmationVerdict((), "line_unreadable")
        read.append(
            ConfirmedLine(line_no=line_no, quantity=quantity, unit_price=price, delivery_on=on)
        )
    return ConfirmationVerdict(tuple(read), None)
