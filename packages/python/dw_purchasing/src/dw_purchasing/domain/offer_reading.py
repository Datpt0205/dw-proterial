"""A model's reading of a supplier's reply to an RFQ, and what code accepts.

The rule DW2 reads a request by (`domain.mail_reading`), applied to a
supplier's quotation: the model copies spans; code finds each as a whole
token run in what the model was shown, parses it, and ties each line to a
line of the request the supplier was asked for by the item code the RFQ
named. Which supplier replied is the verified sender's domain, never the
model's; a price for an item the supplier was not asked about is not read
(the line is left out), and a reply quoting none it was asked is no offer.

**What code checks** (`read_offer_mail`):

1. At least one line; each found once, as a whole token run.
2. In each line, the item code, the unit price and the lead time are found
   and parsed; a currency and a validity date when given are found too. A
   line that fails refuses the whole reply (``line_unreadable``), and so does
   an item quoted twice. A line for an item not asked of this supplier is
   left out; when none is left, ``item_not_asked``.
3. A currency nobody wrote is the request's (the supplier was asked in it).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from dw_purchasing.domain.mail_reading import (
    Span,
    fold,
    occurrences,
    parse_currency,
    parse_date,
    parse_quantity,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
MAX_OFFER_LINES: Final = 20


class ModelOfferLine(BaseModel):
    model_config = _FROZEN

    line_span: Span
    item_code_span: Span | None
    unit_price_span: Span | None
    currency_span: Span | None
    lead_time_span: Span | None
    valid_until_span: Span | None


class ModelOffer(BaseModel):
    model_config = _FROZEN

    lines: tuple[ModelOfferLine, ...] = Field(max_length=MAX_OFFER_LINES)


@dataclass(frozen=True, slots=True)
class ReadOffer:
    line_no: int
    unit_price: Decimal
    currency: str
    lead_time_days: int
    valid_until: date | None


@dataclass(frozen=True, slots=True)
class OfferVerdict:
    offers: tuple[ReadOffer, ...]
    not_read: str | None


_DAYS = re.compile(r"(\d{1,3})\s*(ngày|ngay|days?|日)", re.IGNORECASE)
_WEEKS = re.compile(r"(\d{1,2})\s*(tuần|tuan|weeks?|週間?)", re.IGNORECASE)


def parse_lead_time(span: str) -> int | None:
    """Days as written: ``7 ngày``, ``10 days``, ``2 tuần``, ``3 weeks``."""
    text = unicodedata.normalize("NFKC", span)
    days, weeks = _DAYS.findall(text), _WEEKS.findall(text)
    if len(days) + len(weeks) != 1:
        return None
    value = int(days[0][0]) if days else int(weeks[0][0]) * 7
    return value if value <= 365 else None


def read_offer_mail(
    text: str,
    answer: ModelOffer,
    *,
    asked: Mapping[str, int],
    received_on: date,
    currency: str,
) -> OfferVerdict:
    """What code accepts of one reply. ``asked`` maps each item code the
    supplier was asked for (as the RFQ named it) to its request line."""
    folded = fold(text)
    asked_folded = {fold(code): line_no for code, line_no in asked.items()}
    offers: list[ReadOffer] = []
    unasked = 0
    seen_lines: set[str] = set()
    seen_items: set[int] = set()
    if not answer.lines:
        return OfferVerdict((), "no_lines")
    for line in answer.lines:
        span = fold(line.line_span)
        if span in seen_lines or len(occurrences(folded, span)) != 1:
            return OfferVerdict((), "line_unreadable")
        seen_lines.add(span)

        def found(value: str | None, *, within: str = span) -> bool:
            return value is not None and bool(occurrences(within, fold(value)))

        if not all(
            found(v) for v in (line.item_code_span, line.unit_price_span, line.lead_time_span)
        ):
            return OfferVerdict((), "line_unreadable")
        for optional in (line.currency_span, line.valid_until_span):
            if optional is not None and not found(optional):
                return OfferVerdict((), "line_unreadable")
        assert line.item_code_span and line.unit_price_span and line.lead_time_span
        line_no = asked_folded.get(fold(line.item_code_span))
        if line_no is None:
            unasked += 1
            continue
        if line_no in seen_items:
            return OfferVerdict((), "line_unreadable")
        seen_items.add(line_no)
        price = parse_quantity(line.unit_price_span)
        lead = parse_lead_time(line.lead_time_span)
        written = parse_currency(line.currency_span) if line.currency_span else currency
        valid = (
            parse_date(line.valid_until_span, received_on=received_on)
            if line.valid_until_span
            else None
        )
        if price is None or lead is None or written is None:
            return OfferVerdict((), "line_unreadable")
        if line.valid_until_span is not None and valid is None:
            return OfferVerdict((), "line_unreadable")
        offers.append(ReadOffer(line_no, price, written, lead, valid))
    if not offers and unasked:
        return OfferVerdict((), "item_not_asked")
    return OfferVerdict(tuple(offers), None)
