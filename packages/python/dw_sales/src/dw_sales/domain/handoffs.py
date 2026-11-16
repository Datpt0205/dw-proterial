"""A hand-off to PC or QA, pre-filled from a customer's mail with the customer's
own words: what a model copies, and what code keeps of it.

Ticket 33, dw_sales ADR 0005, Đạt's rule §6. A message routed to Sales as a
delivery change, a complaint or a sample request (by a
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
  number and date from its span (`quantity_at`, `rfq_reading.parse_date`),
  as the mail's own other values settle "2.000" and "05/11", or, where the
  mail says nothing, the customer's notation record does (ticket 37,
  `notation.settle`; such a value is marked `from_record`, and one the mail
  reads otherwise than the record is left for Sales); a quantity is
  taken only in metres, and any other unit keeps the customer's words for
  Sales instead of a value;
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
from typing import Annotated, Final, Literal, NamedTuple, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_platform.domain.notation import UNSTATED, Notation, settle
from dw_sales.domain.catalog import DocumentNo
from dw_sales.domain.message_intent import KindName
from dw_sales.domain.rfq_reading import METRE_UNIT, parse_number
from dw_sales.domain.spans import FoldedText, word_char

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

HandoffKind = Literal["delivery_change", "complaint", "sample_request"]
# Who a hand-off is for: production control or quality assurance. The closed
# set of recipients a tenant's hand-off kind may name (ticket 42): a team,
# never an address; Sales picks the people.
HandoffTeam = Literal["pc", "qa"]
# A line's value read only by the customer's notation record (ticket 37).
FromRecord = Literal["quantity", "date"]
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
    # The customer's words for the quantity; with no `new_quantity`, words
    # code did not read (another unit, an ambiguous grouping) for Sales.
    quantity: Located | None = None
    new_date: date | None = None
    # Likewise the date's words, with no `new_date` when its order is unsettled.
    date_span: Located | None = None
    # The values only the customer's notation record settled (ticket 37).
    from_record: tuple[FromRecord, ...] = ()

    @model_validator(mode="after")
    def _a_value_from_the_record_is_there(self) -> Self:
        if "quantity" in self.from_record and self.new_quantity is None:
            raise ValueError("a quantity from the record is a quantity read")
        if "date" in self.from_record and self.new_date is None:
            raise ValueError("a date from the record is a date read")
        return self


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
    # The customer's words for it; alone, words code did not read (`HandoffLine`).
    quantity: Located | None = None
    # The sample quantity only the customer's notation record settled (ticket 37).
    quantity_from_record: bool = False
    # How many spans the model gave that code refused, by field: a count for
    # the evals and the screen, never the text.
    refused: Mapping[str, int] = Field(default_factory=dict)
    # Read with the tenant's hand-off skill (ticket 42 family 5): the version,
    # the skill's kind (``kind`` above is the fields it asks for), its words
    # for Sales and the team it goes to. None, all four: read as before.
    skill: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*@\d+\.\d+\.\d+$")
    skill_kind: KindName | None = None
    kind_label: str | None = Field(default=None, min_length=1, max_length=60)
    to: HandoffTeam | None = None

    @model_validator(mode="after")
    def _outcome_says_what_is_there(self) -> Self:
        located = bool(
            self.po_no
            or self.lines
            or self.lot
            or self.quotes
            or self.sample_quantity
            or self.quantity
        )
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
        if self.quantity_from_record and self.sample_quantity is None:
            raise ValueError("a quantity from the record is a quantity read")
        if (self.skill is None) != (self.skill_kind is None) or (self.skill is None) != (
            self.to is None
        ):
            raise ValueError("a skill's hand-off names its version, its kind and its team")
        if self.skill is None and self.kind_label is not None:
            raise ValueError("only a skill's hand-off carries the skill's label")
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
# The word after a quantity's number, kept with it when it is no metre spelling.
_UNIT_AFTER = re.compile(r"\s*[^\W\d_]+")
# Metres right after the number (`rfq_reading.METRE_UNIT`, the one list of
# their spellings), as the whole word: not `mm`, not `m2`.
_METRES_AFTER = re.compile(rf"\s*{METRE_UNIT}", re.IGNORECASE)


def _metres_end(text: str, at: int) -> int | None:
    """Where a metre unit that starts right after ``at`` ends, as a whole
    word (not ``mm``, not ``m2``), else None. A rate (``m/cuộn``) is no
    quantity in metres."""
    match = _METRES_AFTER.match(text, at)
    if match is None:
        return None
    end = match.end()
    if (end < len(text) and word_char(text[end])) or text[end:].lstrip().startswith("/"):
        return None
    return end


class QuantityRead(NamedTuple):
    """A located quantity: the value in metres, or None, and the words."""

    value: Decimal | None
    words: Located
    # Read only by the customer's notation record (ticket 37).
    by_record: bool = False
    # The mail reads the number otherwise than the record: left for Sales.
    contradicts_record: bool = False


def quantity_at(
    part: str, located: Located, notation: Notation, record: Notation = UNSTATED
) -> QuantityRead | None:
    """The quantity a located span states, and the customer's words for it.

    The span holds exactly one number (else None: no quantity, or more than
    one). The unit is the word right after that number in the whole text,
    inside the span or after it, so a span the model ended at the number
    ("3" of "3 km") is read with its unit. The value is taken only in metres,
    the one unit a hand-off line is read in, and only as the mail's notation
    reads the number (`notation`: "2.000" with nothing else settling it is
    not read), or the customer's ``record`` where the mail says nothing
    (`notation.settle`). Any other unit or none ("3 km", "4 cuộn", "2巻", "thêm 500")
    is never converted or assumed: the value is None and the words, unit
    included, are kept for Sales to fill from."""
    text = unicodedata.normalize("NFKC", part)
    numbers = list(_NUMBER.finditer(located.text))
    if len(numbers) != 1:
        return None
    number_end = located.start + numbers[0].end()
    metres = _metres_end(text, number_end)
    value = None
    by_record = contradicts = False
    if metres is not None:
        number = numbers[0].group(0)
        settled = settle(lambda n: parse_number(number, n), notation, record)
        value, by_record, contradicts = (
            settled.value,
            settled.by_record,
            settled.contradicts_record,
        )
        end = metres
    else:
        unit = _UNIT_AFTER.match(text, number_end)
        end = unit.end() if unit is not None else number_end
    end = min(max(located.end, end), located.start + 400)
    words = Located(text=text[located.start : end], start=located.start, end=end)
    if value is None or value <= 0:
        return QuantityRead(None, words, contradicts_record=contradicts)
    return QuantityRead(value, words, by_record=by_record)


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
