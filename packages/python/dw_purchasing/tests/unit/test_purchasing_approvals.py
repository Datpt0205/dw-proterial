"""DW02 function 2: a request checked against master data and sent to the
approver its amount and findings name; the decision carried out from the
approval row. Over the in-memory world, with the mock master data."""

from __future__ import annotations

import dataclasses
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.approvals import REQUEST_APPROVAL, REQUEST_DECIDED
from dw_purchasing.domain.cases import CaseStatus
from dw_purchasing.domain.checks import (
    Budget,
    Item,
    MasterData,
    PastPurchase,
    PurchaseFindingCode,
    SupplierQuote,
    cross_check,
)
from dw_purchasing.domain.requests import PrLine, PurchaseRequest
from dw_purchasing.domain.rules import ApprovalRules, ApproveScope
from dw_purchasing.testing.world import ALPHA, BETA, BUYER, World, caller, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
ANSWERS = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)["answers"]
TODAY = date(2026, 11, 2)
HEAD = uuid.UUID(int=0x4EAD)


def _request(*lines: PrLine, budget: str | None = "CC-1", currency: str = "VND") -> PurchaseRequest:
    return PurchaseRequest(
        pr_no="PR-1",
        department="Kho",
        requester="An",
        budget_code=budget,
        currency=currency,
        lines=lines,
    )


def _line(n: int = 1, code: str | None = "IT-1", qty: int = 10, **kw: Any) -> PrLine:
    return PrLine(
        line_no=n, item_code=code, description="x", quantity=Decimal(qty), unit="cái", **kw
    )


MASTER = MasterData(
    items={"IT-1": Item(code="IT-1", description="x", unit="cái")},
    quotes=(
        SupplierQuote(
            item_code="IT-1",
            supplier_code="S2",
            unit_price=Decimal(120),
            currency="VND",
            valid_until=date(2026, 12, 31),
            lead_time_days=10,
        ),
        SupplierQuote(
            item_code="IT-1",
            supplier_code="S1",
            unit_price=Decimal(100),
            currency="VND",
            valid_until=date(2026, 12, 31),
            lead_time_days=10,
        ),
        SupplierQuote(
            item_code="IT-1",
            supplier_code="S0",
            unit_price=Decimal(50),
            currency="VND",
            valid_until=date(2026, 11, 1),
            lead_time_days=1,
        ),
    ),
    history=(
        PastPurchase(
            item_code="IT-1",
            supplier_code="S9",
            unit_price=Decimal(90),
            currency="VND",
            ordered_on=date(2026, 1, 1),
        ),
    ),
    budgets={"CC-1": Budget(code="CC-1", remaining=Decimal(1500), currency="VND")},
)


def _check(request: PurchaseRequest, master: MasterData = MASTER) -> Any:
    return cross_check(request, master, today=TODAY, tolerance_percent=Decimal(10))


# --------------------------------------------------------------- the check --


def test_the_reference_is_the_lowest_quotation_still_valid() -> None:
    check = _check(_request(_line(qty=10)))
    (line,) = check.lines
    assert (line.reference_price, line.basis, line.supplier_code) == (Decimal(100), "quote", "S1")
    assert check.amount == Decimal(1000) and check.findings == ()


def test_without_a_valid_quotation_the_last_price_paid_then_the_estimate() -> None:
    expired = MASTER.model_copy(update={"quotes": (MASTER.quotes[2],)})
    assert _check(_request(_line()), expired).lines[0].basis == "history"
    unknown = _check(_request(_line(code=None, estimated_unit_price=Decimal(7))), MasterData())
    assert (unknown.lines[0].basis, unknown.amount) == ("estimate", Decimal(70))
    assert {f.code for f in unknown.findings} == {
        PurchaseFindingCode.ITEM_UNKNOWN,
        PurchaseFindingCode.BUDGET_UNKNOWN,
    }


def test_a_line_without_any_price_leaves_the_amount_unknown_never_small() -> None:
    check = _check(_request(_line(), _line(n=2, code=None)))
    assert check.amount is None
    assert PurchaseFindingCode.NO_REFERENCE_PRICE in check.codes


def test_a_price_in_another_currency_is_no_reference() -> None:
    check = _check(_request(_line(), currency="USD"))
    assert check.amount is None
    assert {
        PurchaseFindingCode.CURRENCY_MISMATCH,
        PurchaseFindingCode.NO_REFERENCE_PRICE,
    } <= check.codes


def test_an_estimate_past_the_tolerance_a_short_need_by_and_the_budget_are_found() -> None:
    check = _check(
        _request(_line(qty=20, estimated_unit_price=Decimal(111), need_by=date(2026, 11, 5)))
    )
    assert check.codes == {
        PurchaseFindingCode.ESTIMATE_ABOVE_REFERENCE,
        PurchaseFindingCode.NEED_BY_SHORT,
        PurchaseFindingCode.OVER_BUDGET,
    }
    within = _check(_request(_line(qty=1, estimated_unit_price=Decimal(110))))
    assert within.codes == frozenset()
    assert _check(_request(_line(), budget=None)).codes == {PurchaseFindingCode.BUDGET_MISSING}


# ----------------------------------------------------------------- the tiers --


def _rules(**changes: Any) -> ApprovalRules:
    document: dict[str, Any] = {
        "currency": "VND",
        "tiers": [
            {"up_to": "1000", "scope": "purchasing.approve.tier1", "label": "T1"},
            {"up_to": None, "scope": "purchasing.approve.tier3", "label": "T3"},
        ],
        "price_tolerance_percent": "10",
        "escalate": ["over_budget"],
    }
    return ApprovalRules.model_validate({**document, **changes})


def test_a_tier_decides_up_to_its_limit_inclusive_and_the_unknown_goes_to_the_last() -> None:
    rules = _rules()
    assert rules.tier_for(_check(_request(_line(qty=10)))).label == "T1"  # exactly 1000
    assert rules.tier_for(_check(_request(_line(qty=11)))).label == "T3"
    assert rules.tier_for(_check(_request(_line(code=None)))).label == "T3"
    over = _check(_request(_line(qty=10)), MASTER.model_copy(update={"budgets": {}}))
    assert rules.tier_for(over).label == "T1"  # budget_unknown does not escalate here
    tight = MASTER.model_copy(
        update={"budgets": {"CC-1": Budget(code="CC-1", remaining=Decimal(5), currency="VND")}}
    )
    assert rules.tier_for(_check(_request(_line(qty=1)), tight)).label == "T3"


@pytest.mark.parametrize(
    "tiers",
    [
        [{"up_to": "10", "scope": "purchasing.approve.tier1", "label": "A"}],
        [
            {"up_to": None, "scope": "purchasing.approve.tier1", "label": "A"},
            {"up_to": None, "scope": "purchasing.approve.tier2", "label": "B"},
        ],
        [
            {"up_to": "10", "scope": "purchasing.approve.tier1", "label": "A"},
            {"up_to": "5", "scope": "purchasing.approve.tier2", "label": "B"},
            {"up_to": None, "scope": "purchasing.approve.tier3", "label": "C"},
        ],
        [{"up_to": None, "scope": "sales.quote.approve", "label": "A"}],
    ],
    ids=["no-open-last", "two-open", "descending", "foreign-scope"],
)
def test_limits_a_tenant_writes_are_held_to_their_shape(tiers: list[dict[str, Any]]) -> None:
    with pytest.raises(ValidationError):
        _rules(tiers=tiers)


def test_the_scopes_a_rule_may_name_are_the_ones_purchasing_declares() -> None:
    declared = {s.value for s in PurchasingScopes if s.name.startswith("APPROVE_")}
    assert set(get_args(ApproveScope)) == declared


# ------------------------------------------------------------ send, decide --


async def _received(world: World, message_id: str = "P01") -> uuid.UUID:
    item = await world.service.read_mail(caller(), message_id)
    assert item.case_id is not None
    return item.case_id


async def test_a_request_is_sent_to_the_approver_its_amount_names_and_stamped() -> None:
    world = open_world(REPO, ANSWERS)
    case_id = await _received(world)

    preview = await world.approvals.preview(caller(), case_id)
    assert preview.check.amount == Decimal(14_160_000)  # 5,000,000 + 4,600,000 + 4,560,000
    assert [line.basis for line in preview.check.lines] == ["quote", "history", "history"]
    assert (preview.required_scope, preview.tier_label) == (
        "purchasing.approve.tier1",
        "Trưởng phòng Mua hàng",
    )
    change = await world.approvals.submit(caller(), case_id, case_version=1)

    case = await world.service.case(caller(), case_id)
    assert (change.status, case.case_version) == (CaseStatus.AWAITING_APPROVAL, 2)
    assert case.check == preview.check
    assert case.approval is not None and case.approval.required_scope == "purchasing.approve.tier1"
    rows = world.store.rows(*ALPHA)
    (request,) = rows.approvals.values()
    assert (request.approval_type, request.required_scope, request.id) == (
        REQUEST_APPROVAL,
        "purchasing.approve.tier1",
        case.approval.approval_id,
    )
    assert request.payload == {
        "case_id": str(case_id),
        "case_version": 2,
        "makers": [str(BUYER)],
    }
    assert rows.audit[-1].action == "purchasing.request.submitted"
    assert REQUEST_DECIDED == "purchasing.request.decided"


async def test_an_amount_past_the_budget_goes_to_the_last_tier() -> None:
    world = open_world(REPO, ANSWERS)
    case_id = await _received(world, "P02")  # 2 x 18,500,000 against 30,000,000 left
    preview = await world.approvals.preview(caller(), case_id)
    assert preview.check.codes == {
        PurchaseFindingCode.OVER_BUDGET,
        PurchaseFindingCode.NEED_BY_SHORT,
    }
    assert preview.required_scope == "purchasing.approve.tier3"


async def test_sending_is_refused_on_a_stale_version_twice_or_without_its_scope() -> None:
    world = open_world(REPO, ANSWERS)
    case_id = await _received(world)
    with pytest.raises(PermissionDeniedError):
        await world.approvals.submit(
            caller(scopes=frozenset({PurchasingScopes.REQUEST_READ.value})), case_id, case_version=1
        )
    with pytest.raises(ConflictError):
        await world.approvals.submit(caller(), case_id, case_version=2)
    await world.approvals.submit(caller(), case_id, case_version=1)
    with pytest.raises(ConflictError):
        await world.approvals.submit(caller(), case_id, case_version=2)
    assert len(world.store.rows(*ALPHA).approvals) == 1


async def test_rules_that_set_no_limits_send_nothing() -> None:
    world = open_world(REPO, ANSWERS)
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = {
        "version": "9.0.1",
        "pr_form": {
            "required": [],
            "max_lines": 50,
            "currencies": ["VND"],
            "default_currency": "VND",
        },
        "internal_domains": ["seller.example"],
        # Said, not left out: a field a version omits reads as the platform's.
        "approval": None,
    }
    case_id = await _received(world)
    with pytest.raises(ConflictError) as refused:
        await world.approvals.submit(caller(), case_id, case_version=1)
    assert refused.value.details["rule"] == "no_limits"
    assert world.store.rows(*ALPHA).approvals == {}


async def test_another_tenant_cannot_check_or_send_our_case() -> None:
    world = open_world(REPO, ANSWERS)
    case_id = await _received(world)
    with pytest.raises(NotFoundError):
        await world.approvals.preview(caller(BETA), case_id)
    with pytest.raises(NotFoundError):
        await world.approvals.submit(caller(BETA), case_id, case_version=1)


async def _sent(world: World) -> tuple[uuid.UUID, uuid.UUID]:
    case_id = await _received(world)
    await world.approvals.submit(caller(), case_id, case_version=1)
    case = await world.service.case(caller(), case_id)
    assert case.approval is not None
    return case_id, case.approval.approval_id


def _decide(world: World, approval_id: uuid.UUID, *, approved: bool) -> None:
    world.store.decide(
        approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=approved,
        decided_by=HEAD,
        at=datetime(2026, 11, 2, 9, 0, tzinfo=world.clock.now().tzinfo),
        comment="Đồng ý, mua theo báo giá Kimura",
    )


@pytest.mark.parametrize("approved", [True, False])
async def test_a_decision_is_carried_out_from_the_approval_row_once(approved: bool) -> None:
    world = open_world(REPO, ANSWERS)
    case_id, approval_id = await _sent(world)
    head = caller(principal=HEAD, scopes=frozenset())
    with pytest.raises(ConflictError):  # not decided yet
        await world.settlement.settle(approval_id, head)

    _decide(world, approval_id, approved=approved)
    first = await world.settlement.settle(approval_id, head)
    again = await world.settlement.settle(approval_id, head)

    assert first == again
    case = await world.service.case(caller(), case_id)
    expected = CaseStatus.APPROVED if approved else CaseStatus.REJECTED
    assert (case.status, case.case_version) == (expected, 3)
    assert case.decision is not None
    assert (case.decision.decided_by, case.decision.comment) == (
        HEAD,
        "Đồng ý, mua theo báo giá Kimura",
    )
    actions = [e.action for e in world.store.rows(*ALPHA).audit]
    assert actions.count(f"purchasing.request.{expected.value}") == 1


async def test_the_stamped_approver_holds_when_the_rules_change_after_sending() -> None:
    world = open_world(REPO, ANSWERS)
    case_id, approval_id = await _sent(world)
    # The tenant now sends everything to tier 3: the waiting case keeps tier 1.
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = {
        **json.loads(
            json.dumps(
                {
                    "version": "9.1.0",
                    "pr_form": {
                        "required": ["budget_code"],
                        "max_lines": 50,
                        "currencies": ["VND"],
                        "default_currency": "VND",
                    },
                    "internal_domains": ["seller.example"],
                    "approval": {
                        "currency": "VND",
                        "tiers": [
                            {"up_to": None, "scope": "purchasing.approve.tier3", "label": "TGĐ"}
                        ],
                        "price_tolerance_percent": "10",
                        "escalate": [],
                    },
                }
            )
        )
    }
    _decide(world, approval_id, approved=True)
    await world.settlement.settle(approval_id, caller(principal=HEAD, scopes=frozenset()))
    case = await world.service.case(caller(), case_id)
    assert case.status is CaseStatus.APPROVED
    assert case.approval is not None and case.approval.required_scope == "purchasing.approve.tier1"


async def test_the_guard_refuses_a_decision_on_a_case_that_moved_on() -> None:
    world = open_world(REPO, ANSWERS)
    _, approval_id = await _sent(world)
    request = world.store.rows(*ALPHA).approvals[approval_id]
    head = caller(principal=HEAD, scopes=frozenset({"purchasing.approve.tier1"}))

    await world.decisions.check(request, ProposedDecision(True, "ok", {}, 2), head)
    with pytest.raises(ConflictError):
        await world.decisions.check(request, ProposedDecision(True, "ok", {}, 1), head)
    _decide(world, approval_id, approved=True)
    await world.settlement.settle(approval_id, head)
    with pytest.raises(ConflictError):
        await world.decisions.check(request, ProposedDecision(True, "ok", {}, None), head)
    with pytest.raises(NotFoundError):
        await world.decisions.check(request, ProposedDecision(True, "ok", {}, None), caller(BETA))


async def test_a_decision_in_another_tenant_finds_nothing_to_carry_out() -> None:
    world = open_world(REPO, ANSWERS)
    _, approval_id = await _sent(world)
    _decide(world, approval_id, approved=True)
    with pytest.raises(NotFoundError):
        await world.settlement.settle(approval_id, caller(BETA, principal=HEAD))
    case_rows = world.store.rows(*ALPHA).cases.values()
    assert all(c.status is CaseStatus.AWAITING_APPROVAL for c in case_rows)


async def test_the_mock_master_data_answers_its_demo_scope_only() -> None:
    from dw_purchasing.adapters.mock.master_data import MockMasterData

    master = MockMasterData.load(tenant_id=ALPHA[0], workspace_id=ALPHA[1])
    assert "DC-200" in (await master.for_context(caller())).items
    assert await master.for_context(caller(BETA)) == MasterData()


async def test_the_guard_refuses_a_decision_for_another_approval_of_the_case() -> None:
    world = open_world(REPO, ANSWERS)
    _, approval_id = await _sent(world)
    request = world.store.rows(*ALPHA).approvals[approval_id]
    forged = dataclasses.replace(request, id=uuid.uuid4())
    with pytest.raises(ConflictError):
        await world.decisions.check(forged, ProposedDecision(True, "ok", {}, None), caller())
