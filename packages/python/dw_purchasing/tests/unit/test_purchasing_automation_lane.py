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
from dw_purchasing.domain.automation import AutomationLevel, AutomationStep
from dw_purchasing.domain.cases import CaseStatus
from dw_purchasing.testing.lane import DW2, Accounts, lane_of, measure_pr_reading
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
HEAD = uuid.UUID(int=0x4EAD)


def _world() -> World:
    world = open_world(REPO, INTAKE["answers"])
    world.model.by_schema = {
        "ModelOffer": SOURCING["answers"],
        "RfqWording": {"PR-2611-004": SOURCING["rfq_words"]["good"]},
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
    assert len(to_person) == 4 and len(supplier) == 4
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
    assert len([k for k in notices.told if k.startswith("purchasing.mail.supplier:")]) == 4
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

    titles = [notices.told[k][3] for k in notices.told if k.startswith("purchasing.mail.supplier:")]
    assert any("trả lời hỏi giá PR-2611-004" in t for t in titles)
