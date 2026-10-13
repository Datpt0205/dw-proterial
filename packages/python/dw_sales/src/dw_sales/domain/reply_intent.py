"""What a customer's reply in a case's thread says, as a model reads it, and
what code makes of it.

Ticket 32, dw_sales ADR 0005, Đạt's rule §6. A reply to a spec discussion, a
decline or a correction request is linked to its case by the mail's thread
headers (`application.threads`), never by a model. Where a tenant turns it on
(`sales_order_rules.model_assist.reply_intent`), a local model then reads the
newest part of the reply into a typed intent, and code decides what of it is
used:

- **The model gives** (`ModelReplyIntent`) one kind from a closed set and up
  to three sentences of the reply, copied, that say it. No case, no step, no
  status: those are code's.
- **A quote is used** only when code locates it exactly once in the newest
  part (`located_quotes`); an intent with no located quote is ``unclear``
  (`verified_kind`): a reading nobody can point at is no reading.
- **A step is proposed** only by `proposed_step`, one table from the case's
  kind and status and the reply's kind to an existing step, and only where
  that status allows the step. Sales confirms it on the case: nothing here
  applies anything. A conditional acceptance ("we accept if the colour is
  grey") read as ``accepts_spec`` would pass every check above, which is why
  the case shows the quoted sentences beside the proposal.
- **No finding is disposed**: a customer keeping their PO as it is proposes
  that review resumes, and each finding sent back to them is still disposed
  one by one by Sales (spec decision 9).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.spans import FoldedText

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

ReplyKind = Literal[
    "accepts_spec",
    "rejects_spec",
    "counter_proposal",
    "sends_corrected_po",
    "keeps_po_as_is",
    "question",
    "unclear",
]
# A reply says what it says in a sentence or two; three is the most kept.
MAX_QUOTES: Final = 3
_QuoteSpan = Annotated[str, Field(min_length=1, max_length=400)]


class ModelReplyIntent(BaseModel):
    """What one call returns: flat and closed, every key required. The quotes
    come before the kind, so the model reads before it labels."""

    model_config = _FROZEN

    quote_spans: tuple[_QuoteSpan, ...] = Field(max_length=MAX_QUOTES)
    kind: ReplyKind


class ReplyQuote(BaseModel):
    """A sentence of the reply that code found, once, in its newest part:
    the text as the customer wrote it and where it is (offsets into the NFKC
    form of `MessagePart.text`)."""

    model_config = _FROZEN

    text: str = Field(min_length=1, max_length=400)
    start: int = Field(ge=0)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def _a_span(self) -> Self:
        if self.end <= self.start:
            raise ValueError("a quote ends after it starts")
        return self


ReplyOutcome = Literal["read", "unavailable"]


class ReplyReading(BaseModel):
    """What the model reading of a reply did, stamped on its disposition: the
    prompt, profile and route of the call, the rules whose switch asked for
    it, and the outcome. ``unavailable``: no usable answer, so the reply is on
    its case with no proposal and Sales reads it."""

    model_config = _FROZEN

    prompt: str = Field(pattern=r"^[a-z][a-z0-9_.]*@\d+\.\d+\.\d+$")
    model_profile: str = Field(min_length=1, max_length=64)
    route: str = Field(min_length=1, max_length=64)
    rules: str = Field(pattern=r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$")
    outcome: ReplyOutcome
    kind: ReplyKind | None = None
    quotes: tuple[ReplyQuote, ...] = Field(default=(), max_length=MAX_QUOTES)

    @model_validator(mode="after")
    def _outcome_says_what_is_there(self) -> Self:
        read = self.outcome == "read"
        if read != (self.kind is not None):
            raise ValueError("a reading names a kind exactly when it was read")
        if self.quotes and not read:
            raise ValueError("only a reading quotes the reply")
        if read and self.kind != "unclear" and not self.quotes:
            raise ValueError("a kind other than unclear stands on a located quote")
        return self


class CaseReply(BaseModel):
    """A message attached to a case because its thread headers name a message
    already on that case, of the sender's own customer (ticket 32)."""

    model_config = _FROZEN

    # The message on the case the reply's thread names (the mailbox's id).
    linked_to: str = Field(pattern=r"^[!-~]{1,512}$")
    # The model's reading of it, where the tenant's rules asked for one.
    reading: ReplyReading | None = None


def located_quotes(part: str, spans: tuple[str, ...]) -> tuple[ReplyQuote, ...]:
    """The spans code finds exactly once in ``part`` (the newest part, subject
    first), each once, in the order given. A sentence found only in quoted
    history is not in ``part`` at all (`mail_parts.newest_part` cut it), and
    one found twice points at nothing in particular: both are dropped."""
    text = FoldedText(unicodedata.normalize("NFKC", part))
    found: list[ReplyQuote] = []
    for raw in spans:
        span = unicodedata.normalize("NFKC", raw).strip()
        place = text.locate(span)
        if isinstance(place, str):
            continue
        start, end = place
        if any(q.start == start and q.end == end for q in found):
            continue
        found.append(ReplyQuote(text=text.original[start:end], start=start, end=end))
    return tuple(found)


def verified_kind(kind: ReplyKind, quotes: tuple[ReplyQuote, ...]) -> ReplyKind:
    """The kind code accepts: ``unclear`` when no quote of it was located."""
    return kind if quotes else "unclear"


ProposedStep = Literal[
    # QuoteCase.settle_spec: spec_discussion -> design_replied.
    "settle_spec",
    # QuoteCase.decline_request(customer_rejected_spec).
    "decline_customer_rejected_spec",
    # OrderCase.resume_review: correction_requested -> in_review, every
    # finding sent back to the customer still `ask_customer`.
    "resume_review",
    # No move: the corrected PO arrives as a revision of the case and is read
    # by the reader, as any revision is.
    "await_revised_po",
]

# Where a reply's kind may lead, by the case's kind and status: one table, a
# row per move, never a branch. Anything else proposes nothing, and Sales
# reads the reply.
REPLY_STEPS: Final[Mapping[tuple[str, str, ReplyKind], ProposedStep]] = MappingProxyType(
    {
        ("quote", "spec_discussion", "accepts_spec"): "settle_spec",
        ("quote", "spec_discussion", "rejects_spec"): "decline_customer_rejected_spec",
        ("order", "correction_requested", "keeps_po_as_is"): "resume_review",
        ("order", "correction_requested", "sends_corrected_po"): "await_revised_po",
    }
)


def proposed_step(case_kind: str, status: str, reading: ReplyReading | None) -> ProposedStep | None:
    """The step the reply proposes for a ``case_kind`` case in ``status``, or
    None: no reading, an unread or unclear one, or a status the step does not
    start from."""
    if reading is None or reading.kind is None:
        return None
    return REPLY_STEPS.get((case_kind, status, reading.kind))
