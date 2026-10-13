"""What a message is about, as a model reads it, and what code accepts of that.

Ticket 31, dw_sales ADR 0005, Đạt's rule §6. A message whose attachments no
reader accepted (no PO, no request form, no Design reply) was classified by
keyword tables; a phrasing nobody listed fell to `other`. Where a tenant turns
it on (`sales_order_rules.model_assist.message_intent`), a local model reads
the subject and the newest part of the body into a typed intent instead, and
code decides what happens:

- **The model gives** (`ModelMessageIntent`) one kind from a closed set, the
  language, and the spans of any document numbers the message names. No
  route, no owner, no customer, no case: those are code's.
- **Code maps** the kind to the route (`dw_sales.application.message_intent`),
  so a kind can only ever lead where the table says. ``po`` still needs a
  readable PO and ``design_reply`` still needs a Design mailbox the mail
  system verified: the model's word opens no door code would not.
- **A number is used** only when code locates it, as a whole token, in the
  newest part (`located_numbers`) and it resolves exactly and uniquely
  against the sender's own customer's records; anything else is dropped.

There is no "revised PO" kind: whether a document revises another is a fact
of the document (its PO number and revision against the cases), never a
reading.
"""

from __future__ import annotations

import unicodedata
import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from dw_sales.domain.catalog import DocumentNo
from dw_sales.domain.spans import FoldedText

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

IntentKind = Literal[
    "po",
    "quote_request",
    "design_reply",
    "reply_to_case",
    "delivery_change",
    "complaint",
    "sample_request",
    "other",
]
IntentLanguage = Literal["vi", "en", "ja", "other"]
# At most this many numbers are taken from one message: a reply names one or
# two; a list of twenty is not a reference to anything.
MAX_REFERENCES = 5

_NumberSpan = Annotated[str, Field(min_length=1, max_length=64)]


class ModelMessageIntent(BaseModel):
    """What one call returns: flat and closed, every key required, so a server
    decoding against the schema writes each one. The spans come before the
    kind, so the model reads before it labels."""

    model_config = _FROZEN

    language: IntentLanguage
    referenced_number_spans: tuple[_NumberSpan, ...] = Field(max_length=MAX_REFERENCES)
    kind: IntentKind


# ------------------------------------------------------- what is stamped --

ReferenceRecord = Literal["purchase_order", "quote_request"]
IntentOutcome = Literal["read", "unavailable"]


class ResolvedReference(BaseModel):
    """A number the message names that code found in it and resolved to
    exactly one record of the sender's customer."""

    model_config = _FROZEN

    number: DocumentNo
    record: ReferenceRecord
    # The order case DW1 holds for that PO, when it holds one.
    order_case_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _a_case_is_an_order(self) -> Self:
        if self.order_case_id is not None and self.record != "purchase_order":
            raise ValueError("only a purchase order names an order case")
        return self


class IntentReading(BaseModel):
    """What the model reading of a message's intent did, stamped on its
    disposition: the prompt, profile and route of the call, the rules whose
    switch asked for it, and the outcome. ``unavailable``: no usable answer
    within the retry window, so the message went to Sales as `other`."""

    model_config = _FROZEN

    prompt: str = Field(pattern=r"^[a-z][a-z0-9_.]*@\d+\.\d+\.\d+$")
    model_profile: str = Field(min_length=1, max_length=64)
    route: str = Field(min_length=1, max_length=64)
    rules: str = Field(pattern=r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$")
    outcome: IntentOutcome
    kind: IntentKind | None = None
    language: IntentLanguage | None = None
    references: tuple[ResolvedReference, ...] = Field(default=(), max_length=MAX_REFERENCES)

    @model_validator(mode="after")
    def _outcome_says_what_is_there(self) -> Self:
        read = self.outcome == "read"
        if read != (self.kind is not None and self.language is not None):
            raise ValueError("a reading names a kind and a language exactly when it was read")
        if self.references and not read:
            raise ValueError("only a reading resolves references")
        return self


_DOCUMENT_NO: TypeAdapter[str] = TypeAdapter(DocumentNo)


def located_numbers(part: str, spans: tuple[str, ...]) -> tuple[str, ...]:
    """The numbers among ``spans`` that are document numbers and that code
    finds, each as a whole token, in ``part`` (the newest part, subject
    first). In the part's own spelling, upper-cased, once each.

    A number found only in quoted history is not in ``part`` at all
    (`mail_parts.newest_part` cut it), so it is not found. A number is not
    required to appear exactly once: a subject and its body often both name
    it, and the record it resolves to, not its position, is what is used.
    """
    text = FoldedText(unicodedata.normalize("NFKC", part))
    found: list[str] = []
    for raw in spans:
        span = unicodedata.normalize("NFKC", raw).strip()
        places = text.occurrences(span, bounded=True)
        if not places:
            continue
        start, end = places[0]
        number = text.original[start:end].upper()
        try:
            _DOCUMENT_NO.validate_python(number)
        except ValidationError:
            continue
        if number not in found:
            found.append(number)
    return tuple(found)
