"""The quotation domain: what its constructors refuse, its arithmetic, findings and moves."""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dw_kernel.errors import ConflictError, DomainError, PermissionDeniedError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockSalesCatalog
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import Customer, FixedCopper, LmeBand, LmeMonth
from dw_sales.domain.pricing import SalesPricing
from dw_sales.domain.quotes import (
    CopperComponent,
    CustomerQuoteDocument,
    DeclineReason,
    DesignReply,
    LinePrice,
    PolicyFloor,
    PricingDecision,
    QuoteActor,
    QuoteAddressee,
    QuoteCapability,
    QuoteCase,
    QuoteFindingCode,
    QuoteRequest,
    QuoteStatus,
    copper_component,
    copper_cost_per_uom,
    price_findings,
    transition,
)

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
SHA_RFQ = "a" * 64
SHA_REPLY = "b" * 64
PRICER = uuid.UUID(int=101)
APPROVER = uuid.UUID(int=102)
SALES = uuid.UUID(int=103)
HEAD = QuoteActor(user_id=APPROVER, capabilities=frozenset({QuoteCapability.APPROVE}))
AT = datetime(2026, 10, 2, 2, 0, tzinfo=UTC)
LME_SEP = LmeMonth(month="2026-09", usd_per_tonne=Decimal(10870))
LME_AUG = LmeMonth(month="2026-08", usd_per_tonne=Decimal(10610))
BAND_SEP = LmeBand(low_usd_per_tonne=Decimal(10500), high_usd_per_tonne=Decimal(11000))
PRICING = SalesPricing.model_validate(
    {
        "schema_version": "1.0",
        "policy_id": "sales_pricing",
        "policy_version": "1.0.0",
        "copper_adders": [
            {"band": {"low_usd_per_tonne": "10000", "high_usd_per_tonne": "10500"},
             "adder_usd_per_tonne": "360"},
            {"band": {"low_usd_per_tonne": "10500", "high_usd_per_tonne": "11000"},
             "adder_usd_per_tonne": "385"},
        ],
        "floor_margin": "0.18",
        "freight": [{"incoterm": "CIF", "destination": "japan", "usd_per_km": "19.50"}],
    }
)  # fmt: skip
BEFORE_SENT = [
    s
    for s in QuoteStatus
    if s not in (QuoteStatus.SENT, QuoteStatus.MASTER_LIST_RECORDED, QuoteStatus.DECLINED)
]


def _kmh() -> Customer:
    customer = asyncio.run(MockSalesCatalog.load(SCOPE).customer_by_code(SCOPE, "KMH")).data
    assert customer is not None
    return customer


KMH = _kmh()


def _anchor(cell: str, *, attachment_id: str = "M10-A1", sha: str = SHA_RFQ) -> dict[str, Any]:
    return {"attachment_id": attachment_id, "attachment_sha256": sha, "cell_ref": f"RFQ!{cell}"}


def _sourced(value: object, cell: str, **anchor: Any) -> dict[str, Any]:
    return {"value": value, "source": _anchor(cell, **anchor)}


def _item(line_no: int = 1, **overrides: Any) -> dict[str, Any]:
    row = 9 + line_no
    return {
        "line_no": line_no,
        "customer_item_code": _sourced("KMH-21-0045", f"B{row}"),
        "description": _sourced("MULTI-CORE CABLE 4C AWG22", f"C{row}"),
        "quantity": _sourced("9000", f"D{row}"),
        "uom": _sourced("m", f"E{row}"),
        "target_price": _sourced("0.6500", f"F{row}"),
        "needed_by": _sourced("2026-12-18", f"G{row}"),
    } | overrides


def _request(*items: dict[str, Any], **overrides: Any) -> QuoteRequest:
    return QuoteRequest.model_validate(
        {
            "message_id": "M10",
            "received_at": datetime(2026, 9, 30, 2, 20, tzinfo=UTC),
            "sender": {"address": KMH.contacts[0].address},
            "attachment": {
                "attachment_id": "M10-A1",
                "name": "KMH-RFQ-260930-02.xlsx",
                "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size": 100,
                "sha256": SHA_RFQ,
            },
            "customer_code": "KMH",
            "customer_from": "sender_domain",
            "document": {
                "rfq_no": _sourced("KMH-RFQ-260930-02", "B4"),
                "rfq_date": _sourced("2026-09-30", "E4"),
                "quote_due": _sourced("2026-10-07", "B5"),
                "currency": _sourced("USD", "E5"),
                "items": list(items) or [_item()],
            },
        }
        | overrides
    )


def _reply(*line_nos: int, ycbg: str = "YCBG-2609-030", copper: str | None = "11.8") -> DesignReply:
    def at(cell: str) -> dict[str, Any]:
        return {
            "attachment_id": "M25-A1",
            "attachment_sha256": SHA_REPLY,
            "cell_ref": f"YCBG!{cell}",
        }

    lines = [
        {
            "line_no": n,
            "bp_code": {"value": "BP-25-0187", "source": at(f"B{9 + n}")},
            "spec_no": {"value": "SP-5406", "source": at(f"C{9 + n}")},
            "prv_code": {"value": "CB-2007", "source": at(f"D{9 + n}")},
        }
        | ({"copper_kg_per_km": {"value": copper, "source": at(f"E{9 + n}")}} if copper else {})
        for n in (line_nos or (1,))
    ]
    return DesignReply.model_validate(
        {
            "message_id": "M25",
            "received_at": datetime(2026, 10, 1, 3, 0, tzinfo=UTC),
            "attachment": {
                "attachment_id": "M25-A1",
                "name": "YCBG-2609-030-reply.xlsx",
                "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size": 100,
                "sha256": SHA_REPLY,
            },
            "document": {
                "ycbg_no": {"value": ycbg, "source": at("B4")},
                "reply_date": {"value": "2026-10-01", "source": at("E4")},
                "lines": lines,
            },
        }
    )


def _decision(
    *,
    price: str = "0.6890",
    by: uuid.UUID = PRICER,
    basis: FixedCopper | LmeBand = BAND_SEP,
    lme: LmeMonth | None = LME_SEP,
    moq: str = "3000",
    lead_time: int = 45,
    guidance: str | None = None,
) -> PricingDecision:
    return PricingDecision(
        decided_by=by,
        decided_at=AT,
        lme=lme,
        lines=(
            LinePrice(
                line_no=1,
                unit_price=Decimal(price),
                moq=Decimal(moq),
                lead_time_days=lead_time,
                copper_basis=basis,
            ),
        ),
        management_guidance=guidance,
    )


def _priced(case: QuoteCase, decision: PricingDecision | None = None) -> QuoteCase:
    chosen = decision or _decision()
    return case.decide_price(
        chosen,
        price_findings(
            case,
            chosen,
            latest_lme=LME_SEP,
            pricing=PRICING,
            prescribed_basis="lme_band",
            quote_rules_version="sales_quote_rules@1.0.0",
        ),
        by=chosen.decided_by,
    )


def _document(case: QuoteCase, *, quote_no: str = "Q26-0301") -> CustomerQuoteDocument:
    assert case.pricing is not None
    return CustomerQuoteDocument(
        quote_no=quote_no,
        addressee=QuoteAddressee.of(KMH),
        recipients=(KMH.contacts[0],),
        their_reference=case.request.document.rfq_no.value,
        issued_on=date(2026, 10, 2),
        valid_to=date(2026, 12, 30),
        currency=case.request.currency,
        lme=case.pricing.lme,
        lines=case.document_lines(),
    )


def _submitted(case: QuoteCase) -> QuoteCase:
    return case.submit_for_approval(_document(case), by=PRICER, at=AT)


def _approve(case: QuoteCase, actor: QuoteActor = HEAD, **kwargs: Any) -> QuoteCase:
    assert case.submission is not None
    sha = kwargs.pop("document_sha256", case.submission.document_sha256)
    return case.approve(actor, at=AT, document_sha256=sha, **kwargs)


_STEPS: dict[QuoteStatus, Callable[[QuoteCase], QuoteCase]] = {
    QuoteStatus.YCBG_DRAFTED: lambda c: c.draft_ycbg(),
    QuoteStatus.YCBG_RECORDED: lambda c: c.record_ycbg("YCBG-2609-030", by=PRICER, at=AT),
    QuoteStatus.SENT_TO_DESIGN: lambda c: c.send_to_design(),
    QuoteStatus.DESIGN_REPLIED: lambda c: c.record_design_reply(_reply()),
    QuoteStatus.PRICED: _priced,
    QuoteStatus.PENDING_APPROVAL: _submitted,
    QuoteStatus.APPROVED: lambda c: _approve(c, reasons=None),
    QuoteStatus.SENT: lambda c: c.mark_sent(by=PRICER, at=AT),
    QuoteStatus.MASTER_LIST_RECORDED: lambda c: c.record_master_list(by=PRICER, at=AT),
}
_MAIN_PATH = list(_STEPS)


def _case(status: QuoteStatus, request: QuoteRequest | None = None) -> QuoteCase:
    """A case walked along the main path to ``status``, or to its side states."""
    case = QuoteCase.open(uuid.UUID(int=7), request or _request())
    if status is QuoteStatus.RECEIVED:
        return case
    if status is QuoteStatus.SPEC_DISCUSSION:
        return _case(QuoteStatus.DESIGN_REPLIED, request).discuss_spec()
    if status is QuoteStatus.RETURNED:
        return _case(QuoteStatus.PENDING_APPROVAL, request).return_to_pricer(
            HEAD, at=AT, reason="Giá thấp hơn mức chỉ đạo"
        )
    if status is QuoteStatus.DECLINED:
        return case.decline_request(by=PRICER, at=AT, reason=DeclineReason.COMMERCIAL)
    for step in _MAIN_PATH[: _MAIN_PATH.index(status) + 1]:
        case = _STEPS[step](case)
    return case


# ------------------------------------------------------------- the request --


def test_a_value_does_not_exist_without_its_anchor() -> None:
    with pytest.raises(ValidationError):
        _request(_item(quantity={"value": "9000"}))


def test_an_anchor_that_points_nowhere_is_refused() -> None:
    with pytest.raises(ValidationError):
        nowhere = {"attachment_id": "M10-A1", "attachment_sha256": SHA_RFQ}
        _request(_item(quantity={"value": "9000", "source": nowhere}))


def test_every_anchor_names_an_attachment_of_this_message() -> None:
    raw = _request().model_dump(mode="json")
    raw["attachment"]["attachment_id"] = "M10-A2"

    with pytest.raises(ValidationError, match="other than M10-A2"):
        QuoteRequest.model_validate(raw)


def test_an_anchor_into_a_changed_file_is_refused() -> None:
    with pytest.raises(ValidationError):
        _request(_item(quantity=_sourced("9000", "D10", sha="c" * 64)))


def test_a_request_numbers_its_lines_once() -> None:
    with pytest.raises(ValidationError, match="repeats a line number"):
        _request(_item(1), _item(1))


def test_a_value_left_blank_raises_rfq_incomplete_on_its_line_not_a_refusal() -> None:
    case = QuoteCase.open(uuid.UUID(int=7), _request(_item(quantity=_sourced(None, "D10"))))

    (finding,) = case.findings
    assert (finding.code, finding.line_no, finding.missing) == (
        QuoteFindingCode.RFQ_INCOMPLETE,
        1,
        ("quantity",),
    )
    assert finding.blocking and finding.is_open


def test_an_incomplete_request_leaves_received_only_by_decline_or_sales_answer() -> None:
    case = QuoteCase.open(uuid.UUID(int=7), _request(_item(quantity=_sourced(None, "D10"))))

    with pytest.raises(ValidationError, match="answered its findings"):
        case.draft_ycbg()
    assert case.decline_request(by=SALES, at=AT, reason=DeclineReason.COMMERCIAL).status is (
        QuoteStatus.DECLINED
    )
    answered = case.complete_line(1, by=SALES, at=AT, quantity=Decimal(4000))
    assert answered.quantity(1) == Decimal(4000)
    assert answered.draft_ycbg().status is QuoteStatus.YCBG_DRAFTED


def test_sales_types_exactly_the_missing_values() -> None:
    case = QuoteCase.open(uuid.UUID(int=7), _request(_item(quantity=_sourced(None, "D10"))))

    with pytest.raises(ValidationError, match="exactly the missing values"):
        case.complete_line(1, by=SALES, at=AT, needed_by=date(2026, 12, 1))


def test_a_forwarded_request_waits_for_sales_to_confirm_the_customer() -> None:
    raw = _request().model_dump(mode="json")
    raw["customer_from"] = "named_buyer"
    raw["document"]["buyer"] = _sourced("KUMOHANA ELECTRONICS VIETNAM CO., LTD.", "A1")
    case = QuoteCase.open(uuid.UUID(int=7), QuoteRequest.model_validate(raw))

    assert [f.code for f in case.findings] == [QuoteFindingCode.CUSTOMER_UNKNOWN]
    confirmed = case.confirm_customer("KMH", by=SALES, at=AT)
    assert confirmed.customer_code == "KMH"
    assert confirmed.draft_ycbg().status is QuoteStatus.YCBG_DRAFTED


def test_a_customer_found_by_name_needs_the_printed_name() -> None:
    with pytest.raises(ValidationError, match="buyer's name"):
        _request(customer_from="named_buyer")


# ---------------------------------------------------------------- overdue --


def test_overdue_is_derived_from_the_quote_due_date_and_never_stored() -> None:
    case = _case(QuoteStatus.SENT_TO_DESIGN)

    assert not case.is_overdue(date(2026, 10, 7))
    assert case.is_overdue(date(2026, 10, 8))
    assert "overdue" not in {s.value for s in QuoteStatus}
    assert not _case(QuoteStatus.SENT).is_overdue(date(2026, 10, 8))


# ------------------------------------------------------------ the arithmetic --


def test_the_copper_component_is_kg_per_km_at_lme_plus_the_bands_adder() -> None:
    component = copper_component(Decimal("11.8"), LME_SEP, "m", PRICING)

    assert component is not None
    assert component.adder_usd_per_tonne == Decimal(385)
    # 11.8 kg/km x (10870 + 385) USD/t / 1000 kg/t / 1000 m/km
    assert component.usd_per_uom == Decimal("0.132809")
    floor = PolicyFloor.of(component, PRICING)
    assert floor.price == Decimal("0.132809") * Decimal("1.18")


def test_copper_outside_the_policy_table_is_unknown_not_zero() -> None:
    cheap = LmeMonth(month="2026-09", usd_per_tonne=Decimal(9000))

    assert copper_component(Decimal("11.8"), cheap, "m", PRICING) is None
    assert copper_component(None, LME_SEP, "m", PRICING) is None


def test_a_stored_copper_component_cannot_disagree_with_its_formula() -> None:
    with pytest.raises(ValidationError, match="plus adder"):
        CopperComponent(
            copper_kg_per_km=Decimal("11.8"),
            lme=LME_SEP,
            adder_usd_per_tonne=Decimal(385),
            uom="m",
            usd_per_uom=copper_cost_per_uom(Decimal("11.8"), Decimal(10870), "m"),
        )


# ---------------------------------------------------------------- findings --


def _codes(case: QuoteCase) -> set[QuoteFindingCode]:
    return {f.code for f in case.findings}


def test_a_price_under_the_floor_raises_price_below_policy_floor() -> None:
    case = _priced(_case(QuoteStatus.DESIGN_REPLIED), _decision(price="0.1500"))

    assert QuoteFindingCode.PRICE_BELOW_POLICY_FLOOR in _codes(case)
    assert QuoteFindingCode.ABOVE_TARGET_PRICE not in _codes(case)


@pytest.mark.parametrize(
    ("basis", "lme"),
    [
        (FixedCopper(), LME_SEP),  # not the prescribed kind
        (LmeBand(low_usd_per_tonne=Decimal(10000), high_usd_per_tonne=Decimal(10500)), LME_SEP),
        (BAND_SEP, LME_AUG),  # not the latest published month
    ],
)
def test_a_copper_basis_other_than_the_policys_raises_price_basis_mismatch(
    basis: FixedCopper | LmeBand, lme: LmeMonth
) -> None:
    case = _priced(_case(QuoteStatus.DESIGN_REPLIED), _decision(basis=basis, lme=lme))

    (finding,) = [f for f in case.findings if f.code is QuoteFindingCode.PRICE_BASIS_MISMATCH]
    assert finding.blocking
    assert finding.rule_versions == ("sales_pricing@1.0.0", "sales_quote_rules@1.0.0")


def test_a_price_over_the_target_raises_above_target_price_as_information() -> None:
    case = _priced(_case(QuoteStatus.DESIGN_REPLIED))

    (finding,) = case.findings
    assert finding.code is QuoteFindingCode.ABOVE_TARGET_PRICE
    assert not finding.blocking


def test_a_price_inside_every_rule_raises_nothing() -> None:
    assert _priced(_case(QuoteStatus.DESIGN_REPLIED), _decision(price="0.6400")).findings == ()


# ------------------------------------------------------------- transitions --

EXPECTED_MOVES = {
    QuoteStatus.RECEIVED: {QuoteStatus.YCBG_DRAFTED},
    QuoteStatus.YCBG_DRAFTED: {QuoteStatus.YCBG_RECORDED},
    QuoteStatus.YCBG_RECORDED: {QuoteStatus.SENT_TO_DESIGN},
    QuoteStatus.SENT_TO_DESIGN: {QuoteStatus.DESIGN_REPLIED},
    QuoteStatus.DESIGN_REPLIED: {QuoteStatus.SPEC_DISCUSSION, QuoteStatus.PRICED},
    QuoteStatus.SPEC_DISCUSSION: {QuoteStatus.DESIGN_REPLIED, QuoteStatus.SENT_TO_DESIGN},
    QuoteStatus.PRICED: {QuoteStatus.PRICED, QuoteStatus.PENDING_APPROVAL},
    QuoteStatus.PENDING_APPROVAL: {
        QuoteStatus.APPROVED,
        QuoteStatus.RETURNED,
        QuoteStatus.PRICED,
    },
    QuoteStatus.RETURNED: {QuoteStatus.PRICED},
    QuoteStatus.APPROVED: {QuoteStatus.SENT, QuoteStatus.PRICED},
    QuoteStatus.SENT: {QuoteStatus.MASTER_LIST_RECORDED},
    QuoteStatus.MASTER_LIST_RECORDED: set(),
    QuoteStatus.DECLINED: set(),
}


@pytest.mark.parametrize("current", list(QuoteStatus))
def test_a_quotation_makes_exactly_the_moves_the_process_allows(current: QuoteStatus) -> None:
    allowed = EXPECTED_MOVES[current] | (
        {QuoteStatus.DECLINED} if current in BEFORE_SENT else set()
    )
    for target in QuoteStatus:
        if target in allowed:
            assert transition(current, target) is target
        else:
            with pytest.raises(ConflictError):
                transition(current, target)


def test_a_case_walks_the_whole_way_and_every_change_bumps_its_version() -> None:
    case = QuoteCase.open(uuid.UUID(int=7), _request())
    versions = [case.case_version]
    for step in _MAIN_PATH:
        case = _STEPS[step](case)
        assert case.status is step
        versions.append(case.case_version)

    assert versions == list(range(1, len(_MAIN_PATH) + 2))


@pytest.mark.parametrize("status", BEFORE_SENT)
def test_a_quotation_can_be_declined_with_a_reason_from_every_state_before_sent(
    status: QuoteStatus,
) -> None:
    case = _case(status)
    declined = case.decline_request(
        by=PRICER, at=AT, reason=DeclineReason.DESIGN_CANNOT, note="Design không làm được"
    )

    assert declined.status is QuoteStatus.DECLINED
    assert declined.decline is not None and declined.decline.reason is DeclineReason.DESIGN_CANNOT
    assert declined.case_version == case.case_version + 1


@pytest.mark.parametrize(
    "status", [QuoteStatus.SENT, QuoteStatus.MASTER_LIST_RECORDED, QuoteStatus.DECLINED]
)
def test_a_sent_or_declined_quotation_cannot_be_declined(status: QuoteStatus) -> None:
    with pytest.raises(ConflictError):
        _case(status).decline_request(by=PRICER, at=AT, reason=DeclineReason.COMMERCIAL)


def test_a_decline_reason_is_one_of_the_four() -> None:
    with pytest.raises(ValidationError):
        _case(QuoteStatus.RECEIVED).decline_request(by=PRICER, at=AT, reason="busy")  # type: ignore[arg-type]


def test_the_ycbg_is_recorded_with_its_number_and_who_typed_it() -> None:
    case = _case(QuoteStatus.YCBG_RECORDED)

    assert case.ycbg is not None
    assert (case.ycbg.ycbg_no, case.ycbg.recorded_by) == ("YCBG-2609-030", PRICER)


def test_a_reply_to_another_ycbg_cannot_be_recorded_on_the_case() -> None:
    with pytest.raises(ValidationError, match="this case's YCBG"):
        _case(QuoteStatus.SENT_TO_DESIGN).record_design_reply(_reply(ycbg="YCBG-2608-044"))


def test_a_spec_discussion_can_send_the_case_back_to_design_and_keeps_the_reply() -> None:
    again = _case(QuoteStatus.SPEC_DISCUSSION).send_to_design()

    assert again.status is QuoteStatus.SENT_TO_DESIGN
    second = again.record_design_reply(_reply())
    assert len(second.design_replies) == 2


def test_a_returned_price_is_priced_again_and_the_history_is_kept() -> None:
    returned = _case(QuoteStatus.RETURNED)

    assert returned.submission is None
    assert returned.returns[0].returned_by == APPROVER
    repriced = _priced(returned, _decision(price="0.6700"))
    assert repriced.status is QuoteStatus.PRICED
    assert [d.lines[0].unit_price for d in repriced.earlier_pricing] == [Decimal("0.6890")]
    assert repriced.returns == returned.returns


@pytest.mark.parametrize("status", [QuoteStatus.PENDING_APPROVAL, QuoteStatus.APPROVED])
@pytest.mark.parametrize("change", [{"price": "0.6700"}, {"moq": "6000"}, {"lead_time": 60}])
def test_a_change_to_price_moq_or_lead_time_after_submit_returns_the_quote_to_priced(
    status: QuoteStatus, change: dict[str, Any]
) -> None:
    case = _case(status)
    changed = _priced(case, _decision(**change))

    assert changed.status is QuoteStatus.PRICED
    assert changed.submission is None and changed.approval is None
    assert changed.earlier_pricing == (case.pricing,)


# ---------------------------------------------------------------- approval --


def test_the_submission_stamps_the_documents_hash_and_the_pricer() -> None:
    case = _case(QuoteStatus.PENDING_APPROVAL)

    assert case.submission is not None
    assert case.submission.priced_by == PRICER
    assert case.submission.document_sha256 == case.submission.document.sha256()


def test_the_approval_records_the_hash_of_what_was_approved() -> None:
    case = _case(QuoteStatus.APPROVED)

    assert case.approval is not None and case.submission is not None
    assert case.approval.document_sha256 == case.submission.document_sha256
    assert case.approval.approved_by == APPROVER


def test_a_caller_without_the_approve_capability_is_refused() -> None:
    deputy_without_set = QuoteActor(user_id=APPROVER)

    with pytest.raises(PermissionDeniedError):
        _approve(_case(QuoteStatus.PENDING_APPROVAL), deputy_without_set)
    with pytest.raises(PermissionDeniedError):
        _case(QuoteStatus.PENDING_APPROVAL).return_to_pricer(deputy_without_set, at=AT, reason="x")


def test_the_person_who_priced_it_cannot_approve_it_even_holding_the_capability() -> None:
    pricer = QuoteActor(user_id=PRICER, capabilities=frozenset({QuoteCapability.APPROVE}))

    with pytest.raises(ConflictError, match="separation of duties"):
        _approve(_case(QuoteStatus.PENDING_APPROVAL), pricer)


def test_a_price_decided_under_another_persons_name_is_refused() -> None:
    """Else the pricer, naming the approver as ``decided_by``, could then
    approve their own price: the check above compares against that name."""
    replied = _case(QuoteStatus.DESIGN_REPLIED)
    as_the_head = _decision(by=APPROVER)

    with pytest.raises(DomainError, match="its actor's"):
        replied.decide_price(as_the_head, (), by=PRICER)
    assert replied.decide_price(as_the_head, (), by=APPROVER).status is QuoteStatus.PRICED


def test_a_stored_case_approved_by_its_pricer_cannot_be_read_back() -> None:
    approved = _case(QuoteStatus.APPROVED)
    assert approved.approval is not None
    forged = dict(approved) | {
        "approval": approved.approval.model_copy(update={"approved_by": PRICER})
    }

    with pytest.raises(ValidationError, match="not priced_by"):
        QuoteCase.model_validate(forged)


def test_an_approval_of_a_document_other_than_the_submitted_one_is_refused() -> None:
    with pytest.raises(ConflictError, match="changed after it was shown"):
        _approve(_case(QuoteStatus.PENDING_APPROVAL), document_sha256="0" * 64)


def test_a_change_after_submit_invalidates_the_hash_the_approver_saw() -> None:
    shown = _case(QuoteStatus.PENDING_APPROVAL)
    assert shown.submission is not None
    seen = shown.submission.document_sha256
    resubmitted = _submitted(_priced(shown, _decision(price="0.6700")))

    with pytest.raises(ConflictError, match="changed after it was shown"):
        _approve(resubmitted, document_sha256=seen)


def test_a_blocking_price_finding_is_accepted_by_the_approver_with_a_reason() -> None:
    low = _submitted(_priced(_case(QuoteStatus.DESIGN_REPLIED), _decision(price="0.1500")))
    key = (QuoteFindingCode.PRICE_BELOW_POLICY_FLOOR, 1)

    with pytest.raises(ConflictError, match="accepted with a reason"):
        _approve(low)
    approved = _approve(low, reasons={key: "Khách chiến lược, trưởng bộ phận đồng ý"})
    (finding,) = [f for f in approved.findings if f.key == key]
    assert finding.disposition.kind == "accepted"
    assert finding.disposition.by == APPROVER


def test_above_target_price_is_acknowledged_by_the_approval_itself() -> None:
    approved = _case(QuoteStatus.APPROVED)

    (finding,) = approved.findings
    assert finding.code is QuoteFindingCode.ABOVE_TARGET_PRICE
    assert finding.disposition.kind == "accepted"


def test_only_an_approved_quotation_is_sent() -> None:
    with pytest.raises(ConflictError):
        _case(QuoteStatus.PENDING_APPROVAL).mark_sent(by=PRICER, at=AT)


# ----------------------------------------------------- the customer document --


def test_the_documents_numbers_are_the_decided_terms() -> None:
    case = _case(QuoteStatus.PENDING_APPROVAL)
    assert case.submission is not None and case.pricing is not None
    (line,) = case.submission.document.lines
    (terms,) = case.pricing.lines

    assert (line.unit_price, line.moq, line.lead_time_days, line.copper_basis) == (
        terms.unit_price,
        terms.moq,
        terms.lead_time_days,
        terms.copper_basis,
    )
    assert (line.bp_code, line.spec_no, line.prv_code) == ("BP-25-0187", "SP-5406", "CB-2007")
    assert case.submission.document.lme == LME_SEP


def test_a_document_whose_prices_are_not_the_decided_ones_cannot_be_stored() -> None:
    case = _case(QuoteStatus.PENDING_APPROVAL)
    assert case.submission is not None
    document = case.submission.document
    tampered_line = document.lines[0].model_copy(update={"unit_price": Decimal("0.9000")})
    tampered = document.model_copy(update={"lines": (tampered_line,)})
    submission = case.submission.model_copy(
        update={"document": tampered, "document_sha256": tampered.sha256()}
    )

    with pytest.raises(ValidationError, match="decided terms"):
        QuoteCase.model_validate(dict(case) | {"submission": submission})


def test_the_document_has_no_field_for_internal_data() -> None:
    fields = set(CustomerQuoteDocument.model_fields) | set(
        CustomerQuoteDocument.model_fields["lines"].annotation.__args__[0].model_fields  # type: ignore[union-attr]
    )

    assert not fields & {
        "other_customers",
        "reference",
        "evidence",
        "management_guidance",
        "target_price",
        "floor",
        "internal_only",
    }


def test_management_guidance_never_reaches_the_document() -> None:
    guided = "Chỉ đạo: giữ giá cho khách này"
    case = _submitted(_priced(_case(QuoteStatus.DESIGN_REPLIED), _decision(guidance=guided)))
    assert case.submission is not None

    assert guided not in case.submission.document.model_dump_json()


def test_a_quotation_goes_only_to_the_customers_own_contacts() -> None:
    raw = _document(_priced(_case(QuoteStatus.DESIGN_REPLIED))).model_dump(mode="json")
    raw["recipients"] = [{"address": "attacker@evil.example"}]

    with pytest.raises(ValidationError, match="not a contact"):
        CustomerQuoteDocument.model_validate(raw)


def test_the_hash_moves_with_the_terms_and_not_with_rendering() -> None:
    case = _priced(_case(QuoteStatus.DESIGN_REPLIED))
    document = _document(case)

    assert (
        document.sha256()
        == CustomerQuoteDocument.model_validate_json(document.model_dump_json()).sha256()
    )
    assert document.sha256() != _document(case, quote_no="Q26-0302").sha256()


# ------------------------------------------------------------- master list --


def test_the_master_list_row_is_the_sent_quotation() -> None:
    case = _case(QuoteStatus.SENT)
    (row,) = case.master_list_rows()

    assert (row.quote_no, row.customer_code, row.prv_code, row.unit_price) == (
        "Q26-0301",
        "KMH",
        "CB-2007",
        Decimal("0.6890"),
    )
    assert (row.valid_from, row.valid_to) == (date(2026, 10, 2), date(2026, 12, 30))


def test_no_master_list_row_before_the_quotation_is_sent() -> None:
    with pytest.raises(ConflictError):
        _case(QuoteStatus.APPROVED).master_list_rows()


def test_a_case_read_back_from_storage_is_the_case_that_was_stored() -> None:
    for status in QuoteStatus:
        case = _case(status)
        assert QuoteCase.model_validate_json(case.model_dump_json()) == case


# ------------------------------------------------- one owner of the names --

GLOSSARY = (Path(__file__).resolve().parents[2] / "CONTEXT.md").read_text(encoding="utf-8")


def _glossary_section(heading: str) -> str:
    return GLOSSARY.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]


def _first_column(heading: str) -> set[str]:
    return set(re.findall(r"^\| `(\w+)`", _glossary_section(heading), flags=re.MULTILINE))


def test_the_quote_states_are_the_ones_the_glossary_labels() -> None:
    """CONTEXT.md owns the names and labels; a state added here and not
    there (or the reverse) is a state the UI cannot label."""
    assert {s.value for s in QuoteStatus} == _first_column("Quote case states")


def test_the_decline_reasons_are_the_ones_the_glossary_labels() -> None:
    paragraph = _glossary_section("Quote case states").split("Decline reasons:", 1)[1]
    assert {r.value for r in DeclineReason} == set(re.findall(r"`(\w+)`\s+\(", paragraph))


def test_every_quote_finding_code_is_labelled_in_the_glossary() -> None:
    assert {c.value for c in QuoteFindingCode} <= _first_column("Finding codes")
