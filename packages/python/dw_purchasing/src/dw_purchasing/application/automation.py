"""Each step's switch as it runs for a tenant now, and the model steps that
hold `ai_auto` back (`domain.automation`).

- **The level set** is the tenant's `purchasing_automation` version in force,
  else the platform's (`configs/policies/purchasing_automation@*.yaml`).
- **The level in effect** is the level set, unless it is `ai_auto` and a model
  step the step runs on has no passing live measurement on the plant's model
  for this tenant (`dw_agent_runtime.model.readiness`): then `ai_review`,
  with why. Unreadable measurements read as not measured.
- **A version that raises a step to `ai_auto` before it is measured** is
  refused where it is proposed and where it is decided (`AutomationChecks`,
  the engine's `RuleChecksPort`), as a Sales version that turns on an
  unmeasured model step is.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict

from dw_agent_runtime.model.readiness import (
    MODEL_BAR_UNMET,
    Attestation,
    MeasuredScope,
    MeasurementLogPort,
    ModelMeasurement,
    ModelMeasurementsPort,
    ReadinessCheck,
    StepBar,
    StepModelPort,
    StepReadiness,
    refusal,
)
from dw_kernel.errors import ConflictError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import ContextScope, RuleScope, Unready
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.follow_up import ORDER_CONFIRMATION_READING
from dw_purchasing.application.intake import PR_MAIL_READING
from dw_purchasing.application.sourcing import SUPPLIER_QUOTE_READING
from dw_purchasing.domain.automation import (
    STEPS,
    AutomationLevel,
    AutomationStep,
    Effective,
    PurchasingAutomation,
    PurchasingModelStep,
    Why,
    at_most,
)

# The lane that records a DW2 measurement (`run_evals.py --live --attest`).
ATTEST_LANE: Final = "purchasing_model_attest"

# Each model step's bar, the prompt it runs on and the dataset measuring it.
# Proposed by the agent (2026-11-01), as Sales' were: a miss goes to a person,
# so the bar is the share read right before anyone is asked.
BARS: Final[Mapping[PurchasingModelStep, StepBar]] = MappingProxyType(
    {
        # The golden mails that reach the model settled exactly: opened with
        # their number and every line's code, quantity, unit and date, or
        # sent to a person for the expected reason.
        PurchasingModelStep.PR_MAIL_READING: StepBar(
            0.9,
            "golden.right",
            PR_MAIL_READING,
            "purchasing_pr_intake",
            "purchasing.pr_mail_golden",
        ),
        # The golden replies read exactly: each supplier's offers, line,
        # price and lead time, as the mail states them (2026-11-04).
        PurchasingModelStep.SUPPLIER_QUOTE_READING: StepBar(
            0.9,
            "golden.right",
            SUPPLIER_QUOTE_READING,
            "purchasing_sourcing",
            "purchasing.sourcing_golden",
        ),
        # The golden confirmations held to their orders with exactly the
        # expected differences: a misread that finds none would be accepted
        # unasked, so the bar is the same share (2026-11-04).
        PurchasingModelStep.ORDER_CONFIRMATION_READING: StepBar(
            0.9,
            "golden.right",
            ORDER_CONFIRMATION_READING,
            "purchasing_follow_up",
            "purchasing.confirmation_golden",
        ),
    }
)


def step_measured_by(dataset_id: str) -> PurchasingModelStep | None:
    """The step a dataset measures, or None for a dataset that measures none."""
    return next((step for step, owner in BARS.items() if owner.dataset == dataset_id), None)


@dataclass(frozen=True)
class ModelAttestation:
    """Records a live eval's measurement of a DW2 step for one tenant: the
    lane `purchasing_model_attest`, which `scripts/run_evals.py --attest`
    runs, audited as itself."""

    log: MeasurementLogPort
    clock: UtcClock
    ids: IdGenerator

    async def attest(
        self,
        scope: MeasuredScope,
        step: PurchasingModelStep,
        *,
        model: str,
        value: float,
        held: bool,
        dataset: str,
    ) -> ModelMeasurement:
        return await Attestation(
            self.log,
            self.clock,
            self.ids,
            BARS,
            lane=ATTEST_LANE,
            action="purchasing.model_step.measured",
            resource_type="purchasing_model_step_measurement",
        ).attest(scope, step, model=model, value=value, held=held, dataset=dataset)


@dataclass(frozen=True)
class Automation:
    """The switches in effect for a tenant now."""

    measurements: ModelMeasurementsPort
    models: StepModelPort

    def _check(self) -> ReadinessCheck:
        return ReadinessCheck(BARS, self.measurements, self.models)

    async def readiness(self, scope: RuleScope, step: PurchasingModelStep) -> StepReadiness:
        return await self._check().check(scope, step)

    async def effective(
        self, context: AccessContext, switches: PurchasingAutomation, step: AutomationStep
    ) -> Effective:
        chosen = at_most(switches.steps[step], STEPS[step].ceiling)
        if chosen is not AutomationLevel.AI_AUTO or not STEPS[step].model_steps:
            return Effective(step, chosen, chosen, "set")
        scope = ContextScope.of(context)
        waiting = [
            r
            for r in [await self.readiness(scope, m) for m in STEPS[step].model_steps]
            if not r.ready
        ]
        if not waiting:
            return Effective(step, chosen, chosen, "set")
        why: Why = (
            "unreadable" if any(r.reason == "unreadable" for r in waiting) else "not_measured"
        )
        return Effective(
            step,
            chosen,
            AutomationLevel.AI_REVIEW,
            why,
            tuple(PurchasingModelStep(r.step) for r in waiting),
        )

    async def unready(
        self, scope: RuleScope, proposed: PurchasingAutomation, in_force: PurchasingAutomation
    ) -> list[StepReadiness]:
        """The model steps behind every step ``proposed`` raises to `ai_auto`
        (`ai_auto` in it, below in force) that are not ready."""
        raised = [
            step
            for step in AutomationStep
            if proposed.steps[step] is AutomationLevel.AI_AUTO
            and in_force.steps[step] is not AutomationLevel.AI_AUTO
        ]
        needed = {m for step in raised for m in STEPS[step].model_steps}
        found = [await self.readiness(scope, m) for m in sorted(needed)]
        return [r for r in found if not r.ready]


_UNMET_COMMENT: Final = (
    "Đã được duyệt nhưng không áp dụng: bước AI mà phiên bản này cho tự làm ({steps})"
    " chưa có lần đo đạt ngưỡng trên mô hình của nhà máy. Đo lại rồi đề xuất lại."
)


class SwitchesInForcePort(Protocol):
    """The tenant's switches in force (the rule book)."""

    async def switches_in_force(self, scope: RuleScope) -> PurchasingAutomation: ...


class SwitchBookPort(Protocol):
    async def switches(self, context: AccessContext) -> PurchasingAutomation: ...


@dataclass(frozen=True)
class AutomationChecks:
    """Implements the engine's `RuleChecksPort` for DW2's keys: only the
    switches have a check beyond their schema."""

    automation: Automation
    in_force: SwitchesInForcePort

    async def unready(self, scope: RuleScope, key: str, policy: BaseModel) -> Unready | None:
        if not isinstance(policy, PurchasingAutomation):
            return None
        current = await self.in_force.switches_in_force(scope)
        steps = await self.automation.unready(scope, policy, current)
        if not steps:
            return None
        return Unready(
            error=refusal(steps),
            rule=MODEL_BAR_UNMET,
            comment=_UNMET_COMMENT.format(steps=", ".join(str(r.step) for r in steps)),
        )


def ensure(effective: Effective, at_least: AutomationLevel) -> None:
    """Refuses (409) a step that runs below ``at_least`` now: a path that
    acts unasked asks first."""
    order = {AutomationLevel.PERSON: 0, AutomationLevel.AI_REVIEW: 1, AutomationLevel.AI_AUTO: 2}
    if order[effective.level] < order[at_least]:
        raise ConflictError(
            "bước này đang đặt cho người làm",
            details={"rule": "step_not_automated", "step": effective.step.value},
        )


class StepLevelView(BaseModel):
    """One step's switch as the settings page shows it: the level set, the
    level it runs at now, why they differ, and how far it may go."""

    model_config = ConfigDict(frozen=True)

    step: AutomationStep
    chosen: AutomationLevel
    level: AutomationLevel
    why: Why
    ceiling: AutomationLevel
    # The model readings `ai_auto` waits on, and those not yet measured.
    model_steps: list[PurchasingModelStep]
    waiting_on: list[PurchasingModelStep]


class SwitchesView(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref: str
    steps: list[StepLevelView]


@dataclass(frozen=True)
class SwitchesService:
    """What the settings page and every automated path read."""

    gate: Gate
    book: SwitchBookPort
    automation: Automation

    async def view(self, context: AccessContext) -> SwitchesView:
        await self.gate.require_any(
            context,
            PurchasingScopes.REQUEST_READ,
            PurchasingScopes.RULES_PROPOSE,
            PurchasingScopes.RULES_APPROVE,
            resource_type="automation",
        )
        switches = await self.book.switches(context)
        steps = []
        for step in AutomationStep:
            effective = await self.automation.effective(context, switches, step)
            steps.append(
                StepLevelView(
                    step=step,
                    chosen=effective.chosen,
                    level=effective.level,
                    why=effective.why,
                    ceiling=STEPS[step].ceiling,
                    model_steps=list(STEPS[step].model_steps),
                    waiting_on=list(effective.waiting_on),
                )
            )
        return SwitchesView(ref=switches.ref, steps=steps)

    async def level(self, context: AccessContext, step: AutomationStep) -> Effective:
        """The level ``step`` runs at for this tenant now."""
        return await self.automation.effective(context, await self.book.switches(context), step)
