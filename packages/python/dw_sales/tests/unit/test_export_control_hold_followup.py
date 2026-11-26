"""The export-control PIC is told of an NOC/ESF hold (Sales ticket 78).

M03 opens an order with no NOC/ESF on file: it is held on `missing_noc_esf`
until someone holding `sales.compliance.ack` acknowledges it. The hold is a
finding, not a status, so "your turn" never saw it, and the PIC is nobody's
assignee. The follow-ups lane tells them at once: the holders of the scope
that acknowledges it who also prepare orders (`_decide` asks both), and,
while nobody holds both, the heads, told that nobody may.

Over the in-memory world, as `test_followups_lane.py`; the store's SQL is
`test_followup_waits_db.py`'s.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pytest

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_sales.adapters.policy_files import rule_book
from dw_sales.application.access import SalesScopes
from dw_sales.application.followups import FollowupLane
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import Due, Followup, SalesFollowups, Stage, WaitingCase
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN, CALLERS, DIEU, GIANG, KHOA
from dw_sales.evals.world import ALPHA, Caller, SampleSet, World, open_world
from dw_sales.evals.world import Directory as Holders

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
MINUTE = timedelta(minutes=1)
HELD = "M03"
# Holds the scope that acknowledges, and prepares no order: may not decide it.
ACK_ONLY = Caller(
    uuid.UUID(int=0xAC),
    "Trần Thị Kiểm",
    "kiem.tran@alpha.local",
    frozenset({SalesScopes.CASE_READ, SalesScopes.COMPLIANCE_ACK}),
)


@dataclass
class Sender:
    calls: list[tuple[tuple[uuid.UUID, ...], str, str, str]] = field(default_factory=list)

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
        self.calls.append((tuple(recipients), source_key, title, body))

    def holds(self) -> list[tuple[tuple[uuid.UUID, ...], str, str, str]]:
        return [c for c in self.calls if ":export_control_hold:" in c[1]]


@dataclass
class Rig:
    world: World
    lane: FollowupLane
    sender: Sender
    clock: FixedClock
    order: OrderCase

    async def tick(self) -> None:
        self.clock.advance_to(self.world.store.clock.now() + 5 * MINUTE)
        await self.lane.tick(ALPHA)


def _quiet(world: World, **sections: dict[str, object]) -> None:
    """Only the hold speaks: the brief and "your turn" off, as a tenant
    version in force for ALPHA."""
    document = world.policies.followups.model_dump(mode="json")
    document["policy_version"] = "1.0.1"
    quiet: dict[str, dict[str, object]] = {
        "morning_brief": {"enabled": False},
        "your_turn": {"enabled": False},
        **sections,
    }
    for name, values in quiet.items():
        document[name] = {**document[name], **values}
    world.store.rule_versions.seed_approved(
        ALPHA.tenant_id.value, SalesFollowups.model_validate(document)
    )


async def _rig(
    holders: tuple[Caller, ...] = CALLERS,
    *,
    assignee: Caller | None = DIEU,
    **sections: dict[str, object],
) -> Rig:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    ((_, case),) = (await world.process_each(AN, [HELD])).values()
    assert isinstance(case, OrderCase) and case.awaits_export_control, case
    if assignee is not None and assignee != AN:
        await world.services.assignment.reassign(
            GIANG.context(),
            CaseKind.ORDER,
            case.case_id,
            assignee=assignee.user_id,
            case_version=case.case_version,
        )
    _quiet(world, **sections)
    sender = Sender()
    clock = FixedClock(world.store.clock.now())
    lane = FollowupLane(
        uow=world.store,
        policies=rule_book(world.policies, world.store.rule_versions),
        holders=Holders(holders),
        notifications=sender,
        clock=clock,
        ids=Uuid4Generator(),
    )
    return Rig(world, lane, sender, clock, world.order(case.case_id))


async def test_the_hold_tells_the_export_control_pic_and_not_the_assignee_or_head() -> None:
    """An holds `sales.compliance.ack` and prepares orders; Diệu, whose order
    it is, and Giang, the head, hold only the second. An alone is told, in
    the hold's words, once however many ticks."""
    rig = await _rig()
    await rig.tick()
    [(recipients, _, title, body)] = rig.sender.holds()
    assert recipients == (AN.user_id,)
    assert title == f"PO {rig.order.header.po_no} chờ xác nhận NOC/ESF"
    assert "người phụ trách kiểm soát xuất khẩu" in body and rig.order.customer_code in body

    await rig.tick()
    assert len(rig.sender.holds()) == 1


async def test_an_export_control_pic_who_is_the_assignee_is_told_once() -> None:
    rig = await _rig(assignee=AN)
    await rig.tick()
    [(recipients, *_)] = rig.sender.holds()
    assert recipients == (AN.user_id,)


async def test_a_holder_of_the_ack_scope_alone_is_never_told() -> None:
    """The acknowledgement asks `sales.order.prepare` too: someone who holds
    only `sales.compliance.ack` could not decide it, so is not told (and is
    not shown the PO's number). With nobody holding both, the head is told
    that nobody may, in those words, and nobody who cross-checks is."""
    rig = await _rig((ACK_ONLY, DIEU, GIANG, KHOA))
    await rig.tick()
    [(recipients, _, title, body)] = rig.sender.holds()
    assert recipients == (GIANG.user_id,)
    assert "chưa ai có quyền xác nhận" in title
    # Ticket 78 review: the set alone is still nobody, so the words ask for
    # both grants the acknowledgement needs, not the set alone.
    assert "PIC kiểm soát xuất khẩu" in body
    assert "Sales phụ trách (PIC)" in body


async def test_the_pic_granted_after_the_heads_stood_in_is_still_told_once() -> None:
    """Ticket 78 review: the heads' notice is recorded under its own stage,
    so the revision is still owed to the export-control PIC. The heads are
    told once while nobody may; then An, granted both, is told once; then
    nobody again."""
    rig = await _rig((ACK_ONLY, DIEU, GIANG, KHOA))
    await rig.tick()
    await rig.tick()
    [(heads, *_)] = rig.sender.holds()
    assert heads == (GIANG.user_id,)

    rig.lane = dataclasses.replace(rig.lane, holders=Holders((ACK_ONLY, AN, DIEU, GIANG, KHOA)))
    await rig.tick()
    await rig.tick()
    told = [recipients for recipients, *_ in rig.sender.holds()]
    assert told == [(GIANG.user_id,), (AN.user_id,)]
    assert "chưa ai" not in rig.sender.holds()[1][2]


async def test_with_an_export_control_pic_the_head_is_not_told() -> None:
    rig = await _rig((ACK_ONLY, AN, DIEU, GIANG))
    await rig.tick()
    [(recipients, *_)] = rig.sender.holds()
    assert recipients == (AN.user_id,)


async def test_a_tenant_that_switched_the_hold_off_is_told_nothing() -> None:
    rig = await _rig(export_control_hold={"enabled": False})
    await rig.tick()
    assert rig.sender.holds() == []


async def test_the_heads_stand_in_alone_in_a_status_that_waits_on_a_cross_check() -> None:
    """An order held while it waits on its cross-check: the heads stand in
    for the export-control PIC, never with the cross-check's holders added,
    who can do nothing about the hold."""
    rig = await _rig((ACK_ONLY, DIEU, GIANG, KHOA))
    case = WaitingCase(
        kind=CaseKind.ORDER,
        case_id=rig.order.case_id,
        status="uploaded_to_bravo",
        reference="PO-1",
        customer_code="VLX",
        received_at=rig.order.received_at,
        status_since=rig.order.received_at,
        assigned_to=DIEU.user_id,
        due=None,
        export_held=True,
    )
    due = Due(
        case, Followup.EXPORT_CONTROL_HOLD, Stage.NOTIFY, case.received_at, ("export_control",)
    )
    assert await rig.lane._audience(ALPHA, due) == ([GIANG.user_id], True)


async def test_an_unassigned_case_still_tells_the_pic_audience_to_the_heads() -> None:
    """The dispatch keeps what `pic` did before it: nobody assigned, the
    heads (and a checker where the case waits on one)."""
    rig = await _rig()
    case = WaitingCase(
        kind=CaseKind.ORDER,
        case_id=rig.order.case_id,
        status="in_review",
        reference="PO-1",
        customer_code="VLX",
        received_at=rig.order.received_at,
        status_since=rig.order.received_at,
        assigned_to=None,
        due=None,
        export_held=True,
    )
    pic = Due(case, Followup.ORDER_UNCONFIRMED, Stage.REMIND, case.received_at, ("pic",))
    assert await rig.lane._audience(ALPHA, pic) == ([GIANG.user_id], False)
    hold = Due(
        case, Followup.EXPORT_CONTROL_HOLD, Stage.NOTIFY, case.received_at, ("export_control",)
    )
    assert await rig.lane._audience(ALPHA, hold) == ([AN.user_id], False)
