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

The measurement, the store, the check and the refusal are the agent
runtime's since ADR 0013/0014 (`dw_agent_runtime.model.readiness`,
`platform.model_step_measurements`); what stays here is Sales': its steps,
their bars, and the switches in the order rules that turn them on.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from dw_agent_runtime.model import readiness as runtime
from dw_agent_runtime.model.readiness import (
    MODEL_BAR_UNMET,
    MeasurementLogPort,
    ModelMeasurement,
    ModelMeasurementsPort,
    Reason,
    StepBar,
    StepModelPort,
    StepReadiness,
    refusal,
)
from dw_kernel.ports import IdGenerator, UtcClock
from dw_sales.application.handoffs import REQUEST_HANDOFF
from dw_sales.application.layouts import LAYOUT_PROPOSAL
from dw_sales.application.message_intent import MESSAGE_INTENT
from dw_sales.application.model_reading import DESCRIPTION_ATTRIBUTES
from dw_sales.application.po_body_reading import PO_BODY_EXTRACTION
from dw_sales.application.ports import SalesScope
from dw_sales.application.reply_intent import REPLY_INTENT
from dw_sales.application.rfq_reading import RFQ_EXTRACTION
from dw_sales.domain.order_checks import ModelStep, OrderRules

__all__ = [
    "MODEL_BAR_UNMET",
    "MeasurementLogPort",
    "ModelMeasurement",
    "ModelMeasurementsPort",
    "Reason",
    "StepBar",
    "StepModelPort",
    "StepReadiness",
    "refusal",
]

_LOG = logging.getLogger("dw_sales.model")

# The lane that records a measurement: its audit actor is `system:<lane>`
# (ADR 0011), and so is a row's `recorded_by`.
ATTEST_LANE: Final = "sales_model_attest"


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
        # AI item 4: the golden mails' values read into the right field, over
        # every value the golden POs state. A PO refused goes to a person.
        ModelStep.PO_BODY_EXTRACTION: StepBar(
            0.85, "all.right_field", PO_BODY_EXTRACTION, "sales_po_body", "sales.po_body_golden"
        ),
    }
)


def step_measured_by(dataset_id: str) -> ModelStep | None:
    """The step a dataset measures, or None for a dataset that measures none."""
    return next((step for step, owner in BARS.items() if owner.dataset == dataset_id), None)


def bar_verdict(
    step: ModelStep, details: Mapping[str, Any], *, holds: bool = True
) -> dict[str, object]:
    """A golden grader's verdict on its step's bar (`runtime.bar_verdict`
    with the bar this module holds for ``step``)."""
    return runtime.bar_verdict(step, BARS[step], details, holds=holds)


@dataclass(frozen=True)
class ModelReadiness:
    """Implements `ModelStepGatePort`, and is what a rule version's proposal
    and decision ask about the steps it turns on."""

    measurements: ModelMeasurementsPort
    models: StepModelPort

    async def check(self, scope: SalesScope, step: ModelStep) -> StepReadiness:
        return await runtime.ReadinessCheck(BARS, self.measurements, self.models).check(scope, step)

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
        return await runtime.Attestation(
            self.log,
            self.clock,
            self.ids,
            BARS,
            lane=ATTEST_LANE,
            action="sales.model_step.measured",
            resource_type="sales_model_step_measurement",
        ).attest(scope, step, model=model, value=value, held=held, dataset=dataset)
