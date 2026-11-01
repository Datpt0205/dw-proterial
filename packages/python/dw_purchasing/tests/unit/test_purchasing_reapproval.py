"""A choice of suppliers past the approved tier goes back for approval at the
tier its total names (Đạt, 2026-11-01), its reason worded by the model and
kept only when every figure is code's; the decision carried out as the
decider, the choice becoming the selection or the case going back."""

from __future__ import annotations

import dataclasses
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import ConflictError
from dw_purchasing.application.reapprovals import REAPPROVAL
from dw_purchasing.application.sourcing import OfferForm
from dw_purchasing.domain.cases import CaseStatus, PurchaseCase
from dw_purchasing.domain.sourcing import Choice
from dw_purchasing.testing.world import ALPHA, RecordedNotices, World, caller, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
INTAKE = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)
SOURCING = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_sourcing.json").read_text(encoding="utf-8")
)
HEAD = uuid.UUID(int=0x4EAD)
DIRECTOR = uuid.UUID(int=0xD1EC)
PRICEY = [
    Choice(line_no=1, supplier_code="NHUAVIET"),
    Choice(line_no=2, supplier_code="BAOHO"),
    Choice(line_no=3, supplier_code="ANPHAT"),
]


def _world(reason: str | None = None) -> World:
    world = open_world(REPO, INTAKE["answers"])
    world.model.by_schema = {
        "ModelOffer": SOURCING["answers"],
        "RfqWording": {"PR-2611-004": SOURCING["rfq_words"]["good"]},
        "ReasonWords": {} if reason is None else {"PR-2611-004": {"reason": reason}},
    }
    return world


async def _version(world: World, case_id: uuid.UUID) -> int:
    return (await world.service.case(caller(), case_id)).case_version


def _decide(world: World, approval_id: uuid.UUID, by: uuid.UUID, ok: bool = True) -> None:
    world.store.decide(
        approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=ok,
        decided_by=by,
        at=datetime(2026, 11, 2, 9, tzinfo=UTC),
        comment="ok" if ok else "không",
    )


async def _offered(world: World) -> uuid.UUID:
    item = await world.service.read_mail(caller(), "P01")
    case_id = item.case_id
    assert case_id is not None
    await world.approvals.submit(caller(), case_id, case_version=1)
    case = await world.service.case(caller(), case_id)
    assert case.approval is not None
    _decide(world, case.approval.approval_id, HEAD)
    await world.settlement.settle(case.approval.approval_id, caller(principal=HEAD))
    await world.sourcing.draft_rfq(caller(), case_id, case_version=3)
    for message_id in ("Q01", "Q02", "Q03"):
        await world.sourcing.read_offer_mail(
            caller(), case_id, message_id, case_version=await _version(world, case_id)
        )
    offer = OfferForm(
        supplier_code="NHUAVIET",
        line_no=1,
        unit_price=Decimal(5_000_000),
        currency="VND",
        lead_time_days=2,
    )
    await world.sourcing.record_offer(
        caller(), case_id, offer, case_version=await _version(world, case_id)
    )
    return case_id


async def _pricey(world: World, case_id: uuid.UUID, by: uuid.UUID | None = None) -> PurchaseCase:
    chooser = caller() if by is None else caller(principal=by)
    await world.sourcing.select(
        chooser, case_id, PRICEY, case_version=await _version(world, case_id)
    )
    return await world.service.case(caller(), case_id)


def _facts_reason(case: PurchaseCase) -> str:
    """A reason whose every figure is one of the facts' (the request number,
    the approved limit and the chosen total as code writes them)."""
    assert case.approval is not None and case.approval.limit is not None
    limit = f"{case.approval.limit.normalize():f}"
    return f"{case.request.pr_no} được duyệt trong hạn mức {limit}; cần người duyệt mới."


async def test_past_the_tier_the_choice_waits_on_the_tier_its_total_names() -> None:
    world, notices = _world(), RecordedNotices()
    assert world.sourcing.reapprovals is not None
    world.sourcing = dataclasses.replace(
        world.sourcing,
        reapprovals=dataclasses.replace(world.sourcing.reapprovals, notices=notices),
    )
    chooser = uuid.UUID(int=0xC40)
    case = await _pricey(world, await _offered(world), by=chooser)

    assert case.status is CaseStatus.AWAITING_REAPPROVAL and case.selection is None
    assert case.reapproval is not None and case.approval is not None
    asked = case.reapproval.approval
    assert asked.required_scope != case.approval.required_scope
    assert case.reapproval.selection.total > (case.approval.limit or 0)
    request = world.store.rows(*ALPHA).approvals[asked.approval_id]
    assert (request.approval_type, request.required_scope) == (REAPPROVAL, asked.required_scope)
    # Whoever chose is a maker, besides who made the request: the platform's
    # strict rule keeps them all off it.
    makers = request.payload["makers"]
    assert isinstance(makers, list) and {str(chooser), str(caller().principal_id)} <= set(makers)
    told = notices.told[f"purchasing.reapproval.asked:{asked.approval_id}"]
    assert told[0] == frozenset({asked.required_scope})


async def test_a_reason_is_kept_only_when_every_figure_is_a_fact() -> None:
    probe = await _pricey(world := _world(), await _offered(world))
    good = _facts_reason(probe)
    kept = await _pricey(world := _world(good), await _offered(world))
    assert kept.reapproval is not None and kept.reapproval.explanation == good
    invented = await _pricey(
        world := _world("Vượt khoảng 30% so với hạn mức, tức 6000000 đồng."),
        await _offered(world),
    )
    assert invented.reapproval is not None and invented.reapproval.explanation is None
    world = _world(good)
    assert world.sourcing.reapprovals is not None
    world.sourcing = dataclasses.replace(
        world.sourcing, reapprovals=dataclasses.replace(world.sourcing.reapprovals, model=None)
    )
    none = await _pricey(world, await _offered(world))
    assert none.reapproval is not None and none.reapproval.explanation is None


async def test_within_the_tenants_tolerance_the_choice_is_the_selection() -> None:
    from dw_purchasing.adapters.policy_files import PolicyFiles

    world = _world()
    rules: dict[str, Any] = (
        PolicyFiles.load(REPO / "configs/policies").current().model_dump(mode="json")
    )
    rules["policy_version"] = "9.5.0"
    rules["approval"]["reapproval_tolerance_percent"] = "100"
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = rules
    case = await _pricey(world, await _offered(world))
    assert case.status is CaseStatus.SUPPLIER_SELECTED and case.reapproval is None


async def test_approved_the_choice_is_the_selection_and_the_orders_can_be_drafted() -> None:
    world = _world()
    case = await _pricey(world, await _offered(world))
    assert case.reapproval is not None
    approval_id = case.reapproval.approval.approval_id
    request = world.store.rows(*ALPHA).approvals[approval_id]
    with pytest.raises(ConflictError):
        await world.reapproval_decisions.check(
            request,
            ProposedDecision(True, "ok", {}, case.case_version - 1),
            caller(principal=DIRECTOR),
        )
    await world.reapproval_decisions.check(
        request, ProposedDecision(True, "ok", {}, case.case_version), caller(principal=DIRECTOR)
    )
    _decide(world, approval_id, DIRECTOR)
    settled = await world.reapproval_settlement.settle(approval_id, caller(principal=DIRECTOR))
    again = await world.reapproval_settlement.settle(approval_id, caller(principal=DIRECTOR))
    assert settled == again and settled.status is CaseStatus.SUPPLIER_SELECTED
    chosen = await world.service.case(caller(), case.case_id)
    assert chosen.selection == case.reapproval.selection
    drafted = await world.orders.draft(caller(), case.case_id, case_version=chosen.case_version)
    assert drafted.status is CaseStatus.PO_DRAFTED


async def test_rejected_the_case_goes_back_to_choosing_with_the_choice_kept() -> None:
    world = _world()
    case = await _pricey(world, await _offered(world))
    assert case.reapproval is not None
    approval_id = case.reapproval.approval.approval_id
    _decide(world, approval_id, DIRECTOR, ok=False)
    await world.reapproval_settlement.settle(approval_id, caller(principal=DIRECTOR))
    back = await world.service.case(caller(), case.case_id)
    assert back.status is CaseStatus.RFQ_DRAFTED and back.selection is None
    assert back.reapproval is not None and back.reapproval.decision is not None
    assert not back.reapproval.decision.approved


async def test_each_guard_refuses_the_others_approval() -> None:
    world = _world()
    case = await _pricey(world, await _offered(world))
    assert case.reapproval is not None and case.approval is not None
    rows = world.store.rows(*ALPHA)
    reapproval = rows.approvals[case.reapproval.approval.approval_id]
    first = rows.approvals[case.approval.approval_id]
    with pytest.raises(ConflictError):
        await world.decisions.check(
            reapproval, ProposedDecision(True, "ok", {}, None), caller(principal=DIRECTOR)
        )
    with pytest.raises(ConflictError):
        await world.reapproval_decisions.check(
            first, ProposedDecision(True, "ok", {}, None), caller(principal=DIRECTOR)
        )
    # An approval naming this very case and version, but not the one the
    # choice waits on, decides nothing.
    forged = dataclasses.replace(reapproval, id=uuid.uuid4())
    with pytest.raises(ConflictError):
        await world.reapproval_decisions.check(
            forged, ProposedDecision(True, "ok", {}, None), caller(principal=DIRECTOR)
        )
