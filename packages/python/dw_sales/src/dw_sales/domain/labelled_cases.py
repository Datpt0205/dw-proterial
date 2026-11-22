"""A model's proposal beside what a person kept: a labelled case (dw_sales
ADR 0015 decision 5, ticket 43).

Every model step stamps what it read on what it produced, and
`sales.step_outcomes` records when it ran and what code made of it. Neither
records what a PERSON then did with the proposal, which is the one piece of
data ADR 0015's method needs (`docs/research/2026-11-16-less-human-review.md`
section 2.6): the pair (what the model proposed, what the person kept) is a
correct-or-wrong label. The labels set the thresholds and the audits of
ticket 44, and are the examples and the replay set of ticket 43's later
parts.

`LabelledCase` is that pair, one per item a person decided: the step and the
versions that produced the proposal, the item by reference (the message,
the case, the attachment, the line, the field: never a copy of the mail's
text), the proposal as the step typed it, the value kept (None: rejected),
who and when. Its `verdict` is derived from the two values in one place
(`verdict_of`), and the table's CHECK holds the same rule, so no writer
decides on its own what a correction is.

One function per step derives the case from what the step's own service
already holds when the person decides (`mapping_label`, `po_value_label`,
`rfq_value_labels`, `change_line_label`, `layout_label`, `triage_label`); each returns
nothing for an item no model proposed (a code reader's value, a line the
convert list mapped, a change a person typed), because such an item labels
no model.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from dw_sales.domain.activity import request_step
from dw_sales.domain.assistant import Proposal, ProposedDecision
from dw_sales.domain.catalog import CustomerCode
from dw_sales.domain.change_requests import ChangeLine, ChangeRequest
from dw_sales.domain.description_reading import GateRoute
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.layouts import LayoutPrefill, PoLayout
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import (
    MappingStatus,
    OrderCase,
    RegionFlag,
    value_with_correction,
)
from dw_sales.domain.quotes import QuoteCase, QuoteFindingCode
from dw_sales.domain.triage import TriageCard

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# What the person did with the proposal: kept it as it was, kept another
# value, or kept none.
Verdict = Literal["confirmed", "corrected", "rejected"]

# The most a proposal or a kept value holds, as JSON text (a layout's mapping
# is the largest; a value is a code, a number or a date). The table's CHECK
# holds the same bound.
MAX_VALUE_BYTES: Final = 16_384

_VERSION = r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$"


def verdict_of(proposed: JsonValue, kept: JsonValue | None) -> Verdict:
    """The one rule for what a person's decision says about a proposal:
    nothing kept is a rejection, the same value a confirmation, any other a
    correction. `ck_labelled_cases_verdict` holds the table to it."""
    if kept is None:
        return "rejected"
    return "confirmed" if kept == proposed else "corrected"


def _bounded(value: JsonValue | None, name: str) -> None:
    if value is not None and len(json.dumps(value).encode()) > MAX_VALUE_BYTES:
        raise ValueError(f"{name} is longer than a labelled case holds")


class LabelledCase(BaseModel):
    """One item a person decided on a model's proposal (module docstring)."""

    model_config = _FROZEN

    label_id: uuid.UUID
    decided_at: AwareDatetime
    step: ModelStep
    lane: CaseKind
    # The input, by reference: the case (None for a PO layout, which belongs
    # to no case), the customer, the message, the attachment read (None: the
    # mail's own text), the line (None: the document's own value), and the
    # field the proposal fills.
    case_id: uuid.UUID | None
    customer_code: CustomerCode | None
    message_id: str = Field(pattern=r"^[!-~]{1,512}$")
    attachment_id: str | None = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    line_no: int | None = Field(ge=1, le=99_999)
    field: str = Field(pattern=r"^[a-z_]{1,40}$")
    # What the step proposed, in the form the step's value takes as text (a
    # code, an ISO date, a number in one form, a mapping as JSON); and what
    # the person kept, in the same form, None when they kept nothing.
    proposed: JsonValue
    kept: JsonValue | None
    # The versions that produced the proposal: the prompt (or the reader's
    # parser version), the model profile where the stamp names one, the
    # tenant's rules version where it does.
    prompt: str = Field(pattern=_VERSION)
    model_profile: str | None = Field(min_length=1, max_length=64)
    rules: str | None = Field(pattern=_VERSION)
    decided_by: uuid.UUID
    # How sure the model was of the proposal, where the step scores it, and
    # what code's gate did with it (ticket 44): what the threshold is set
    # from and the audits are counted from. None for a result that was not
    # gated: not eligible, or decided before ticket 44.
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    gate: GateRoute | None = None

    @model_validator(mode="after")
    def _values_fit(self) -> Self:
        if self.proposed is None:
            raise ValueError("a labelled case holds what the model proposed")
        _bounded(self.proposed, "the proposal")
        _bounded(self.kept, "the kept value")
        return self

    @property
    def verdict(self) -> Verdict:
        return verdict_of(self.proposed, self.kept)


def value_text(value: object) -> str:
    """A field's value in one text form, so that one value is one text: a
    number without trailing zeros, a date in ISO form, an enum by its value."""
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


NewId = Callable[[], uuid.UUID]


# ---------------------------------------------------------------- per step --


def mapping_label(
    before: OrderCase,
    line_no: int,
    prv_code: str | None,
    *,
    new_id: NewId,
    at: AwareDatetime,
    by: uuid.UUID,
) -> LabelledCase | None:
    """A line's PRV code confirmed by Sales, where the candidates came from a
    model's reading of the description (`description_attributes`). The
    proposal is the candidates in their order, the kept value the one code:
    one candidate kept is confirmed; one of several picked, or a code typed,
    is a correction (the reading did not settle the item). ``prv_code`` None
    is the candidates rejected ("Không phải mã này", ticket 44): nothing
    kept. None where no model read the line, or the convert list mapped it;
    a line whose candidates were rejected holds no reading any more, so the
    code typed after it labels nothing a second time."""
    line = before.line(line_no)
    reading = line.basis.description_reading
    if reading is None or reading.outcome != "read" or line.mapping.status is MappingStatus.EXACT:
        return None
    return LabelledCase(
        label_id=new_id(),
        decided_at=at,
        step=ModelStep.DESCRIPTION_ATTRIBUTES,
        lane=CaseKind.ORDER,
        case_id=before.case_id,
        customer_code=before.customer_code,
        message_id=before.message_id,
        attachment_id=before.document.attachment_id,
        line_no=line_no,
        field="prv_code",
        proposed=list(line.mapping.candidates),
        kept=None if prv_code is None else [prv_code],
        prompt=reading.prompt,
        model_profile=reading.model_profile,
        rules=before.rules_version,
        decided_by=by,
        confidence=reading.confidence,
        gate=reading.gate,
    )


def undo_label(
    before: OrderCase,
    line_no: int,
    *,
    new_id: NewId,
    at: AwareDatetime,
    by: uuid.UUID,
) -> LabelledCase:
    """A person undoing the PRV code DW applied by itself (ticket 44): the
    applied code, rejected. The case is the error the threshold and the
    audits learn from; a code the person then confirms is a case of its own."""
    line = before.line(line_no)
    reading = line.basis.description_reading
    code = line.mapping.prv_code
    if reading is None or reading.gate != "applied" or code is None:
        raise ValueError("only a code DW applied by itself is undone")
    return LabelledCase(
        label_id=new_id(),
        decided_at=at,
        step=ModelStep.DESCRIPTION_ATTRIBUTES,
        lane=CaseKind.ORDER,
        case_id=before.case_id,
        customer_code=before.customer_code,
        message_id=before.message_id,
        attachment_id=before.document.attachment_id,
        line_no=line_no,
        field="prv_code",
        proposed=[code],
        kept=None,
        prompt=reading.prompt,
        model_profile=reading.model_profile,
        rules=before.rules_version,
        decided_by=by,
        confidence=reading.confidence,
        gate=reading.gate,
    )


def po_value_label(
    before: OrderCase, after: OrderCase, finding_key: str, field: str, *, new_id: NewId
) -> LabelledCase | None:
    """One value of a PO a model read from the mail's body
    (`po_body_extraction`, the only reader that flags `model_read` on an
    order), as Sales typed it (``after``'s correction of ``field``). Compared
    as the field's type, so ``1000`` typed for ``1000.00`` read is a
    confirmation. None for a value a code reader flagged (a hidden sheet,
    OCR, a new layout)."""
    finding = before.finding(finding_key)
    correction = (
        after.header_correction(field)
        if finding.line_no is None
        else after.line(finding.line_no).correction(field)
    )
    if correction is None:
        return None
    holder = before.header if finding.line_no is None else before.line(finding.line_no).po_line
    flag = next(
        (f for f in holder.flags if f.field == field and f.flag is RegionFlag.MODEL_READ), None
    )
    if flag is None:
        return None
    read = getattr(holder, field)
    typed = getattr(value_with_correction(holder, correction), field)
    return LabelledCase(
        label_id=new_id(),
        decided_at=correction.at,
        step=ModelStep.PO_BODY_EXTRACTION,
        lane=CaseKind.ORDER,
        case_id=before.case_id,
        customer_code=before.customer_code,
        message_id=before.message_id,
        attachment_id=before.document.attachment_id,
        line_no=finding.line_no,
        field=field,
        proposed=value_text(read),
        kept=value_text(typed),
        prompt=before.document.parser_version,
        model_profile=before.document.model_profile,
        rules=before.rules_version,
        decided_by=correction.by,
        # How sure the model was (ticket 44): what the step's threshold is
        # measured on; None where the call gave no token probabilities.
        confidence=flag.confidence,
        # What the gate did with it: a label with no gate is measured on
        # nothing (`GatedLabelsPort`).
        gate=flag.gate,
    )


def rfq_value_labels(before: QuoteCase, after: QuoteCase, *, new_id: NewId) -> list[LabelledCase]:
    """Each value of a request a model read (`rfq_extraction`) that Sales
    confirmed by this decision: one per confirmation the decision added, as
    read or as typed ("as read" confirms several at once, each its own
    case). Nothing where the request was read by its fixed labels."""
    reading = after.request.reading
    if reading is None:
        return []
    earlier = {
        (f.line_no, c.field)
        for f in before.findings
        if f.code is QuoteFindingCode.VALUE_UNCERTAIN
        for c in f.confirmed
    }
    attachment = after.request.attachment
    labels: list[LabelledCase] = []
    for finding in after.findings:
        if finding.code is not QuoteFindingCode.VALUE_UNCERTAIN:
            continue
        for confirmation in finding.confirmed:
            if (finding.line_no, confirmation.field) in earlier:
                continue
            labels.append(
                LabelledCase(
                    label_id=new_id(),
                    decided_at=confirmation.at,
                    step=request_step(reading),
                    lane=CaseKind.QUOTE,
                    case_id=after.case_id,
                    customer_code=after.customer_code,
                    message_id=after.request.message_id,
                    attachment_id=None if attachment is None else attachment.attachment_id,
                    line_no=finding.line_no,
                    field=confirmation.field,
                    proposed=confirmation.read,
                    kept=confirmation.read if confirmation.as_read else confirmation.value,
                    prompt=reading.prompt,
                    model_profile=reading.model_profile,
                    rules=reading.rules,
                    decided_by=confirmation.by,
                )
            )
    return labels


def change_line_label(
    case: OrderCase, request: ChangeRequest, decided: ChangeLine, *, new_id: NewId
) -> LabelledCase | None:
    """One line of a change request a model read from the mail's words
    (`change_request`), confirmed (the value asked, kept) or rejected
    (nothing kept). None for a line read from a table or typed by a person."""
    reading = request.reading
    if decided.read_by != "model" or reading is None or decided.state == "open":
        return None
    assert decided.decided_by is not None and decided.decided_at is not None  # decided
    return LabelledCase(
        label_id=new_id(),
        decided_at=decided.decided_at,
        step=ModelStep.CHANGE_REQUEST,
        lane=CaseKind.ORDER,
        case_id=case.case_id,
        customer_code=case.customer_code,
        message_id=request.message_id,
        attachment_id=None,
        line_no=decided.line_no,
        field=decided.field,
        proposed=decided.asked,
        kept=decided.asked if decided.state == "confirmed" else None,
        prompt=reading.prompt,
        model_profile=reading.model_profile,
        rules=reading.rules,
        decided_by=decided.decided_by,
    )


def layout_label(
    prefill: LayoutPrefill | None, layout: PoLayout, *, new_id: NewId
) -> LabelledCase | None:
    """A PO layout a person proposed on the form a model pre-filled
    (`layout_proposal`): the pre-filled mapping beside the one proposed. None
    when the model proposed no mapping for this attachment."""
    if (
        prefill is None
        or prefill.mapping is None
        or prefill.attachment_id != layout.sample.attachment_id
    ):
        return None
    return LabelledCase(
        label_id=new_id(),
        decided_at=layout.proposed_at,
        step=ModelStep.LAYOUT_PROPOSAL,
        lane=CaseKind.ORDER,
        case_id=None,
        customer_code=layout.customer_code,
        message_id=layout.sample.message_id,
        attachment_id=layout.sample.attachment_id,
        line_no=None,
        field="mapping",
        proposed=prefill.mapping.model_dump(mode="json"),
        kept=layout.mapping.model_dump(mode="json"),
        prompt=prefill.prompt,
        model_profile=prefill.model_profile,
        rules=prefill.rules,
        decided_by=layout.proposed_by,
    )


def chat_decision_label(
    before: OrderCase,
    after: OrderCase,
    finding_key: str,
    stated: Sequence[Proposal],
    *,
    new_id: NewId,
    at: AwareDatetime,
    by: uuid.UUID,
) -> LabelledCase | None:
    """A flag's decision recorded by the person to whom the case chat had
    stated one for it (`case_chat`, tickets 56 and 57): the chat's latest
    statement on that flag in their own case conversation, beside what they
    recorded, by the chat's button or the page's. The same decision is a
    confirmation; another one (asking the customer where the chat said
    accept, a value typed) a correction. The reason is the person's own
    words, so it is not compared. None where the chat stated nothing on the
    flag, the statement was read by no stamped prompt, or the flag is
    reopened rather than decided."""
    statement = next(
        (
            s
            for s in reversed(stated)
            if isinstance(s, ProposedDecision)
            and s.case_id == before.case_id
            and s.finding_key == finding_key
        ),
        None,
    )
    decided = after.finding(finding_key).disposition
    if statement is None or statement.prompt is None or decided.kind.value == "open":
        return None
    finding = before.finding(finding_key)
    return LabelledCase(
        label_id=new_id(),
        decided_at=at,
        step=ModelStep.CASE_CHAT,
        lane=CaseKind.ORDER,
        case_id=before.case_id,
        customer_code=before.customer_code,
        message_id=before.message_id,
        attachment_id=None,
        line_no=finding.line_no,
        field="flag_decision",
        proposed={"finding_key": finding_key, "decision": statement.decision},
        kept={"finding_key": finding_key, "decision": decided.kind.value},
        prompt=statement.prompt,
        model_profile=None,
        rules=before.rules_version,
        decided_by=by,
    )


def triage_label(
    card: TriageCard,
    *,
    message_id: str,
    customer_code: str | None,
    new_id: NewId,
) -> LabelledCase:
    """A person's decision on a mail's triage card (`triage_card`, ticket
    33): the kind read, the step and the case suggested, beside the step and
    the case the person took (the kind as read: the person routes, they do
    not relabel). Taken as suggested is a confirmation, another step a
    correction, a dismissal a rejection (`verdict_of`)."""
    decided = card.decided
    if decided is None:
        raise ValueError("only a decided card is a labelled case")
    proposed = card.proposal()
    kept = (
        None
        if decided.step is None
        else {
            "kind": card.kind,
            "step": decided.step,
            "case_id": None if decided.case_id is None else str(decided.case_id),
        }
    )
    return LabelledCase(
        label_id=new_id(),
        decided_at=decided.at,
        step=ModelStep.TRIAGE_CARD,
        lane=CaseKind.ORDER,
        case_id=decided.case_id or card.case_id,
        customer_code=customer_code,
        message_id=message_id,
        attachment_id=None,
        line_no=None,
        field="triage",
        proposed=dict(proposed),
        kept=kept,
        prompt=card.prompt,
        model_profile=card.model_profile,
        rules=card.rules,
        decided_by=decided.by,
    )
