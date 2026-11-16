"""A card for a mail nothing else read (ticket 33, rebuilt under dw_sales ADR
0014; ADR 0012 decision 2's third use).

A message no reader, thread or model routed anywhere goes to Sales as
``other``, and a person reads it from nothing. Where the tenant turns the
step on (`ModelStep.TRIAGE_CARD`), such a message carries a card in the
inbox. The card is advice: the message stays routed ``other`` until a person
acts on it.

- **What it seems to be** is one structured call under the tenant's served
  ``mail-kinds`` skill: one of the kinds that version names, or none. The
  model gives a kind and the numbers the mail quotes; never a route, a case,
  a customer or a step.
- **Which case it seems to concern** is code's: the numbers code locates in
  the mail and resolves against the SENDER's customer's records only
  (`message_intent.IntentReader.resolve`, the one answer to "which record is
  this number"); the card names a case only where they lead to exactly one
  live order case (acceptance 1).
- **The one step it suggests** is code's too: the route the skill maps the
  kind onto (`mail_kinds.ROUTES`), where that route is a move a person can
  make on a routed message (`TRIAGE_STEPS`): routing it again with that
  reason, or, for ``reply_to_case`` with the card's case, attaching it to
  that case as a reply. A kind whose route only a document opens (``po``,
  ``quote_request``, ``design_reply``) or ``other`` suggests no step.
- **A person decides** (`CardVerdict`): takes the step as suggested,
  changes it to another legal step, or dismisses the card. Each decision is
  a labelled case of the step (`labelled_cases.triage_label`), so the step
  is measured on real work like every other.
"""

from __future__ import annotations

import uuid
from typing import Final, Literal, Self, cast, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.message_intent import (
    MAX_REFERENCES,
    IntentKind,
    KindName,
    ResolvedReference,
)

__all__ = [
    "TRIAGE_STEPS",
    "CardDecision",
    "CardVerdict",
    "TriageCard",
    "TriageStep",
    "card_case",
    "card_step",
]

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_VERSION = r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$"

# The moves a person may make from a card: the routes of the closed set that
# route a message to Sales with a reason of their own (the `RoutingReason`
# rows of `order_intake.INTENT_ROUTES` but ``other``; a test holds the two
# together). ``reply_to_case`` with the card's case attaches the message to
# that case instead.
TriageStep = Literal[
    "reply_to_case",
    "delivery_change",
    "complaint",
    "sample_request",
    "portal_notice",
]
TRIAGE_STEPS: Final[frozenset[str]] = frozenset(get_args(TriageStep))
# What a person did with the card.
CardDecision = Literal["taken", "changed", "dismissed"]


def card_step(route: IntentKind | None) -> TriageStep | None:
    """The one step a card suggests for a kind the skill maps onto
    ``route``: the route itself where a person can take it on a routed
    message, else none (module docstring)."""
    return cast("TriageStep", route) if route in TRIAGE_STEPS else None


def card_case(references: tuple[ResolvedReference, ...]) -> uuid.UUID | None:
    """The case a card names: the one live order case the resolved numbers
    lead to; none where they lead to none or to several (never a guess)."""
    cases = {r.order_case_id for r in references if r.order_case_id is not None}
    return next(iter(cases)) if len(cases) == 1 else None


class CardVerdict(BaseModel):
    """What a person did with a card, and when."""

    model_config = _FROZEN

    decision: CardDecision
    # The step taken; None for a dismissed card.
    step: TriageStep | None
    # The case the message was attached to: only the card's own, and only
    # with ``reply_to_case``.
    case_id: uuid.UUID | None = None
    by: uuid.UUID
    at: AwareDatetime

    @model_validator(mode="after")
    def _a_step_unless_dismissed(self) -> Self:
        if (self.decision == "dismissed") != (self.step is None):
            raise ValueError("a decision takes a step exactly when it is not a dismissal")
        if self.case_id is not None and self.step != "reply_to_case":
            raise ValueError("only a reply is attached to a case")
        return self


class TriageCard(BaseModel):
    """The card a message routed ``other`` carries (module docstring): the
    call's stamp, what the model read, what code resolved and suggests, and
    the person's decision once there is one."""

    model_config = _FROZEN

    prompt: str = Field(pattern=r"^[a-z][a-z0-9_.]*@\d+\.\d+\.\d+$")
    model_profile: str = Field(min_length=1, max_length=64)
    route: str = Field(min_length=1, max_length=64)
    rules: str = Field(pattern=_VERSION)
    # The version of the mail-kinds skill it was read with.
    skill: str = Field(pattern=r"^[a-z][a-z0-9_]*@\d+\.\d+\.\d+$")
    # The kind the model read, one the skill names; None where it named none.
    kind: KindName | None = None
    # The skill's words for that kind, where it gives some.
    kind_label: str | None = Field(default=None, min_length=1, max_length=60)
    # The route the skill maps the kind onto.
    routed_as: IntentKind | None = None
    # The numbers code located in the mail and resolved against the sender's
    # customer's records.
    references: tuple[ResolvedReference, ...] = Field(default=(), max_length=MAX_REFERENCES)
    # The one live order case those numbers lead to.
    case_id: uuid.UUID | None = None
    # The one step suggested (`card_step`).
    step: TriageStep | None = None
    decided: CardVerdict | None = None

    @model_validator(mode="after")
    def _code_derived_what_it_holds(self) -> Self:
        if (self.kind is None) != (self.routed_as is None):
            raise ValueError("a card names a route exactly when it names a kind")
        if self.kind_label is not None and self.kind is None:
            raise ValueError("only a kind has a label")
        if self.step != card_step(self.routed_as):
            raise ValueError("a card's step is its kind's route where a person can take it")
        if self.case_id != card_case(self.references):
            raise ValueError("a card's case is the one its resolved numbers lead to")
        decided = self.decided
        if decided is not None:
            if decided.case_id is not None and decided.case_id != self.case_id:
                raise ValueError("a message is attached only to the case its card names")
            taken = (decided.step, decided.case_id) == self.suggested
            if (decided.decision == "taken") != taken and decided.decision != "dismissed":
                raise ValueError("a card is taken as suggested, or changed to another step")
        return self

    @property
    def suggested(self) -> tuple[TriageStep | None, uuid.UUID | None]:
        """The step suggested and the case it would attach the message to."""
        return self.step, self.case_id if self.step == "reply_to_case" else None

    def proposal(self) -> dict[str, str | None]:
        """What the model's reading proposed, as a labelled case holds it."""
        step, case_id = self.suggested
        return {
            "kind": self.kind,
            "step": step,
            "case_id": None if case_id is None else str(case_id),
        }
