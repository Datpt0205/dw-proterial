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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from dw_platform.domain.messages import InboundMessage
from dw_sales.application.access import PriceView
from dw_sales.application.autonomy import applied_by
from dw_sales.application.case_store import (
    JobError,
    JobStatus,
    LoggedMessage,
    MessageHandled,
    ProcessingJob,
    SentRead,
    ServedSource,
    SourceRegion,
    WorkerState,
)
from dw_sales.application.source import (
    NOTHING_OPENED,
    OpenedSources,
    UnopenedValue,
    unopened_values,
    value_unserved,
)
from dw_sales.application.threads import CaseThread
from dw_sales.domain.anchors import SourceAnchor, TextRange
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
from dw_sales.domain.change_requests import (
    Blocked,
    ChangeField,
    ChangeLineState,
    ChangeOutcome,
    ChangeRequest,
    ChangeRequestState,
    ReadBy,
)
from dw_sales.domain.description_reading import DescriptionReading
from dw_sales.domain.descriptions import StatedAttributes
from dw_sales.domain.dispositions import CaseKind, MessageDisposition
from dw_sales.domain.followups import SalesFollowups, due_soon
from dw_sales.domain.handoffs import Handoff, HandoffTeam
from dw_sales.domain.layouts import LayoutPrefill
from dw_sales.domain.message_intent import IntentReading
from dw_sales.domain.orders import (
    ALLOWED_DISPOSITIONS,
    AMOUNT_FIELDS,
    AgreementHow,
    AskCustomer,
    ChangedField,
    CorrectedBySales,
    CountedFrom,
    DayCount,
    Derivation,
    DispositionKind,
    Finding,
    FindingCode,
    FindingDisposition,
    FlaggedValue,
    InternalReason,
    LineChange,
    MappingStatus,
    OrderCase,
    OrderLine,
    OrderStatus,
    PcVerdict,
    PoDocument,
    PoLineAnchors,
    PrintCopy,
    UpdateStep,
    ValueCorrection,
)
from dw_sales.domain.quotes import (
    DesignCheck,
    FindingAccepted,
    FindingCorrected,
    FromOrder,
    PriceEvidence,
    PriceSuggestion,
    QuoteCase,
    QuoteFinding,
    RequestReading,
    suggest_price,
)
from dw_sales.domain.reply_intent import (
    AgentFallback,
    Author,
    CaseReply,
    ProposedStep,
    ReplyReading,
    ThreadIntent,
    proposed_step,
)
from dw_sales.domain.triage import CardVerdict, TriageStep

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


class UnappliedDecisionView(BaseModel):
    """A cross-check decision the platform recorded and DW1's run could not
    apply to the order (ticket 14): who decided which way, on which version,
    and the reason code. Ids and codes only."""

    model_config = _VIEW

    approval_id: uuid.UUID | None
    run_id: uuid.UUID
    decided_by: uuid.UUID
    approved: bool
    decided_on: int | None
    reason_code: str
    at: datetime


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


class ValueState(StrEnum):
    """How sure a value on a case is (CONTEXT.md "Value states")."""

    DW = "dw"
    UNCERTAIN = "uncertain"
    CONFIRMED = "confirmed"
    # Prepared, but the preparer was never served the page or sheet it was
    # read from (audit gap 1): nobody checked it, whatever the step says.
    NOT_OPENED = "not_opened"
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
    # The values a `value_uncertain` flagged, each corrected on its own
    # (`POST .../corrections`); empty for every other code.
    fields: list[str]


class ValueCorrectionView(BaseModel):
    """A value Sales typed for a flagged field, beside the value as read. An
    amount is shown only with `sales.price.read`."""

    model_config = _VIEW

    field: str
    value: Words
    by: uuid.UUID
    at: datetime


class AppliedChangeView(BaseModel):
    """A value of the line the customer asked to change by mail, which a
    person confirmed (ticket 27): it replaces the value above where the line
    is entered. Never an amount."""

    model_config = _VIEW

    field: ChangedField
    value: str
    request_id: uuid.UUID
    by: uuid.UUID
    at: datetime


class ChangeLineView(BaseModel):
    """One value a customer's mail asks to change (`ChangeLine`)."""

    model_config = _VIEW

    seq: int
    line_no: int
    field: ChangeField
    # In the field's one form: an ISO date, a number. None: the case holds
    # no value there (no such line, or a line printed with no date).
    held: str | None
    asked: str
    written: str
    unit: str | None
    # Characters of the request's `text`; None for a line a person typed.
    anchor: TextRange | None
    read_by: ReadBy
    # Why it cannot be confirmed as read; the screen disables the button
    # with this reason, and the server refuses anyway.
    blocked: Blocked | None
    state: ChangeLineState
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    reason: str | None


class ChangeRequestView(BaseModel):
    """A change request on the order (ticket 27, dw_sales ADR 0010), with
    the mail's newest part its anchors index into: the customer's own words.
    The mail may state a price, so its text is served only to a holder of
    `sales.price.read`, as the mail text of a PO read from the body is; for
    anyone else it is absent, and the lines' own words stand."""

    model_config = _VIEW

    request_id: uuid.UUID
    message_id: str
    opened_by: uuid.UUID
    opened_at: datetime
    state: ChangeRequestState
    lines: list[ChangeLineView]
    unread: int
    # None: the caller may not read prices (above).
    text: str | None
    # The model call that read the free text, where one was made.
    reading: ChangeOutcome | None
    prompt: str | None


def change_request_view(request: ChangeRequest, *, prices: PriceView) -> ChangeRequestView:
    return ChangeRequestView(
        request_id=request.request_id,
        message_id=request.message_id,
        opened_by=request.opened_by,
        opened_at=request.opened_at,
        state=request.state,
        lines=[ChangeLineView.model_validate(line.model_dump()) for line in request.lines],
        unread=request.unread,
        text=request.text.text if prices.amounts else None,
        reading=request.reading.outcome if request.reading else None,
        prompt=request.reading.prompt if request.reading else None,
    )


def _corrections(
    corrections: Iterable[ValueCorrection], prices: PriceView
) -> list[ValueCorrectionView]:
    return [
        ValueCorrectionView(
            field=c.field,
            value=c.value if prices.amounts or c.field not in AMOUNT_FIELDS else HIDDEN,
            by=c.by,
            at=c.at,
        )
        for c in corrections
    ]


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


def order_finding(case: OrderCase, finding: Finding, prices: PriceView) -> OrderFindingView:
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
        allowed=sorted(kind.value for kind in _offered(case, finding)),
        fields=sorted(case.correctable_fields(finding)),
    )


def _offered(case: OrderCase, finding: Finding) -> frozenset[DispositionKind]:
    """What the findings table allows, less a free-text value on a
    `value_uncertain` the case would refuse (`OrderCase.takes_value_note`): the
    screen offers what the write takes."""
    allowed = ALLOWED_DISPOSITIONS[finding.code]
    if finding.code is FindingCode.VALUE_UNCERTAIN and not case.takes_value_note(finding):
        return allowed - {DispositionKind.CORRECTED_BY_SALES}
    return allowed


class MappingView(BaseModel):
    model_config = _VIEW

    status: str
    prv_code: str | None
    candidates: list[str]
    confirmed_by: uuid.UUID | None
    confirmed_at: datetime | None
    hand_entered: bool
    # DW confirmed the code by itself (ticket 44): shown as such, and undone
    # by a person in one click. Never says whether a line still waiting was
    # sampled for the audit: the person decides it as any other.
    applied_by_dw: bool = False


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
    # None: the item master did not hold it, and the check did not run.
    moq: Decimal | None
    pack_multiple: Decimal | None
    standard_lead_time_days: int | None


class SpanReadView(BaseModel):
    """One attribute a model reading located: the text, where it sits in the
    normalised description, the value, and whether code parsed the value
    (``code``) or it is the model's label (``model``), which Sales checks."""

    model_config = _VIEW

    attribute: str
    span: str
    start: int
    end: int
    value: str
    read_by: Literal["code", "model"]


class DescriptionReadingView(BaseModel):
    """What a model reading of the description did (dw_sales ADR 0005).
    ``outcome``: ``read``, ``not_understood`` (``reason`` says which check
    refused it) or ``unavailable`` (no usable answer: DW1 could not read it)."""

    model_config = _VIEW

    outcome: Literal["read", "not_understood", "unavailable"]
    reason: str | None
    prompt: str
    model_profile: str
    spans: list[SpanReadView]


class StatedAttributesView(BaseModel):
    """What the description stated of the attributes the candidate picker
    compares with each item (`ItemView`), as stamped when the line was
    mapped (`LineBasis.stated_attributes`). None: not stated."""

    model_config = _VIEW

    spec_no: str | None
    family: str | None
    cores: int | None
    gauge: str | None


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
    # None: no model was asked about this line.
    description_reading: DescriptionReadingView | None
    # None: DW1 did not read the description (a convert entry decided, or
    # the text was not understood), or the line predates the stamp.
    stated_attributes: StatedAttributesView | None


class DeliveryScheduleView(BaseModel):
    """One delivery of a line's quantity (ticket 21), as the line is entered
    (a schedule the PO prints is never typed over): where it is printed,
    DW1's suggested date for it, and, on a line the PO splits, the date Sales
    confirmed for it (ticket 35)."""

    model_config = _VIEW

    quantity: Decimal
    requested_date: date
    anchor: SourceAnchor
    suggested_delivery_date: date | None
    # None before confirmation, and on a line delivered once, whose date is
    # the line's `confirmed_delivery_date`.
    confirmed_delivery_date: date | None


class PcDeliveryView(BaseModel):
    """One delivery of a line as PC confirmed it (ticket 07)."""

    model_config = _VIEW

    quantity: Decimal
    # Bravo's "Ngày XN giao hàng lần đầu", kept when PC confirms again.
    first_date: date
    # Bravo's "Ngày XN giao hàng": PC's date now.
    date: date


class PcAnswerView(BaseModel):
    """PC's answer for a line and who recorded it (ticket 07)."""

    model_config = _VIEW

    deliveries: list[PcDeliveryView]
    by: uuid.UUID
    at: datetime


class PcRequestStateView(BaseModel):
    """Sales asked PC for these lines' dates, and waits (ticket 07)."""

    model_config = _VIEW

    lines: list[int]
    by: uuid.UUID
    at: datetime


class DesignRequestStateView(BaseModel):
    """Sales asked Design to create a PRV code for this line, and waits (ticket 06)."""

    model_config = _VIEW

    line_no: int
    by: uuid.UUID
    at: datetime


class UpdateDeliveryView(BaseModel):
    """One delivery PC gives a changed line in the update loop (ticket 29)."""

    model_config = _VIEW

    quantity: Decimal
    date: date


class UpdateLineView(BaseModel):
    """One line a customer's change asks about, in the update loop: what the
    order holds now, what is asked (None: that value is not changed) and PC's
    answer for it, once recorded."""

    model_config = _VIEW

    line_no: int
    held_quantity: Decimal
    held_requested_date: date | None
    asked_quantity: Decimal | None
    asked_requested_date: date | None
    pc_deliveries: list[UpdateDeliveryView] | None
    pc_answered_by: uuid.UUID | None


class UpdateApprovalView(BaseModel):
    """The Bravo update file the PIC approved, by its id and hash."""

    model_config = _VIEW

    artifact_id: uuid.UUID
    sha256: str
    case_version: int
    by: uuid.UUID
    at: datetime


# The one action the update loop waits on now: its step's, or once the
# customer accepted, the Bravo update's (approve the file, record it entered,
# the cross-check, the confirmation).
UpdateAwaits = Literal[
    "ask_pc",
    "waiting_pc",
    "answer_customer",
    "waiting_customer",
    "approve_update",
    "bravo_entry",
    "cross_check",
    "confirm",
]


class ImpliedTermView(BaseModel):
    """A customer's days of silence that count as agreement, as the rules
    stamped on the case gave them when the confirmation left (ticket 28)."""

    model_config = _VIEW

    days: int
    day_count: DayCount
    counted_from: CountedFrom


class ConfirmationView(BaseModel):
    """The confirmation that left (ticket 28): when (the clock of silence),
    the sent copy it was recorded from, and, for a customer with days of
    silence, the term and the instant it counts as agreement. None of the
    two: never by silence."""

    model_config = _VIEW

    sent_at: datetime
    message_id: str | None
    term: ImpliedTermView | None
    implied_from: datetime | None


class AgreementView(BaseModel):
    """How the customer agreed, as a person recorded it (ticket 28): in
    words, from their reply and its located sentences when recorded from
    one, or by silence."""

    model_config = _VIEW

    how: AgreementHow
    by: uuid.UUID
    at: datetime
    message_id: str | None
    quotes: list[str]


class ConfirmationCopyView(BaseModel):
    """A message Sales sent on the case's thread carrying the processed
    Excel DW1 made at this case version (by sha256), while the confirmation
    is ahead of the order: it proposes "Ghi đã gửi xác nhận", from that
    mail's time (ticket 28). A suggestion: the PIC records it."""

    model_config = _VIEW

    message_id: str
    received_at: datetime
    subject: str


def confirmation_view(case: OrderCase) -> ConfirmationView | None:
    sent = case.confirmation
    if sent is None:
        return None
    term = sent.term
    return ConfirmationView(
        sent_at=sent.sent_at,
        message_id=sent.message_id,
        term=(
            ImpliedTermView(
                days=term.days, day_count=term.day_count, counted_from=term.counted_from
            )
            if term is not None
            else None
        ),
        implied_from=sent.implied_from,
    )


def agreement_view(case: OrderCase) -> AgreementView | None:
    agreed = case.agreement
    if agreed is None:
        return None
    return AgreementView(
        how=agreed.how,
        by=agreed.by,
        at=agreed.at,
        message_id=agreed.message_id,
        quotes=list(agreed.quotes),
    )


class UpdateLoopView(BaseModel):
    """A customer's change on an order in Bravo (ticket 29): its step, since
    when, code's verdict on PC's answer (6-DW4 ``can_do`` or 6-DW3
    ``proposes``), the lines and the approved Bravo update file."""

    model_config = _VIEW

    request_id: uuid.UUID
    step: UpdateStep
    since: datetime
    awaits: UpdateAwaits
    verdict: PcVerdict | None
    lines: list[UpdateLineView]
    approval: UpdateApprovalView | None
    # Why, for Proterial's own change (ticket 10); None: a customer's.
    reason: InternalReason | None = None


def _update_awaits(case: OrderCase) -> UpdateAwaits:
    loop = case.update_loop
    assert loop is not None
    if loop.step != "bravo_update":
        return loop.step
    if case.status is OrderStatus.CHANGE_REVIEW:
        return "approve_update" if loop.approval is None else "bravo_entry"
    return "cross_check" if case.awaits_cross_check else "confirm"


def update_loop_view(case: OrderCase) -> UpdateLoopView | None:
    """The order's update loop as its page shows it; None with none."""
    loop = case.update_loop
    if loop is None:
        return None
    lines = []
    for held in loop.lines:
        line = case.line(held.line_no).effective
        asked = {c.field: c.value for c in held.changes}
        pc = held.pc_answer
        lines.append(
            UpdateLineView(
                line_no=held.line_no,
                held_quantity=line.quantity,
                held_requested_date=line.requested_date,
                asked_quantity=Decimal(asked["quantity"]) if "quantity" in asked else None,
                asked_requested_date=(
                    date.fromisoformat(asked["requested_date"])
                    if "requested_date" in asked
                    else None
                ),
                pc_deliveries=(
                    None
                    if pc is None
                    else [
                        UpdateDeliveryView(quantity=d.quantity, date=d.date) for d in pc.deliveries
                    ]
                ),
                pc_answered_by=None if pc is None else pc.by,
            )
        )
    return UpdateLoopView(
        request_id=loop.request_id,
        step=loop.step,
        since=loop.since,
        awaits=_update_awaits(case),
        verdict=loop.verdict,
        lines=lines,
        reason=loop.reason,
        approval=(
            None
            if loop.approval is None
            else UpdateApprovalView.model_validate(loop.approval.model_dump())
        ),
    )


class OrderLineView(BaseModel):
    model_config = _VIEW

    line_no: int
    # The line's own PO number, where the file prints one per line (a
    # portal's export, ticket 18), and where; None: the PO's.
    po_no: str | None = None
    po_no_anchor: SourceAnchor | None = None
    customer_item_code: str
    description: str
    quantity: Decimal
    uom: str
    unit_price: Amount
    amount: Amount
    # None: printed blank, "date to follow" (`requested_date_missing`).
    requested_date: date | None
    # Earliest first; a line with one quantity and one date is a list of one,
    # a line printed with no date has none, and `printed_schedules` says
    # whether the PO prints them apart.
    schedules: list[DeliveryScheduleView]
    printed_schedules: bool
    anchors: dict[str, SourceAnchor]
    flags: list[FlaggedValue]
    # What Sales typed for flagged values; the values above stay as read.
    corrections: list[ValueCorrectionView]
    # What a person confirmed of the customer's change requests (ticket 27).
    changes: list[AppliedChangeView] = []
    value_states: dict[str, ValueState]
    mapping: MappingView
    basis: LineBasisView
    suggested_delivery_date: date | None
    # A line delivered once; a split line's dates are its schedules' (ticket 35).
    confirmed_delivery_date: date | None
    pc_confirmed_by: uuid.UUID | None
    pc_confirmed_at: datetime | None
    # PC's answer: the line's deliveries with PC's first and current dates
    # (ticket 07); once given, the line is confirmed one date per delivery.
    pc_answer: PcAnswerView | None = None
    # Every date Sales confirmed, one per delivery (`OrderLine.deliveries`):
    # a line PC split is confirmed per PC delivery (ticket 07).
    confirmed_delivery_dates: list[date] = []


def _line_states(case: OrderCase, line: OrderLine, checked: OpenedSources) -> dict[str, ValueState]:
    """Each printed value's state: hand-entered once Sales typed it, uncertain
    while its region is flagged and nothing is typed for it, otherwise as DW1
    read it until the PIC prepared the case. Once prepared, confirmed only
    where the preparer had been served the page or sheet the value was read
    from (``checked``), and not opened where they had not: the step alone
    is no evidence that anyone looked (audit gap 1)."""
    flagged = line.po_line.flagged
    typed = {c.field for c in line.corrections}
    # A preparer is stamped exactly while the self-check stands.
    prepared = case.prepared_by is not None
    states: dict[str, ValueState] = {}
    for field in PoLineAnchors.model_fields:
        if field in typed:
            states[field] = ValueState.HAND_ENTERED
        elif field in flagged:
            states[field] = ValueState.UNCERTAIN
        elif not prepared:
            states[field] = ValueState.DW
        elif checked.holds(getattr(line.po_line.anchors, field)):
            states[field] = ValueState.CONFIRMED
        else:
            states[field] = ValueState.NOT_OPENED
    return states


def preparer_checked(case: OrderCase, servings: Iterable[ServedSource]) -> OpenedSources:
    """What the preparer was served of the case's files before preparing it:
    the regions a prepared value counts as checked in. Nothing before then."""
    if case.prepared_by is None or case.prepared_at is None:
        return NOTHING_OPENED
    return OpenedSources.of(servings, by=case.prepared_by, until=case.prepared_at)


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
        description_reading=_reading(basis.description_reading),
        stated_attributes=_stated(basis.stated_attributes),
    )


def _stated(stated: StatedAttributes | None) -> StatedAttributesView | None:
    if stated is None:
        return None
    return StatedAttributesView(
        spec_no=stated.spec_no, family=stated.family, cores=stated.cores, gauge=stated.gauge
    )


def _applied_by_dw(line: OrderLine) -> bool:
    """Whether the line's code is one DW applied by itself and nobody has
    confirmed or undone since (`OrderCase.undo_applied_mapping` takes it)."""
    mapping, reading = line.mapping, line.basis.description_reading
    return (
        mapping.status is MappingStatus.CANDIDATE_CONFIRMED
        and mapping.confirmed_by == applied_by()
        and reading is not None
        and reading.gate == "applied"
    )


def _reading(reading: DescriptionReading | None) -> DescriptionReadingView | None:
    if reading is None:
        return None
    return DescriptionReadingView(
        outcome=reading.outcome,
        reason=reading.reason,
        prompt=reading.prompt,
        model_profile=reading.model_profile,
        spans=[SpanReadView(**span.model_dump()) for span in reading.spans],
    )


def order_line(
    case: OrderCase,
    line: OrderLine,
    prices: PriceView,
    *,
    checked: OpenedSources = NOTHING_OPENED,
) -> OrderLineView:
    """One line; ``checked`` is what its preparer opened (`preparer_checked`),
    nothing by default, so a prepared value reads as not opened."""
    po = line.po_line
    mapping = line.mapping
    confirmed = {index: day for index, (_, day) in enumerate(line.confirmed_schedules())}
    return OrderLineView(
        line_no=po.line_no,
        po_no=po.line_po.po_no if po.line_po is not None else None,
        po_no_anchor=po.line_po.anchor if po.line_po is not None else None,
        customer_item_code=po.customer_item_code,
        description=po.description,
        quantity=po.quantity,
        uom=po.uom,
        unit_price=_shown(po.unit_price, prices.amounts),
        amount=_shown(po.amount, prices.amounts),
        requested_date=po.requested_date,
        schedules=[
            DeliveryScheduleView(
                quantity=s.quantity,
                requested_date=s.requested_date,
                anchor=s.anchor,
                suggested_delivery_date=line.suggested_date(s),
                confirmed_delivery_date=confirmed.get(index),
            )
            for index, s in enumerate(line.effective.schedules)
        ],
        printed_schedules=po.prints_schedules,
        anchors=_seen_anchors(po.anchors, prices),
        flags=list(po.flags),
        corrections=_corrections(line.corrections, prices),
        changes=[AppliedChangeView.model_validate(c.model_dump()) for c in line.changes],
        value_states=_line_states(case, line, checked),
        mapping=MappingView(
            status=mapping.status.value,
            prv_code=mapping.prv_code,
            candidates=list(mapping.candidates),
            confirmed_by=mapping.confirmed_by,
            confirmed_at=mapping.confirmed_at,
            hand_entered=mapping.hand_entered,
            applied_by_dw=_applied_by_dw(line),
        ),
        basis=_basis(line, prices),
        suggested_delivery_date=line.suggested_delivery_date,
        confirmed_delivery_date=line.confirmed_delivery_date,
        pc_confirmed_by=line.pc_confirmed_by,
        pc_confirmed_at=line.pc_confirmed_at,
        pc_answer=(
            PcAnswerView.model_validate(line.pc_answer.model_dump()) if line.pc_answer else None
        ),
        confirmed_delivery_dates=list(line.confirmed_delivery_dates),
    )


class LineChangeView(BaseModel):
    model_config = _VIEW

    line_no: int
    field: str
    before: Words | None
    after: Words | None


def _change(change: LineChange, prices: PriceView) -> LineChangeView:
    visible = prices.amounts or change.field not in AMOUNT_FIELDS
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
    # None: that revision was written in the mail (AI item 4).
    attachment_id: str | None
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
    # Rows the file marks as other than a firm order (a portal's forecast,
    # ticket 18): counted, never read: "N dòng dự báo, không đặt hàng".
    forecast_rows: int = 0


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
    # `OrderCase.awaits_cross_check`: the review page lists these, not every
    # order in Bravo (an order whose rules waive it is confirmed instead).
    awaits_cross_check: bool


class QuoteLinkView(BaseModel):
    """A quote case opened from the order (ticket 09): for which lines, who
    opened it and when, and its status now. ``status`` None: the caller does
    not see that quote case, and is shown only that it exists."""

    model_config = _VIEW

    quote_case_id: uuid.UUID
    lines: list[int]
    by: uuid.UUID
    at: datetime
    status: str | None
    # The order waits on it: it is neither approved nor declined.
    waiting: bool


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
    # The revision the file's name suggests ("R1"; ticket 22): a hint shown
    # beside ``revision``, which with the lines still decides. None: none.
    name_revision: str | None = None
    po_date: date
    currency: Currency
    # None: the PO was written in the mail (AI item 4); its values' anchors
    # are ranges of the message's text, served by its own route, and
    # ``attachment_sha256`` is that text's digest.
    attachment_id: str | None
    attachment_sha256: str
    header_anchors: dict[str, SourceAnchor]
    header_flags: list[FlaggedValue]
    # What Sales typed for the header values and the total (`total`) the
    # PO-level `value_uncertain` flagged; the values here stay as read.
    header_corrections: list[ValueCorrectionView]
    buyer: str | None
    buyer_anchor: SourceAnchor | None
    total: Amount | None
    total_anchor: SourceAnchor | None
    # The first value read from text typed in a TCVN3 or VNI font, which
    # `legacy_encoding` opens the source at; None when there is none.
    legacy_text_anchor: SourceAnchor | None
    # The second file of the same PO in the mail: the PDF print beside its
    # workbook (ticket 34), or any other (ticket 22); None: none was.
    print_copy: PrintCopyView | None
    coverage: CoverageView
    lines: list[OrderLineView]
    findings: list[OrderFindingView]
    changes: list[LineChangeView]
    superseded: list[SupersededView]
    # Stamped when checked (spec decision 11) and when opened (G22).
    rules_version: str | None
    parser_version: str
    # How the bytes the PO was read from were made from the attachment (ticket
    # 27): a converted copy, or an OCR reading; None: read as it was sent.
    derivation: Derivation | None = None
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
    # What left and how the customer agreed (ticket 28).
    confirmation: ConfirmationView | None = None
    agreement: AgreementView | None = None
    # A sent copy on the thread carrying this version's processed Excel,
    # proposing "Ghi đã gửi xác nhận" while the confirmation is ahead.
    confirmation_copy: ConfirmationCopyView | None = None
    close_reason: str | None
    closed_by: uuid.UUID | None
    closed_at: datetime | None
    superseded_by_case: uuid.UUID | None
    # Everyone the cross-checker must not be (spec decision 7): the screen
    # disables the control with the reason, the server refuses anyway.
    makers: list[uuid.UUID]
    # The cross-check approval this order waits on, while it does.
    decision: PendingDecisionView | None = None
    # Nothing is on the way to the cross-check the order awaits: no approval
    # pending and no DW1 run about it unfinished. Its Bravo recorder or the
    # head raises it again (ticket 14).
    cross_check_stalled: bool
    # The last cross-check decision recorded and not applied, said while the
    # order still awaits its cross-check.
    unapplied_decision: UnappliedDecisionView | None
    # The customer's replies its thread headers attached to the case (ticket 32).
    replies: list[CaseReplyView] = []
    # The messages of its thread(s) received before it opened (ticket 24).
    thread_before: list[ThreadMessageView] = []
    # The messages Sales sent on its thread(s) (ticket 25).
    thread_sent: list[SentMessageView] = []
    # What the customer asked to change by mail, oldest first (ticket 27).
    change_requests: list[ChangeRequestView] = []
    # Sales asked PC for delivery dates and waits on the answer (ticket 07).
    pc_request: PcRequestStateView | None = None
    # Sales asked Design for a new PRV code and waits, per line (ticket 06).
    design_requests: list[DesignRequestStateView] = []
    # A customer's change on the order once it is in Bravo (ticket 29).
    update_loop: UpdateLoopView | None = None
    # "Thay đổi nội bộ" may be applied now (ticket 10,
    # `OrderCase.takes_internal_change`): the page offers it by this.
    internal_change_open: bool = False
    # The quote cases opened from the order for lines with no valid
    # quotation, oldest first (ticket 09).
    quote_links: list[QuoteLinkView] = []
    # The values whose page or sheet no person was served before the
    # cross-check step began (Bravo recorded), for the cross-checker to open
    # first (audit gap 5). Only for a holder of `sales.order.cross_check`;
    # None for anyone else, since it tells how colleagues read the case.
    unopened_values: list[UnopenedValue] | None = None


class ThreadMessageView(BaseModel):
    """A message of a case's mail thread received before the case opened:
    the talk before the PO (ticket 24, dw_sales ADR 0009). The mail itself
    opens in the inbox."""

    model_config = _VIEW

    message_id: str
    received_at: datetime
    sender: str
    subject: str


def thread_message(message: InboundMessage) -> ThreadMessageView:
    return ThreadMessageView(
        message_id=message.message_id,
        received_at=message.received_at,
        sender=message.sender.address,
        subject=message.subject,
    )


class IntentView(BaseModel):
    """One thread intent a model read and code kept (ticket 26), with the
    sentences it stands on."""

    model_config = _VIEW

    intent: ThreadIntent
    quotes: list[str]


def _intents(reading: ReplyReading | None) -> list[IntentView]:
    if reading is None:
        return []
    return [IntentView(intent=i.intent, quotes=[q.text for q in i.quotes]) for i in reading.intents]


class CaseReplyView(BaseModel):
    """A customer's reply attached to the case by its thread (ticket 32), with
    the thread intents a model read in it (ticket 26) and the step code
    proposes from that, now.

    ``proposal`` is computed from the case's status as it is now, and only for
    the newest message of the case's thread, a reply or one Sales sent: an
    older one's reading does not pre-select anything. It is a suggestion: the
    step is the existing one, which Sales confirms and the server checks as
    for any other caller. The quotes are the customer's sentences, shown to a
    case reader as the inbox shows the whole mail.
    """

    model_config = _VIEW

    message_id: str
    processed_at: datetime
    linked_to: str
    # None: no model was asked (the tenant's rules leave it off).
    outcome: Literal["read", "unavailable"] | None
    intents: list[IntentView]
    prompt: str | None
    proposal: ProposedStep | None
    # Who picked the case among those the reply's thread holds (ticket 24);
    # None where code linked it.
    picked_by: uuid.UUID | None = None
    # Why the thread agent gave no reading of its own, where it was asked
    # first (tickets 30 and 31): the reading is then the one call's, or none.
    fallback: AgentFallback | None = None
    # The skill versions DW1's agent loaded to read it (ticket 40): the
    # tenant's own or the platform's, each ``<key>@<version>``.
    skills: list[str] = Field(default_factory=list)


class SentMessageView(BaseModel):
    """A message Sales sent on the case's thread (ticket 25: "Sales gửi"),
    with the thread intents a model read in it where the tenant's rules turn
    the step on (ticket 26), and the step that proposes when it is the
    thread's newest: Sales asking the customer proposes that the case waits
    on them. Its subject is Sales' own words."""

    model_config = _VIEW

    message_id: str
    received_at: datetime
    subject: str
    # None: DW1 has not read it (the step is off, or its turn has not come).
    outcome: Literal["read", "unavailable"] | None
    intents: list[IntentView]
    prompt: str | None
    proposal: ProposedStep | None
    # As on a reply: why the thread agent fell back, where it was asked.
    fallback: AgentFallback | None = None
    # As on a reply: the skill versions DW1's agent loaded to read it.
    skills: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CaseTalk:
    """The case's replies and the messages Sales sent on its thread, each
    oldest first, the newest of all of them with its proposal."""

    replies: list[CaseReplyView]
    sent: list[SentMessageView]


def case_talk(
    case_kind: CaseKind,
    case_id: uuid.UUID,
    status: str,
    logged: Sequence[LoggedMessage],
    thread: CaseThread | None = None,
    read: Mapping[str, SentRead] | None = None,
) -> CaseTalk:
    """The replies on one case and Sales' messages on its thread
    (``thread``), with what DW1 read of each (``read``: the sent messages it
    took up, by id). The newest message of the two, by when it was
    received, proposes a step: by who wrote it (`proposed_step`)."""
    replies: list[tuple[LoggedMessage, CaseReply]] = [
        (entry, entry.disposition.reply)
        for entry in sorted(logged, key=lambda e: (e.processed_at, e.disposition.message_id))
        if entry.disposition.reply is not None
        and entry.disposition.case_kind is case_kind
        and entry.disposition.case_id == case_id
    ]
    sent = [] if thread is None else thread.sent
    sent_readings = {m: r.reading for m, r in (read or {}).items()}
    received = {} if thread is None else thread.received
    # Every message with who wrote it, its time and its reading; the newest
    # of them proposes.
    talk: list[tuple[datetime, str, Author, ReplyReading | None]] = [
        (
            received.get(entry.disposition.message_id, entry.processed_at),
            entry.disposition.message_id,
            "customer",
            reply.reading,
        )
        for entry, reply in replies
    ]
    talk += [
        (message.received_at, message.message_id, "sales", sent_readings.get(message.message_id))
        for message in sent
    ]
    newest = max(talk, key=lambda t: (t[0], t[1]), default=None)
    proposal = (
        None
        if newest is None
        else (newest[1], proposed_step(newest[2], case_kind.value, status, newest[3]))
    )

    def proposed(message_id: str) -> ProposedStep | None:
        return proposal[1] if proposal is not None and proposal[0] == message_id else None

    return CaseTalk(
        replies=[
            CaseReplyView(
                message_id=entry.disposition.message_id,
                processed_at=entry.processed_at,
                linked_to=reply.linked_to,
                outcome=reply.reading.outcome if reply.reading else None,
                intents=_intents(reply.reading),
                prompt=reply.reading.prompt if reply.reading else None,
                proposal=proposed(entry.disposition.message_id),
                picked_by=reply.picked_by,
                fallback=reply.reading.fallback if reply.reading else None,
                skills=list(reply.reading.skills) if reply.reading else [],
            )
            for entry, reply in replies
        ],
        sent=[
            _sent_view(message, sent_readings.get(message.message_id), proposed) for message in sent
        ],
    )


def _sent_view(
    message: InboundMessage,
    reading: ReplyReading | None,
    proposed: Callable[[str], ProposedStep | None],
) -> SentMessageView:
    return SentMessageView(
        message_id=message.message_id,
        received_at=message.received_at,
        subject=message.subject,
        outcome=reading.outcome if reading else None,
        intents=_intents(reading),
        prompt=reading.prompt if reading else None,
        proposal=proposed(message.message_id),
        fallback=reading.fallback if reading else None,
        skills=list(reading.skills) if reading else [],
    )


# The key a message's intents are read against while a customer's change
# runs in the update loop: no row of `INTENT_STEPS` names it, so nothing is
# proposed then (the customer's answer is the loop's, ticket 29).
IN_UPDATE_LOOP: Final = "in_update_loop"


def talk_status(case: OrderCase) -> str:
    """The status a message on ``case`` proposes a step from: its own, or
    `IN_UPDATE_LOOP` while a customer's change runs in the loop."""
    return case.status.value if case.update_loop is None else IN_UPDATE_LOOP


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
        awaits_cross_check=case.awaits_cross_check,
    )


class PrintDifferenceView(BaseModel):
    """A value the PO's second file shows differently, where it shows it, and
    both values as each file prints them (ticket 22; None for a difference
    stored before they were kept)."""

    model_config = _VIEW

    line_no: int | None
    field: str
    anchor: SourceAnchor
    ours: str | None = None
    theirs: str | None = None


class PrintCopyView(BaseModel):
    model_config = _VIEW

    attachment_id: str
    differences: list[PrintDifferenceView]


def _seen_anchors(
    anchors: Iterable[tuple[str, SourceAnchor]], prices: PriceView
) -> dict[str, SourceAnchor]:
    """Where each value was read. A PDF anchor quotes the printed words, so a
    price's anchor shows the price: a viewer who may not see amounts gets
    none for one (spec decision 8), and could not open the source anyway."""
    return {field: a for field, a in anchors if prices.amounts or field not in AMOUNT_FIELDS}


def _legacy_anchor(document: PoDocument, prices: PriceView) -> SourceAnchor | None:
    """Where the first legacy text the viewer may see is: an anchor can quote
    the printed words, so a price typed in a legacy font is passed over for a
    viewer who may not see amounts, as `_seen_anchors` does for every price."""
    return next(
        (
            anchor
            for field, anchor, _ in document.legacy_texts()
            if prices.amounts or field not in AMOUNT_FIELDS
        ),
        None,
    )


def _print_copy(copy: PrintCopy | None, prices: PriceView) -> PrintCopyView | None:
    if copy is None:
        return None
    return PrintCopyView(
        attachment_id=copy.attachment_id,
        differences=[
            PrintDifferenceView(
                line_no=d.line_no, field=d.field, anchor=d.anchor, ours=d.ours, theirs=d.theirs
            )
            for d in copy.differences
            if prices.amounts or d.field not in AMOUNT_FIELDS
        ],
    )


def order_case(
    case: OrderCase,
    *,
    assigned_to: uuid.UUID | None,
    release_manifest_ref: str | None,
    prices: PriceView,
    decision: PendingDecisionView | None = None,
    stalled: bool = False,
    replies: Sequence[LoggedMessage] = (),
    servings: Sequence[ServedSource] = (),
    cross_checker: bool = False,
    thread: CaseThread | None = None,
    sent: Mapping[str, SentRead] | None = None,
    change_requests: Sequence[ChangeRequest] = (),
    confirmation_copy: InboundMessage | None = None,
    quote_links: Sequence[QuoteLinkView] = (),
) -> OrderCaseView:
    """The case for one caller. ``servings`` are every region served of it
    (`SourceServedPort.servings`): none by default, so no prepared value
    reads as checked. ``cross_checker``: the caller holds the cross-check
    scope, and is told which values nobody opened. ``confirmation_copy``:
    the sent copy that proposes the confirmation sent
    (`confirmations.confirmation_copy`)."""
    document = case.document
    talk = case_talk(CaseKind.ORDER, case.case_id, talk_status(case), replies, thread, sent)
    checked = preparer_checked(case, servings)
    unapplied = case.unapplied_decision
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
        name_revision=document.name_revision,
        po_date=case.header.po_date,
        currency=case.header.currency,
        attachment_id=document.attachment_id,
        attachment_sha256=document.attachment_sha256,
        header_anchors=dict(case.header.anchors),
        header_flags=list(case.header.flags),
        header_corrections=_corrections(case.header_corrections, prices),
        buyer=document.buyer,
        buyer_anchor=document.buyer_anchor,
        total=_amount(total.amount, prices.amounts) if total else None,
        total_anchor=total.anchor if total and prices.amounts else None,
        legacy_text_anchor=_legacy_anchor(document, prices),
        print_copy=_print_copy(document.print_copy, prices),
        coverage=CoverageView(
            lines_printed=coverage.lines_printed,
            lines_read=coverage.lines_read,
            regions=list(coverage.regions),
            unchecked_regions=list(document.unchecked_regions),
            checks_run=coverage.checks_run,
            findings=coverage.findings,
            forecast_rows=coverage.forecast_rows,
        ),
        lines=[order_line(case, line, prices, checked=checked) for line in case.lines],
        findings=[order_finding(case, f, prices) for f in case.findings],
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
        derivation=document.derivation,
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
        confirmation=confirmation_view(case),
        agreement=agreement_view(case),
        confirmation_copy=(
            ConfirmationCopyView(
                message_id=confirmation_copy.message_id,
                received_at=confirmation_copy.received_at,
                subject=confirmation_copy.subject,
            )
            if confirmation_copy is not None
            else None
        ),
        close_reason=case.close_reason.value if case.close_reason else None,
        closed_by=case.closed_by,
        closed_at=case.closed_at,
        superseded_by_case=case.superseded_by_case,
        makers=sorted(case.makers),
        decision=decision,
        cross_check_stalled=stalled,
        unapplied_decision=(
            UnappliedDecisionView(
                approval_id=unapplied.approval_id,
                run_id=unapplied.run_id,
                decided_by=unapplied.decided_by,
                approved=unapplied.approved,
                decided_on=unapplied.decided_on,
                reason_code=unapplied.reason_code,
                at=unapplied.at,
            )
            if unapplied
            else None
        ),
        replies=talk.replies,
        thread_before=[thread_message(m) for m in thread.before] if thread else [],
        thread_sent=talk.sent,
        change_requests=[change_request_view(r, prices=prices) for r in change_requests],
        pc_request=(
            PcRequestStateView.model_validate(case.pc_request.model_dump())
            if case.pc_request
            else None
        ),
        design_requests=[
            DesignRequestStateView.model_validate(r.model_dump()) for r in case.design_requests
        ],
        update_loop=update_loop_view(case),
        internal_change_open=case.takes_internal_change,
        quote_links=list(quote_links),
        unopened_values=(
            unopened_values(case, OpenedSources.of(servings, until=case.bravo_recorded_at))
            if cross_checker
            else None
        ),
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


class ValueConfirmationView(BaseModel):
    """One value a model read, as Sales confirmed it (ticket 29)."""

    model_config = _VIEW

    field: str
    read: str
    value: str
    by: uuid.UUID
    at: datetime


class QuoteFindingView(BaseModel):
    model_config = _VIEW

    key: str
    code: str
    blocking: bool
    line_no: int | None
    missing: list[str]
    # `value_uncertain`: the values a model read, and those Sales confirmed.
    flagged: list[str] = []
    confirmed: list[ValueConfirmationView] = []
    # Of the flagged values still to confirm, those whose source this caller
    # has not been served at this case version: confirming one is refused
    # 409 `source_not_served` until they open it (audit gap 2).
    source_not_served: list[str] = []
    # Every quotation code compares amounts or a copper basis: price-bearing.
    expected: Words | None
    actual: Words | None
    rule_versions: list[str]
    disposition: QuoteDispositionView


def quote_finding_key(finding: QuoteFinding) -> str:
    """``code:line`` (``-`` for the request as a whole), as an order's key."""
    return f"{finding.code.value}:{finding.line_no or '-'}"


def _source_not_served(
    case: QuoteCase, finding: QuoteFinding, served: frozenset[SourceRegion]
) -> list[str]:
    """The finding's values still to confirm that `require_value_served`
    would refuse for a caller ``served`` these regions (`value_unserved`)."""
    done = {c.field for c in finding.confirmed}
    return [
        field
        for field in finding.flagged
        if field not in done and value_unserved(case, finding.line_no, field, served) is not None
    ]


def quote_finding(
    finding: QuoteFinding, prices: PriceView, *, source_not_served: Sequence[str]
) -> QuoteFindingView:
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
        flagged=list(finding.flagged),
        confirmed=[ValueConfirmationView(**c.model_dump()) for c in finding.confirmed],
        source_not_served=list(source_not_served),
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
    # The fields a model read, which Sales confirms (ticket 29).
    model_read: list[str] = []
    # A target price the customer stated and a model read: the customer's
    # words, never price evidence. Price-bearing.
    stated_target_price: Amount | None = None
    # The items ticket 28's reading of the description fits, for Sales and
    # Design to weigh, and the reading itself.
    candidates: list[str] = []
    description_reading: DescriptionReading | None = None


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
    # None: Design wrote the reply in the mail (AI item 6), read by a model
    # and confirmed by ``confirmed_by``; each anchor quotes its words.
    attachment_id: str | None
    ycbg_no: str
    reply_date: date
    lines: list[DesignLineView]
    confirmed_by: uuid.UUID | None = None


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


class SignedCopyView(BaseModel):
    """The signed paper copy uploaded to the quotation: its file, who, when."""

    model_config = _VIEW

    artifact_id: uuid.UUID
    content_type: str
    uploaded_by: uuid.UUID
    uploaded_at: datetime


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
    # None: Bravo is not connected; nobody knows the orders (audit 1).
    orders: list[OrderedLineView] | None
    lme: LmeView | None
    copper_usd_per_uom: Amount | None
    floor: Amount | None
    freight_usd_per_km: Amount | None
    reference_price: Amount | Hidden | None
    # DW1's starting point for the price, from the rows above; None when
    # nothing supports one. Formed without other customers' prices for a
    # viewer who may not see them, so it never reveals one.
    suggestion: SuggestionView | None = None


class SuggestionView(BaseModel):
    model_config = _VIEW

    unit_price: Decimal
    basis: str
    source_no: str | None
    raised_to_floor: bool
    moq: Decimal | None
    lead_time_days: int | None
    copper_basis: CopperBasisView | None


def _suggestion(suggestion: PriceSuggestion | None) -> SuggestionView | None:
    if suggestion is None:
        return None
    return SuggestionView(
        unit_price=suggestion.unit_price,
        basis=suggestion.basis.value,
        source_no=suggestion.source_no,
        raised_to_floor=suggestion.raised_to_floor,
        moq=suggestion.moq,
        lead_time_days=suggestion.lead_time_days,
        copper_basis=(_copper(suggestion.copper_basis, True) if suggestion.copper_basis else None),
    )


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
                orders=(
                    None
                    if row.orders is None
                    else [
                        OrderedLineView(
                            so_no=line.so_no,
                            order_date=line.order_date,
                            currency=line.currency,
                            quantity=line.quantity,
                            unit_price=line.unit_price,
                        )
                        for line in row.orders
                    ]
                ),
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
                suggestion=_suggestion(suggest_price(row, others=prices.other_customers)),
            )
        )
    return out


class QuoteSummaryView(BaseModel):
    model_config = _VIEW

    case_id: uuid.UUID
    case_version: int
    status: str
    customer_code: str
    rfq_no: str | None
    received_at: datetime
    quote_due: date | None
    overdue: bool
    # "Sắp đến hạn" by the tenant's follow-up policy (audit 15).
    due_soon: bool
    assigned_to: uuid.UUID | None
    ycbg_no: str | None
    open_findings: int


class QuoteCoverageView(BaseModel):
    """The request's coverage statement (`QuoteCase.coverage`)."""

    model_config = _VIEW

    lines_read: int
    # "page N", a sheet's name, or "message_text" (lines read from the mail).
    regions: list[str]
    model_read: int
    model_read_confirmed: int
    findings: int


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
    rfq_no: str | None
    rfq_date: date | None
    quote_due: date | None
    overdue: bool
    # "Sắp đến hạn", by the tenant's follow-up policy (`followups.due_soon`):
    # the page draws the flag and holds no threshold of its own (audit 15).
    due_soon: bool
    currency: Currency
    # The request's file; None for a request a model read from the mail alone.
    attachment_id: str | None
    attachment_sha256: str | None
    # Where the request's own values were read, by field.
    anchors: dict[str, SourceAnchor] = {}
    # The request's own fields a model read (ticket 29).
    model_read: list[str] = []
    # The message's newest part a model read, which body anchors (no
    # `attachment_id`) index into, is not here: it may state a price, and it
    # is served as a source is, by its own route, which records it (ticket
    # 29: confirming a value read from it requires that record).
    # How the model was asked: None for the fixed-label form.
    reading: RequestReading | None = None
    rules_version: str
    parser_version: str
    catalog_as_of: datetime
    release_manifest_ref: str | None
    coverage: QuoteCoverageView
    lines: list[QuoteLineView]
    findings: list[QuoteFindingView]
    ycbg_no: str | None
    ycbg_recorded_by: uuid.UUID | None
    ycbg_recorded_at: datetime | None
    design_reply: DesignReplyView | None
    design_replies: int
    # Design's result as Bravo holds it, read from an export (ticket 16).
    design_check: DesignCheck | None = None
    pricing: PricingView | None
    earlier_pricing: int
    returns: list[ReturnView]
    submission: SubmissionView | None
    approval: QuoteApprovalView | None
    sent: StampView | None
    master_list: StampView | None
    decline: DeclineView | None
    # The quotation as signed on paper and uploaded (no e-signature).
    signed_copy: SignedCopyView | None = None
    evidence: list[EvidenceView] | Hidden | None
    # The approval this quotation waits on, while it does.
    decision: PendingDecisionView | None = None
    # The customer's replies its thread headers attached to the case (ticket 32).
    replies: list[CaseReplyView] = []
    # The messages of its thread(s) received before it opened (ticket 24).
    thread_before: list[ThreadMessageView] = []
    # The messages Sales sent on its thread(s) (ticket 25).
    thread_sent: list[SentMessageView] = []
    # The order case it was opened from (ticket 09); None for a request.
    from_order: FromOrder | None = None


def _anchors(**named: SourceAnchor | None) -> dict[str, SourceAnchor]:
    return {name: anchor for name, anchor in named.items() if anchor is not None}


def _due_soon(case: QuoteCase, today: date, followups: SalesFollowups) -> bool:
    """The quote's due day is "sắp đến hạn" by the tenant's policy (audit 15)."""
    due = case.request.document.quote_due
    return due is not None and due_soon(due.value, today, followups)


def quote_summary(
    case: QuoteCase, assigned_to: uuid.UUID | None, today: date, followups: SalesFollowups
) -> QuoteSummaryView:
    document = case.request.document
    return QuoteSummaryView(
        case_id=case.case_id,
        case_version=case.case_version,
        status=case.status.value,
        customer_code=case.customer_code,
        rfq_no=case.request.rfq_no,
        received_at=case.request.received_at,
        quote_due=document.quote_due.value if document.quote_due else None,
        overdue=case.is_overdue(today),
        due_soon=_due_soon(case, today, followups),
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
    followups: SalesFollowups,
    prices: PriceView,
    evidence_rows: Sequence[PriceEvidence] | None,
    decision: PendingDecisionView | None = None,
    replies: Sequence[LoggedMessage] = (),
    served: frozenset[SourceRegion] = frozenset(),
    thread: CaseThread | None = None,
    sent: Mapping[str, SentRead] | None = None,
) -> QuoteCaseView:
    """The case for one caller. ``served``: the regions of this case version
    the caller was served (`SourceServedPort.served`); none by default, so
    every value still to confirm reads as needing its source opened."""
    request = case.request
    talk = case_talk(CaseKind.QUOTE, case.case_id, case.status.value, replies, thread, sent)
    coverage = case.coverage()
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
        rfq_no=request.rfq_no,
        rfq_date=document.rfq_date.value if document.rfq_date else None,
        quote_due=document.quote_due.value if document.quote_due else None,
        overdue=case.is_overdue(today),
        due_soon=_due_soon(case, today, followups),
        currency=request.currency,
        attachment_id=request.attachment.attachment_id if request.attachment else None,
        attachment_sha256=request.attachment.sha256 if request.attachment else None,
        anchors=_anchors(
            rfq_no=document.rfq_no.source if document.rfq_no else None,
            rfq_date=document.rfq_date.source if document.rfq_date else None,
            quote_due=document.quote_due.source if document.quote_due else None,
            currency=document.currency.source,
        ),
        model_read=sorted(document.model_read),
        reading=request.reading,
        rules_version=case.rules_version,
        parser_version=case.parser_version,
        catalog_as_of=case.catalog_as_of,
        release_manifest_ref=release_manifest_ref,
        coverage=QuoteCoverageView(
            lines_read=coverage.lines_read,
            regions=list(coverage.regions),
            model_read=coverage.model_read,
            model_read_confirmed=coverage.model_read_confirmed,
            findings=coverage.findings,
        ),
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
                    # Its `quote` is the price as the form prints it: absent,
                    # like the value, for a caller who may not see prices.
                    target_price=(
                        item.target_price.source if item.target_price and prices.amounts else None
                    ),
                    stated_target_price=(
                        item.stated_target_price.source
                        if item.stated_target_price and prices.amounts
                        else None
                    ),
                    needed_by=item.needed_by.source,
                ),
                model_read=sorted(item.model_read),
                stated_target_price=(
                    _amount(item.stated_target_price.value, prices.amounts)
                    if item.stated_target_price
                    else None
                ),
                candidates=list(item.candidates),
                description_reading=item.description_reading,
            )
            for item in document.items
        ],
        findings=[
            quote_finding(f, prices, source_not_served=_source_not_served(case, f, served))
            for f in case.findings
        ],
        ycbg_no=case.ycbg.ycbg_no if case.ycbg else None,
        ycbg_recorded_by=case.ycbg.recorded_by if case.ycbg else None,
        ycbg_recorded_at=case.ycbg.recorded_at if case.ycbg else None,
        design_reply=(
            DesignReplyView(
                message_id=reply.message_id,
                received_at=reply.received_at,
                attachment_id=reply.attachment.attachment_id if reply.attachment else None,
                confirmed_by=reply.confirmed_by,
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
        design_check=case.design_check,
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
        signed_copy=(
            SignedCopyView(
                artifact_id=case.signed_copy.artifact_id,
                content_type=case.signed_copy.content_type,
                uploaded_by=case.signed_copy.uploaded_by,
                uploaded_at=case.signed_copy.uploaded_at,
            )
            if case.signed_copy
            else None
        ),
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
        replies=talk.replies,
        thread_before=[thread_message(m) for m in thread.before] if thread else [],
        thread_sent=talk.sent,
        from_order=case.from_order,
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
    # What a model reading of the message's intent did (ticket 31): the kind
    # and language read, the numbers code resolved, and the call's stamp.
    reading: IntentReading | None = None
    # A reply attached to its case by its thread headers (ticket 32).
    reply: CaseReply | None = None
    # The hand-off a model pre-filled for a routed message (ticket 33): what
    # code located, parsed and resolved, and the call's stamp.
    handoff: Handoff | None = None
    # A model's pre-fill of the mapping of a PO form no layout reads (ticket
    # 30), for the onboarding screen.
    layout_prefill: LayoutPrefill | None = None
    # A routed message a person marked handled (`routed_mail.py`): who, when,
    # and the note they left; all None while it waits on someone.
    handled_at: datetime | None = None
    handled_by: uuid.UUID | None = None
    handled_note: str | None = None
    # The cases a reply's thread holds when it names none of them, for Sales
    # to pick one ("Chọn hồ sơ", ticket 24).
    thread_cases: list[ThreadCaseView] = []
    # Every order case a mail with several POs is on, one per PO number, in
    # the mail's order (ticket 19), those the caller may see; empty for a
    # message on one case, whose ``case_id`` says it.
    order_cases: list[ThreadCaseView] = []
    # A message Sales sent ("Sales gửi", ticket 25): its sender is a member's
    # own sign-in address, as the server resolved it. It has no disposition
    # of its own (``kind`` stays `not_yet_processed`) and is never processed
    # into a case: it shows under its thread, on the case.
    outgoing: bool = False
    # The triage card of a message routed ``other`` (ticket 33).
    triage: TriageCardView | None = None


class TriageCardView(BaseModel):
    """A message's triage card as the inbox shows it: what it seems to be
    (the skill's kind, its label where the skill gives one, and the route
    the skill maps it onto), the one step suggested, the case it names
    where the caller may see it, and the decision once made."""

    model_config = _VIEW

    kind: str | None
    kind_label: str | None
    routed_as: str | None
    step: TriageStep | None
    case: ThreadCaseView | None
    # The mail-kinds version it was read with.
    skill: str
    decided: CardVerdict | None


class ThreadCaseView(BaseModel):
    """A case a message names: one offered for a reply, or one of a mail's
    several POs; its kind, id and the number it goes by (the PO's, or the
    request's)."""

    model_config = _VIEW

    case_kind: CaseKind
    case_id: uuid.UUID
    number: str


def message_disposition(
    disposition: MessageDisposition,
    processed_at: datetime | None,
    handled: MessageHandled | None = None,
    numbers: Mapping[uuid.UUID, str] | None = None,
    *,
    outgoing: bool = False,
) -> MessageDispositionView:
    """The disposition as the inbox shows it. ``numbers``: what each case a
    reply is offered, or a mail with several POs is on, goes by, for those the
    caller may see; a case not in it is left out."""
    shown = numbers or {}
    card = disposition.triage
    return MessageDispositionView(
        kind=disposition.kind.value,
        case_kind=disposition.case_kind,
        case_id=disposition.case_id,
        reason=disposition.reason.value if disposition.reason else None,
        detail=disposition.detail,
        owner=disposition.owner,
        customer_code=disposition.customer_code,
        processed_at=processed_at,
        reading=disposition.reading,
        reply=disposition.reply,
        handoff=disposition.handoff,
        layout_prefill=disposition.layout_prefill,
        handled_at=handled.at if handled else None,
        handled_by=handled.by if handled else None,
        handled_note=handled.note if handled else None,
        thread_cases=[
            ThreadCaseView(case_kind=c.case_kind, case_id=c.case_id, number=shown[c.case_id])
            for c in disposition.thread_cases
            if c.case_id in shown
        ],
        order_cases=[
            ThreadCaseView(case_kind=CaseKind.ORDER, case_id=case_id, number=shown[case_id])
            for case_id in (disposition.case_ids if disposition.more_cases else ())
            if case_id in shown
        ],
        outgoing=outgoing,
        triage=(
            None
            if card is None
            else TriageCardView(
                kind=card.kind,
                kind_label=card.kind_label,
                routed_as=card.routed_as,
                step=card.step,
                case=(
                    ThreadCaseView(
                        case_kind=CaseKind.ORDER, case_id=card.case_id, number=shown[card.case_id]
                    )
                    if card.case_id is not None and card.case_id in shown
                    else None
                ),
                skill=card.skill,
                decided=card.decided,
            )
        ),
    )


class AttachmentView(BaseModel):
    model_config = _VIEW

    attachment_id: str
    name: str
    media_type: str
    size: int


class HandoffDraftView(BaseModel):
    """A routed message's hand-off as code wrote it from the template, for
    Sales to review, edit and send from their own mailbox (ticket 33). ``to``
    names the team, never an address: Sales picks the recipients.
    ``kind_label``: the tenant's hand-off skill's words for its kind, where
    the skill read it and gives some (ticket 42 family 5)."""

    model_config = _VIEW

    to: HandoffTeam
    subject: str
    body: str
    template_ref: str
    kind_label: str | None = None


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
    handoff_draft: HandoffDraftView | None = None
    # Its processing, once someone asked for it (ticket 25): what the page
    # shows while DW1 works, and why it stopped if it failed.
    processing: ProcessingJobView | None = None


class ProcessingJobView(BaseModel):
    """A message's processing job (ticket 25): ids, a status and a reason
    code, never anything read from the message."""

    model_config = _VIEW

    job_id: uuid.UUID
    message_id: str
    status: JobStatus
    requested_at: datetime
    attempts: int
    error: JobError | None


def processing_job(job: ProcessingJob) -> ProcessingJobView:
    return ProcessingJobView(
        job_id=job.job_id,
        message_id=job.message_id,
        status=job.status,
        requested_at=job.requested_at,
        attempts=job.attempts,
        error=job.error,
    )


def inbox_message(
    message: InboundMessage,
    disposition: MessageDispositionView,
    handoff_draft: HandoffDraftView | None = None,
    processing: ProcessingJob | None = None,
) -> InboxMessageView:
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
        handoff_draft=handoff_draft,
        processing=None if processing is None else processing_job(processing),
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
    """An item as the master-data page and the candidate picker show it.
    None: the item master does not hold the value (Bravo's holds no MOQ,
    lead time or attribute but those its name states, ticket 36)."""

    model_config = _VIEW

    prv_code: str
    # Bravo's name for it, None for an item that has none.
    name: str | None
    family: str | None
    spec_no: str | None
    cores: int | None
    gauge: str | None
    uom: str | None
    # The unit as the item master writes it ("Pcs" where ``uom`` is None).
    unit: str | None
    moq: Decimal | None
    pack_multiple: Decimal | None
    standard_lead_time_days: int | None


def item(record: Item) -> ItemView:
    return ItemView(
        prv_code=record.prv_code,
        name=record.name,
        family=record.family,
        spec_no=record.attributes.spec_no,
        cores=record.attributes.cores,
        gauge=record.attributes.gauge,
        uom=record.uom,
        unit=record.unit,
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
