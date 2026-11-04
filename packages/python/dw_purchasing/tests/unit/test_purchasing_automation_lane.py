"""DW2's `purchasing_automation` lane: each step taken as far as the tenant's
switch lets it, under DW2's service account, every person told what is
theirs to do, nothing guessed when the model is down."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_purchasing.application.automation_lane import (
    LANE_CEILING,
    dw2_subject,
)
from dw_purchasing.application.ports import Disposition
from dw_purchasing.domain.automation import AutomationLevel, AutomationStep, PurchasingModelStep
from dw_purchasing.domain.cases import CaseStatus
from dw_purchasing.testing.flows import orders_drafted
from dw_purchasing.testing.lane import DW2, Accounts, lane_of, measure, measure_pr_reading
from dw_purchasing.testing.world import (
    ALPHA,
    BETA,
    RecordedNotices,
    World,
    caller,
    open_world,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
FIXTURES = REPO / "evals/fixtures/cases"
INTAKE = json.loads((FIXTURES / "purchasing_pr_intake.json").read_text(encoding="utf-8"))
SOURCING = json.loads((FIXTURES / "purchasing_sourcing.json").read_text(encoding="utf-8"))
FOLLOW_UP = json.loads((FIXTURES / "purchasing_follow_up.json").read_text(encoding="utf-8"))
# P01's orders: Kimura's (C01 confirms it as ordered), Bảo Hộ's (C02: fewer
# gloves, later).
KIMURA, BAOHO = "PR-2611-004-03", "PR-2611-004-02"
HEAD = uuid.UUID(int=0x4EAD)


def _world() -> World:
    world = open_world(REPO, INTAKE["answers"])
    world.model.by_schema = {
        "ModelOffer": SOURCING["answers"],
        "RfqWording": {"PR-2611-004": SOURCING["rfq_words"]["good"]},
        "ModelConfirmation": FOLLOW_UP["answers"],
    }
    return world


def _lane(world: World, notices: RecordedNotices, accounts: Accounts | None = None) -> Any:
    return lane_of(world, notices, accounts)


async def _measure(world: World) -> None:
    await measure_pr_reading(world)


def _switches(world: World, **levels: AutomationLevel) -> None:
    steps = {step.value: AutomationLevel.AI_REVIEW.value for step in AutomationStep}
    steps |= {
        AutomationStep.MAIL_SORTING.value: "ai_auto",
        AutomationStep.SUBMISSION.value: "ai_auto",
        AutomationStep.PO_DRAFTING.value: "ai_auto",
    }
    steps |= {k: v.value for k, v in levels.items()}
    world.tenant_policies.documents[(ALPHA[0], "purchasing_automation")] = {
        "policy_version": "9.0.0",
        "steps": steps,
    }


def _cases(world: World, *statuses: CaseStatus) -> list[Any]:
    return [c for c in world.store.rows(*ALPHA).cases.values() if c.status in statuses]


async def test_measured_reading_opens_and_sends_each_request_and_tells_its_approver() -> None:
    world, notices = _world(), RecordedNotices()
    await _measure(world)
    tick = await _lane(world, notices).tick(*ALPHA)

    sent = _cases(world, CaseStatus.AWAITING_APPROVAL)
    # PR-2611-013 was read from its Excel form.
    assert {c.request.pr_no for c in sent} == {"PR-2611-004", "PR-2611-009", "PR-2611-013"}
    assert all(c.received_by == DW2 and c.review is None for c in sent)
    asked = [k for k in notices.told if k.startswith("purchasing.approval.asked:")]
    assert len(asked) == 3
    # A request read from a scan waits for a person even at "AI tự làm".
    (scanned,) = _cases(world, CaseStatus.RECEIVED)
    assert scanned.request.pr_no == "PR-2611-014"
    assert scanned.review is not None and scanned.review.pending
    review = notices.told[f"purchasing.case.review:{scanned.case_id}"]
    assert "bản scan" in review[3]
    # The approver is told; who made the request (here DW2's account, which
    # received and sent it) is never asked to approve it.
    assert all(DW2 in notices.told[k][2] for k in asked)
    # Mail that is no request goes to a person, with why, and they are told;
    # a known supplier's mail is never read as a request.
    to_person = [k for k in notices.told if k.startswith("purchasing.mail.to_person:")]
    supplier = [k for k in notices.told if k.startswith("purchasing.mail.supplier:")]
    # Supplier mail: P03 and the quotes Q01-Q03, the confirmations C01-C02.
    assert len(to_person) == 4 and len(supplier) == 6
    # Q04 claims a supplier's domain but the mail system did not verify it.
    assert "purchasing.mail.to_person:Q04" in to_person
    outcomes = world.store.rows(*ALPHA).outcomes
    assert {m for m in outcomes if m.startswith("Q")} == {"Q04"}
    actions = [e.action for e in world.store.rows(*ALPHA).audit if e.actor_id.value != DW2]
    assert actions.count("purchasing.automation.submitted") == 3
    assert any("submitted" in d for d in tick.done)


async def test_unmeasured_reading_waits_for_a_person_before_it_is_sent() -> None:
    world, notices = _world(), RecordedNotices()
    await _lane(world, notices).tick(*ALPHA)

    received = _cases(world, CaseStatus.RECEIVED)
    assert len(received) == 4 and all(c.review is not None and c.review.pending for c in received)
    assert _cases(world, CaseStatus.AWAITING_APPROVAL) == []
    assert len([k for k in notices.told if k.startswith("purchasing.case.review:")]) == 4
    one = received[0]
    await world.service.reviewed(caller(), one.case_id, case_version=one.case_version)
    await _lane(world, notices).tick(*ALPHA)
    assert [c.case_id for c in _cases(world, CaseStatus.AWAITING_APPROVAL)] == [one.case_id]


async def test_at_person_the_lane_reads_nothing_and_tells_the_buyers() -> None:
    world, notices = _world(), RecordedNotices()
    _switches(world, pr_drafting=AutomationLevel.PERSON)
    await _lane(world, notices).tick(*ALPHA)
    assert world.store.rows(*ALPHA).cases == {} and world.model.calls == []
    assert len([k for k in notices.told if k.startswith("purchasing.mail.arrived:")]) == 8
    # P03, the quotes Q01-Q03 and the confirmations C01-C02.
    assert len([k for k in notices.told if k.startswith("purchasing.mail.supplier:")]) == 6
    _switches(world, mail_sorting=AutomationLevel.PERSON)
    quiet = RecordedNotices()
    await _lane(world, quiet).tick(*ALPHA)
    assert quiet.told == {}


async def test_the_model_down_guesses_nothing_and_the_next_tick_tries_again() -> None:
    world, notices = _world(), RecordedNotices()
    world.model.failure = ModelUnavailableError("down")
    tick = await _lane(world, notices).tick(*ALPHA)
    assert "mail: model unavailable" in tick.done
    rows = world.store.rows(*ALPHA)
    assert rows.cases == {} and len(rows.outcomes) <= 2
    world.model.failure = None
    await _lane(world, notices).tick(*ALPHA)
    assert len(_cases(world, CaseStatus.RECEIVED)) == 4


async def test_without_dw2s_account_or_for_another_tenant_the_lane_does_nothing() -> None:
    world, notices = _world(), RecordedNotices()
    accounts = Accounts(set())
    tick = await _lane(world, notices, accounts).tick(*ALPHA)
    assert tick.done == ("no DW2 account",) and world.store.rows(*ALPHA).cases == {}
    assert accounts.asked == [(dw2_subject(ALPHA[0]), LANE_CEILING)]
    other = await _lane(world, notices, Accounts({BETA})).tick(*BETA)
    assert world.store.rows(*BETA).cases == {} and world.store.rows(*ALPHA).cases == {}
    assert other.done == ()


async def test_submission_at_ai_review_tells_the_buyers_and_sends_nothing() -> None:
    world, notices = _world(), RecordedNotices()
    await _measure(world)
    _switches(world, pr_drafting=AutomationLevel.AI_AUTO, submission=AutomationLevel.AI_REVIEW)
    await _lane(world, notices).tick(*ALPHA)
    assert _cases(world, CaseStatus.AWAITING_APPROVAL) == []
    ready = [k for k in notices.told if k.startswith("purchasing.case.ready_to_submit:")]
    # Not the scanned request: it waits for a person to compare it first.
    assert len(ready) == 3


async def test_an_approved_request_gets_its_rfqs_drafted_and_nothing_is_sent() -> None:
    world, notices = _world(), RecordedNotices()
    await _measure(world)
    lane = _lane(world, notices)
    await lane.tick(*ALPHA)
    case = next(c for c in _cases(world, CaseStatus.AWAITING_APPROVAL))
    assert case.approval is not None
    world.store.decide(
        case.approval.approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=True,
        decided_by=HEAD,
        at=datetime(2026, 11, 2, 9, tzinfo=UTC),
    )
    await world.settlement.settle(case.approval.approval_id, caller(principal=HEAD))
    await lane.tick(*ALPHA)
    drafted = world.store.rows(*ALPHA).cases[case.case_id]
    assert drafted.status is CaseStatus.RFQ_DRAFTED and drafted.rfq is not None
    assert f"purchasing.case.rfq_drafted:{case.case_id}" in notices.told
    _switches(world, rfq=AutomationLevel.PERSON)
    assert (await world.switches.level(caller(), AutomationStep.RFQ)).level.value == "person"


async def test_a_refused_step_is_told_once_in_its_own_words() -> None:
    world, notices = _world(), RecordedNotices()
    await _measure(world)
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = {
        "version": "9.0.0",
        "pr_form": {
            "required": [],
            "max_lines": 50,
            "currencies": ["VND"],
            "default_currency": "VND",
        },
        "internal_domains": ["seller.example"],
        "approval": None,
    }
    lane = _lane(world, notices)
    await lane.tick(*ALPHA)
    await lane.tick(*ALPHA)
    refused = [k for k in notices.told if k.startswith("purchasing.case.submission_refused:")]
    # Every case nobody still has to look over (the scanned one waits).
    received = [c for c in _cases(world, CaseStatus.RECEIVED) if c.review is None]
    assert len(refused) == len(received) and all(k.endswith(":no_limits") for k in refused)
    assert _cases(world, CaseStatus.AWAITING_APPROVAL) == []


async def test_a_suppliers_reply_to_a_case_asking_tells_the_buyer_which_case() -> None:
    world, notices = _world(), RecordedNotices()
    item = await world.service.read_mail(caller(), "P01")
    assert item.case_id is not None
    await world.approvals.submit(caller(), item.case_id, case_version=1)
    case = await world.service.case(caller(), item.case_id)
    assert case.approval is not None
    world.store.decide(
        case.approval.approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=True,
        decided_by=HEAD,
        at=datetime(2026, 11, 2, 9, tzinfo=UTC),
        comment="ok",
    )
    await world.settlement.settle(case.approval.approval_id, caller(principal=HEAD))
    await world.sourcing.draft_rfq(caller(), item.case_id, case_version=3)

    await _lane(world, notices).tick(*ALPHA)

    told = notices.told["purchasing.mail.quote:Q01"]
    assert "trả lời hỏi giá PR-2611-004" in told[3]
    # Not measured: the buyer presses "DW2 đọc báo giá"; nothing is read.
    assert world.store.rows(*ALPHA).cases[item.case_id].offers == ()


async def _rfq_drafted(world: World) -> uuid.UUID:
    item = await world.service.read_mail(caller(), "P01")
    assert item.case_id is not None
    await world.approvals.submit(caller(), item.case_id, case_version=1)
    case = await world.service.case(caller(), item.case_id)
    assert case.approval is not None
    world.store.decide(
        case.approval.approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=True,
        decided_by=HEAD,
        at=datetime(2026, 11, 2, 9, tzinfo=UTC),
        comment="ok",
    )
    await world.settlement.settle(case.approval.approval_id, caller(principal=HEAD))
    await world.sourcing.draft_rfq(caller(), item.case_id, case_version=3)
    return item.case_id


async def test_a_measured_quote_reading_records_each_reply_and_tells_the_buyer_to_choose() -> None:
    world, notices = _world(), RecordedNotices()
    await measure(world, PurchasingModelStep.SUPPLIER_QUOTE_READING)
    lane = _lane(world, notices)
    # Before any case asks, a supplier's mail is told once and left unsettled.
    await lane.tick(*ALPHA)
    assert "purchasing.mail.supplier:Q01" in notices.told
    assert "Q01" not in world.store.rows(*ALPHA).outcomes
    case_id = await _rfq_drafted(world)

    await lane.tick(*ALPHA)

    case = world.store.rows(*ALPHA).cases[case_id]
    assert {o.source_ref for o in case.offers} == {"Q01", "Q02", "Q03"}
    assert all(o.recorded_by == DW2 for o in case.offers)
    # Choosing stays the buyer's.
    assert case.status is CaseStatus.RFQ_DRAFTED and case.selection is None
    told = notices.told["purchasing.mail.quote:Q01"]
    assert "DW2 đã ghi báo giá" in told[3] and "chọn" in told[4]
    outcomes = world.store.rows(*ALPHA).outcomes
    assert {m: (o.disposition, o.case_id) for m, o in outcomes.items() if m in {"Q01", "Q02"}} == {
        "Q01": (Disposition.SUPPLIER, case_id),
        "Q02": (Disposition.SUPPLIER, case_id),
    }
    audited = [e.action for e in world.store.rows(*ALPHA).audit]
    assert audited.count("purchasing.automation.quote_read") == 3
    # Settled: the next tick reads nothing again.
    calls = len(world.model.calls)
    await lane.tick(*ALPHA)
    assert len(world.model.calls) == calls


async def _numbered(world: World, case_id: uuid.UUID) -> None:
    for po_ref, number in ((KIMURA, "PO-26110007"), (BAOHO, "PO-26110008")):
        version = (await world.service.case(caller(), case_id)).case_version
        await world.follow_up.record_bravo_no(
            caller(), case_id, po_ref, number, case_version=version
        )


def _tracked(world: World, case_id: uuid.UUID, po_ref: str) -> Any:
    case = world.store.rows(*ALPHA).cases[case_id]
    return next((t for t in case.tracking if t.po_ref == po_ref), None)


async def test_a_confirmation_as_ordered_is_accepted_and_one_that_differs_goes_to_the_buyer() -> (
    None
):
    world, notices = _world(), RecordedNotices()
    await measure(world, PurchasingModelStep.ORDER_CONFIRMATION_READING)
    case_id = await orders_drafted(world)
    await _numbered(world, case_id)

    await _lane(world, notices).tick(*ALPHA)

    same = _tracked(world, case_id, KIMURA).confirmation
    assert same.source_ref == "C01" and same.accepted_by == DW2 and same.differences == ()
    differs = _tracked(world, case_id, BAOHO).confirmation
    assert differs.source_ref == "C02" and differs.accepted_by is None and differs.differences
    # Told only what is the buyer's: the one that differs.
    assert "purchasing.mail.confirmation:C01" not in notices.told
    told = notices.told["purchasing.mail.confirmation:C02"]
    assert "khác đơn" in told[3] and told[5] == f"/purchasing/requests/{case_id}"
    outcomes = world.store.rows(*ALPHA).outcomes
    assert (outcomes["C01"].disposition, outcomes["C01"].case_id) == (Disposition.SUPPLIER, case_id)
    audited = [e.action for e in world.store.rows(*ALPHA).audit]
    assert audited.count("purchasing.automation.confirmation_accepted") == 1


async def test_an_unmeasured_confirmation_reading_is_read_and_left_for_the_buyer_to_accept() -> (
    None
):
    world, notices = _world(), RecordedNotices()
    case_id = await orders_drafted(world)
    await _numbered(world, case_id)

    await _lane(world, notices).tick(*ALPHA)

    same = _tracked(world, case_id, KIMURA).confirmation
    assert same.source_ref == "C01" and same.accepted_by is None
    assert "khớp đơn" in notices.told["purchasing.mail.confirmation:C01"][3]
    assert "khác đơn" in notices.told["purchasing.mail.confirmation:C02"][3]


async def test_at_person_a_confirmation_is_told_with_its_case_and_nothing_read() -> None:
    world, notices = _world(), RecordedNotices()
    _switches(world, confirmation_reading=AutomationLevel.PERSON)
    case_id = await orders_drafted(world)
    await _numbered(world, case_id)

    await _lane(world, notices).tick(*ALPHA)

    assert _tracked(world, case_id, KIMURA).confirmation is None
    told = notices.told["purchasing.mail.confirmation:C01"]
    assert told[5] == f"/purchasing/requests/{case_id}"


async def test_each_late_line_is_told_to_the_buyers_once_per_date_it_is_due() -> None:
    world, notices = _world(), RecordedNotices()
    case_id = await orders_drafted(world)
    lane = _lane(world, notices)
    await lane.tick(*ALPHA)
    assert not [k for k in notices.told if k.startswith("purchasing.order.late:")]

    # Needed by 20/11; it is 21/11 at the plant.
    world.clock.advance_to(datetime(2026, 11, 21, 2, 0, tzinfo=UTC))
    await lane.tick(*ALPHA)
    await lane.tick(*ALPHA)

    late = sorted(k for k in notices.told if k.startswith("purchasing.order.late:"))
    assert late == [
        f"purchasing.order.late:{case_id}:{BAOHO}:2:2026-11-20",
        f"purchasing.order.late:{case_id}:{KIMURA}:1:2026-11-20",
    ]
    told = notices.told[late[0]]
    assert told[0] == frozenset({"purchasing.po.prepare"})
    assert "trễ hạn" in told[3] and "20/11/2026" in told[4]
    assert told[5] == f"/purchasing/requests/{case_id}"


async def test_the_model_down_leaves_a_confirmation_unsettled_for_the_next_tick() -> None:
    world, notices = _world(), RecordedNotices()
    await measure(world, PurchasingModelStep.ORDER_CONFIRMATION_READING)
    case_id = await orders_drafted(world)
    # The requests ahead of it read first, so the down tick reaches C01 (it
    # names Bravo's number, not typed yet: nothing to tie it to until then).
    await _lane(world, notices).tick(*ALPHA)
    assert "C01" not in world.store.rows(*ALPHA).outcomes
    await _numbered(world, case_id)
    world.model.failure = ModelUnavailableError("down")

    tick = await _lane(world, notices).tick(*ALPHA)

    assert "mail: model unavailable" in tick.done
    assert "C01" not in world.store.rows(*ALPHA).outcomes
    assert _tracked(world, case_id, KIMURA).confirmation is None
    world.model.failure = None
    await _lane(world, notices).tick(*ALPHA)
    assert _tracked(world, case_id, KIMURA).confirmation.accepted_by == DW2
