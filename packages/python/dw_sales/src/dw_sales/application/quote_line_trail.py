"""Why a requested line of a quotation went the way it did (ticket 62).

The quote page's counterpart of `line_trail`: the same step view, read from
what the quote case already holds, never kept a second time. The request's
reading and what a model read on the line; what the customer's notation left
unsettled; each finding on the line, its decision and the values Sales
confirmed; the YCBG; mass or pcs; each Design reply and Design's result in
Bravo; every price decision, the earlier ones included; the pcs price; the
submission, each return, the approval, the sending, the master list, the
signed copy and the decline; and the model steps the activity rows name for
the line. A field the case or the line gains without a step here is a trail
that lies by omission: `test_quote_line_trail.py` lists every one.

Design is outside DW: its reply and its result in Bravo are a person's
decision with no DW user to name. No amount reaches a step: a price, a
target price and a finding's compared values stay on the case page, where
`sales.price.read` gates them.
"""

from __future__ import annotations

from collections.abc import Sequence

from dw_sales.application.line_trail import LineTrailView, TrailStepView
from dw_sales.domain.activity import StepOutcome
from dw_sales.domain.quotes import (
    FindingAccepted,
    FindingCorrected,
    PricingDecision,
    QuoteCase,
    RequestedItem,
)


def quote_line_trail(
    case: QuoteCase, line_no: int, outcomes: Sequence[StepOutcome]
) -> LineTrailView:
    """The steps of requested line ``line_no`` on ``case``, in the order the
    case takes them."""
    item = case.request.document.item(line_no)
    steps: list[TrailStepView] = [*_read(case, item), *_findings(case, line_no)]
    steps.extend(_design(case, line_no))
    steps.extend(_pricing(case, line_no))
    steps.extend(_case_steps(case))
    steps.extend(
        TrailStepView(
            kind="model_step",
            code=o.step.value,
            decided_by="model" if o.automatic else "person",
            at=o.occurred_at,
            outcome=o.result,
            gate=o.gate,
        )
        for o in outcomes
        if o.case_id == case.case_id and o.line_no == line_no
    )
    return LineTrailView(case_id=case.case_id, line_no=line_no, steps=tuple(steps))


def _read(case: QuoteCase, item: RequestedItem) -> list[TrailStepView]:
    request = case.request
    source = item.description.source
    reading = request.reading
    by_model = reading is not None or bool(item.flags)
    steps = [
        TrailStepView(
            kind="read",
            code=reading.prompt if reading is not None else "read",
            decided_by="model" if by_model else "rule",
            at=request.received_at,
            cell=source.cell_ref,
            page=source.page,
            # The fields a model read on this line, or the PO it was opened
            # from (ticket 09).
            value=",".join(f.field for f in item.flags)
            or (case.from_order.po_no if case.from_order is not None else None),
        )
    ]
    if item.description_reading is not None:
        steps.append(
            TrailStepView(
                kind="model_reading",
                code=item.description_reading.prompt,
                decided_by="model",
                outcome=item.description_reading.outcome,
                confidence=item.description_reading.confidence,
                gate=item.description_reading.gate,
            )
        )
    if item.candidates:
        steps.append(
            TrailStepView(
                kind="candidates",
                code="description_candidates",
                decided_by="rule",
                value=",".join(item.candidates),
            )
        )
    if item.unsettled:
        steps.append(
            TrailStepView(
                kind="unsettled",
                code="customer_notation",
                decided_by="rule",
                value=",".join(item.unsettled),
            )
        )
    return steps


def _findings(case: QuoteCase, line_no: int) -> list[TrailStepView]:
    steps: list[TrailStepView] = []
    for finding in case.findings:
        if finding.line_no != line_no:
            continue
        code = finding.code.value
        steps.append(
            TrailStepView(
                kind="finding",
                code=code,
                decided_by="rule",
                severity="blocking" if finding.blocking else "info",
                rule_version=",".join(finding.rule_versions) or None,
            )
        )
        steps.extend(
            TrailStepView(
                kind="value_confirmed",
                code=code,
                decided_by="person",
                actor_user_id=c.by,
                at=c.at,
                value=c.field,
            )
            for c in finding.confirmed
        )
        decision = finding.disposition
        if isinstance(decision, FindingAccepted | FindingCorrected):
            steps.append(
                TrailStepView(
                    kind="finding_decided",
                    code=code,
                    decided_by="person",
                    actor_user_id=decision.by,
                    at=decision.at,
                    outcome=decision.kind,
                )
            )
    return steps


def _design(case: QuoteCase, line_no: int) -> list[TrailStepView]:
    steps: list[TrailStepView] = []
    if case.ycbg is not None:
        steps.append(
            TrailStepView(
                kind="ycbg_recorded",
                code="ycbg",
                decided_by="person",
                actor_user_id=case.ycbg.recorded_by,
                at=case.ycbg.recorded_at,
                value=case.ycbg.ycbg_no,
            )
        )
    if case.production_type is not None:
        stamp = case.production_type_set
        steps.append(
            TrailStepView(
                kind="production_type",
                code="production_type",
                decided_by="person",
                actor_user_id=stamp.by if stamp is not None else None,
                at=stamp.at if stamp is not None else None,
                value=case.production_type,
            )
        )
    for reply in case.design_replies:
        for line in reply.document.lines:
            if line.line_no != line_no:
                continue
            steps.append(
                TrailStepView(
                    kind="design_reply",
                    code="design_reply",
                    decided_by="person",
                    at=reply.received_at,
                    value=line.bp_code.value,
                    # Read from the mail, a person checked the reading first.
                    outcome="confirmed" if reply.confirmed_by is not None else None,
                )
            )
    check = case.design_check
    if check is not None:
        for result in check.lines:
            if result.line_no != line_no:
                continue
            steps.append(
                TrailStepView(
                    kind="design_check",
                    code="design_check",
                    decided_by="person",
                    at=check.read_at,
                    value=result.bp_code or check.ycbg_no,
                    outcome=result.verdict,
                )
            )
    return steps


def _priced(decision: PricingDecision, line_no: int) -> TrailStepView:
    line = decision.line(line_no)
    return TrailStepView(
        kind="priced",
        code="pricing",
        decided_by="person",
        actor_user_id=decision.decided_by,
        at=decision.decided_at,
        # How the price moves with copper; never the price.
        outcome=line.copper_basis.kind,
    )


def _pricing(case: QuoteCase, line_no: int) -> list[TrailStepView]:
    steps = [_priced(d, line_no) for d in case.earlier_pricing]
    if case.pricing is not None:
        steps.append(_priced(case.pricing, line_no))
    pcs = case.pcs_price
    if pcs is not None and any(p.line_no == line_no for p in pcs.lines):
        steps.append(
            TrailStepView(
                kind="pcs_priced",
                code="pcs_price",
                decided_by="person",
                actor_user_id=pcs.recorded_by,
                at=pcs.recorded_at,
            )
        )
    return steps


def _case_steps(case: QuoteCase) -> list[TrailStepView]:
    """The case's own steps, which move every line of the quotation."""
    steps: list[TrailStepView] = []
    if case.submission is not None:
        steps.append(
            TrailStepView(
                kind="submitted",
                code="submission",
                decided_by="person",
                actor_user_id=case.submission.submitted_by,
                at=case.submission.submitted_at,
            )
        )
    steps.extend(
        TrailStepView(
            kind="returned",
            code="return",
            decided_by="person",
            actor_user_id=r.returned_by,
            at=r.returned_at,
        )
        for r in case.returns
    )
    if case.approval is not None:
        steps.append(
            TrailStepView(
                kind="approved",
                code="approval",
                decided_by="person",
                actor_user_id=case.approval.approved_by,
                at=case.approval.approved_at,
            )
        )
    if case.sent is not None:
        steps.append(
            TrailStepView(
                kind="quote_sent",
                code="sent",
                decided_by="person",
                actor_user_id=case.sent.by,
                at=case.sent.at,
            )
        )
    if case.master_list is not None:
        steps.append(
            TrailStepView(
                kind="master_listed",
                code="master_list",
                decided_by="person",
                actor_user_id=case.master_list.by,
                at=case.master_list.at,
            )
        )
    if case.signed_copy is not None:
        steps.append(
            TrailStepView(
                kind="signed_copy",
                code="signed_copy",
                decided_by="person",
                actor_user_id=case.signed_copy.uploaded_by,
                at=case.signed_copy.uploaded_at,
            )
        )
    if case.decline is not None:
        steps.append(
            TrailStepView(
                kind="declined",
                code="decline",
                decided_by="person",
                actor_user_id=case.decline.declined_by,
                at=case.decline.declined_at,
                outcome=case.decline.reason.value,
            )
        )
    return sorted(steps, key=lambda s: s.at or case.request.received_at)
