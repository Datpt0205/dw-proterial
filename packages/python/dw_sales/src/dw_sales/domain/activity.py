"""What DW1 did at each model step, kept after the run (slice 3, "AI activity").

Every model step already stamps what it did on what it produced: a line's
`DescriptionReading`, a message's `IntentReading`, `CaseReply.reading`,
`Handoff`, `LayoutPrefill`, a quote's `RequestReading`. Those stamps are the
owner of WHAT was read and are kept on the case or the message. What they do
not hold, and what an activity page needs, is:

- **when** the step ran and **how long** its calls took, and on **which
  model** (a stamp names the profile and the route, not the model the profile
  routed to, and the platform keeps a call's latency in telemetry only);
- the step's outcome in one shape across the six steps, queryable by step and
  time: handled automatically, or left to a person, and why (a reason code);
- a step that ran and left **no stamp** (a request a model could not read is
  routed with no case to stamp): without a row of its own, a failure would be
  invisible and the automatic share would only count successes.

`StepOutcome` is that row: one per item a step handled (a line for the
description reading, the message otherwise). It holds ids, codes, counts and
times, never a value read and never a prompt or a model's words: the values
stay where they were stamped, and a reader joins them from there.

`outcomes_of` derives the rows from the stamps and the timed calls, after the
step, where the disposition and the case are written (`InboxProcessing`), so
the rows commit or roll back with them. It never raises on what it reads: a
reason code outside its shape is recorded as ``other``, because a record of
what happened must not stop the thing that happened.
"""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.description_reading import DescriptionReading
from dw_sales.domain.dispositions import CaseKind, MessageDisposition
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import MappingStatus, OrderCase
from dw_sales.domain.quotes import QuoteCase

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# What code made of the step's answer: taken (each of its checks passed),
# refused by a check (the reason code says which), or no usable answer.
StepResult = Literal["accepted", "refused", "unavailable"]

_CODE: Final = re.compile(r"^[a-z_]{1,40}$")
# A reason code that does not fit the shape a row holds.
OTHER_REASON: Final = "other"
# A description reading code accepted whose attributes fit no item: the line
# is unmapped, for a person to map, as it would be without the model.
NO_ITEM_FITS: Final = "no_item_fits"
# A step whose calls ran and that left no stamp on anything the message ended
# in (a request no model reading could extract is routed with no case).
NOT_USED: Final = "not_used"

_HANDOFF_RESULT: Final[Mapping[str, StepResult]] = {
    "read": "accepted",
    "nothing_located": "refused",
    "unavailable": "unavailable",
}
_PREFILL_RESULT: Final[Mapping[str, StepResult]] = {
    "proposed": "accepted",
    "refused": "refused",
    "unavailable": "unavailable",
}

# Which lane a step belongs to when the row names no case (a routed message):
# a hand-off and a layout are about orders, a request read is a quotation.
_STEP_LANE: Final[Mapping[ModelStep, CaseKind]] = {
    ModelStep.RFQ_EXTRACTION: CaseKind.QUOTE,
    ModelStep.REQUEST_HANDOFF: CaseKind.ORDER,
    ModelStep.LAYOUT_PROPOSAL: CaseKind.ORDER,
}


@dataclass(frozen=True, slots=True)
class ModelCall:
    """One call a step made to a model, as the door to the model timed it."""

    # `<prompt_id>@<version>`, as the stamps write it.
    prompt: str
    # The profile the call ran on, and the model it routed the call to (None
    # when that could not be resolved).
    model_profile: str
    model: str | None
    duration_ms: float
    # False: no usable answer (`ModelUnavailableError`).
    answered: bool


class StepOutcome(BaseModel):
    """One item a model step handled: what code made of the answer, whether
    DW1 carried it or a person does, and the calls behind it.

    ``calls`` and ``duration_ms`` are the step's calls for the whole message,
    held on the first row of that (message, step) only; the step's other rows
    hold 0 and None, so no sum or percentile counts a call twice.
    """

    model_config = _FROZEN

    outcome_id: uuid.UUID
    occurred_at: AwareDatetime
    message_id: str = Field(pattern=r"^[!-~]{1,512}$")
    # The case's kind when it names a case; the step's own lane otherwise,
    # None for a step of either lane (the message's intent).
    lane: CaseKind | None
    case_id: uuid.UUID | None
    line_no: int | None = Field(ge=1, le=99_999)
    step: ModelStep
    result: StepResult
    # DW1 carried the item: its reading stands for a person to confirm, as
    # every model value does (dw_sales ADR 0005). False: a person does the
    # step's work by hand.
    automatic: bool
    # Why a person does it, when a check refused the answer or code found
    # nothing to use in it. None for an automatic item and for no answer.
    reason_code: str | None = Field(pattern=_CODE.pattern)
    # Values code refused inside an item it took, by reason: counts only.
    refusals: Mapping[str, int]
    prompt: str = Field(pattern=r"^[a-z][a-z0-9_.]*@\d+\.\d+\.\d+$")
    model_profile: str = Field(min_length=1, max_length=64)
    model: str | None = Field(min_length=1, max_length=200)
    calls: int = Field(ge=0, le=1000)
    duration_ms: int | None = Field(ge=0)

    @model_validator(mode="after")
    def _says_what_happened(self) -> Self:
        if self.case_id is not None and self.lane is None:
            raise ValueError("a row on a case names the case's kind")
        if self.automatic and (self.result != "accepted" or self.reason_code is not None):
            raise ValueError("an automatic item was accepted and has no reason")
        if self.result == "refused" and self.reason_code is None:
            raise ValueError("a refused item names why")
        if self.result == "unavailable" and (self.automatic or self.reason_code is not None):
            raise ValueError("an item with no answer went to a person, with no reason")
        if (self.calls == 0) != (self.duration_ms is None):
            raise ValueError("a duration is the duration of calls")
        for code, count in self.refusals.items():
            if _CODE.fullmatch(code) is None or count < 1:
                raise ValueError("a refusal is a reason code and a count")
        return self

    @property
    def to_person(self) -> bool:
        return not self.automatic


# --------------------------------------------------------------- derivation --


@dataclass(frozen=True, slots=True)
class _Stamped:
    """One item as a stamp says it went, before its row is made."""

    step: ModelStep
    prompt: str
    model_profile: str
    result: StepResult
    automatic: bool
    reason_code: str | None = None
    lane: CaseKind | None = None
    case_id: uuid.UUID | None = None
    line_no: int | None = None
    refusals: Mapping[str, int] = field(default_factory=dict)


def _code(value: str) -> str:
    return value if _CODE.fullmatch(value) else OTHER_REASON


def _counts(refused: Mapping[str, int]) -> dict[str, int]:
    kept: Counter[str] = Counter()
    for code, count in refused.items():
        if count > 0:
            kept[_code(code)] += count
    return dict(kept)


def _reading_row(
    reading: DescriptionReading,
    *,
    mapped: bool,
    lane: CaseKind,
    case_id: uuid.UUID,
    line_no: int,
) -> _Stamped:
    """A line's description reading: read and mapped is DW1's; read and
    fitting no item, or refused by a check, or unanswered, is a person's."""
    if reading.outcome == "read":
        result: StepResult = "accepted"
        reason = None if mapped else NO_ITEM_FITS
    elif reading.outcome == "not_understood":
        result, reason = "refused", _code(reading.reason or OTHER_REASON)
    else:
        result, reason = "unavailable", None
    return _Stamped(
        ModelStep.DESCRIPTION_ATTRIBUTES,
        reading.prompt,
        reading.model_profile,
        result,
        automatic=result == "accepted" and mapped,
        reason_code=reason,
        lane=lane,
        case_id=case_id,
        line_no=line_no,
    )


def _from_disposition(disposition: MessageDisposition) -> list[_Stamped]:
    lane, case_id = disposition.case_kind, disposition.case_id
    found: list[_Stamped] = []
    intent = disposition.reading
    if intent is not None:
        read = intent.outcome == "read"
        found.append(
            _Stamped(
                ModelStep.MESSAGE_INTENT,
                intent.prompt,
                intent.model_profile,
                "accepted" if read else "unavailable",
                automatic=read,
                lane=lane,
                case_id=case_id,
            )
        )
    reply = disposition.reply.reading if disposition.reply is not None else None
    if reply is not None:
        read = reply.outcome == "read"
        found.append(
            _Stamped(
                ModelStep.REPLY_INTENT,
                reply.prompt,
                reply.model_profile,
                "accepted" if read else "unavailable",
                automatic=read,
                lane=lane,
                case_id=case_id,
            )
        )
    handoff = disposition.handoff
    if handoff is not None:
        result = _HANDOFF_RESULT[handoff.outcome]
        found.append(
            _Stamped(
                ModelStep.REQUEST_HANDOFF,
                handoff.prompt,
                handoff.model_profile,
                result,
                automatic=result == "accepted",
                reason_code="nothing_located" if result == "refused" else None,
                lane=CaseKind.ORDER,
                # The order the hand-off is about, when code resolved one.
                case_id=handoff.order_case_id,
                refusals=_counts(handoff.refused),
            )
        )
    prefill = disposition.layout_prefill
    if prefill is not None:
        result = _PREFILL_RESULT[prefill.outcome]
        found.append(
            _Stamped(
                ModelStep.LAYOUT_PROPOSAL,
                prefill.prompt,
                prefill.model_profile,
                result,
                automatic=result == "accepted",
                reason_code=(
                    _code(prefill.problems[0] if prefill.problems else "refused")
                    if result == "refused"
                    else None
                ),
                lane=CaseKind.ORDER,
            )
        )
    return found


def _from_case(
    disposition: MessageDisposition, case: OrderCase | QuoteCase | None
) -> list[_Stamped]:
    """The steps a case holds the stamps of, for the message that made them
    (a later message on the case, a revision or a reply, did not read them)."""
    found: list[_Stamped] = []
    if isinstance(case, OrderCase) and case.message_id == disposition.message_id:
        for line in case.lines:
            reading = line.basis.description_reading
            if reading is not None:
                found.append(
                    _reading_row(
                        reading,
                        mapped=line.mapping.status is not MappingStatus.UNMAPPED,
                        lane=CaseKind.ORDER,
                        case_id=case.case_id,
                        line_no=line.line_no,
                    )
                )
    elif isinstance(case, QuoteCase) and case.request.message_id == disposition.message_id:
        request = case.request.reading
        if request is not None:
            found.append(
                _Stamped(
                    ModelStep.RFQ_EXTRACTION,
                    str(request.prompt),
                    request.model_profile,
                    "accepted",
                    automatic=True,
                    lane=CaseKind.QUOTE,
                    case_id=case.case_id,
                    refusals=_counts(request.refused),
                )
            )
        for item in case.request.document.items:
            reading = item.description_reading
            if reading is not None:
                found.append(
                    _reading_row(
                        reading,
                        mapped=bool(item.candidates),
                        lane=CaseKind.QUOTE,
                        case_id=case.case_id,
                        line_no=item.line_no,
                    )
                )
    return found


@dataclass(frozen=True, slots=True)
class _Timing:
    calls: int
    duration_ms: int | None
    model_profile: str
    model: str | None
    answered: bool


def _timings(calls: Iterable[ModelCall]) -> dict[str, _Timing]:
    by_prompt: dict[str, list[ModelCall]] = {}
    for call in calls:
        by_prompt.setdefault(call.prompt, []).append(call)
    timed: dict[str, _Timing] = {}
    for prompt, made in by_prompt.items():
        model = next((c.model for c in made if c.answered and c.model), None) or next(
            (c.model for c in made if c.model), None
        )
        timed[prompt] = _Timing(
            calls=len(made),
            duration_ms=round(sum(c.duration_ms for c in made)),
            model_profile=made[0].model_profile,
            model=model,
            answered=any(c.answered for c in made),
        )
    return timed


def outcomes_of(
    disposition: MessageDisposition,
    case: OrderCase | QuoteCase | None,
    calls: Sequence[ModelCall],
    *,
    steps_by_prompt: Mapping[str, ModelStep],
    at: AwareDatetime,
    new_id: Callable[[], uuid.UUID],
) -> tuple[StepOutcome, ...]:
    """The rows for one processed message: one per item each model step
    handled, from the stamps on ``disposition`` and ``case``, timed by
    ``calls`` (matched to a step by prompt). A step whose calls ran and that
    stamped nothing is a row of its own (``steps_by_prompt`` names it): not
    used, or not answered."""
    stamped = _from_disposition(disposition) + _from_case(disposition, case)
    timings = _timings(calls)
    claimed = {s.prompt for s in stamped}
    for prompt, unclaimed in timings.items():
        step = steps_by_prompt.get(prompt)
        if prompt in claimed or step is None:
            continue
        reason = disposition.reason.value if disposition.reason is not None else NOT_USED
        stamped.append(
            _Stamped(
                step,
                prompt,
                unclaimed.model_profile,
                "refused" if unclaimed.answered else "unavailable",
                automatic=False,
                reason_code=_code(reason) if unclaimed.answered else None,
                lane=disposition.case_kind or _STEP_LANE.get(step),
                case_id=disposition.case_id,
            )
        )
    rows: list[StepOutcome] = []
    timed_once: set[str] = set()
    for item in stamped:
        timing = timings.get(item.prompt)
        first = timing is not None and item.prompt not in timed_once
        if first:
            timed_once.add(item.prompt)
        rows.append(
            StepOutcome(
                outcome_id=new_id(),
                occurred_at=at,
                message_id=disposition.message_id,
                lane=item.lane,
                case_id=item.case_id,
                line_no=item.line_no,
                step=item.step,
                result=item.result,
                automatic=item.automatic,
                reason_code=item.reason_code,
                refusals=item.refusals,
                prompt=item.prompt,
                model_profile=item.model_profile,
                model=timing.model if timing is not None else None,
                calls=timing.calls if first and timing is not None else 0,
                duration_ms=timing.duration_ms if first and timing is not None else None,
            )
        )
    return tuple(rows)


# -------------------------------------------------------------- the summary --


def percentile(values: Sequence[int], q: float) -> int | None:
    """The nearest-rank ``q`` percentile (0 < q <= 1) of ``values``; None for
    none. A value that occurred, never an interpolation between two."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


@dataclass(slots=True)
class StepTally:
    """One step's rows, counted: what the activity page and the process page
    show beside the step."""

    handled: int = 0
    automatic: int = 0
    # Of the items a person does: no answer at all.
    unavailable: int = 0
    # Reason codes, each occurrence once: an item's own reason, and the
    # values refused inside an item code took.
    reasons: Counter[str] = field(default_factory=Counter)
    # The step's duration per (message, step): the rows that hold one.
    durations: list[int] = field(default_factory=list)

    @property
    def to_person(self) -> int:
        return self.handled - self.automatic

    @property
    def automatic_share(self) -> float | None:
        """Automatic over handled; None when the step handled nothing."""
        return None if self.handled == 0 else self.automatic / self.handled

    def add(self, row: StepOutcome) -> None:
        self.handled += 1
        self.automatic += int(row.automatic)
        self.unavailable += int(row.result == "unavailable")
        if row.reason_code is not None:
            self.reasons[row.reason_code] += 1
        self.reasons.update(row.refusals)
        if row.duration_ms is not None:
            self.durations.append(row.duration_ms)


def tally(rows: Iterable[StepOutcome]) -> dict[ModelStep, StepTally]:
    """Every model step's tally over ``rows``, a step with none included."""
    tallies = {step: StepTally() for step in ModelStep}
    for row in rows:
        tallies[row.step].add(row)
    return tallies
