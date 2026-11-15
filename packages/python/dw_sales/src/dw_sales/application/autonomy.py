"""Results that apply themselves under a measured error rate: the gate, the
threshold lane and the head's view (dw_sales ADR 0015, ticket 44; the rules
are `dw_sales.domain.autonomy`).

- `AutonomyGate`: what code's gate does with one result whose checks passed,
  for the threshold the tenant's labelled cases set for the step, the prompt
  and the model profile it was read with. Asked by the step that read it
  (`OrderIntake`), which stamps the answer on the result.
- `ThresholdLane`: the worker's `sales_auto_apply` lane. On each tick, per
  workspace, it sets every step's threshold again from its labelled cases
  (`dw_sales.domain.autonomy.measure`) and stores it with the cases count,
  the audits and the date; a threshold that moved is audited as the lane
  (ADR 0011). The applying itself is `dw_sales.application.auto_apply`,
  under the same lane's name: the lane whose measure lets a result apply
  itself is the actor that applied it.
- `autonomy_summary`: per step, for the head: its tier, the mode it is in,
  the threshold and what it was set from, the audited error, and what the
  gate did with its results lately.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.domain.audit import AuditEvent, lane_audit_event, system_actor
from dw_sales.application.order_ports import OrderRulesPort
from dw_sales.application.ports import SalesScope
from dw_sales.domain.activity import StepOutcome
from dw_sales.domain.autonomy import (
    LabelledScore,
    StepThreshold,
    Tier,
    cases_needed,
    gate_route,
    measure,
    target_error,
    tier_of,
)
from dw_sales.domain.description_reading import GateRoute
from dw_sales.domain.order_checks import ModelStep, OrderRules

_VIEW = ConfigDict(frozen=True)

# The worker lane that sets the thresholds and in whose name a result is
# applied (ADR 0011: a lane audits as itself, by its registry name).
AUTO_APPLY_LANE: Final = "sales_auto_apply"


def applied_by() -> uuid.UUID:
    """The actor a result DW applied by itself names: the lane's."""
    return system_actor(AUTO_APPLY_LANE).value


# A step's labelled cases are read per prompt and model profile: a new
# version of either starts from none (ADR 0015 "Method").
VersionKey = tuple[ModelStep, str, str]


class StepThresholdReadPort(Protocol):
    """The thresholds of one workspace, read under its RLS."""

    async def threshold(
        self, scope: SalesScope, step: ModelStep, prompt: str, model_profile: str
    ) -> StepThreshold | None:
        """The step's threshold for that prompt and profile; None when the
        lane has set none yet."""
        ...

    async def thresholds(self, scope: SalesScope) -> Sequence[StepThreshold]:
        """Every threshold the workspace has."""
        ...


class StepThresholdStorePort(StepThresholdReadPort, Protocol):
    """The lane's side: the thresholds written with their audit rows, in one
    transaction."""

    async def save(
        self,
        scope: SalesScope,
        thresholds: Sequence[StepThreshold],
        audits: Sequence[AuditEvent],
    ) -> None: ...


class GatedLabelsPort(Protocol):
    """The labelled cases of results code's gate saw, in one workspace."""

    async def gated(self, scope: SalesScope) -> Mapping[VersionKey, Sequence[LabelledScore]]:
        """By step, prompt and model profile; a version with none is left out."""
        ...


@dataclass(frozen=True)
class AutonomyGate:
    """What the gate does with one result (`dw_sales.domain.autonomy.
    gate_route`), for the threshold stored for its step and versions."""

    thresholds: StepThresholdReadPort

    async def route(
        self,
        scope: SalesScope,
        rules: OrderRules,
        step: ModelStep,
        *,
        prompt: str,
        model_profile: str,
        confidence: float | None,
        item_key: str,
    ) -> GateRoute:
        if tier_of(step) is Tier.PERSON_APPROVES or confidence is None:
            return "person"
        threshold = await self.thresholds.threshold(scope, step, prompt, model_profile)
        return gate_route(
            step,
            confidence,
            threshold,
            item_key=f"{scope.tenant_id.value}:{item_key}",
            audit_share=rules.autonomy.audit_share,
        )


@dataclass(frozen=True)
class ThresholdLane:
    """One tick of the `sales_auto_apply` lane in one workspace."""

    labels: GatedLabelsPort
    thresholds: StepThresholdStorePort
    rules: OrderRulesPort
    clock: UtcClock
    ids: IdGenerator

    async def tick(self, scope: SalesScope) -> Sequence[StepThreshold]:
        """Every step's threshold set again from its labelled cases, at the
        tenant's targets in force now; stored with an audit row for each that
        moved. Returns what was stored."""
        rules = await self.rules.rules(scope)
        at = self.clock.now()
        before = {
            (t.step, t.prompt, t.model_profile): t for t in await self.thresholds.thresholds(scope)
        }
        stored: list[StepThreshold] = []
        audits: list[AuditEvent] = []
        for (step, prompt, profile), labels in (await self.labels.gated(scope)).items():
            measured = measure(step, prompt, profile, labels, rules.autonomy, at)
            if measured is None:
                continue
            stored.append(measured)
            earlier = before.get((step, prompt, profile))
            if earlier is None or (earlier.threshold, earlier.stopped) != (
                measured.threshold,
                measured.stopped,
            ):
                audits.append(self._audit(scope, measured))
        if stored:
            await self.thresholds.save(scope, stored, audits)
        return stored

    def _audit(self, scope: SalesScope, threshold: StepThreshold) -> AuditEvent:
        return lane_audit_event(
            lane=AUTO_APPLY_LANE,
            event_id=self.ids.new_uuid(),
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            action="sales.autonomy.threshold_set",
            resource_type="sales_step_threshold",
            resource_id=f"{threshold.step.value}:{threshold.prompt}",
            occurred_at=threshold.computed_at,
            # Codes and counts only: a threshold is a number, a case never.
            details={
                "step": threshold.step.value,
                "prompt": threshold.prompt,
                "model_profile": threshold.model_profile,
                "target": threshold.target,
                "threshold": threshold.threshold,
                "cases": threshold.cases,
                "audits": threshold.audits,
                "audit_errors": threshold.audit_errors,
                "stopped": threshold.stopped,
            },
        )


# ------------------------------------------------------------ head's view --

# Where a step stands: it never applies itself (T2); it is measuring (no
# certified threshold yet: every result goes to a person, its confidence and
# the person's decision recorded); it applies what clears the threshold; or
# its audits stopped it.
StepMode = Literal["never", "measuring", "applying", "stopped"]


class StepAutonomyView(BaseModel):
    """One step's line on the head's view (ticket 44)."""

    model_config = _VIEW

    step: ModelStep
    tier: Tier
    mode: StepMode
    # The tenant's target error and the labelled cases it needs; None for a
    # step that never applies itself.
    target: float | None
    needed: int | None
    # The threshold in force and what it was set from, for the versions the
    # step was last measured on; None before the lane measured it.
    threshold: float | None
    cases: int
    audits: int
    audited_error: float | None
    computed_at: str | None
    # What the gate did with the step's results over ``days`` days.
    applied: int
    audited: int
    shadow: int
    to_person: int


class AutonomySummaryView(BaseModel):
    model_config = _VIEW

    days: int
    steps: tuple[StepAutonomyView, ...]


def _mode(tier: Tier, threshold: StepThreshold | None) -> StepMode:
    if tier is Tier.PERSON_APPROVES:
        return "never"
    if threshold is None or threshold.threshold is None:
        return "measuring"
    return "stopped" if threshold.stopped else "applying"


def autonomy_summary(
    rules: OrderRules,
    thresholds: Sequence[StepThreshold],
    outcomes: Sequence[StepOutcome],
    *,
    days: int,
) -> AutonomySummaryView:
    """Every model step in its declared order. A step measured on several
    versions shows the latest measure (a new prompt starts again)."""
    latest: dict[ModelStep, StepThreshold] = {}
    for threshold in thresholds:
        known = latest.get(threshold.step)
        if known is None or threshold.computed_at > known.computed_at:
            latest[threshold.step] = threshold
    routes: dict[tuple[ModelStep, GateRoute], int] = {}
    for row in outcomes:
        if row.gate is not None:
            routes[(row.step, row.gate)] = routes.get((row.step, row.gate), 0) + 1
    steps = []
    for step in ModelStep:
        tier = tier_of(step)
        target = target_error(tier, rules.autonomy)
        found = latest.get(step)
        steps.append(
            StepAutonomyView(
                step=step,
                tier=tier,
                mode=_mode(tier, found),
                target=target,
                needed=None if target is None else cases_needed(target),
                threshold=None if found is None else found.threshold,
                cases=0 if found is None else found.cases,
                audits=0 if found is None else found.audits,
                audited_error=None if found is None else found.audited_error,
                computed_at=None if found is None else found.computed_at.isoformat(),
                applied=routes.get((step, "applied"), 0),
                audited=routes.get((step, "audit"), 0),
                shadow=routes.get((step, "shadow"), 0),
                to_person=routes.get((step, "person"), 0),
            )
        )
    return AutonomySummaryView(days=days, steps=tuple(steps))
