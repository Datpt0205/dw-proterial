"""Which results apply themselves, and at what measured error (dw_sales ADR
0015, decided 2026-11-16; ticket 44).

The method is the research note's (`docs/research/2026-11-16-less-human-
review.md`, section 2): code checks the result as today; a result also needs
a confidence (`DescriptionReading.confidence`, from the call's token
probabilities) at or above a threshold set on the tenant's own labelled cases
(ticket 43), such that the share of wrong results among those that clear it
stays at or below the tenant's target with confidence 1 - `DELTA`. Below it,
with any check failing, or with no threshold, a person decides, as before.

Everything here is code's and pure:

- **The tier of each step** (`STEP_TIERS`) is what the step's effect is, so it
  is not configuration: a reading, classification, link or unsent draft
  applies itself (T0, `Tier.APPLIES_ITSELF`); an internal hand-off or a move
  into someone's queue does at a stricter target (T1, `Tier.HAND_OFF`);
  anything sent, any Bravo write, a price, a date given to a customer or an
  approval never does (T2, `Tier.PERSON_APPROVES`). A step left out of the
  table is T2: fail closed.
- **The threshold** (`conformal_threshold`): Learn-then-Test with fixed-
  sequence testing. Thresholds are scanned from strict to loose over the
  labelled scores; each is tested with the exact (Clopper-Pearson) upper bound
  on the error among the cases it accepts, which is the finite-sample
  correction (a plug-in error rate on 20 cases would certify 5% from 20
  confirmations; the bound needs `cases_needed` of them: 59 at 5%, 149 at 2%,
  299 at 1%). The scan starts at the first threshold that accepts that many,
  the fewest that could certify the target at all, and stops at the first
  that fails; the last that passed is the threshold. Fewer labelled cases
  than that: no threshold, and nothing applies itself.
- **The audits** (`in_audit_sample`, `audit_stopped`): a share of what would
  apply itself goes to the case's person instead, chosen by a hash of the
  item, so the same item is always or never sampled and nobody can tell from
  the screen which it was. Their decisions are labelled cases like any other,
  and count with every undo of an applied result.
  When the exact lower bound on the audited error exceeds the target, the
  step is stopped: what clears the threshold is logged as shadow and goes to
  a person, until a new prompt or model version is measured from the start.
- **The gate** (`gate_route`) puts the three together for one result.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.description_reading import GateRoute
from dw_sales.domain.labelled_cases import Verdict
from dw_sales.domain.order_checks import Autonomy, ModelStep

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# The chance the threshold's guarantee does not hold (the research note's
# δ). The statistics' own constant, not a tenant's: the tenant sets the
# target, and a looser δ would only make the target mean less.
DELTA: Final = 0.05


class Tier(StrEnum):
    """What a step's effect is, and so whether its result may apply itself."""

    # T0: reversible and internal (reading, classifying, linking a mail to a
    # case, an unsent draft, a reminder).
    APPLIES_ITSELF = "applies_itself"
    # T1: internal, but someone else then acts on it (a hand-off to PC, QA or
    # Design, a move into another person's queue), at a stricter target.
    HAND_OFF = "hand_off"
    # T2: irreversible or outside DW (anything sent, any Bravo write, prices,
    # dates given to a customer, approvals): never automatic.
    PERSON_APPROVES = "person_approves"


STEP_TIERS: Final[Mapping[ModelStep, Tier]] = MappingProxyType(
    {
        # A line's PRV code read from its description: a reading into the
        # case, undone in one click; the Bravo file is still approved.
        ModelStep.DESCRIPTION_ATTRIBUTES: Tier.APPLIES_ITSELF,
        ModelStep.MESSAGE_INTENT: Tier.APPLIES_ITSELF,
        ModelStep.RFQ_EXTRACTION: Tier.APPLIES_ITSELF,
        ModelStep.REPLY_INTENT: Tier.APPLIES_ITSELF,
        ModelStep.THREAD_AGENT: Tier.APPLIES_ITSELF,
        ModelStep.SKILL_INTENTS: Tier.APPLIES_ITSELF,
        # The same classification as the message intent's, by the company's
        # kinds; where the mail goes is still a route code holds (ticket 42).
        ModelStep.SKILL_MAIL_KINDS: Tier.APPLIES_ITSELF,
        # The same request reading as ticket 29's, by the company's forms;
        # every value is still found at its cell and flagged (ticket 42).
        ModelStep.SKILL_DOCUMENT_FORMS: Tier.APPLIES_ITSELF,
        # A card that suggests; the message moves only when a person takes
        # it (ticket 33).
        ModelStep.TRIAGE_CARD: Tier.APPLIES_ITSELF,
        # Values of a PO written in the mail's body, read into the case.
        ModelStep.PO_BODY_EXTRACTION: Tier.APPLIES_ITSELF,
        # A draft nobody has sent; sending is a person's.
        ModelStep.REPLY_DRAFT: Tier.APPLIES_ITSELF,
        # The same draft, worded by the company's kinds (ticket 42 family 5).
        ModelStep.SKILL_REPLY_DRAFTS: Tier.APPLIES_ITSELF,
        # Work put in PC's, QA's or Design's hands.
        ModelStep.REQUEST_HANDOFF: Tier.HAND_OFF,
        # The same hand-off, by the company's kinds; its team is still one
        # code holds (ticket 42 family 5).
        ModelStep.SKILL_HANDOFFS: Tier.HAND_OFF,
        # A layout, once approved, reads every later PO of the form: an
        # approval (dw_sales ticket 30).
        ModelStep.LAYOUT_PROPOSAL: Tier.PERSON_APPROVES,
        # A SalesOrder file goes to Bravo only once a person approved it
        # (ADR 0026), whatever filled it (ticket 41).
        ModelStep.SALESORDER_SKILL: Tier.PERSON_APPROVES,
        # A change to what the customer was confirmed, line by line by a
        # person (dw_sales ADR 0010).
        ModelStep.CHANGE_REQUEST: Tier.PERSON_APPROVES,
    }
)


def tier_of(step: ModelStep) -> Tier:
    """The step's tier; a step the table does not name never applies itself."""
    return STEP_TIERS.get(step, Tier.PERSON_APPROVES)


def target_error(tier: Tier, autonomy: Autonomy) -> float | None:
    """The tenant's target error for ``tier``; None for a tier that never
    applies itself."""
    match tier:
        case Tier.APPLIES_ITSELF:
            return autonomy.applies_itself_error
        case Tier.HAND_OFF:
            return autonomy.hand_off_error
        case Tier.PERSON_APPROVES:
            return None


# ------------------------------------------------------------- statistics --


def cases_needed(alpha: float, delta: float = DELTA) -> int:
    """The fewest accepted cases, none of them wrong, whose exact upper bound
    on the error is at most ``alpha``: 59 at 5%, 149 at 2%, 299 at 1%."""
    return math.ceil(math.log(delta) / math.log1p(-alpha))


def _binomial_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p), summed in log space."""
    if k < 0:
        return 0.0
    if k >= n or p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    log_p, log_q = math.log(p), math.log1p(-p)
    total = 0.0
    for i in range(k + 1):
        log_term = (
            math.lgamma(n + 1)
            - math.lgamma(i + 1)
            - math.lgamma(n - i + 1)
            + i * log_p
            + (n - i) * log_q
        )
        total += math.exp(log_term)
    return min(1.0, total)


def upper_bound(errors: int, cases: int, delta: float = DELTA) -> float:
    """The exact one-sided (Clopper-Pearson) upper bound on the error rate at
    confidence 1 - ``delta``, from ``errors`` among ``cases``."""
    if cases <= 0 or errors >= cases:
        return 1.0
    low, high = errors / cases, 1.0
    for _ in range(100):
        middle = (low + high) / 2
        if _binomial_cdf(errors, cases, middle) > delta:
            low = middle
        else:
            high = middle
    return high


def lower_bound(errors: int, cases: int, delta: float = DELTA) -> float:
    """The exact one-sided (Clopper-Pearson) lower bound on the error rate at
    confidence 1 - ``delta``, from ``errors`` among ``cases``."""
    if cases <= 0 or errors <= 0:
        return 0.0
    low, high = 0.0, errors / cases
    for _ in range(100):
        middle = (low + high) / 2
        # P(X >= errors) at ``middle``, rising with it.
        if 1.0 - _binomial_cdf(errors - 1, cases, middle) < delta:
            low = middle
        else:
            high = middle
    return low


@dataclass(frozen=True, slots=True)
class ScoredCase:
    """One labelled case as the threshold reads it: the result's confidence,
    and whether the person kept it as proposed."""

    confidence: float
    correct: bool


@dataclass(frozen=True, slots=True)
class Threshold:
    """A certified threshold: the score, and the cases it accepts and how
    many of them were wrong."""

    score: float
    accepted: int
    errors: int


def conformal_threshold(
    cases: Sequence[ScoredCase], alpha: float, delta: float = DELTA
) -> Threshold | None:
    """The loosest threshold whose accepted cases certify ``alpha`` (module
    docstring); None with too few cases, or when the first threshold that
    could certify it does not."""
    needed = cases_needed(alpha, delta)
    if len(cases) < needed:
        return None
    by_score: dict[float, list[bool]] = {}
    for case in cases:
        by_score.setdefault(case.confidence, []).append(case.correct)
    found: Threshold | None = None
    accepted = errors = 0
    for score in sorted(by_score, reverse=True):
        verdicts = by_score[score]
        accepted += len(verdicts)
        errors += sum(1 for correct in verdicts if not correct)
        if accepted < needed:
            continue
        if upper_bound(errors, accepted, delta) > alpha:
            break
        found = Threshold(score=score, accepted=accepted, errors=errors)
    return found


def audit_stopped(audits: int, errors: int, alpha: float, delta: float = DELTA) -> bool:
    """Whether the audited error is above ``alpha`` with confidence 1 -
    ``delta``: its exact lower bound exceeds it."""
    return lower_bound(errors, audits, delta) > alpha


def in_audit_sample(item_key: str, share: float) -> bool:
    """Whether the item is in the audit sample: the same answer for the same
    item every time, about ``share`` of all items."""
    digest = hashlib.sha256(item_key.encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < share


# ------------------------------------------------------------ the measure --


class LabelledScore(BaseModel):
    """A labelled case of a gated result, as the measure reads it."""

    model_config = _FROZEN

    confidence: float | None = Field(ge=0.0, le=1.0)
    verdict: Verdict
    gate: GateRoute


class StepThreshold(BaseModel):
    """One step's threshold for a tenant's workspace, for the prompt and the
    model profile its labelled cases were read with: a new version of either
    starts from no cases (ADR 0015 "Method"). Kept with what it was set from,
    so the head sees the numbers behind it."""

    model_config = _FROZEN

    step: ModelStep
    prompt: str = Field(pattern=r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$")
    model_profile: str = Field(min_length=1, max_length=64)
    tier: Tier
    # The target it was set at, and the cases a zero-error sample needs.
    target: float = Field(gt=0.0, le=1.0)
    needed: int = Field(ge=1)
    # The labelled cases with a confidence it was set from.
    cases: int = Field(ge=0)
    # The threshold, and the cases it accepts and the wrong among them; None
    # when none is certified (too few cases, or too many wrong).
    threshold: float | None = Field(ge=0.0, le=1.0)
    accepted: int = Field(ge=0)
    errors: int = Field(ge=0)
    # The audits decided so far (the blind sample, and any person's decision
    # on a result DW applied, an undo included), and the wrong among them.
    audits: int = Field(ge=0)
    audit_errors: int = Field(ge=0)
    # The audited error is above the target (`audit_stopped`).
    stopped: bool
    computed_at: AwareDatetime

    @model_validator(mode="after")
    def _holds_together(self) -> Self:
        if self.tier is Tier.PERSON_APPROVES:
            raise ValueError("a step a person approves has no threshold")
        if self.errors > self.accepted or self.accepted > self.cases:
            raise ValueError("the accepted cases are some of the cases")
        if self.audit_errors > self.audits:
            raise ValueError("the wrong audits are some of the audits")
        if (self.threshold is None) != (self.accepted == 0):
            raise ValueError("a threshold accepts cases, and only a threshold does")
        return self

    @property
    def applying(self) -> bool:
        """Whether a result that clears it applies itself now."""
        return self.threshold is not None and not self.stopped

    @property
    def audited_error(self) -> float | None:
        return self.audit_errors / self.audits if self.audits else None


def measure(
    step: ModelStep,
    prompt: str,
    model_profile: str,
    labels: Sequence[LabelledScore],
    autonomy: Autonomy,
    at: AwareDatetime,
) -> StepThreshold | None:
    """The step's threshold from its labelled cases of one prompt and model
    profile; None for a step that never applies itself (T2)."""
    tier = tier_of(step)
    target = target_error(tier, autonomy)
    if target is None:
        return None
    scored = [
        ScoredCase(label.confidence, label.verdict == "confirmed")
        for label in labels
        if label.confidence is not None
    ]
    found = conformal_threshold(scored, target)
    # The blind audits, and every decision a person took on a result DW
    # applied (an undo, or a code confirmed again): both are a person's
    # verdict on what cleared the threshold. The second is not blind and
    # leans to the errors people notice, which can only stop a step sooner.
    audits = [label for label in labels if label.gate in ("audit", "applied")]
    audit_errors = sum(1 for label in audits if label.verdict != "confirmed")
    return StepThreshold(
        step=step,
        prompt=prompt,
        model_profile=model_profile,
        tier=tier,
        target=target,
        needed=cases_needed(target),
        cases=len(scored),
        threshold=None if found is None else found.score,
        accepted=0 if found is None else found.accepted,
        errors=0 if found is None else found.errors,
        audits=len(audits),
        audit_errors=audit_errors,
        stopped=audit_stopped(len(audits), audit_errors, target),
        computed_at=at,
    )


# ---------------------------------------------------------------- the gate --


def gate_route(
    step: ModelStep,
    confidence: float | None,
    threshold: StepThreshold | None,
    *,
    item_key: str,
    audit_share: float,
) -> GateRoute:
    """What happens to one result whose code checks passed: a person decides
    it unless its step may apply itself, it has a confidence, and that clears
    a certified threshold for the step (``threshold``: the one for the prompt
    and profile the result was read with). Cleared while the step is stopped,
    it is logged as shadow; sampled for audit, a person decides it unaware."""
    if tier_of(step) is Tier.PERSON_APPROVES:
        return "person"
    if (
        confidence is None
        or threshold is None
        or threshold.step is not step
        or threshold.threshold is None
        or confidence < threshold.threshold
    ):
        return "person"
    if threshold.stopped:
        return "shadow"
    if in_audit_sample(item_key, audit_share):
        return "audit"
    return "applied"
