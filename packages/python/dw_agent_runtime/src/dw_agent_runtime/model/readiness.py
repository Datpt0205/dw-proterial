"""Whether a model step has earned its switch: the measurements, and the
check every context's steps are held to (dw_sales ADR 0005 addendum of
2026-10-23, where it was built; lifted by ADR 0013/0014).

A context may let a model step run unattended only "once that step's live
eval meets its bar". Each context registers its steps and their bars
(`StepBar`: the bar, the metric's path in the golden grader's details, the
prompt the step runs on, the dataset that measures it); this module owns
what the bars are held to:

- **A store of live measurements** (`platform.model_step_measurements`),
  written only by a live eval run with ``--attest`` (`Attestation`, audited
  as the context's lane) and read through `ModelMeasurementsPort`.
- **The check** (`ReadinessCheck.check`): a step is ready only when the
  latest measurement for the model the tenant's profile routes it to now
  (`StepModelPort`) and the prompt version it pins now passed, at today's bar
  and on today's metric. Anything else, an unreadable store included, is not
  ready.
- **The refusal** a version meets when it turns on a step that is not ready
  (`refusal`), naming each step's bar, model, prompt and latest measurement.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol, Self
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_agent_runtime.model.interpretation import PromptRef
from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.domain.audit import AuditEvent, lane_audit_event, system_actor_label

_LOG = logging.getLogger("dw_agent_runtime.readiness")
_LOCAL: Final = ZoneInfo("Asia/Ho_Chi_Minh")

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


def metric_at(details: Mapping[str, Any], path: str) -> float:
    found: Any = details
    for part in path.split("."):
        found = found[part]
    return float(found)


def bar_verdict(
    step: str, owner: StepBar, details: Mapping[str, Any], *, holds: bool = True
) -> dict[str, object]:
    """A golden grader's verdict on its step's bar, read from the grader's own
    ``details`` at the metric's path. ``holds`` is any condition of the
    grader's own besides the share."""
    value = metric_at(details, owner.metric)
    return {
        "step": str(step),
        "metric": owner.metric,
        "value": value,
        "bar": owner.bar,
        "passed": holds and value >= owner.bar,
    }


class MeasuredScope(Protocol):
    """Whose measurements a read or a write is bound to."""

    @property
    def tenant_id(self) -> TenantId: ...

    @property
    def workspace_id(self) -> WorkspaceId: ...


class ModelMeasurement(BaseModel):
    """One live measurement of one step: a row of
    `platform.model_step_measurements`, whose CHECKs say the same."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    measurement_id: uuid.UUID
    step: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
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
        self, scope: MeasuredScope, step: str, *, model: str, prompt: str
    ) -> ModelMeasurement | None:
        """The newest measurement of ``step`` on ``model`` and ``prompt``."""
        ...


class MeasurementLogPort(Protocol):
    """Where the attesting lane writes: the row and its audit event in one
    transaction, under the tenant's RLS. Append-only."""

    async def record(
        self, scope: MeasuredScope, measurement: ModelMeasurement, event: AuditEvent
    ) -> None: ...


class StepModelPort(Protocol):
    """The model a tenant's model steps run on now: the route the context's
    profile resolves to for that tenant, read as the gateway reads it."""

    def model_for(self, tenant_id: uuid.UUID) -> str: ...


Reason = Literal["ready", "not_measured", "failed", "unreadable"]


@dataclass(frozen=True, slots=True)
class StepReadiness:
    # The step as the context names it (its own enum value, kept as given).
    step: str
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


def passes(owner: StepBar, latest: ModelMeasurement) -> bool:
    """A pass, at today's bar, on today's metric."""
    return latest.passed and latest.value >= owner.bar and latest.metric == owner.metric


@dataclass(frozen=True)
class ReadinessCheck:
    """Whether each of a context's steps is ready for a tenant now."""

    bars: Mapping[Any, StepBar]
    measurements: ModelMeasurementsPort
    models: StepModelPort

    async def check(self, scope: MeasuredScope, step: str) -> StepReadiness:
        owner = self.bars[step]
        prompt = str(owner.prompt)
        try:
            model = self.models.model_for(scope.tenant_id.value)
            latest = await self.measurements.latest(scope, step, model=model, prompt=prompt)
        except Exception as exc:
            _LOG.warning(
                "model step %s: measurements unreadable for tenant %s (%s)",
                step,
                scope.tenant_id.value,
                type(exc).__name__,
            )
            return StepReadiness(step, None, prompt, owner.bar, None, "unreadable")
        if latest is None:
            reason: Reason = "not_measured"
        else:
            reason = "ready" if passes(owner, latest) else "failed"
        return StepReadiness(step, model, prompt, owner.bar, latest, reason)


def refusal(unready: Sequence[StepReadiness]) -> ConflictError:
    """The 409 a version meets when it turns on the ``unready`` steps: each
    named with its bar, the model and prompt it runs on, and its latest
    measurement or "chưa đo"."""
    return ConflictError(
        "Chưa bật được bước có mô hình: "
        + "; ".join(worded(r) for r in unready)
        + ". Một bước chỉ bật được khi lần đo trực tiếp gần nhất, trên mô hình và"
        " lời nhắc bước đó đang dùng, đạt ngưỡng. Tắt bước đó trong phiên bản này,"
        " hoặc đo lại (run_evals.py --live --attest) rồi đề xuất lại.",
        details={"rule": MODEL_BAR_UNMET, "steps": [_detail(r) for r in unready]},
    )


def worded(readiness: StepReadiness) -> str:
    latest = readiness.latest
    if readiness.reason == "unreadable":
        measured = "không đọc được kết quả đo"
    elif latest is None:
        measured = "chưa đo"
    else:
        when = latest.measured_at.astimezone(_LOCAL).strftime("%H:%M %d/%m/%Y")
        measured = f"lần đo gần nhất {latest.value:.1%} lúc {when}, chưa đạt"
    return (
        f"«{readiness.step}» (ngưỡng {readiness.bar:.0%}, mô hình"
        f" {readiness.model or 'không xác định'}, lời nhắc {readiness.prompt}: {measured})"
    )


def _detail(readiness: StepReadiness) -> dict[str, object]:
    latest = readiness.latest
    return {
        "step": str(readiness.step),
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


@dataclass(frozen=True)
class Attestation:
    """Records a live eval's measurement of a step for one tenant, as the
    context's attesting lane (`system:<lane>`), audited in the same
    transaction (`<audit_prefix>.measured`)."""

    log: MeasurementLogPort
    clock: UtcClock
    ids: IdGenerator
    bars: Mapping[Any, StepBar]
    lane: str
    action: str
    resource_type: str

    async def attest(
        self,
        scope: MeasuredScope,
        step: str,
        *,
        model: str,
        value: float,
        held: bool,
        dataset: str,
    ) -> ModelMeasurement:
        """``value`` is the step's metric as the live run measured it, and
        ``held`` whether that run's own verdict passed. The bar and the
        metric are the registry's; the row passes only at or above the bar."""
        owner = self.bars[step]
        now = self.clock.now()
        kept = round(value, 4)
        measurement = ModelMeasurement(
            measurement_id=self.ids.new_uuid(),
            step=str(step),
            model=model,
            prompt=str(owner.prompt),
            metric=owner.metric,
            value=kept,
            bar=owner.bar,
            passed=held and kept >= owner.bar,
            dataset=dataset,
            measured_at=now,
            recorded_by=system_actor_label(self.lane),
        )
        event = lane_audit_event(
            lane=self.lane,
            event_id=self.ids.new_uuid(),
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            action=self.action,
            resource_type=self.resource_type,
            resource_id=str(measurement.measurement_id),
            occurred_at=now,
            details={
                "step": str(step),
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
