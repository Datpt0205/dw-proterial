"""Web Push from the follow-ups lane (ticket 48), over the in-memory world.

M01 opens an order assigned to An (PIC), received Monday 21 September 2026
at 08:12 local; Giang is the head. The lane pushes once per person per tick,
after the reminders it recorded, with a payload that names the kind of work
and the case number at most.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.domain.audit import system_actor
from dw_sales.adapters.policy_files import rule_book
from dw_sales.application.followups import (
    SALES_FOLLOWUPS_LANE,
    FollowupLane,
    item_link,
    push_notice,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import Audience, Due, Followup, SalesFollowups, Stage, WaitingCase
from dw_sales.evals.graders import AN, CALLERS, GIANG
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, _Followups, open_world
from dw_sales.evals.world import Directory as Holders
from dw_sales.testing.followups import platform_reminder_copy

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
HOUR = timedelta(hours=1)
CUSTOMER = "KHXYZ"


@dataclass(frozen=True, slots=True)
class Outcome:
    reached: int
    removed: int


@dataclass(frozen=True, slots=True)
class Pushed:
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    person: uuid.UUID
    payload: Mapping[str, object]


@dataclass
class Pusher:
    """`PushNoticePort` keeping every push; each person has one device."""

    pushed: list[Pushed] = field(default_factory=list)
    fail: bool = False

    async def push(
        self,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        person: uuid.UUID,
        payload: Mapping[str, object],
    ) -> Outcome:
        if self.fail:
            raise RuntimeError("push service down")
        self.pushed.append(Pushed(tenant_id, workspace_id, person, dict(payload)))
        return Outcome(reached=1, removed=0)

    def to(self, person: uuid.UUID) -> list[Mapping[str, object]]:
        return [p.payload for p in self.pushed if p.person == person]


@dataclass
class Sender:
    async def deliver(self, context: Any, **_: Any) -> None:
        return None


@dataclass
class Rig:
    world: World
    lane: FollowupLane
    pusher: Pusher
    clock: FixedClock
    order_id: uuid.UUID
    received: datetime

    async def tick(self, at: datetime, scope: SalesScope = ALPHA) -> None:
        self.clock.advance_to(at)
        await self.lane.tick(scope)


async def _rig(*, turn: bool = False, case_number: bool = True) -> Rig:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    seen = await world.process_each(AN, ["M01"])
    order_id = seen["M01"][0].case_id
    assert order_id is not None
    document = world.policies.followups.model_dump(mode="json")
    document["policy_version"] = "1.5.1"
    document["morning_brief"] = {**document["morning_brief"], "enabled": False}
    document["your_turn"] = {"enabled": turn}
    document["push"] = {"case_number": case_number}
    world.store.rule_versions.seed_approved(
        ALPHA.tenant_id.value, SalesFollowups.model_validate(document)
    )
    pusher = Pusher()
    received = world.order(order_id).received_at
    clock = FixedClock(received)
    lane = FollowupLane(
        uow=world.store,
        policies=rule_book(world.policies, world.store.rule_versions),
        holders=Holders(CALLERS),
        notifications=Sender(),
        clock=clock,
        ids=Uuid4Generator(),
        push=pusher,
    )
    return Rig(world, lane, pusher, clock, order_id, received)


# ------------------------------------------------------------ the lane --


async def test_a_reminder_reaches_the_person_told_as_one_push_opening_the_item() -> None:
    rig = await _rig()
    await rig.tick(rig.received + 4 * HOUR)
    (payload,) = rig.pusher.to(AN.user_id)
    assert payload["title"] == "Sắp quá hạn xác nhận"
    assert payload["body"] == "PO VLX-PO-2609-0118"
    # The deep link opens the item on the feed, expanded.
    assert payload["url"] == f"/sales?item=order:{rig.order_id}"
    assert payload["count"] == 1
    # Only the person told, in the case's tenant and workspace.
    (push,) = rig.pusher.pushed
    assert (push.tenant_id, push.workspace_id) == (ALPHA.tenant_id.value, ALPHA.workspace_id.value)


async def test_several_items_in_one_tick_ring_once() -> None:
    """Told "your turn" and the 4-hour reminder in the same tick: one push,
    counted, opening the feed."""
    rig = await _rig(turn=True)
    await rig.tick(rig.received + 4 * HOUR)
    (payload,) = rig.pusher.to(AN.user_id)
    assert payload == {
        "title": "2 việc mới",
        "body": "Mở DW1 để xem và quyết định.",
        "url": "/sales",
        "count": 2,
        "tag": "sales:batch",
    }


async def test_the_escalation_reaches_the_head_once() -> None:
    rig = await _rig()
    await rig.tick(rig.received + 4 * HOUR)
    await rig.tick(rig.received + 24 * HOUR)
    await rig.tick(rig.received + 25 * HOUR)
    await rig.tick(rig.received + 48 * HOUR)
    (escalated,) = rig.pusher.to(GIANG.user_id)
    assert escalated["title"] == "Quá hạn xác nhận"
    # The PIC was pushed for the reminder once and not again.
    assert len(rig.pusher.to(AN.user_id)) == 1


async def test_nothing_recorded_pushes_nothing() -> None:
    """A tick in another tenant's workspace, or before anything is owed,
    pushes to nobody."""
    rig = await _rig()
    await rig.tick(rig.received + 4 * HOUR - timedelta(minutes=1))
    await rig.tick(rig.received + 30 * HOUR, scope=BETA)
    assert rig.pusher.pushed == []


async def test_a_push_is_audited_as_the_lane_by_counts() -> None:
    rig = await _rig()
    await rig.tick(rig.received + 4 * HOUR)
    events = [e for e in rig.world.store.state(ALPHA).audit if e.action == "sales.followup.pushed"]
    (event,) = events
    assert event.actor_id == system_actor(SALES_FOLLOWUPS_LANE)
    assert event.details["items"] == 1 and event.details["devices"] == 1
    assert str(AN.user_id) not in json.dumps(event.details, default=str)


async def test_a_failing_push_costs_the_reminder_nothing() -> None:
    rig = await _rig()
    rig.pusher.fail = True
    await rig.tick(rig.received + 4 * HOUR)
    assert len(rig.world.store.state(ALPHA).followups) == 1


async def test_the_tenant_may_keep_the_number_off_the_lock_screen() -> None:
    rig = await _rig(case_number=False)
    await rig.tick(rig.received + 4 * HOUR)
    (payload,) = rig.pusher.to(AN.user_id)
    assert payload["body"] == "PO"
    assert "VLX-PO-2609-0118" not in json.dumps(payload, ensure_ascii=False)


# ------------------------------------------------------- what a push says --

# Every stage `owed` can produce, per follow-up, and who it may go to.
_STAGES: tuple[tuple[Followup, Stage, tuple[Audience, ...]], ...] = (
    (Followup.YOUR_TURN, Stage.NOTIFY, ("pic",)),
    (Followup.YOUR_TURN, Stage.NOTIFY, ("head",)),
    (Followup.ORDER_UNCONFIRMED, Stage.REMIND, ("pic",)),
    (Followup.ORDER_UNCONFIRMED, Stage.ESCALATE, ("head",)),
    (Followup.QUOTE_WAITING_DESIGN, Stage.REMIND, ("pic",)),
    (Followup.QUOTE_DEADLINE, Stage.WARN, ("pic",)),
    (Followup.WAITING_CUSTOMER, Stage.REMIND, ("pic",)),
    (Followup.WAITING_PC, Stage.REMIND, ("pic",)),
    (Followup.IMPLIED_ACCEPTANCE, Stage.NOTIFY, ("pic",)),
    (Followup.WAITING_DESIGN_CODE, Stage.REMIND, ("pic",)),
    (Followup.WAITING_QUOTE, Stage.REMIND, ("pic",)),
)
T0 = datetime(2026, 9, 21, 1, 12, tzinfo=UTC)


def _due(followup: Followup, stage: Stage, notify: tuple[Audience, ...], *, ref: str) -> Due:
    kind = (
        CaseKind.QUOTE
        if followup in {Followup.QUOTE_WAITING_DESIGN, Followup.QUOTE_DEADLINE}
        else CaseKind.ORDER
    )
    case = WaitingCase(
        kind=kind,
        case_id=uuid.UUID(int=7),
        status="in_review",
        reference=ref,
        customer_code=CUSTOMER,
        received_at=T0,
        status_since=T0,
        assigned_to=uuid.UUID(int=1),
        due=date(2026, 9, 30),
    )
    return Due(case, followup, stage, T0, notify)


def test_every_followup_has_its_push() -> None:
    assert {f for f, _, _ in _STAGES} == set(Followup)


@pytest.mark.parametrize(("followup", "stage", "notify"), _STAGES)
@pytest.mark.parametrize("case_number", [True, False])
def test_no_push_carries_a_price_an_amount_or_the_customers_text(
    followup: Followup, stage: Stage, notify: tuple[Audience, ...], case_number: bool
) -> None:
    """Acceptance 2, over every push kind: five fields, the kind of work in
    words and the number at most. A reference that is the customer's words
    (a price written where the number should be) never leaves; neither does
    the customer's code."""
    for ref, shown in (("PO-26/0457", True), ("Giá 12.500.000 đ cho khách", False)):
        payload = push_notice(
            platform_reminder_copy().push,
            [_due(followup, stage, notify, ref=ref)],
            case_number=case_number,
        )
        data = payload.payload()
        assert set(data) == {"title", "body", "url", "count", "tag"}
        text = json.dumps(data, ensure_ascii=False)
        assert CUSTOMER not in text
        assert "12.500.000" not in text and "Giá" not in text
        assert (ref in text) == (shown and case_number)
        assert data["url"] == item_link(
            CaseKind.QUOTE if "Báo giá" in str(data["body"]) else CaseKind.ORDER,
            uuid.UUID(int=7),
        )


async def test_a_reminder_another_worker_recorded_rings_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two workers read before either records: both deliver (the inbox keeps
    one), only the one whose record lands pushes."""
    rig = await _rig()
    await rig.tick(rig.received + 4 * HOUR)

    async def nothing_sent(self: object, keys: object) -> frozenset[object]:
        return frozenset()

    monkeypatch.setattr(_Followups, "already_sent", nothing_sent)
    await rig.tick(rig.received + 4 * HOUR + timedelta(minutes=1))
    assert len(rig.pusher.to(AN.user_id)) == 1
