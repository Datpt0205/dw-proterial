"""What a message in a case's thread does, as a model reads it, and what code
makes of it: thread intents (ticket 26, dw_sales ADR 0010 decision 1).

Ticket 32 read a customer's reply into one kind of two waits (a spec
discussion, a correction request). One closed set now serves every message
in a thread, the customer's and Sales' own (ticket 25): `ThreadIntent`. A
message may carry several. A reply is linked to its case by the mail's thread
headers (`application.threads`), never by a model; where a tenant turns the
step on (`sales_order_rules.model_assist.reply_intent`), a local model reads
the newest part of the message, and code decides what of it is used:

- **The model gives** (`ModelThreadIntents`) up to `MAX_INTENTS` intents
  from the closed set, each with up to three sentences of the message,
  copied, that say it. No case, no step, no status: those are code's.
- **A quote is used** only when code locates it exactly once in the newest
  part (`located_quotes`); an intent with no located quote becomes
  ``unclear`` (`verified_intents`): a reading nobody can point at is no
  reading.
- **A step is proposed** only by `proposed_step`, one table from who wrote
  the message, the case's kind and status and an intent to an existing step
  (`INTENT_STEPS`); anything not in it proposes nothing, and intents that
  point at two different steps propose nothing either: a person reads it.
  Sales confirms the step on the case: nothing here applies anything (Đạt,
  11-04: no HITL relaxed before the plant). A conditional acceptance ("we
  accept if the colour is grey") read as ``accepts`` would pass every check
  above, which is why the case shows the quoted sentences beside the
  proposal.
- **No finding is disposed**: a customer keeping their PO as it is proposes
  that review resumes, and each finding sent back to them is still disposed
  one by one by Sales (spec decision 9).
"""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.spans import FoldedText

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# dw_sales ADR 0010 decision 1, the one set for every message in a thread;
# labels in CONTEXT.md ("Thread intent").
ThreadIntent = Literal[
    "sends_po",
    "requests_change",
    "cancels",
    "accepts",
    "rejects",
    "asks",
    "adds_info",
    "sends_rfq",
    "unclear",
]
# Who wrote the message: the customer, or Sales (an outgoing message, ticket
# 25). The same words propose different steps from each.
Author = Literal["customer", "sales"]
# A message says what it says in a sentence or two; three is the most kept.
MAX_QUOTES: Final = 3
# A message does a few things at once ("we accept line 1, push line 3"), not
# the whole set.
MAX_INTENTS: Final = 4
_QuoteSpan = Annotated[str, Field(min_length=1, max_length=400)]


class ModelIntent(BaseModel):
    """One intent as the model gives it. The quotes come before the intent,
    so the model reads before it labels."""

    model_config = _FROZEN

    quote_spans: tuple[_QuoteSpan, ...] = Field(max_length=MAX_QUOTES)
    intent: ThreadIntent


class ModelThreadIntents(BaseModel):
    """What one call returns: flat and closed, every key required."""

    model_config = _FROZEN

    intents: tuple[ModelIntent, ...] = Field(max_length=MAX_INTENTS)


class ReplyQuote(BaseModel):
    """A sentence of the message that code found, once, in its newest part:
    the text as written and where it is (offsets into the NFKC form of
    `MessagePart.text`)."""

    model_config = _FROZEN

    text: str = Field(min_length=1, max_length=400)
    start: int = Field(ge=0)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def _a_span(self) -> Self:
        if self.end <= self.start:
            raise ValueError("a quote ends after it starts")
        return self


class ReadIntent(BaseModel):
    """One intent code kept, standing on the quotes it located."""

    model_config = _FROZEN

    intent: ThreadIntent
    quotes: tuple[ReplyQuote, ...] = Field(default=(), max_length=MAX_QUOTES)

    @model_validator(mode="after")
    def _stands_on_a_quote(self) -> Self:
        if self.intent != "unclear" and not self.quotes:
            raise ValueError("an intent other than unclear stands on a located quote")
        return self


ReplyOutcome = Literal["read", "unavailable"]
# Why the thread agent (dw_sales ADR 0012) gave no reading of its own: a
# ceiling of its turn (calls, spend, time) or no usable answer.
AgentFallback = Literal["calls", "spend", "time", "unavailable"]


class ReplyReading(BaseModel):
    """What the model reading of a thread message did, stamped where the
    message is kept (a reply's disposition, a sent message's record): the
    prompt, profile and route of the call, the rules whose switch asked for
    it, the outcome and the intents code kept. ``unavailable``: no usable
    answer, so the message proposes nothing and Sales reads it."""

    model_config = _FROZEN

    prompt: str = Field(pattern=r"^[a-z][a-z0-9_.]*@\d+\.\d+\.\d+$")
    model_profile: str = Field(min_length=1, max_length=64)
    route: str = Field(min_length=1, max_length=64)
    rules: str = Field(pattern=r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$")
    outcome: ReplyOutcome
    intents: tuple[ReadIntent, ...] = Field(default=(), max_length=MAX_INTENTS)
    # Set where the thread agent was asked first and fell back, and why: the
    # reading is then the one-call reading's, or, with that one off too, no
    # reading (``unavailable``), for Sales (ticket 31). None otherwise.
    fallback: AgentFallback | None = None

    @model_validator(mode="after")
    def _outcome_says_what_is_there(self) -> Self:
        if (self.outcome == "read") != bool(self.intents):
            raise ValueError("a reading names its intents exactly when it was read")
        if len({i.intent for i in self.intents}) != len(self.intents):
            raise ValueError("a reading names each intent once")
        return self

    @property
    def kinds(self) -> tuple[ThreadIntent, ...]:
        """The intents read, in the order the model gave them."""
        return tuple(i.intent for i in self.intents)


class CaseReply(BaseModel):
    """A message attached to a case because its thread headers name a message
    already on that case, of the sender's own customer (ticket 32)."""

    model_config = _FROZEN

    # The message on the case the reply's thread names (the mailbox's id).
    linked_to: str = Field(pattern=r"^[!-~]{1,512}$")
    # The model's reading of it, where the tenant's rules asked for one.
    reading: ReplyReading | None = None
    # Who picked the case, where the thread held several and the reply named
    # none of them (ticket 24); None where code linked it.
    picked_by: uuid.UUID | None = None


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


def verified_intents(part: str, answer: ModelThreadIntents) -> tuple[ReadIntent, ...]:
    """The intents code accepts from ``answer``, read against ``part`` (the
    newest part): each with the quotes located in it, ``unclear`` where none
    was; an intent the model gave twice is kept once with the quotes of both
    (at most three); an answer naming none is ``unclear``. Never empty."""
    kept: dict[ThreadIntent, list[ReplyQuote]] = {}
    for given in answer.intents:
        quotes = located_quotes(part, given.quote_spans)
        intent: ThreadIntent = given.intent if quotes else "unclear"
        held = kept.setdefault(intent, [])
        for quote in quotes:
            if len(held) < MAX_QUOTES and quote not in held:
                held.append(quote)
    if not kept:
        kept["unclear"] = []
    return tuple(ReadIntent(intent=k, quotes=tuple(q)) for k, q in kept.items())


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
    # OrderCase.request_correction: in_review -> correction_requested, the
    # case waits on the customer (Sales asked them, from Outlook too).
    "request_correction",
    # QuoteCase.discuss_spec: design_replied -> spec_discussion, the case
    # waits on the customer.
    "discuss_spec",
    # OrderCase.agreed(accepted): confirmation_sent -> confirmed, the
    # customer agreed to the confirmation in words (ticket 28).
    "record_accepted",
    # OrderCase.declined: confirmation_sent -> change_review, the customer
    # did not agree to the confirmation (ticket 28, dw_sales ADR 0011).
    "record_declined",
]

# Where an intent may lead, by who wrote the message and the case's kind and
# status: one table, a row per move, never a branch. Anything else proposes
# nothing, and Sales reads the message. A customer keeping their PO as it is
# does not accept the correction asked (`rejects`); one agreeing to it
# (`accepts`) leaves Sales to correct it: both resume the review, which
# disposes no finding.
INTENT_STEPS: Final[Mapping[tuple[Author, str, str, ThreadIntent], ProposedStep]] = (
    MappingProxyType(
        {
            ("customer", "quote", "spec_discussion", "accepts"): "settle_spec",
            ("customer", "quote", "spec_discussion", "rejects"): ("decline_customer_rejected_spec"),
            ("customer", "order", "correction_requested", "rejects"): "resume_review",
            ("customer", "order", "correction_requested", "accepts"): "resume_review",
            ("customer", "order", "correction_requested", "sends_po"): "await_revised_po",
            # The customer's answer to the confirmation (ADR 0011): a person
            # records it beside the quoted sentences, never DW1.
            ("customer", "order", "confirmation_sent", "accepts"): "record_accepted",
            ("customer", "order", "confirmation_sent", "rejects"): "record_declined",
            # Sales asked the customer, by mail: the case waits on them, the
            # wait the `waiting_customer` follow-up watches.
            ("sales", "order", "in_review", "asks"): "request_correction",
            ("sales", "quote", "design_replied", "asks"): "discuss_spec",
        }
    )
)


def proposed_step(
    author: Author, case_kind: str, status: str, reading: ReplyReading | None
) -> ProposedStep | None:
    """The step a message ``author`` wrote proposes for a ``case_kind`` case
    in ``status``, or None: no reading, an unread one, no row for any of its
    intents, or intents pointing at two different steps (only one can be
    taken, and which is a person's to say)."""
    if reading is None:
        return None
    steps = {
        step
        for intent in reading.kinds
        if (step := INTENT_STEPS.get((author, case_kind, status, intent))) is not None
    }
    return steps.pop() if len(steps) == 1 else None
