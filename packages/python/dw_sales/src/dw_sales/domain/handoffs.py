"""A hand-off to PC or QA, pre-filled from a customer's mail with the customer's
own words: what a model copies, and what code keeps of it.

Ticket 33, dw_sales ADR 0005, Đạt's rule §6. A message routed to Sales as a
delivery change, a complaint or a sample request (by the keyword tables or a
model's reading of its intent, ticket 31) was retyped by Sales into a mail to
PC or QA. Where a tenant turns it on
(`sales_order_rules.model_assist.request_handoff`), a local model copies the
spans that mail needs out of the newest part of the message, and code builds
the hand-off:

- **The model gives spans only** (`ModelDeliveryChange`, `ModelComplaint`,
  `ModelSampleRequest`, one per kind; the kind is the routing reason, never
  this call's choice): the PO number, the line or item, the new quantity and
  date, the lot, the sentences that describe a problem, the sample items and
  quantity. It writes no sentence of its own: nothing reaches PC or QA as if
  it were the customer's words, and an instruction in the mail cannot be
  paraphrased into the hand-off.
- **Code locates every span** exactly once in the newest part (`locate`), so
  a value found only in quoted history, or twice, is refused; a PO number
  only has to be there, as a whole token (`locate_identifier`): a subject
  and its body often both name it, and the order it resolves to, not where
  it is written, is what is used (as ticket 31's numbers); **parses** each
  number and date from its span (`quantity_of`, `rfq_reading.parse_date`);
  and **resolves** the PO against the sender's own customer's orders only and
  each line exactly against that order (`application.handoffs`).
- **A quote carries no destination**: a sentence naming an email address, a
  web address or a phone number is dropped (`carries_contact`). PC and QA
  reach people through master data; a customer's "ship the replacement to
  ..." is not routed through a hand-off.
- **Code writes the hand-off** from a versioned template
  (`configs/copy/sales_handoffs@<version>.yaml`); Sales reviews, edits and
  sends it. Nothing is sent and no ERP date or quantity changes.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.catalog import DocumentNo
from dw_sales.domain.rfq_reading import parse_number
from dw_sales.domain.spans import FoldedText

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

HandoffKind = Literal["delivery_change", "complaint", "sample_request"]
MAX_LINES: Final = 20
MAX_QUOTES: Final = 3
MAX_ITEMS: Final = 5

_Span = Annotated[str, Field(min_length=1, max_length=120)]
_Quote = Annotated[str, Field(min_length=1, max_length=400)]


# ------------------------------------------------- what the model returns --


class ModelChangeLine(BaseModel):
    """One line the customer asks to change: how they name it, and the new
    quantity and date as they write them."""

    model_config = _FROZEN

    line_or_item_span: _Span
    new_quantity_span: _Span | None
    new_date_span: _Span | None


class ModelDeliveryChange(BaseModel):
    model_config = _FROZEN

    po_no_span: _Span | None
    lines: tuple[ModelChangeLine, ...] = Field(max_length=MAX_LINES)


class ModelComplaint(BaseModel):
    model_config = _FROZEN

    po_no_span: _Span | None
    lot_no_span: _Span | None
    problem_quote_spans: tuple[_Quote, ...] = Field(max_length=MAX_QUOTES)


class ModelSampleRequest(BaseModel):
    model_config = _FROZEN

    item_spans: tuple[_Quote, ...] = Field(max_length=MAX_ITEMS)
    quantity_span: _Span | None


# The schema a call is asked for, by the kind the routing already decided.
MODEL_SCHEMAS: Final[Mapping[HandoffKind, type[BaseModel]]] = MappingProxyType(
    {
        "delivery_change": ModelDeliveryChange,
        "complaint": ModelComplaint,
        "sample_request": ModelSampleRequest,
    }
)


# ------------------------------------------------------ what code keeps --


class Located(BaseModel):
    """Text code found exactly once in the newest part, with its offsets
    into the NFKC form of `MessagePart.text`."""

    model_config = _FROZEN

    text: str = Field(min_length=1, max_length=400)
    start: int = Field(ge=0)
    end: int = Field(ge=1)


class HandoffLine(BaseModel):
    """A line of the order the customer asks to change, resolved by code."""

    model_config = _FROZEN

    reference: Located
    line_no: int = Field(ge=1, le=9999)
    # The order line's item as the order holds it (PRV code), from the order.
    item: str | None = Field(default=None, max_length=64)
    new_quantity: Decimal | None = Field(default=None, gt=0)
    quantity: Located | None = None
    new_date: date | None = None
    date_span: Located | None = None


HandoffOutcome = Literal["read", "unavailable", "nothing_located"]


class Handoff(BaseModel):
    """The pre-filled hand-off stamped on a routed message's disposition.

    ``read``: some value was located. ``nothing_located``: the model answered
    and code kept nothing of it. ``unavailable``: no usable answer. Either of
    the last two is an empty form Sales fills by hand, as before.
    """

    model_config = _FROZEN

    kind: HandoffKind
    prompt: str = Field(pattern=r"^[a-z][a-z0-9_.]*@\d+\.\d+\.\d+$")
    model_profile: str = Field(min_length=1, max_length=64)
    route: str = Field(min_length=1, max_length=64)
    rules: str = Field(pattern=r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$")
    outcome: HandoffOutcome
    # The PO, when it resolved to exactly one order of the sender's customer.
    po_no: DocumentNo | None = None
    po: Located | None = None
    so_no: DocumentNo | None = None
    order_case_id: uuid.UUID | None = None
    lines: tuple[HandoffLine, ...] = Field(default=(), max_length=MAX_LINES)
    lot: Located | None = None
    # A complaint's problem sentences, or a sample request's items: the
    # customer's words, located.
    quotes: tuple[Located, ...] = Field(default=(), max_length=MAX_ITEMS)
    sample_quantity: Decimal | None = Field(default=None, gt=0)
    quantity: Located | None = None
    # How many spans the model gave that code refused, by field: a count for
    # the evals and the screen, never the text.
    refused: Mapping[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _outcome_says_what_is_there(self) -> Self:
        located = bool(self.po_no or self.lines or self.lot or self.quotes or self.sample_quantity)
        if (self.outcome == "read") != located:
            raise ValueError("a hand-off is read exactly when code kept a value of it")
        if self.po_no is None and (self.lines or self.so_no or self.order_case_id):
            raise ValueError("lines and orders stand on a resolved PO")
        if self.kind != "delivery_change" and self.lines:
            raise ValueError("only a delivery change names lines")
        if self.kind != "complaint" and self.lot is not None:
            raise ValueError("only a complaint names a lot")
        if self.kind != "sample_request" and self.sample_quantity is not None:
            raise ValueError("only a sample request states a sample quantity")
        if self.kind == "sample_request" and self.po_no is not None:
            raise ValueError("a sample request names no order")
        return self


# ------------------------------------------------------- verification --


def locate(part: str, span: str | None, *, bounded: bool = False) -> Located | None:
    """``span`` where code finds it exactly once in ``part``, else None."""
    if span is None:
        return None
    text = FoldedText(unicodedata.normalize("NFKC", part))
    place = text.locate(unicodedata.normalize("NFKC", span).strip(), bounded=bounded)
    if isinstance(place, str):
        return None
    start, end = place
    return Located(text=text.original[start:end], start=start, end=end)


def locate_identifier(part: str, span: str | None) -> Located | None:
    """``span`` where code first finds it as a whole token in ``part``: a
    document number, which is used for the record it names, not its place."""
    if span is None:
        return None
    text = FoldedText(unicodedata.normalize("NFKC", part))
    found = text.occurrences(unicodedata.normalize("NFKC", span).strip(), bounded=True)
    if not found:
        return None
    start, end = found[0]
    return Located(text=text.original[start:end], start=start, end=end)


_NUMBER = re.compile(r"\d[\d.,  ]*\d|\d")


def quantity_of(span: str) -> Decimal | None:
    """The one number a quantity span holds, as a customer groups it
    (`rfq_reading.parse_number`), whatever words or unit stand around it
    ("2.000 m", "4,000m", "各50m"); None for a span with no number or with
    two, which says more than one quantity."""
    numbers = _NUMBER.findall(unicodedata.normalize("NFKC", span))
    if len(numbers) != 1:
        return None
    value = parse_number(numbers[0])
    return value if value is not None and value > 0 else None


_LINE_NUMBER = re.compile(
    r"^(?:dòng|line|ln\.?|no\.?|#|行)?\s*(\d{1,4})\s*(?:行目|行)?(?:\s*[(:].*)?$",
    re.IGNORECASE,
)


def line_number_of(span: str) -> int | None:
    """A line named by its number ("2", "dòng 2", "line 2", "2行目"), what
    follows it in brackets or after a colon aside ("Dòng 1 (mã VX-C4B22)");
    else None."""
    match = _LINE_NUMBER.match(unicodedata.normalize("NFKC", span).strip())
    return int(match.group(1)) if match else None


_EMAIL = re.compile(r"[^\s@<>()]+@[^\s@<>()]+\.[a-z]{2,}", re.IGNORECASE)
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
# A run of digits and the separators phone numbers are written with; a phone
# number has at least nine digits, which a date (eight) or a lot does not.
_PHONE = re.compile(r"\+?\d[\d .()-]{6,}\d")
_PHONE_DIGITS: Final = 9


def carries_contact(text: str) -> bool:
    """Whether a quote names somewhere to send something: an email address, a
    web address or a phone number. Such a sentence is not carried into a
    hand-off (module docstring)."""
    folded = unicodedata.normalize("NFKC", text)
    if _EMAIL.search(folded) or _URL.search(folded):
        return True
    return any(
        sum(c.isdigit() for c in run.group(0)) >= _PHONE_DIGITS for run in _PHONE.finditer(folded)
    )
