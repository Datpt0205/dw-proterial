"""What the Sales API answers: one view and one mapper per resource.

**Amounts fail closed** (spec decision 8, dw_sales ADR 0003, ui-quality §6).
Each mapper takes the caller's `PriceView` and leaves every amount out unless
it allows that amount: a price, a line amount, a printed total, an LME
figure, a copper basis band, a finding's expected/actual for a price-bearing
code, a corrected value that may be an amount, price evidence. A hidden
amount is `{"hidden": true}`, never zero and never absent, so a screen can
say "Đã ẩn" and a test can tell hidden from missing. Another customer's
price, and anything formed from one (the reference price), also needs
``other_customers``.

**A mutation answers with ids only** (`CaseChangeView`): no amount, so the
platform's idempotency store, which keeps the response for a replay, never
holds one, and a replay can never show a price to someone who may not see
it. The screen reads the case again, through the mapper.

Views carry ids, codes, states and the anchors values were read at. Labels
are the screen's (CONTEXT.md): a code goes out as its code.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from dw_sales.application.access import PriceView
from dw_sales.application.case_store import WorkerState
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import (
    BravoOrder,
    ConvertEntry,
    CopperBasis,
    Currency,
    Customer,
    FixedCopper,
    Item,
    LmeMonth,
    OpenYcbg,
    Quotation,
)
from dw_sales.domain.dispositions import CaseKind, MessageDisposition
from dw_sales.domain.messages import InboundMessage
from dw_sales.domain.orders import (
    ALLOWED_DISPOSITIONS,
    AskCustomer,
    CorrectedBySales,
    Finding,
    FindingCode,
    FindingDisposition,
    FlaggedValue,
    LineChange,
    OrderCase,
    OrderLine,
    PoLineAnchors,
)
from dw_sales.domain.quotes import (
    FindingAccepted,
    FindingCorrected,
    PriceEvidence,
    QuoteCase,
    QuoteFinding,
)

_VIEW = ConfigDict(frozen=True)


class Hidden(BaseModel):
    """An amount the caller may not see: there, and not shown."""

    model_config = _VIEW

    hidden: Literal[True] = True


HIDDEN: Final = Hidden()

type Amount = Decimal | Hidden
type Words = str | Hidden


def _shown(value: Decimal, visible: bool) -> Amount:
    """The amount, or the mark that it is hidden. Zero is an amount like any
    other: it is hidden as one, and shown as one."""
    return value if visible else HIDDEN


def _amount(value: Decimal | None, visible: bool) -> Amount | None:
    """As `_shown`, for an amount that may be unknown: None stays None."""
    return None if value is None else _shown(value, visible)


def _words(value: str | None, visible: bool) -> Words | None:
    if value is None:
        return None
    return value if visible else HIDDEN


class CopperBasisView(BaseModel):
    """How a price follows copper. A band's limits are prices of copper."""

    model_config = _VIEW

    kind: Literal["fixed", "lme_band"]
    low_usd_per_tonne: Amount | None = None
    high_usd_per_tonne: Amount | None = None


def _copper(basis: CopperBasis, visible: bool) -> CopperBasisView:
    if isinstance(basis, FixedCopper):
        return CopperBasisView(kind="fixed")
    return CopperBasisView(
        kind="lme_band",
        low_usd_per_tonne=_amount(basis.low_usd_per_tonne, visible),
        high_usd_per_tonne=_amount(basis.high_usd_per_tonne, visible),
    )


class LmeView(BaseModel):
    model_config = _VIEW

    month: str
    usd_per_tonne: Amount | None


def _lme(lme: LmeMonth | None, visible: bool) -> LmeView | None:
    if lme is None:
        return None
    return LmeView(month=lme.month, usd_per_tonne=_shown(lme.usd_per_tonne, visible))


class CaseChangeView(BaseModel):
    """What a mutation answers: which case, at which version, in which state."""

    model_config = _VIEW

    case_kind: CaseKind
    case_id: uuid.UUID
    case_version: int
    status: str


class PendingDecisionView(BaseModel):
    """The platform approval a case waits on: the decision is made there
    (`POST /api/v1/approvals/{approval_id}/decisions`), never on a Sales
    route. Present only while the case is in the state that waits on it."""

    model_config = _VIEW

    approval_id: uuid.UUID
    approval_type: str


def order_change(case: OrderCase) -> CaseChangeView:
    return CaseChangeView(
        case_kind=CaseKind.ORDER,
        case_id=case.case_id,
        case_version=case.case_version,
        status=case.status.value,
    )


def quote_change(case: QuoteCase) -> CaseChangeView:
    return CaseChangeView(
        case_kind=CaseKind.QUOTE,
        case_id=case.case_id,
        case_version=case.case_version,
        status=case.status.value,
    )


# ------------------------------------------------------------------ orders --

# The codes whose expected/actual compare amounts (spec "Findings the checks
# raise"). `value_uncertain`'s typed correction may be an amount too, so its
# corrected value is held to the same rule.
PRICE_BEARING_ORDER_CODES: Final = frozenset(
    {
        FindingCode.PRICE_MISMATCH,
        FindingCode.CURRENCY_MISMATCH,
        FindingCode.LME_BAND_MISMATCH,
        FindingCode.LINE_TOTAL_MISMATCH,
    }
)
_TYPED_AMOUNT_CODES: Final = PRICE_BEARING_ORDER_CODES | {FindingCode.VALUE_UNCERTAIN}
_AMOUNT_FIELDS: Final = frozenset({"unit_price", "amount"})


class ValueState(StrEnum):
    """How sure a value on a case is (CONTEXT.md "Value states")."""

    DW = "dw"
    UNCERTAIN = "uncertain"
    CONFIRMED = "confirmed"
    HAND_ENTERED = "hand_entered"
    SUPERSEDED = "superseded"


class DispositionView(BaseModel):
    model_config = _VIEW

    kind: str
    reason: str | None = None
    value: Words | None = None
    source: str | None = None
    by: uuid.UUID | None = None
    at: datetime | None = None


class OrderFindingView(BaseModel):
    model_config = _VIEW

    key: str
    code: FindingCode
    severity: str
    blocking: bool
    line_no: int | None
    expected: Words | None
    actual: Words | None
    rule_version: str
    disposition: DispositionView
    # What the findings table allows besides `open`, for the screen to offer.
    allowed: list[str]


def _order_disposition(
    code: FindingCode, disposition: FindingDisposition, prices: PriceView
) -> DispositionView:
    if isinstance(disposition, CorrectedBySales):
        return DispositionView(
            kind=disposition.kind.value,
            value=_words(disposition.value, prices.amounts or code not in _TYPED_AMOUNT_CODES),
            source=disposition.source,
            by=disposition.by,
            at=disposition.at,
        )
    if isinstance(disposition, AskCustomer):
        return DispositionView(kind=disposition.kind.value, by=disposition.by, at=disposition.at)
    reason = getattr(disposition, "reason", None)
    return DispositionView(
        kind=disposition.kind.value,
        reason=reason,
        by=getattr(disposition, "by", None),
        at=getattr(disposition, "at", None),
    )


def order_finding(finding: Finding, prices: PriceView) -> OrderFindingView:
    visible = prices.amounts or finding.code not in PRICE_BEARING_ORDER_CODES
    return OrderFindingView(
        key=finding.key,
        code=finding.code,
        severity=finding.severity.value,
        blocking=finding.blocking,
        line_no=finding.line_no,
        expected=_words(finding.expected, visible),
        actual=_words(finding.actual, visible),
        rule_version=finding.rule_version,
        disposition=_order_disposition(finding.code, finding.disposition, prices),
        allowed=sorted(kind.value for kind in ALLOWED_DISPOSITIONS[finding.code]),
    )


class MappingView(BaseModel):
    model_config = _VIEW

    status: str
    prv_code: str | None
    candidates: list[str]
    confirmed_by: uuid.UUID | None
    confirmed_at: datetime | None
    hand_entered: bool


class QuotationBasisView(BaseModel):
    model_config = _VIEW

    quote_no: str
    unit_price: Amount
    currency: Currency
    uom: str | None
    moq: Decimal
    lead_time_days: int
    copper_basis: CopperBasisView
    valid_from: date
    valid_to: date


class ItemBasisView(BaseModel):
    model_config = _VIEW

    prv_code: str
    uom: str | None
    moq: Decimal
    pack_multiple: Decimal
    standard_lead_time_days: int


class LineBasisView(BaseModel):
    model_config = _VIEW

    convert_prv_code: str | None
    candidates: list[str]
    item: ItemBasisView | None
    quotation: QuotationBasisView | None
    lme: LmeView | None
    lead_time_days: int | None
    lead_time_source: str | None
    checks_run: list[str]


class OrderLineView(BaseModel):
    model_config = _VIEW

    line_no: int
    customer_item_code: str
    description: str
    quantity: Decimal
    uom: str
    unit_price: Amount
    amount: Amount
    requested_date: date
    anchors: dict[str, SourceAnchor]
    flags: list[FlaggedValue]
    value_states: dict[str, ValueState]
    mapping: MappingView
    basis: LineBasisView
    suggested_delivery_date: date | None
    confirmed_delivery_date: date | None
    pc_confirmed_by: uuid.UUID | None
    pc_confirmed_at: datetime | None


def _line_states(case: OrderCase, line: OrderLine) -> dict[str, ValueState]:
    """Each printed value's state: uncertain while its region is flagged and
    the finding on it undecided, hand-entered once Sales typed it, confirmed
    once the PIC prepared the case against the source, otherwise as DW1 read
    it."""
    flagged = {flag.field for flag in line.po_line.flags}
    uncertain = [
        f
        for f in case.findings
        if f.code is FindingCode.VALUE_UNCERTAIN and f.line_no == line.line_no
    ]
    typed = any(isinstance(f.disposition, CorrectedBySales) for f in uncertain)
    # A preparer is stamped exactly while the self-check stands.
    prepared = case.prepared_by is not None
    states: dict[str, ValueState] = {}
    for field in PoLineAnchors.model_fields:
        if field in flagged and typed:
            states[field] = ValueState.HAND_ENTERED
        elif field in flagged:
            states[field] = ValueState.UNCERTAIN
        elif prepared:
            states[field] = ValueState.CONFIRMED
        else:
            states[field] = ValueState.DW
    return states


def _basis(line: OrderLine, prices: PriceView) -> LineBasisView:
    basis = line.basis
    quotation = basis.quotation
    return LineBasisView(
        convert_prv_code=basis.convert_prv_code,
        candidates=list(basis.candidates),
        item=ItemBasisView(**basis.item.model_dump()) if basis.item else None,
        quotation=(
            QuotationBasisView(
                quote_no=quotation.quote_no,
                unit_price=_shown(quotation.unit_price, prices.amounts),
                currency=quotation.currency,
                uom=quotation.uom,
                moq=quotation.moq,
                lead_time_days=quotation.lead_time_days,
                copper_basis=_copper(quotation.copper_basis, prices.amounts),
                valid_from=quotation.valid_from,
                valid_to=quotation.valid_to,
            )
            if quotation
            else None
        ),
        lme=(
            LmeView(
                month=basis.lme.month,
                # None: no figure on record for the month, itself the finding.
                usd_per_tonne=_amount(basis.lme.usd_per_tonne, prices.amounts),
            )
            if basis.lme
            else None
        ),
        lead_time_days=basis.lead_time_days,
        lead_time_source=basis.lead_time_source,
        checks_run=list(basis.checks_run),
    )


def order_line(case: OrderCase, line: OrderLine, prices: PriceView) -> OrderLineView:
    po = line.po_line
    mapping = line.mapping
    return OrderLineView(
        line_no=po.line_no,
        customer_item_code=po.customer_item_code,
        description=po.description,
        quantity=po.quantity,
        uom=po.uom,
        unit_price=_shown(po.unit_price, prices.amounts),
        amount=_shown(po.amount, prices.amounts),
        requested_date=po.requested_date,
        anchors=dict(po.anchors),
        flags=list(po.flags),
        value_states=_line_states(case, line),
        mapping=MappingView(
            status=mapping.status.value,
            prv_code=mapping.prv_code,
            candidates=list(mapping.candidates),
            confirmed_by=mapping.confirmed_by,
            confirmed_at=mapping.confirmed_at,
            hand_entered=mapping.hand_entered,
        ),
        basis=_basis(line, prices),
        suggested_delivery_date=line.suggested_delivery_date,
        confirmed_delivery_date=line.confirmed_delivery_date,
        pc_confirmed_by=line.pc_confirmed_by,
        pc_confirmed_at=line.pc_confirmed_at,
    )


class LineChangeView(BaseModel):
    model_config = _VIEW

    line_no: int
    field: str
    before: Words | None
    after: Words | None


def _change(change: LineChange, prices: PriceView) -> LineChangeView:
    visible = prices.amounts or change.field not in _AMOUNT_FIELDS
    return LineChangeView(
        line_no=change.line_no,
        field=change.field,
        before=_words(change.before, visible),
        after=_words(change.after, visible),
    )


class SupersededView(BaseModel):
    model_config = _VIEW

    message_id: str
    received_at: datetime
    attachment_id: str
    revision: int
    value_state: ValueState = ValueState.SUPERSEDED


class CoverageView(BaseModel):
    model_config = _VIEW

    lines_printed: int
    lines_read: int
    regions: list[str]
    unchecked_regions: list[str]
    checks_run: int
    findings: int


class OrderSummaryView(BaseModel):
    """A row of the order list: no amount at all."""

    model_config = _VIEW

    case_id: uuid.UUID
    case_version: int
    status: str
    customer_code: str
    po_no: str
    revision: int
    received_at: datetime
    assigned_to: uuid.UUID | None
    lines: int
    open_findings: int
    open_blocking_findings: int


class OrderCaseView(BaseModel):
    model_config = _VIEW

    case_id: uuid.UUID
    case_version: int
    status: str
    customer_code: str
    message_id: str
    received_at: datetime
    assigned_to: uuid.UUID | None
    po_no: str
    revision: int
    po_date: date
    currency: Currency
    attachment_id: str
    attachment_sha256: str
    header_anchors: dict[str, SourceAnchor]
    header_flags: list[FlaggedValue]
    buyer: str | None
    buyer_anchor: SourceAnchor | None
    total: Amount | None
    total_anchor: SourceAnchor | None
    coverage: CoverageView
    lines: list[OrderLineView]
    findings: list[OrderFindingView]
    changes: list[LineChangeView]
    superseded: list[SupersededView]
    # Stamped when checked (spec decision 11) and when opened (G22).
    rules_version: str | None
    parser_version: str
    catalog_as_of: datetime | None
    release_manifest_ref: str | None
    cross_check_required: bool | None
    export_control_mode: str | None
    duplicate_of_case: uuid.UUID | None
    duplicate_of_so: str | None
    base_so_no: str | None
    prepared_by: uuid.UUID | None
    prepared_at: datetime | None
    bravo_so_no: str | None
    bravo_recorded_by: uuid.UUID | None
    bravo_recorded_at: datetime | None
    bravo_entry_compared: bool
    cross_checked_by: uuid.UUID | None
    cross_checked_at: datetime | None
    returned_reason: str | None
    returned_by: uuid.UUID | None
    returned_at: datetime | None
    confirmed_by: uuid.UUID | None
    confirmed_at: datetime | None
    close_reason: str | None
    closed_by: uuid.UUID | None
    closed_at: datetime | None
    superseded_by_case: uuid.UUID | None
    # Everyone the cross-checker must not be (spec decision 7): the screen
    # disables the control with the reason, the server refuses anyway.
    makers: list[uuid.UUID]
    # The cross-check approval this order waits on, while it does.
    decision: PendingDecisionView | None = None


def order_summary(case: OrderCase, assigned_to: uuid.UUID | None) -> OrderSummaryView:
    open_findings = [f for f in case.findings if f.is_open]
    return OrderSummaryView(
        case_id=case.case_id,
        case_version=case.case_version,
        status=case.status.value,
        customer_code=case.customer_code,
        po_no=case.header.po_no,
        revision=case.header.revision,
        received_at=case.received_at,
        assigned_to=assigned_to,
        lines=len(case.lines),
        open_findings=len(open_findings),
        open_blocking_findings=sum(1 for f in open_findings if f.blocking),
    )


def order_case(
    case: OrderCase,
    *,
    assigned_to: uuid.UUID | None,
    release_manifest_ref: str | None,
    prices: PriceView,
    decision: PendingDecisionView | None = None,
) -> OrderCaseView:
    document = case.document
    total = document.total
    coverage = case.coverage()
    return OrderCaseView(
        case_id=case.case_id,
        case_version=case.case_version,
        status=case.status.value,
        customer_code=case.customer_code,
        message_id=case.message_id,
        received_at=case.received_at,
        assigned_to=assigned_to,
        po_no=case.header.po_no,
        revision=case.header.revision,
        po_date=case.header.po_date,
        currency=case.header.currency,
        attachment_id=document.attachment_id,
        attachment_sha256=document.attachment_sha256,
        header_anchors=dict(case.header.anchors),
        header_flags=list(case.header.flags),
        buyer=document.buyer,
        buyer_anchor=document.buyer_anchor,
        total=_amount(total.amount, prices.amounts) if total else None,
        total_anchor=total.anchor if total else None,
        coverage=CoverageView(
            lines_printed=coverage.lines_printed,
            lines_read=coverage.lines_read,
            regions=list(coverage.regions),
            unchecked_regions=list(document.unchecked_regions),
            checks_run=coverage.checks_run,
            findings=coverage.findings,
        ),
        lines=[order_line(case, line, prices) for line in case.lines],
        findings=[order_finding(f, prices) for f in case.findings],
        changes=[_change(change, prices) for change in case.changes],
        superseded=[
            SupersededView(
                message_id=old.message_id,
                received_at=old.received_at,
                attachment_id=old.document.attachment_id,
                revision=old.document.header.revision,
            )
            for old in case.superseded
        ],
        rules_version=case.rules_version,
        parser_version=document.parser_version,
        catalog_as_of=case.catalog_as_of,
        release_manifest_ref=release_manifest_ref,
        cross_check_required=case.cross_check_required,
        export_control_mode=case.export_control_mode,
        duplicate_of_case=case.duplicate_of_case,
        duplicate_of_so=case.duplicate_of_so,
        base_so_no=case.base_so_no,
        prepared_by=case.prepared_by,
        prepared_at=case.prepared_at,
        bravo_so_no=case.bravo_so_no,
        bravo_recorded_by=case.bravo_recorded_by,
        bravo_recorded_at=case.bravo_recorded_at,
        bravo_entry_compared=case.bravo_entry_compared,
        cross_checked_by=case.cross_checked_by,
        cross_checked_at=case.cross_checked_at,
        returned_reason=case.returned_reason,
        returned_by=case.returned_by,
        returned_at=case.returned_at,
        confirmed_by=case.confirmed_by,
        confirmed_at=case.confirmed_at,
        close_reason=case.close_reason.value if case.close_reason else None,
        closed_by=case.closed_by,
        closed_at=case.closed_at,
        superseded_by_case=case.superseded_by_case,
        makers=sorted(case.makers),
        decision=decision,
    )


# ------------------------------------------------------------------ quotes --


class QuoteDispositionView(BaseModel):
    model_config = _VIEW

    kind: str
    by: uuid.UUID | None = None
    at: datetime | None = None
    reason: str | None = None
    note: str | None = None
    quantity: Decimal | None = None
    needed_by: date | None = None
    customer_code: str | None = None


class QuoteFindingView(BaseModel):
    model_config = _VIEW

    key: str
    code: str
    blocking: bool
    line_no: int | None
    missing: list[str]
    # Every quotation code compares amounts or a copper basis: price-bearing.
    expected: Words | None
    actual: Words | None
    rule_versions: list[str]
    disposition: QuoteDispositionView


def quote_finding_key(finding: QuoteFinding) -> str:
    """``code:line`` (``-`` for the request as a whole), as an order's key."""
    return f"{finding.code.value}:{finding.line_no or '-'}"


def quote_finding(finding: QuoteFinding, prices: PriceView) -> QuoteFindingView:
    disposition = finding.disposition
    if isinstance(disposition, FindingCorrected):
        decided = QuoteDispositionView(
            kind=disposition.kind,
            by=disposition.by,
            at=disposition.at,
            note=disposition.note,
            quantity=disposition.quantity,
            needed_by=disposition.needed_by,
            customer_code=disposition.customer_code,
        )
    elif isinstance(disposition, FindingAccepted):
        decided = QuoteDispositionView(
            kind=disposition.kind, by=disposition.by, at=disposition.at, reason=disposition.reason
        )
    else:
        decided = QuoteDispositionView(kind=disposition.kind)
    return QuoteFindingView(
        key=quote_finding_key(finding),
        code=finding.code.value,
        blocking=finding.blocking,
        line_no=finding.line_no,
        missing=list(finding.missing),
        expected=_words(finding.expected, prices.amounts),
        actual=_words(finding.actual, prices.amounts),
        rule_versions=list(finding.rule_versions),
        disposition=decided,
    )


class QuoteLineView(BaseModel):
    model_config = _VIEW

    line_no: int
    customer_item_code: str | None
    description: str
    quantity: Decimal | None
    uom: str
    target_price: Amount | None
    needed_by: date | None
    anchors: dict[str, SourceAnchor]


class DesignLineView(BaseModel):
    model_config = _VIEW

    line_no: int
    bp_code: str
    spec_no: str
    prv_code: str | None
    copper_kg_per_km: Decimal | None
    anchors: dict[str, SourceAnchor]


class DesignReplyView(BaseModel):
    model_config = _VIEW

    message_id: str
    received_at: datetime
    attachment_id: str
    ycbg_no: str
    reply_date: date
    lines: list[DesignLineView]


class PricedLineView(BaseModel):
    model_config = _VIEW

    line_no: int
    unit_price: Amount
    moq: Decimal
    lead_time_days: int
    copper_basis: CopperBasisView


class PricingView(BaseModel):
    model_config = _VIEW

    decided_by: uuid.UUID
    decided_at: datetime
    lme: LmeView | None
    lines: list[PricedLineView]
    # Management's words on the price, for the approver: may name a figure.
    management_guidance: Words | None


class SubmissionView(BaseModel):
    model_config = _VIEW

    quote_no: str
    issued_on: date
    valid_to: date
    document_sha256: str
    priced_by: uuid.UUID
    submitted_by: uuid.UUID
    submitted_at: datetime
    recipients: list[str]


class ReturnView(BaseModel):
    model_config = _VIEW

    returned_by: uuid.UUID
    returned_at: datetime
    reason: str
    case_version: int


class QuoteApprovalView(BaseModel):
    model_config = _VIEW

    approved_by: uuid.UUID
    approved_at: datetime
    case_version: int
    document_sha256: str


class StampView(BaseModel):
    model_config = _VIEW

    by: uuid.UUID
    at: datetime


class DeclineView(BaseModel):
    model_config = _VIEW

    declined_by: uuid.UUID
    declined_at: datetime
    reason: str
    note: str | None


class QuotationRowView(BaseModel):
    """A quotation in the evidence or the master data."""

    model_config = _VIEW

    quote_no: str
    customer_code: str
    prv_code: str
    unit_price: Amount
    currency: Currency
    uom: str | None
    moq: Decimal
    lead_time_days: int
    copper_basis: CopperBasisView
    valid_from: date
    valid_to: date


def quotation_row(quotation: Quotation, visible: bool) -> QuotationRowView:
    return QuotationRowView(
        quote_no=quotation.quote_no,
        customer_code=quotation.customer_code,
        prv_code=quotation.prv_code,
        unit_price=_shown(quotation.unit_price, visible),
        currency=quotation.currency,
        uom=quotation.uom,
        moq=quotation.moq,
        lead_time_days=quotation.lead_time_days,
        copper_basis=_copper(quotation.copper_basis, visible),
        valid_from=quotation.valid_from,
        valid_to=quotation.valid_to,
    )


class OrderedLineView(BaseModel):
    model_config = _VIEW

    so_no: str
    order_date: date
    currency: Currency
    quantity: Decimal
    unit_price: Amount


class EvidenceView(BaseModel):
    """What Sales weighs for one line (step 7). Only for `sales.price.read`;
    other customers' rows and the reference price only for
    `sales.price.other_customers.read` too."""

    model_config = _VIEW

    line_no: int
    prv_code: str | None
    as_of: date
    pricing_policy: str
    target_price: Amount | None
    own_history: list[QuotationRowView]
    other_customers: list[QuotationRowView] | Hidden
    orders: list[OrderedLineView]
    lme: LmeView | None
    copper_usd_per_uom: Amount | None
    floor: Amount | None
    freight_usd_per_km: Amount | None
    reference_price: Amount | Hidden | None


def evidence(rows: Iterable[PriceEvidence], prices: PriceView) -> list[EvidenceView] | Hidden:
    if not prices.amounts:
        return HIDDEN
    out = []
    for row in rows:
        out.append(
            EvidenceView(
                line_no=row.line_no,
                prv_code=row.prv_code,
                as_of=row.as_of,
                pricing_policy=row.pricing_policy,
                target_price=row.target_price,
                own_history=[quotation_row(q, True) for q in row.own_history],
                other_customers=(
                    [quotation_row(r.quotation, True) for r in row.other_customers]
                    if prices.other_customers
                    else HIDDEN
                ),
                orders=[
                    OrderedLineView(
                        so_no=line.so_no,
                        order_date=line.order_date,
                        currency=line.currency,
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                    )
                    for line in row.orders
                ],
                lme=_lme(row.lme, True),
                copper_usd_per_uom=row.copper.usd_per_uom if row.copper else None,
                floor=row.floor.price if row.floor else None,
                freight_usd_per_km=(
                    row.freight.rate.usd_per_km if row.freight and row.freight.rate else None
                ),
                reference_price=(
                    (row.reference.price if row.reference else None)
                    if prices.other_customers
                    else HIDDEN
                ),
            )
        )
    return out


class QuoteSummaryView(BaseModel):
    model_config = _VIEW

    case_id: uuid.UUID
    case_version: int
    status: str
    customer_code: str
    rfq_no: str
    received_at: datetime
    quote_due: date | None
    overdue: bool
    assigned_to: uuid.UUID | None
    ycbg_no: str | None
    open_findings: int


class QuoteCaseView(BaseModel):
    model_config = _VIEW

    case_id: uuid.UUID
    case_version: int
    status: str
    customer_code: str
    customer_from: str
    message_id: str
    received_at: datetime
    sender: str
    assigned_to: uuid.UUID | None
    rfq_no: str
    rfq_date: date
    quote_due: date | None
    overdue: bool
    currency: Currency
    attachment_id: str
    attachment_sha256: str
    rules_version: str
    parser_version: str
    catalog_as_of: datetime
    release_manifest_ref: str | None
    lines: list[QuoteLineView]
    findings: list[QuoteFindingView]
    ycbg_no: str | None
    ycbg_recorded_by: uuid.UUID | None
    ycbg_recorded_at: datetime | None
    design_reply: DesignReplyView | None
    design_replies: int
    pricing: PricingView | None
    earlier_pricing: int
    returns: list[ReturnView]
    submission: SubmissionView | None
    approval: QuoteApprovalView | None
    sent: StampView | None
    master_list: StampView | None
    decline: DeclineView | None
    evidence: list[EvidenceView] | Hidden | None
    # The approval this quotation waits on, while it does.
    decision: PendingDecisionView | None = None


def _anchors(**named: SourceAnchor | None) -> dict[str, SourceAnchor]:
    return {name: anchor for name, anchor in named.items() if anchor is not None}


def quote_summary(case: QuoteCase, assigned_to: uuid.UUID | None, today: date) -> QuoteSummaryView:
    document = case.request.document
    return QuoteSummaryView(
        case_id=case.case_id,
        case_version=case.case_version,
        status=case.status.value,
        customer_code=case.customer_code,
        rfq_no=document.rfq_no.value,
        received_at=case.request.received_at,
        quote_due=document.quote_due.value if document.quote_due else None,
        overdue=case.is_overdue(today),
        assigned_to=assigned_to,
        ycbg_no=case.ycbg.ycbg_no if case.ycbg else None,
        open_findings=sum(1 for f in case.findings if f.is_open),
    )


def quote_case(
    case: QuoteCase,
    *,
    assigned_to: uuid.UUID | None,
    release_manifest_ref: str | None,
    today: date,
    prices: PriceView,
    evidence_rows: Sequence[PriceEvidence] | None,
    decision: PendingDecisionView | None = None,
) -> QuoteCaseView:
    request = case.request
    document = request.document
    reply = case.design_reply
    pricing = case.pricing
    submission = case.submission
    return QuoteCaseView(
        case_id=case.case_id,
        case_version=case.case_version,
        status=case.status.value,
        customer_code=case.customer_code,
        customer_from=request.customer_from,
        message_id=request.message_id,
        received_at=request.received_at,
        sender=request.sender.address,
        assigned_to=assigned_to,
        rfq_no=document.rfq_no.value,
        rfq_date=document.rfq_date.value,
        quote_due=document.quote_due.value if document.quote_due else None,
        overdue=case.is_overdue(today),
        currency=request.currency,
        attachment_id=request.attachment.attachment_id,
        attachment_sha256=request.attachment.sha256,
        rules_version=case.rules_version,
        parser_version=case.parser_version,
        catalog_as_of=case.catalog_as_of,
        release_manifest_ref=release_manifest_ref,
        lines=[
            QuoteLineView(
                line_no=item.line_no,
                customer_item_code=(
                    item.customer_item_code.value if item.customer_item_code else None
                ),
                description=item.description.value,
                quantity=case.quantity(item.line_no),
                uom=item.uom.value,
                target_price=(
                    _amount(item.target_price.value, prices.amounts) if item.target_price else None
                ),
                needed_by=case.needed_by(item.line_no),
                anchors=_anchors(
                    customer_item_code=(
                        item.customer_item_code.source if item.customer_item_code else None
                    ),
                    description=item.description.source,
                    quantity=item.quantity.source,
                    uom=item.uom.source,
                    target_price=item.target_price.source if item.target_price else None,
                    needed_by=item.needed_by.source,
                ),
            )
            for item in document.items
        ],
        findings=[quote_finding(f, prices) for f in case.findings],
        ycbg_no=case.ycbg.ycbg_no if case.ycbg else None,
        ycbg_recorded_by=case.ycbg.recorded_by if case.ycbg else None,
        ycbg_recorded_at=case.ycbg.recorded_at if case.ycbg else None,
        design_reply=(
            DesignReplyView(
                message_id=reply.message_id,
                received_at=reply.received_at,
                attachment_id=reply.attachment.attachment_id,
                ycbg_no=reply.ycbg_no,
                reply_date=reply.document.reply_date.value,
                lines=[
                    DesignLineView(
                        line_no=line.line_no,
                        bp_code=line.bp_code.value,
                        spec_no=line.spec_no.value,
                        prv_code=line.prv_code.value if line.prv_code else None,
                        copper_kg_per_km=(
                            line.copper_kg_per_km.value if line.copper_kg_per_km else None
                        ),
                        anchors=_anchors(
                            bp_code=line.bp_code.source,
                            spec_no=line.spec_no.source,
                            prv_code=line.prv_code.source if line.prv_code else None,
                            copper_kg_per_km=(
                                line.copper_kg_per_km.source if line.copper_kg_per_km else None
                            ),
                        ),
                    )
                    for line in reply.document.lines
                ],
            )
            if reply
            else None
        ),
        design_replies=len(case.design_replies),
        pricing=(
            PricingView(
                decided_by=pricing.decided_by,
                decided_at=pricing.decided_at,
                lme=_lme(pricing.lme, prices.amounts),
                lines=[
                    PricedLineView(
                        line_no=line.line_no,
                        unit_price=_shown(line.unit_price, prices.amounts),
                        moq=line.moq,
                        lead_time_days=line.lead_time_days,
                        copper_basis=_copper(line.copper_basis, prices.amounts),
                    )
                    for line in pricing.lines
                ],
                management_guidance=_words(pricing.management_guidance, prices.amounts),
            )
            if pricing
            else None
        ),
        earlier_pricing=len(case.earlier_pricing),
        returns=[ReturnView(**r.model_dump()) for r in case.returns],
        submission=(
            SubmissionView(
                quote_no=submission.document.quote_no,
                issued_on=submission.document.issued_on,
                valid_to=submission.document.valid_to,
                document_sha256=submission.document_sha256,
                priced_by=submission.priced_by,
                submitted_by=submission.submitted_by,
                submitted_at=submission.submitted_at,
                recipients=[r.address for r in submission.document.recipients],
            )
            if submission
            else None
        ),
        approval=QuoteApprovalView(**case.approval.model_dump()) if case.approval else None,
        sent=StampView(**case.sent.model_dump()) if case.sent else None,
        master_list=StampView(**case.master_list.model_dump()) if case.master_list else None,
        decline=(
            DeclineView(
                declined_by=case.decline.declined_by,
                declined_at=case.decline.declined_at,
                reason=case.decline.reason.value,
                note=case.decline.note,
            )
            if case.decline
            else None
        ),
        evidence=evidence(evidence_rows, prices) if evidence_rows is not None else None,
        decision=decision,
    )


# ------------------------------------------------------------------- inbox --


class MessageDispositionView(BaseModel):
    model_config = _VIEW

    kind: str
    case_kind: CaseKind | None = None
    case_id: uuid.UUID | None = None
    reason: str | None = None
    detail: str | None = None
    owner: str | None = None
    customer_code: str | None = None
    processed_at: datetime | None = None


def message_disposition(
    disposition: MessageDisposition, processed_at: datetime | None
) -> MessageDispositionView:
    return MessageDispositionView(
        kind=disposition.kind.value,
        case_kind=disposition.case_kind,
        case_id=disposition.case_id,
        reason=disposition.reason.value if disposition.reason else None,
        detail=disposition.detail,
        owner=disposition.owner,
        customer_code=disposition.customer_code,
        processed_at=processed_at,
    )


class AttachmentView(BaseModel):
    model_config = _VIEW

    attachment_id: str
    name: str
    media_type: str
    size: int


class InboxMessageView(BaseModel):
    model_config = _VIEW

    message_id: str
    sender: str
    sender_name: str
    subject: str
    received_at: datetime
    body_text: str
    attachments: list[AttachmentView]
    sender_verified: bool
    disposition: MessageDispositionView


def inbox_message(message: InboundMessage, disposition: MessageDispositionView) -> InboxMessageView:
    return InboxMessageView(
        message_id=message.message_id,
        sender=message.sender.address,
        sender_name=message.sender.display_name,
        subject=message.subject,
        received_at=message.received_at,
        body_text=message.body_text,
        attachments=[
            AttachmentView(
                attachment_id=a.attachment_id, name=a.name, media_type=a.media_type, size=a.size
            )
            for a in message.attachments
        ],
        sender_verified=message.authentication.verified,
        disposition=disposition,
    )


class WorkerStateView(BaseModel):
    model_config = _VIEW

    paused: bool
    changed_by: uuid.UUID | None
    changed_at: datetime | None
    reason: str | None


def worker_state(state: WorkerState) -> WorkerStateView:
    return WorkerStateView(
        paused=state.paused,
        changed_by=state.changed_by,
        changed_at=state.changed_at,
        reason=state.reason,
    )


# ------------------------------------------------------------- master data --


class CustomerView(BaseModel):
    model_config = _VIEW

    code: str
    name: str
    language: str
    intra_group: bool
    status: str
    confirmation_channel: str
    contacts: list[str]
    sales_pic: str | None
    noc_confirmed: bool
    esf_fiscal_year: int | None
    denial_list_checked_on: date | None


def customer(record: Customer) -> CustomerView:
    return CustomerView(
        code=record.code,
        name=record.name,
        language=record.language,
        intra_group=record.intra_group,
        status=record.status,
        confirmation_channel=record.confirmation_channel,
        contacts=[c.address for c in record.contacts],
        sales_pic=record.sales_pic,
        noc_confirmed=record.compliance.noc_confirmed,
        esf_fiscal_year=record.compliance.esf_fiscal_year,
        denial_list_checked_on=record.compliance.denial_list_checked_on,
    )


class ItemView(BaseModel):
    model_config = _VIEW

    prv_code: str
    family: str | None
    spec_no: str
    cores: int
    gauge: str
    uom: str | None
    moq: Decimal
    pack_multiple: Decimal
    standard_lead_time_days: int


def item(record: Item) -> ItemView:
    return ItemView(
        prv_code=record.prv_code,
        family=record.family,
        spec_no=record.attributes.spec_no,
        cores=record.attributes.cores,
        gauge=record.attributes.gauge,
        uom=record.uom,
        moq=record.moq,
        pack_multiple=record.pack_multiple,
        standard_lead_time_days=record.standard_lead_time_days,
    )


class ConvertEntryView(BaseModel):
    model_config = _VIEW

    customer_code: str
    customer_item_code: str
    prv_code: str


def convert_entry(record: ConvertEntry) -> ConvertEntryView:
    return ConvertEntryView(**record.model_dump())


class BravoOrderLineView(BaseModel):
    model_config = _VIEW

    line_no: int
    prv_code: str
    quantity: Decimal
    unit_price: Amount
    delivery_date: date


class BravoOrderView(BaseModel):
    model_config = _VIEW

    so_no: str
    customer_code: str
    po_no: str
    po_revision: int
    order_date: date
    currency: Currency
    lines: list[BravoOrderLineView]


def bravo_order(record: BravoOrder, visible: bool) -> BravoOrderView:
    return BravoOrderView(
        so_no=record.so_no,
        customer_code=record.customer_code,
        po_no=record.po_no,
        po_revision=record.po_revision,
        order_date=record.order_date,
        currency=record.currency,
        lines=[
            BravoOrderLineView(
                line_no=line.line_no,
                prv_code=line.prv_code,
                quantity=line.quantity,
                unit_price=_shown(line.unit_price, visible),
                delivery_date=line.delivery_date,
            )
            for line in record.lines
        ],
    )


def lme_month(record: LmeMonth, visible: bool) -> LmeView:
    view = _lme(record, visible)
    assert view is not None
    return view


class OpenYcbgView(BaseModel):
    model_config = _VIEW

    ycbg_no: str
    customer_code: str
    rfq_no: str
    issued_on: date


def open_ycbg(record: OpenYcbg) -> OpenYcbgView:
    return OpenYcbgView(**record.model_dump())


class MasterDataView[T](BaseModel):
    """A master-data list and the snapshot's ``as_of`` it was read at."""

    model_config = _VIEW

    as_of: datetime
    items: list[T]
