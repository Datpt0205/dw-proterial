"""The worker's `sales_followups` lane over the in-memory world (ticket 42).

M01 opens an order assigned to An (PIC), received Monday 21 September 2026
at 08:12 local; Giang is the head (`sales.case.assign`). The lane reads the
tenant's resolved policy through the rule book, so a tenant version changes
what it does with no deploy. The integration suite
(`test_sales_followups_db.py`) repeats the record and RLS on PostgreSQL.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import system_actor
from dw_sales.adapters.policy_files import rule_book
from dw_sales.application.followups import (
    BRIEF,
    SALES_FOLLOWUPS_LANE,
    FollowupKey,
    FollowupLane,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import SalesFollowups
from dw_sales.evals.graders import AN, CALLERS, DIEU, GIANG
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world
from dw_sales.evals.world import Directory as Holders

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class Call:
    context: AccessContext
    recipients: tuple[uuid.UUID, ...]
    source_key: str
    title: str
    body: str
    link: str | None


@dataclass
class Sender:
    """`NotificationSenderPort` keeping every call, deduplicating nothing: a
    second call for one reminder is visible here."""

    calls: list[Call] = field(default_factory=list)

    async def deliver(
        self,
        context: AccessContext,
        *,
        recipients: Sequence[uuid.UUID],
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None:
        self.calls.append(Call(context, tuple(recipients), source_key, title, body, link))

    def briefs(self) -> list[Call]:
        return [c for c in self.calls if f":{BRIEF}:" in c.source_key]


@dataclass
class Rig:
    world: World
    lane: FollowupLane
    sender: Sender
    clock: FixedClock
    order_id: uuid.UUID
    received: datetime

    async def tick(self, at: datetime, scope: SalesScope = ALPHA) -> tuple[str, ...]:
        self.clock.advance_to(at)
        return (await self.lane.tick(scope)).sent

    def records(self, scope: SalesScope = ALPHA) -> set[FollowupKey]:
        return set(self.world.store.state(scope).followups)


def _platform(world: World) -> SalesFollowups:
    return world.policies.followups


def _tenant_version(world: World, version: str, **sections: dict[str, Any]) -> None:
    """A tenant version of `sales_followups` in force for ALPHA, as if two
    people proposed and approved it (`/sales/rules`)."""
    document = _platform(world).model_dump(mode="json")
    document["policy_version"] = version
    for name, values in sections.items():
        document[name] = {**document[name], **values}
    world.store.rule_versions.seed_approved(
        ALPHA.tenant_id.value, SalesFollowups.model_validate(document)
    )


async def _rig(*, brief: bool = False, **sections: dict[str, Any]) -> Rig:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    seen = await world.process_each(AN, ["M01"])
    order_id = seen["M01"][0].case_id
    assert order_id is not None
    if not brief:
        sections = {"morning_brief": {"enabled": False}, **sections}
    if sections:
        _tenant_version(world, "1.0.1", **sections)
    sender = Sender()
    clock = FixedClock(world.order(order_id).received_at)
    lane = FollowupLane(
        uow=world.store,
        policies=rule_book(world.policies, world.store.rule_versions),
        holders=Holders(CALLERS),
        notifications=sender,
        clock=clock,
        ids=Uuid4Generator(),
    )
    return Rig(world, lane, sender, clock, order_id, world.order(order_id).received_at)


# ------------------------------------------------------------- reminders --


async def test_the_pic_is_reminded_once_four_hours_after_the_po_arrived() -> None:
    rig = await _rig()
    assert await rig.tick(rig.received + 4 * HOUR - MINUTE) == ()
    sent = await rig.tick(rig.received + 4 * HOUR)
    assert len(sent) == 1
    (call,) = rig.sender.calls
    assert call.recipients == (AN.user_id,)
    assert call.link == f"/sales/orders/{rig.order_id}"
    assert call.title == "Nhắc: PO VLX-PO-2609-0118 chưa xác nhận"
    assert "đã hơn 4 giờ" in call.body
    # The lane delivers as itself, in the case's tenant and workspace.
    assert call.context.principal_id == system_actor(SALES_FOLLOWUPS_LANE).value
    assert (call.context.tenant_id, call.context.workspace_id) == (
        ALPHA.tenant_id.value,
        ALPHA.workspace_id.value,
    )
    assert call.context.scopes == frozenset()


async def test_a_reminder_is_delivered_at_most_once_however_many_ticks() -> None:
    rig = await _rig()
    await rig.tick(rig.received + 4 * HOUR)
    await rig.tick(rig.received + 4 * HOUR + 5 * MINUTE)
    await rig.tick(rig.received + 5 * HOUR)
    assert len(rig.sender.calls) == 1
    assert {(k.followup, k.stage) for k in rig.records()} == {("order_unconfirmed", "remind")}


async def test_a_lost_record_delivers_again_under_the_same_key() -> None:
    """Delivered, then the record lost (a crash in between): the next tick
    sends again, under the same source key, which the inbox ignores for a
    recipient who has it."""
    rig = await _rig()
    await rig.tick(rig.received + 4 * HOUR)
    rig.world.store.state(ALPHA).followups.clear()
    await rig.tick(rig.received + 4 * HOUR + 5 * MINUTE)
    first, second = rig.sender.calls
    assert first.source_key == second.source_key


async def test_a_reassigned_case_does_not_remind_its_new_pic_of_the_same_stage() -> None:
    rig = await _rig()
    await rig.tick(rig.received + 4 * HOUR)
    case = rig.world.order(rig.order_id)
    await rig.world.services.assignment.reassign(
        GIANG.context(),
        CaseKind.ORDER,
        rig.order_id,
        assignee=DIEU.user_id,
        case_version=case.case_version,
    )
    await rig.tick(rig.received + 5 * HOUR)
    assert [c.recipients for c in rig.sender.calls] == [(AN.user_id,)]


async def test_a_day_unconfirmed_tells_the_head() -> None:
    rig = await _rig()
    await rig.tick(rig.received + 4 * HOUR)
    # Tuesday 08:12: inside working hours.
    await rig.tick(rig.received + 24 * HOUR)
    escalated = rig.sender.calls[-1]
    assert escalated.recipients == (GIANG.user_id,)
    assert escalated.title == "PO VLX-PO-2609-0118 quá 24 giờ chưa xác nhận"


async def test_quiet_hours_defer_a_reminder_and_never_drop_it() -> None:
    # Owed at 12:12; the first tick is at 18:00, after work.
    rig = await _rig()
    evening = rig.received.replace(hour=18, minute=0)
    rig.clock.advance_to(evening)
    deferred = await rig.lane.tick(ALPHA)
    assert deferred.sent == () and deferred.deferred == 1
    assert rig.records() == set()
    # Next morning at 08:00 it goes.
    morning = (rig.received + 24 * HOUR).replace(hour=8, minute=0)
    assert len(await rig.tick(morning)) == 1
    assert rig.sender.calls[0].recipients == (AN.user_id,)


async def test_sunday_is_no_working_day() -> None:
    rig = await _rig()
    sunday = rig.received + 6 * 24 * HOUR  # Sunday 27 September, 08:12
    assert sunday.weekday() == 6
    assert await rig.tick(sunday.replace(hour=10)) == ()


async def test_a_switched_off_followup_sends_nothing() -> None:
    rig = await _rig(order_unconfirmed={"enabled": False})
    assert await rig.tick(rig.received + 30 * HOUR) == ()


async def test_a_tenant_version_changes_the_timing_without_a_deploy() -> None:
    rig = await _rig(
        order_unconfirmed={
            "remind": {"after_hours": 6, "notify": ["pic", "head"]},
            "escalate": {"after_hours": 48, "notify": ["head"]},
        }
    )
    assert await rig.tick(rig.received + 4 * HOUR) == ()
    await rig.tick(rig.received + 6 * HOUR)
    assert rig.sender.calls[0].recipients == (AN.user_id, GIANG.user_id)
    assert "đã hơn 6 giờ" in rig.sender.calls[0].body


async def test_a_paused_dw1_reminds_nobody() -> None:
    rig = await _rig()
    await rig.world.services.worker.pause(AN.context(), reason="Kiểm tra")
    rig.clock.advance_to(rig.received + 4 * HOUR)
    assert (await rig.lane.tick(ALPHA)).stopped == "paused"
    assert rig.sender.calls == []


async def test_the_lane_audits_as_itself_naming_no_person() -> None:
    rig = await _rig()
    await rig.tick(rig.received + 4 * HOUR)
    (event,) = [e for e in rig.world.audit() if e.action == "sales.followup.sent"]
    assert event.actor_id == system_actor(SALES_FOLLOWUPS_LANE)
    assert event.details["actor"] == "system:sales_followups"
    assert event.resource_id == str(rig.order_id)
    assert event.details["recipients"] == 1
    assert str(AN.user_id) not in str(event.details)


# ---------------------------------------------------------------- tenants --


async def test_another_tenants_cases_never_reach_a_person() -> None:
    """Alpha's order is owed; Beta's tick reads Beta's workspace only, and
    tells nobody anything."""
    rig = await _rig()
    rig.clock.advance_to(rig.received + 30 * HOUR)
    tick = await rig.lane.tick(BETA)
    assert tick.sent == ()
    assert rig.sender.calls == []
    # Beta's own day is done with nobody to tell; nothing of Alpha's is there.
    assert {k.followup for k in rig.records(BETA)} <= {BRIEF}


async def test_a_delivery_is_bound_to_the_ticks_own_tenant() -> None:
    rig = await _rig()
    await rig.tick(rig.received + 4 * HOUR)
    for call in rig.sender.calls:
        assert call.context.tenant_id == ALPHA.tenant_id.value
        assert call.context.workspace_id == ALPHA.workspace_id.value


# ------------------------------------------------------------------ brief --


def _no_amounts(world: World, order_id: uuid.UUID, text: str) -> None:
    case = world.order(order_id)
    amounts: set[Decimal] = set()
    for line in case.document.lines:
        amounts |= {line.unit_price, line.amount}
    for value in amounts:
        if value >= 100:  # a two-digit count is a count
            assert f"{value}" not in text and f"{value:,}" not in text, value
    assert case.document.header.currency not in text


async def test_the_morning_brief_counts_and_never_names_an_amount() -> None:
    rig = await _rig(brief=True, order_unconfirmed={"enabled": False})
    # Tuesday 22 September 07:30 local: the order came in Monday morning,
    # after Monday's brief.
    tuesday = (rig.received + 24 * HOUR).replace(hour=7, minute=30)
    await rig.tick(tuesday)
    briefs = {c.recipients: c for c in rig.sender.briefs()}
    head, pic = briefs[(GIANG.user_id,)], briefs[(AN.user_id,)]
    assert head.title == "Tóm tắt sáng 22/09: 1 hồ sơ mới (bộ phận Sales)"
    assert pic.title == "Tóm tắt sáng 22/09: 1 hồ sơ mới (hồ sơ của bạn)"
    assert "1 hồ sơ mới (1 đơn hàng, 0 báo giá); đang chờ: Sales 1." in head.body
    assert "Đang chờ: Sales 1." in head.body
    assert head.link == pic.link == "/sales"
    # Diệu holds no case: nothing to brief her on.
    assert (DIEU.user_id,) not in briefs
    for call in rig.sender.calls:
        _no_amounts(rig.world, rig.order_id, call.title + call.body)


async def test_the_brief_goes_once_a_day() -> None:
    rig = await _rig(brief=True, order_unconfirmed={"enabled": False})
    tuesday = (rig.received + 24 * HOUR).replace(hour=7, minute=30)
    await rig.tick(tuesday)
    first = len(rig.sender.briefs())
    await rig.tick(tuesday + 5 * MINUTE)
    await rig.tick(tuesday + 3 * HOUR)
    assert len(rig.sender.briefs()) == first
    await rig.tick(tuesday + 24 * HOUR)
    assert len(rig.sender.briefs()) == 2 * first
    days = sorted(k.subject for k in rig.records() if k.followup == BRIEF)
    assert days == ["2026-09-22", "2026-09-23"]


async def test_the_brief_waits_for_its_time_and_a_tenant_may_move_it() -> None:
    rig = await _rig(
        brief=True,
        order_unconfirmed={"enabled": False},
        morning_brief={"at": "09:00", "enabled": True},
    )
    tuesday = (rig.received + 24 * HOUR).replace(hour=8, minute=59)
    await rig.tick(tuesday)
    assert rig.sender.briefs() == []
    await rig.tick(tuesday + MINUTE)
    assert rig.sender.briefs() != []


async def test_old_brief_records_are_forgotten() -> None:
    rig = await _rig(brief=True, order_unconfirmed={"enabled": False})
    tuesday = (rig.received + 24 * HOUR).replace(hour=7, minute=30)
    await rig.tick(tuesday)
    # Monday 2 November: Tuesday's record is past 35 days.
    await rig.tick(tuesday + 41 * 24 * HOUR)
    days = sorted(k.subject for k in rig.records() if k.followup == BRIEF)
    assert len(days) == 1
