"""Why a PO line went the way it did: its steps, each with who decided (ticket 62).

A line's trail is read from what the case already stamps on the line, never
kept a second time: the read and its anchor, the convert list's code, a
model's reading, the mapping and who confirmed it, the quotation and checks
it was held to, each finding on it and its decision, Sales' corrections, the
customer's changes, PC's request and answer, Design's request, Bravo's entry,
the cross-check and the confirmation, and the model steps the activity rows
name for it. A field the line gains without a step here is a trail that
lies by omission, so `test_line_trail.py` builds a line with every one set.

Each step says who decided it:

- ``rule``: code, under a versioned rule (a check, the convert list);
- ``model``: a model's reading, which a person or DW1's gate then took;
- ``dw``: DW1 applied it by itself (dw_sales ADR 0015's lane);
- ``person``: someone in Sales, named by user id.

No amount reaches a step: a finding's compared values and a quotation's
price stay on the case page, where `sales.price.read` gates them.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from dw_sales.application.autonomy import applied_by
from dw_sales.application.bravo_line_writes import BravoLineWrite
from dw_sales.application.ports import SalesScope
from dw_sales.domain.activity import StepOutcome
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import MappingStatus, Open, OrderCase, OrderLine

TrailActor = Literal["rule", "model", "dw", "person"]
OrderTrailKind = Literal[
    "read",
    "convert",
    "model_reading",
    "mapping",
    "quotation",
    "checks",
    "finding",
    "finding_decided",
    "correction",
    "change",
    "design_asked",
    "pc_asked",
    "pc_short_lead",
    "pc_answer",
    "model_step",
    "bravo_recorded",
    "cross_checked",
    "confirmed",
    # A date or quantity written into Bravo (ticket 53): proposed, then
    # settled by the approver's write.
    "bravo_write",
]
# A requested line of a quotation (`quote_line_trail`).
QuoteTrailKind = Literal[
    "read",
    "model_reading",
    "candidates",
    "unsettled",
    "finding",
    "finding_decided",
    "value_confirmed",
    "ycbg_recorded",
    "production_type",
    "design_reply",
    "design_check",
    "priced",
    "pcs_priced",
    "submitted",
    "returned",
    "approved",
    "quote_sent",
    "master_listed",
    "signed_copy",
    "declined",
    "model_step",
]
TrailKind = Literal[OrderTrailKind, QuoteTrailKind]


class TrailStepView(BaseModel):
    """One step of a line's trail. ``code`` is the rule's, check's or
    model step's own code; the other fields are what the step rests on."""

    model_config = ConfigDict(frozen=True)

    kind: TrailKind
    code: str
    decided_by: TrailActor
    actor_user_id: uuid.UUID | None = None
    at: datetime | None = None
    # Where the line was read: a cell (`Sheet!B10`) or a page of the file.
    cell: str | None = None
    page: int | None = None
    # A code or field the step names: a PRV code, a quotation number, a
    # field corrected, a check list. Never an amount.
    value: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    severity: str | None = None
    # What came of the step: a mapping status, a reading's outcome, a
    # finding's decision, a model step's result.
    outcome: str | None = None
    rule_version: str | None = None
    confidence: float | None = None
    gate: str | None = None
    # A model reading: how many decided lines it was shown (ticket 43); the
    # reading's stamp keeps which.
    examples: int | None = None


class LineTrailView(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: uuid.UUID
    line_no: int
    steps: tuple[TrailStepView, ...]


# The model steps whose result is already a step of the trail above.
_SHOWN_AS_THEIR_OWN_STEP = frozenset(
    {ModelStep.DESCRIPTION_ATTRIBUTES, ModelStep.PO_BODY_EXTRACTION}
)


class CaseBravoWritesPort(Protocol):
    """The Bravo writes proposed on an order case's lines (ticket 53)."""

    async def of_case(self, scope: SalesScope, case_id: uuid.UUID) -> Sequence[BravoLineWrite]: ...


def line_trail(
    case: OrderCase,
    line_no: int,
    outcomes: Sequence[StepOutcome],
    writes: Sequence[BravoLineWrite] = (),
) -> LineTrailView:
    """The steps of ``line_no`` on ``case``, in the order they happen."""
    line = case.line(line_no)
    mine = [o for o in outcomes if o.case_id == case.case_id and o.line_no == line_no]
    steps: list[TrailStepView] = [_read(case, line, mine)]
    steps.extend(_mapping(line))
    steps.extend(_checks(line))
    steps.extend(_findings(case, line_no))
    steps.extend(_people(case, line))
    steps.extend(
        TrailStepView(
            kind="model_step",
            code=o.step.value,
            decided_by="model" if o.automatic else "person",
            at=o.occurred_at,
            outcome=o.result,
            gate=o.gate,
        )
        for o in mine
        if o.step not in _SHOWN_AS_THEIR_OWN_STEP
    )
    steps.extend(_case_steps(case, line))
    steps.extend(_bravo_writes(case, line_no, writes))
    return LineTrailView(case_id=case.case_id, line_no=line_no, steps=tuple(steps))


def _bravo_writes(
    case: OrderCase, line_no: int, writes: Sequence[BravoLineWrite]
) -> list[TrailStepView]:
    """Each Bravo write of the line: its proposal, and its settlement once
    the approver decided (written, refused, in doubt, rejected)."""
    steps: list[TrailStepView] = []
    mine = [w for w in writes if w.case_id == case.case_id and w.line_no == line_no]
    for write in sorted(mine, key=lambda w: w.proposed_at):
        steps.append(
            TrailStepView(
                kind="bravo_write",
                code=write.kind,
                decided_by="person",
                actor_user_id=write.proposed_by,
                at=write.proposed_at,
                value=write.field,
                outcome="proposed",
            )
        )
        if write.decided_by is not None:
            steps.append(
                TrailStepView(
                    kind="bravo_write",
                    code=write.kind,
                    decided_by="person",
                    actor_user_id=write.decided_by,
                    at=write.settled_at,
                    value=write.field,
                    outcome=write.status,
                )
            )
    return steps


def _read(case: OrderCase, line: OrderLine, mine: Sequence[StepOutcome]) -> TrailStepView:
    anchor = line.po_line.anchors.line_no
    by_model = any(o.step is ModelStep.PO_BODY_EXTRACTION for o in mine)
    return TrailStepView(
        kind="read",
        code=ModelStep.PO_BODY_EXTRACTION.value if by_model else "read",
        decided_by="model" if by_model else "rule",
        at=case.received_at,
        cell=anchor.cell_ref,
        page=anchor.page,
    )


def _mapping(line: OrderLine) -> list[TrailStepView]:
    steps: list[TrailStepView] = []
    basis, mapping = line.basis, line.mapping
    if basis.convert_prv_code is not None:
        steps.append(
            TrailStepView(
                kind="convert", code="convert_list", decided_by="rule", value=basis.convert_prv_code
            )
        )
    reading = basis.description_reading
    if reading is not None:
        steps.append(
            TrailStepView(
                kind="model_reading",
                code=reading.prompt,
                decided_by="model",
                outcome=reading.outcome,
                confidence=reading.confidence,
                gate=reading.gate,
                examples=len(reading.examples),
            )
        )
    if mapping.status is MappingStatus.CANDIDATE_CONFIRMED:
        by_dw = mapping.confirmed_by == applied_by()
        steps.append(
            TrailStepView(
                kind="mapping",
                code="mapping",
                decided_by="dw" if by_dw else "person",
                actor_user_id=None if by_dw else mapping.confirmed_by,
                at=mapping.confirmed_at,
                value=mapping.prv_code,
                outcome=mapping.status.value,
            )
        )
    else:
        steps.append(
            TrailStepView(
                kind="mapping",
                code="mapping",
                decided_by="rule",
                value=mapping.checked_against,
                outcome=mapping.status.value,
            )
        )
    return steps


def _checks(line: OrderLine) -> list[TrailStepView]:
    basis = line.basis
    steps: list[TrailStepView] = []
    if basis.quotation is not None:
        steps.append(
            TrailStepView(
                kind="quotation",
                code="quotation",
                decided_by="rule",
                value=basis.quotation.quote_no,
                valid_from=basis.quotation.valid_from,
                valid_to=basis.quotation.valid_to,
            )
        )
    steps.append(
        TrailStepView(
            kind="checks", code="checks", decided_by="rule", value=",".join(basis.checks_run)
        )
    )
    return steps


def _findings(case: OrderCase, line_no: int) -> list[TrailStepView]:
    steps: list[TrailStepView] = []
    for finding in case.findings:
        if finding.line_no != line_no:
            continue
        steps.append(
            TrailStepView(
                kind="finding",
                code=finding.code.value,
                decided_by="rule",
                severity=finding.severity.value,
                rule_version=finding.rule_version,
            )
        )
        decision = finding.disposition
        if isinstance(decision, Open):
            continue
        steps.append(
            TrailStepView(
                kind="finding_decided",
                code=finding.code.value,
                decided_by="person",
                actor_user_id=decision.by,
                at=decision.at,
                outcome=decision.kind.value,
            )
        )
    return steps


def _people(case: OrderCase, line: OrderLine) -> list[TrailStepView]:
    """Every value a person set on the line, oldest first."""
    no = line.po_line.line_no
    steps: list[TrailStepView] = [
        TrailStepView(
            kind="correction",
            code="correction",
            decided_by="person",
            actor_user_id=c.by,
            at=c.at,
            value=c.field,
        )
        for c in line.corrections
    ]
    steps.extend(
        TrailStepView(
            kind="change",
            code="change_request",
            decided_by="person",
            actor_user_id=c.by,
            at=c.at,
            value=c.field,
        )
        for c in line.changes
    )
    steps.extend(
        TrailStepView(
            kind="design_asked",
            code="design_request",
            decided_by="person",
            actor_user_id=d.by,
            at=d.at,
        )
        for d in case.design_requests
        if d.line_no == no
    )
    if case.pc_request is not None and no in case.pc_request.lines:
        request = case.pc_request
        steps.append(
            TrailStepView(
                kind="pc_asked",
                code="pc_request",
                decided_by="person",
                actor_user_id=request.by,
                at=request.at,
            )
        )
    if line.pc_confirmed_by is not None:
        steps.append(
            TrailStepView(
                kind="pc_short_lead",
                code="pc_short_lead_time",
                decided_by="person",
                actor_user_id=line.pc_confirmed_by,
                at=line.pc_confirmed_at,
            )
        )
    if line.pc_answer is not None:
        answer = line.pc_answer
        steps.append(
            TrailStepView(
                kind="pc_answer",
                code="pc_answer",
                decided_by="person",
                actor_user_id=answer.by,
                at=answer.at,
                value=str(len(answer.deliveries)),
            )
        )
    return sorted(steps, key=lambda s: s.at or case.received_at)


def _case_steps(case: OrderCase, line: OrderLine) -> list[TrailStepView]:
    """The case's own steps that move this line: entered in Bravo, checked
    by a second person, confirmed to the customer with its dates."""
    steps: list[TrailStepView] = []
    if case.bravo_recorded_by is not None:
        steps.append(
            TrailStepView(
                kind="bravo_recorded",
                code="bravo_entry",
                decided_by="person",
                actor_user_id=case.bravo_recorded_by,
                at=case.bravo_recorded_at,
                value=case.bravo_so_no,
            )
        )
    if case.cross_checked_by is not None:
        steps.append(
            TrailStepView(
                kind="cross_checked",
                code="cross_check",
                decided_by="person",
                actor_user_id=case.cross_checked_by,
                at=case.cross_checked_at,
            )
        )
    if case.confirmed_by is not None and line.confirmed_delivery_dates:
        steps.append(
            TrailStepView(
                kind="confirmed",
                code="confirmation",
                decided_by="person",
                actor_user_id=case.confirmed_by,
                at=case.confirmed_at,
                value=str(len(line.confirmed_delivery_dates)),
            )
        )
    return steps
