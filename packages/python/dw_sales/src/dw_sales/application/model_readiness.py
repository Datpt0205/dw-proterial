"""Whether a model step has earned its switch (dw_sales ADR 0005, addendum of
2026-10-23).

ADR 0005 lets a tenant turn a model step on "once that step's live eval meets
its bar". Until this module nothing checked that: the bars were constants in
the eval modules and the live results files on whoever ran the lane. Now:

- **One owner for the bars**: `BARS`, per `ModelStep`, with the prompt the
  step runs on, the dataset and golden grader that measure it, and the path
  of the metric in that grader's details. The eval modules read their bar
  from here (`bar_verdict`); nothing else states one.
- **A store of live measurements** (`sales.model_step_measurements`), written
  only by the live lane run with ``--attest`` (`ModelAttestation`, the lane
  `sales_model_attest`, audited as itself) and read through
  `ModelMeasurementsPort`.
- **Enforced where the effect happens**: `ModelReadiness.allows` is asked by
  every place that would call a model, and a rule version that turns a step
  on is refused by `ModelReadiness.refusal` when it is proposed and when it
  is decided (`application.rules`). A step is ready only when the latest
  measurement for the model the tenant's profile routes it to now
  (`StepModelPort`) and the prompt version it pins now passed, at today's bar
  and on today's metric. Anything else, an unreadable store included, is not
  ready: the step does what it does when it is off, and the log says why.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_kernel.errors import ConflictError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.domain.audit import AuditEvent, lane_audit_event, system_actor_label
from dw_sales.application.artifact_content import local_time
from dw_sales.application.handoffs import REQUEST_HANDOFF
from dw_sales.application.layouts import LAYOUT_PROPOSAL
from dw_sales.application.message_intent import MESSAGE_INTENT
from dw_sales.application.model_reading import DESCRIPTION_ATTRIBUTES, PromptRef
from dw_sales.application.ports import SalesScope
from dw_sales.application.reply_intent import REPLY_INTENT
from dw_sales.application.rfq_reading import RFQ_EXTRACTION
from dw_sales.domain.order_checks import ModelStep, OrderRules

_LOG = logging.getLogger("dw_sales.model")

# The lane that records a measurement: its audit actor is `system:<lane>`
# (ADR 0011), and so is a row's `recorded_by`.
ATTEST_LANE: Final = "sales_model_attest"
# The rule a refusal names when a version turns on a step that is not ready.
MODEL_BAR_UNMET: Final = "model_bar_unmet"


@dataclass(frozen=True, slots=True)
class StepBar:
    """What a step's live eval must show before its switch does anything."""

    # The share the metric must reach.
    bar: float
    # Where the golden grader's details hold the metric, dot-separated.
    metric: str
    # The prompt the step runs on: a measurement of another version is not
    # one of this step as it runs.
    prompt: PromptRef
    # The dataset that measures the step, and its golden case's grader.
    dataset: str
    grader: str


# Each step's bar. Set by Đạt where the comment says so; the rest are the
# proposed bars the tickets reported, now enforced (addendum of 2026-10-23).
BARS: Final[Mapping[ModelStep, StepBar]] = MappingProxyType(
    {
        # Ticket 28; set by Đạt on 2026-10-15 at 70% (from a proposed 80%,
        # against 71.1% measured on the local Qwen 9B, thinking off): the gold
        # code among the candidates for the VI/EN golden lines. A miss goes to
        # a person, never to a wrong code.
        ModelStep.DESCRIPTION_ATTRIBUTES: StepBar(
            0.70,
            "vi_en.gold_in_candidates",
            DESCRIPTION_ATTRIBUTES,
            "sales_descriptions",
            "sales.description_golden",
        ),
        # Ticket 31: the golden residue read as its kind.
        ModelStep.MESSAGE_INTENT: StepBar(
            0.90, "all.kind_accuracy", MESSAGE_INTENT, "sales_intent", "sales.intent_golden"
        ),
        # Ticket 29: the stated VI/EN values read into the right field.
        ModelStep.RFQ_EXTRACTION: StepBar(
            0.85, "vi_en.right_field", RFQ_EXTRACTION, "sales_rfq", "sales.rfq_golden"
        ),
        # Ticket 32: the golden replies other than conditional ones and
        # non-answers read as their kind, and none of those two read as
        # `accepts_spec` (the grader's own condition).
        ModelStep.REPLY_INTENT: StepBar(
            0.85, "bar_set.kind_accuracy", REPLY_INTENT, "sales_reply", "sales.reply_golden"
        ),
        # Ticket 33: the golden fields carried right.
        ModelStep.REQUEST_HANDOFF: StepBar(
            0.85, "all.right", REQUEST_HANDOFF, "sales_handoff", "sales.handoff_golden"
        ),
        # Ticket 30: the golden forms' fields mapped right before human edits,
        # and no accepted swap (the grader's own condition).
        ModelStep.LAYOUT_PROPOSAL: StepBar(
            0.90, "all.right", LAYOUT_PROPOSAL, "sales_layout", "sales.layout_golden"
        ),
    }
)


def step_measured_by(dataset_id: str) -> ModelStep | None:
    """The step a dataset measures, or None for a dataset that measures none."""
    return next((step for step, owner in BARS.items() if owner.dataset == dataset_id), None)


def _at(details: Mapping[str, Any], path: str) -> float:
    found: Any = details
    for part in path.split("."):
        found = found[part]
    return float(found)


def bar_verdict(
    step: ModelStep, details: Mapping[str, Any], *, holds: bool = True
) -> dict[str, object]:
    """A golden grader's verdict on its step's bar, read from the grader's own
    ``details`` at the metric's path. ``holds`` is any condition of the
    grader's own besides the share (no accepted swap, no false accept)."""
    owner = BARS[step]
    value = _at(details, owner.metric)
    return {
        "step": step.value,
        "metric": owner.metric,
        "value": value,
        "bar": owner.bar,
        "passed": holds and value >= owner.bar,
    }


# ------------------------------------------------------- the measurement --


class ModelMeasurement(BaseModel):
    """One live measurement of one step: a row of
    `sales.model_step_measurements`, whose CHECKs say the same."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    measurement_id: uuid.UUID
    step: ModelStep
    # The model the step was measured on: the profile route's `model`.
    model: str = Field(min_length=1, max_length=200)
    prompt: str = Field(pattern=r"^[a-z0-9_.]+@\d+\.\d+\.\d+$")
    metric: str = Field(pattern=r"^[a-z_]+(\.[a-z_]+)*$")
    value: float = Field(ge=0, le=1)
    # The bar when it was measured.
    bar: float = Field(ge=0, le=1)
    passed: bool
    # ``dataset_id@version`` the eval ran.
    dataset: str = Field(pattern=r"^[a-z0-9_]+@\d+\.\d+\.\d+$")
    measured_at: AwareDatetime
    recorded_by: str = Field(pattern=r"^system:[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def _a_pass_meets_its_bar(self) -> Self:
        if self.passed and self.value < self.bar:
            raise ValueError("a passing measurement is at or above its bar")
        return self


class ModelMeasurementsPort(Protocol):
    """The tenant's measurements, read under its RLS: never another's."""

    async def latest(
        self, scope: SalesScope, step: ModelStep, *, model: str, prompt: str
    ) -> ModelMeasurement | None:
        """The newest measurement of ``step`` on ``model`` and ``prompt``."""
        ...


class MeasurementLogPort(Protocol):
    """Where the attesting lane writes: the row and its audit event in one
    transaction, under the tenant's RLS. Append-only."""

    async def record(
        self, scope: SalesScope, measurement: ModelMeasurement, event: AuditEvent
    ) -> None: ...


class StepModelPort(Protocol):
    """The model a tenant's model steps run on now: the route DW1's profile
    resolves to for that tenant, read as the gateway reads it."""

    def model_for(self, tenant_id: uuid.UUID) -> str: ...


# ------------------------------------------------------------ readiness --

Reason = Literal["ready", "not_measured", "failed", "unreadable"]


@dataclass(frozen=True, slots=True)
class StepReadiness:
    step: ModelStep
    # None when it could not be resolved (`unreadable`).
    model: str | None
    prompt: str
    bar: float
    # The newest measurement on ``model`` and ``prompt``; None: none, or unreadable.
    latest: ModelMeasurement | None
    reason: Reason

    @property
    def ready(self) -> bool:
        return self.reason == "ready"


def _passes(owner: StepBar, latest: ModelMeasurement) -> bool:
    """A pass, at today's bar, on today's metric."""
    return latest.passed and latest.value >= owner.bar and latest.metric == owner.metric


@dataclass(frozen=True)
class ModelReadiness:
    """Implements `ModelStepGatePort`, and is what a rule version's proposal
    and decision ask about the steps it turns on."""

    measurements: ModelMeasurementsPort
    models: StepModelPort

    async def check(self, scope: SalesScope, step: ModelStep) -> StepReadiness:
        owner = BARS[step]
        prompt = str(owner.prompt)
        try:
            model = self.models.model_for(scope.tenant_id.value)
            latest = await self.measurements.latest(scope, step, model=model, prompt=prompt)
        except Exception as exc:
            _LOG.warning(
                "model step %s: measurements unreadable for tenant %s (%s)",
                step.value,
                scope.tenant_id.value,
                type(exc).__name__,
            )
            return StepReadiness(step, None, prompt, owner.bar, None, "unreadable")
        if latest is None:
            reason: Reason = "not_measured"
        else:
            reason = "ready" if _passes(owner, latest) else "failed"
        return StepReadiness(step, model, prompt, owner.bar, latest, reason)

    async def allows(self, scope: SalesScope, rules: OrderRules, step: ModelStep) -> bool:
        if not rules.model_assist.on(step):
            return False
        readiness = await self.check(scope, step)
        if not readiness.ready:
            # Ids and the reason only: the step runs as when it is off.
            _LOG.info(
                "model step %s on in %s but not used for tenant %s: %s (model %s, prompt %s)",
                step.value,
                rules.version,
                scope.tenant_id.value,
                readiness.reason,
                readiness.model,
                readiness.prompt,
            )
        return readiness.ready

    async def unready(
        self, scope: SalesScope, proposed: OrderRules, in_force: OrderRules
    ) -> list[StepReadiness]:
        """The steps ``proposed`` turns on (on in it, off in ``in_force``) that
        are not ready. Turning a step off, or keeping one on, is never listed
        here; a step kept on that is not ready is still not used (`allows`)."""
        turned_on = [
            step
            for step in ModelStep
            if proposed.model_assist.on(step) and not in_force.model_assist.on(step)
        ]
        return [r for r in [await self.check(scope, s) for s in turned_on] if not r.ready]


def refusal(unready: Sequence[StepReadiness]) -> ConflictError:
    """The 409 a version meets when it turns on the ``unready`` steps: each
    named with its bar, the model and prompt it runs on, and its latest
    measurement or "chưa đo"."""
    return ConflictError(
        "Chưa bật được bước có mô hình: "
        + "; ".join(_worded(r) for r in unready)
        + ". Một bước chỉ bật được khi lần đo trực tiếp gần nhất, trên mô hình và"
        " lời nhắc bước đó đang dùng, đạt ngưỡng. Tắt bước đó trong phiên bản này,"
        " hoặc đo lại (run_evals.py --live --attest) rồi đề xuất lại.",
        details={"rule": MODEL_BAR_UNMET, "steps": [_detail(r) for r in unready]},
    )


def _worded(readiness: StepReadiness) -> str:
    latest = readiness.latest
    if readiness.reason == "unreadable":
        measured = "không đọc được kết quả đo"
    elif latest is None:
        measured = "chưa đo"
    else:
        when = local_time(latest.measured_at).strftime("%H:%M %d/%m/%Y")
        measured = f"lần đo gần nhất {latest.value:.1%} lúc {when}, chưa đạt"
    return (
        f"«{readiness.step.value}» (ngưỡng {readiness.bar:.0%}, mô hình"
        f" {readiness.model or 'không xác định'}, lời nhắc {readiness.prompt}: {measured})"
    )


def _detail(readiness: StepReadiness) -> dict[str, object]:
    latest = readiness.latest
    return {
        "step": readiness.step.value,
        "bar": readiness.bar,
        "model": readiness.model,
        "prompt": readiness.prompt,
        "reason": readiness.reason,
        "latest": None
        if latest is None
        else {
            "value": latest.value,
            "passed": latest.passed,
            "measured_at": latest.measured_at.isoformat(),
        },
    }


# --------------------------------------------------------- attestation --


@dataclass(frozen=True)
class ModelAttestation:
    """Records a live eval's measurement of a step for one tenant: the lane
    `sales_model_attest`, which `scripts/run_evals.py --attest` runs."""

    log: MeasurementLogPort
    clock: UtcClock
    ids: IdGenerator

    async def attest(
        self,
        scope: SalesScope,
        step: ModelStep,
        *,
        model: str,
        value: float,
        held: bool,
        dataset: str,
    ) -> ModelMeasurement:
        """``value`` is the step's metric as the live run measured it, and
        ``held`` whether that run's own verdict passed (the grader's
        conditions and every case of the dataset). The bar and the metric are
        this module's; the row passes only at or above the bar."""
        owner = BARS[step]
        now = self.clock.now()
        kept = round(value, 4)
        measurement = ModelMeasurement(
            measurement_id=self.ids.new_uuid(),
            step=step,
            model=model,
            prompt=str(owner.prompt),
            metric=owner.metric,
            value=kept,
            bar=owner.bar,
            passed=held and kept >= owner.bar,
            dataset=dataset,
            measured_at=now,
            recorded_by=system_actor_label(ATTEST_LANE),
        )
        event = lane_audit_event(
            lane=ATTEST_LANE,
            event_id=self.ids.new_uuid(),
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            action="sales.model_step.measured",
            resource_type="sales_model_step_measurement",
            resource_id=str(measurement.measurement_id),
            occurred_at=now,
            details={
                "step": step.value,
                "model": model,
                "prompt": measurement.prompt,
                "value": measurement.value,
                "bar": measurement.bar,
                "passed": measurement.passed,
                "dataset": dataset,
            },
        )
        await self.log.record(scope, measurement, event)
        return measurement
