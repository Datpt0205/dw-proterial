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
from dw_sales.application.change_reading import CHANGE_REQUEST
from dw_sales.application.chat_prompts import QUESTION_INTENT
from dw_sales.application.document_forms import DOCUMENT_FORMS_PROMPT
from dw_sales.application.handoffs import HANDOFF_KINDS_PROMPT, REQUEST_HANDOFF
from dw_sales.application.internal_changes import INTERNAL_CHANGE
from dw_sales.application.layouts import LAYOUT_PROPOSAL
from dw_sales.application.mail_kinds import MAIL_KINDS_PROMPT
from dw_sales.application.message_intent import MESSAGE_INTENT
from dw_sales.application.model_reading import DESCRIPTION_ATTRIBUTES
from dw_sales.application.pc_dates import PC_DATES
from dw_sales.application.po_body_reading import PO_BODY_EXTRACTION
from dw_sales.application.ports import SalesScope
from dw_sales.application.reply_drafts import REPLY_DRAFT, REPLY_KINDS_PROMPT
from dw_sales.application.reply_intent import REPLY_INTENT
from dw_sales.application.rfq_reading import RFQ_EXTRACTION
from dw_sales.application.salesorder_fill import SALESORDER_FILL
from dw_sales.application.thread_agent import DW1_AGENT, THREAD_AGENT
from dw_sales.application.triage import TRIAGE_CARD_PROMPT
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
        # Ticket 42 family 3: the golden request files, read by the platform's
        # document forms and a company's forms for its new customers, values
        # into the right field over every value they state, at ticket 29's
        # bar so the two readings of one file compare on one number. A
        # company's own version is replayed and read by its head before it
        # applies, not by this bar. Proposed by the agent.
        ModelStep.SKILL_DOCUMENT_FORMS: StepBar(
            0.85,
            "all.right_field",
            DOCUMENT_FORMS_PROMPT,
            "sales_document_forms",
            "sales.document_forms_golden",
        ),
        # Tickets 32 and 26: the golden thread messages other than
        # conditional ones and non-answers read as exactly their intents, and
        # none of those two read as `accepts` (the grader's own condition).
        ModelStep.REPLY_INTENT: StepBar(
            0.85, "bar_set.intent_accuracy", REPLY_INTENT, "sales_reply", "sales.reply_golden"
        ),
        # Ticket 33: the golden fields carried right.
        ModelStep.REQUEST_HANDOFF: StepBar(
            0.85, "all.right", REQUEST_HANDOFF, "sales_handoff", "sales.handoff_golden"
        ),
        # Ticket 42 family 5: the same golden mails, each pre-filled by the
        # platform's hand-off skill's kind for it, at ticket 33's bar on the
        # same metric, so the two readings of one task compare on one number.
        # A tenant's own version is replayed and read by its head before it
        # applies, not by this bar. Proposed by the agent.
        ModelStep.SKILL_HANDOFFS: StepBar(
            0.85,
            "all.right",
            HANDOFF_KINDS_PROMPT,
            "sales_handoff_kinds",
            "sales.handoff_kinds_golden",
        ),
        # Ticket 30: the golden forms' fields mapped right before human edits,
        # and no accepted swap (the grader's own condition).
        ModelStep.LAYOUT_PROPOSAL: StepBar(
            0.90, "all.right", LAYOUT_PROPOSAL, "sales_layout", "sales.layout_golden"
        ),
        # Ticket 41: the golden pairs' SalesOrder cells filled with the
        # customer's skill come out as the PIC's file, every one traced, over
        # every cell compared (a flagged cell is a miss); and the grader's
        # own conditions: no injected instruction and no other customer's
        # value ever written. A tenant's own version of a skill is replayed
        # on its customer's pairs before the head decides it, not by this
        # bar. Proposed by the agent; the attested measurement is on the
        # plant's model.
        ModelStep.SALESORDER_SKILL: StepBar(
            0.95,
            "golden.cell_accuracy",
            SALESORDER_FILL,
            "sales_salesorder_skill",
            "sales.salesorder_skill_golden",
        ),
        # AI item 4: the golden mails' values read into the right field, over
        # every value the golden POs state. A PO refused goes to a person.
        ModelStep.PO_BODY_EXTRACTION: StepBar(
            0.85, "all.right_field", PO_BODY_EXTRACTION, "sales_po_body", "sales.po_body_golden"
        ),
        # Ticket 27: the golden mails' changes read as exactly their line,
        # field and value, over every change the golden mails ask. A change
        # missed or dropped goes to a person, who types it.
        ModelStep.CHANGE_REQUEST: StepBar(
            0.85,
            "all.right_change",
            CHANGE_REQUEST,
            "sales_change_request",
            "sales.change_request_golden",
        ),
        # Tickets 30 and 31 (dw_sales ADR 0012 decision 5): the golden thread
        # messages other than conditional ones and non-answers read as
        # exactly their intents with tools, at the one-call reading's bar; and
        # the grader's own conditions: no false `accepts`, no turn over its
        # call ceiling, and no tool answering for another customer. Proposed
        # by the agent; the attested measurement is on the plant's model.
        ModelStep.THREAD_AGENT: StepBar(
            0.85,
            "bar_set.intent_accuracy",
            THREAD_AGENT,
            "sales_thread_agent",
            "sales.thread_agent_golden",
        ),
        # Ticket 32: the golden mails (each kind, in the customers' three
        # languages) drafted, every figure among the facts, and stating the
        # figures the mail is for (the PO and each date it answers with); the
        # grader's own condition: no draft kept naming an amount, an address
        # or a figure the facts lack. Proposed by the agent.
        ModelStep.REPLY_DRAFT: StepBar(
            0.85, "all.complete", REPLY_DRAFT, "sales_reply_draft", "sales.reply_draft_golden"
        ),
        # Ticket 42 family 5: the same drafts, worded by the platform's
        # reply-drafts skill, at ticket 32's bar on the same metric. Proposed
        # by the agent.
        ModelStep.SKILL_REPLY_DRAFTS: StepBar(
            0.85,
            "all.complete",
            REPLY_KINDS_PROMPT,
            "sales_reply_kinds",
            "sales.reply_kinds_golden",
        ),
        # Ticket 40 (dw_sales ADR 0014 decision 4): DW1's agent with its
        # platform skill reads the bar's set at the thread agent's bar, on the
        # same metric, so the three readings of one task are compared on one
        # number; held only with no false `accepts` and no tool answering
        # with another customer's record. A tenant's own version of the skill
        # is read by its head before it applies, not by this bar. Proposed by
        # the agent; the attested measurement is on the plant's model.
        ModelStep.SKILL_INTENTS: StepBar(
            0.85,
            "bar_set.intent_accuracy",
            DW1_AGENT,
            "sales_skill_intents",
            "sales.skill_intents_golden",
        ),
        # Ticket 42 family 1: the message intent's golden residue classified
        # by the platform's mail-classifying skill, routed as its kind's route
        # and held at the one call's bar, on the same metric, so the two
        # readings of one task compare on one number. A tenant's own version
        # is replayed and read by its head before it applies, not by this
        # bar. Proposed by the agent.
        ModelStep.SKILL_MAIL_KINDS: StepBar(
            0.90,
            "all.kind_accuracy",
            MAIL_KINDS_PROMPT,
            "sales_mail_kinds",
            "sales.mail_kinds_golden",
        ),
        # Ticket 33: the golden residue's cards, each suggesting the step and
        # naming the case a person would take (no step and no case where it
        # concerns none), over every golden mail; held only while no card
        # names another customer's case and no injection suggests a step
        # outside the closed set. Advice a person takes or dismisses, so the
        # bar is the mail kinds' minus their routing margin. Proposed by the
        # agent; the attested measurement is on the plant's model.
        ModelStep.TRIAGE_CARD: StepBar(
            0.85,
            "golden.card_accuracy",
            TRIAGE_CARD_PROMPT,
            "sales_triage_card",
            "sales.triage_card_golden",
        ),
        # Ticket 10: the golden pastes of PC's mail read as exactly their
        # lines, each with its deliveries, over every paste, at ticket 27's
        # bar for the customer's own change. Sales applies every line, so a
        # miss costs a line typed. Proposed by the agent.
        ModelStep.INTERNAL_CHANGE: StepBar(
            0.85,
            "all.right",
            INTERNAL_CHANGE,
            "sales_internal_change",
            "sales.internal_change_golden",
        ),
        # Tickets 56 and 57: the PICs' sentences in a case's chat read as
        # exactly the flag and decision they state. Set at the reading steps'
        # 0.85 from the first live run (2026-11-22, Strata's
        # qwen3.8-flash-next-q2_0 on Giang's home lab, not the plant: 8 of 8
        # sentences, the Bravo writes 3 of 3). Every statement still waits on
        # the PIC's confirmation.
        ModelStep.CASE_CHAT: StepBar(
            0.85,
            "all.right",
            QUESTION_INTENT,
            "sales_case_chat",
            "sales.case_chat_golden",
        ),
        # Ticket 77: PC's mail read with no person pressing, on the prompt and
        # the golden mails Sales' own reading of PC's mail is graded on
        # (`sales_pc_dates`): every date of each mail read for its line, as
        # that day, and nothing more, at the reading steps' 0.85. Each date
        # still waits on the PIC's press. Proposed by the agent; no live run
        # yet, so the step is not ready anywhere.
        ModelStep.PC_REPLY: StepBar(
            0.85,
            "all.right",
            PC_DATES,
            "sales_pc_dates",
            "sales.pc_date_golden",
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

    async def configured(self, scope: SalesScope, step: ModelStep) -> bool:
        """Whether a model is configured for ``step`` for the tenant now,
        measured or not: what a step reading in shadow needs (ticket 67).
        Unreadable is not configured: fail closed."""
        return (await self.check(scope, step)).model is not None

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
