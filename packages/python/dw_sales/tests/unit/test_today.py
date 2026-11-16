"""One place for a person's day (tickets 47 and 48), over the in-memory world.

The follow-ups lane delivers into the inbox; the feed reads back the brief
of today and the reminders of the last week for the caller alone, and the
caller marks reminders "Đã xử lý", "Không cần" or "Nhắc lại sau". A
customer's term is never hidden. The work list beside it carries each item's
SLA from the same timings the lane reminds and escalates by.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ports import FixedClock
from dw_sales.application.followups import (
    BRIEF,
    BRIEF_STAGE,
    OPENING_PREFIX,
    FollowupKey,
    lane_context,
    parse_source_key,
    source_key,
)
from dw_sales.application.ports import SalesScope
from dw_sales.application.today import REMINDERS, Mark, MarkIn, ReminderMark, rank
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import CUSTOMER_TERM, Followup, SalesFollowups, Stage, sla_of
from dw_sales.evals.graders import AN, CALLERS, DIEU, OUTSIDER
from dw_sales.evals.world import ALPHA, BETA, NOW, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
HOUR = timedelta(hours=1)
CASE = uuid.UUID(int=0xCA5E)


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, OUTSIDER))


async def _tell(
    world: World,
    followup: str,
    stage: str,
    *,
    to: uuid.UUID = AN.user_id,
    scope: SalesScope = ALPHA,
    subject: str = str(CASE),
    since: datetime = NOW,
    body: str = "Mở hồ sơ để xử lý.",
) -> str:
    """What the lane delivers for one stage, under its own key."""
    key = source_key(FollowupKey(followup, stage, subject, since), scope)
    await world.notifications.deliver(
        lane_context(scope),
        recipients=[to],
        source_key=key,
        title=f"{followup} {stage}",
        body=body,
        link=f"/sales/orders/{CASE}",
    )
    return key


async def _ids(world: World, caller_context: object) -> dict[str, uuid.UUID]:
    view = await world.services.today.today(caller_context)  # type: ignore[arg-type]
    return {r.followup: r.notification_id for r in view.reminders}


# ------------------------------------------------------------ the feed --


async def test_the_brief_and_the_reminders_are_one_feed() -> None:
    """Acceptance 2: today's brief opens it, its model-written opening apart
    from code's counts; the reminders follow; "your turn" is the work list's
    and is not repeated here."""
    world = _world()
    today = NOW.astimezone(world.policies.followups.working_hours.zone).date()
    await _tell(
        world,
        BRIEF,
        BRIEF_STAGE,
        subject=today.isoformat(),
        body=f"{OPENING_PREFIX}Xử lý PO quá hạn trước.\n\nĐang chờ: Sales 2.\nQuá hạn: 1.",
    )
    await _tell(world, Followup.ORDER_UNCONFIRMED, Stage.REMIND)
    await _tell(world, Followup.YOUR_TURN, Stage.NOTIFY)
    view = await world.services.today.today(AN.context())
    assert view.brief is not None
    assert view.brief.opening == "Xử lý PO quá hạn trước."
    assert view.brief.counts == ["Đang chờ: Sales 2.", "Quá hạn: 1."]
    assert [r.followup for r in view.reminders] == ["order_unconfirmed"]
    assert view.reminders[0].case_id == CASE


async def test_yesterdays_brief_is_not_todays() -> None:
    world = _world()
    await _tell(world, BRIEF, BRIEF_STAGE, subject=date(2026, 10, 4).isoformat())
    assert (await world.services.today.today(AN.context())).brief is None


async def test_one_persons_feed_and_marks_never_reach_another() -> None:
    """Acceptance 4: Diệu sees none of An's reminders and An's "Không cần"
    hides nothing of Diệu's; another tenant's person reads nothing and may
    mark nothing of An's."""
    world = _world()
    await _tell(world, Followup.WAITING_PC, Stage.REMIND)
    await _tell(world, Followup.WAITING_PC, Stage.REMIND, to=DIEU.user_id, since=NOW - HOUR)
    an = (await world.services.today.today(AN.context())).reminders
    dieu = (await world.services.today.today(DIEU.context())).reminders
    assert len(an) == len(dieu) == 1 and an[0].notification_id != dieu[0].notification_id
    await world.services.today.mark(AN.context(), an[0].notification_id, MarkIn(mark="dismissed"))
    assert (await world.services.today.today(AN.context())).reminders == []
    assert len((await world.services.today.today(DIEU.context())).reminders) == 1
    # Diệu cannot mark An's, nor can another tenant's PIC.
    for caller in (DIEU.context(), OUTSIDER.context(BETA)):
        with pytest.raises(NotFoundError):
            await world.services.today.mark(caller, an[0].notification_id, MarkIn(mark="done"))
    with pytest.raises(NotFoundError):
        await world.services.today.mark(
            OUTSIDER.context(BETA), dieu[0].notification_id, MarkIn(mark="done")
        )
    assert (await world.services.today.today(OUTSIDER.context(BETA))).reminders == []


async def test_another_workspaces_reminders_stay_there() -> None:
    world = _world()
    other = SalesScope(ALPHA.tenant_id, BETA.workspace_id)
    await _tell(world, Followup.WAITING_PC, Stage.REMIND, scope=other)
    assert (await world.services.today.today(AN.context())).reminders == []


async def test_snoozed_comes_back_and_done_stays_done() -> None:
    world = _world()
    await _tell(world, Followup.WAITING_CUSTOMER, Stage.REMIND)
    await _tell(world, Followup.QUOTE_WAITING_DESIGN, Stage.REMIND, since=NOW - HOUR)
    ids = await _ids(world, AN.context())
    today = world.services.today
    await today.mark(AN.context(), ids["waiting_customer"], MarkIn(mark="snoozed", hours=4))
    await today.mark(AN.context(), ids["quote_waiting_design"], MarkIn(mark="done"))
    view = await today.today(AN.context())
    assert view.reminders == [] and view.hidden == 2
    clock = world.notifications.clock  # the world's one clock
    assert isinstance(clock, FixedClock)
    clock.advance_to(NOW + 4 * HOUR + timedelta(minutes=1))
    assert [r.followup for r in (await today.today(AN.context())).reminders] == ["waiting_customer"]


async def test_a_customers_term_is_never_hidden_however_often_dismissed() -> None:
    """Acceptance 1: the service refuses to dismiss or snooze it; "Đã xử
    lý" alone takes it off the list."""
    world = _world()
    for followup in sorted(CUSTOMER_TERM):
        await _tell(world, followup, Stage.WARN)
    ids = await _ids(world, AN.context())
    for followup in CUSTOMER_TERM:
        for mark in (MarkIn(mark="dismissed"), MarkIn(mark="snoozed", hours=1)):
            with pytest.raises(ConflictError):
                await world.services.today.mark(AN.context(), ids[followup], mark)
    view = await world.services.today.today(AN.context())
    assert {r.followup for r in view.reminders} == {f.value for f in CUSTOMER_TERM}
    assert all(r.customer_term for r in view.reminders)


def test_a_term_dismissed_anyway_is_read_as_nothing_and_ranks_first() -> None:
    """The read floor: a mark that exists anyway (written before the rule,
    or by hand) hides no term; the person's frequent "Không cần" sinks a
    kind without dropping it, and a term stays on top."""

    class Notice:
        def __init__(self, n: int, at: datetime) -> None:
            self.id = uuid.UUID(int=n)
            self.source_key = ""
            self.title = self.body = ""
            self.link = None
            self.created_at = at

    term, pc, pc_old, design = (
        Notice(1, NOW - 3 * HOUR),
        Notice(2, NOW),
        Notice(3, NOW - HOUR),
        Notice(4, NOW - 2 * HOUR),
    )
    key = parse_source_key(source_key(FollowupKey("x", "y", "z", NOW), ALPHA))
    assert key is not None
    rows = [
        (pc, key, Followup.WAITING_PC),
        (term, key, Followup.QUOTE_DEADLINE),
        (design, key, Followup.QUOTE_WAITING_DESIGN),
        (pc_old, key, Followup.WAITING_PC),
    ]
    marks = [
        ReminderMark(term.id, Followup.QUOTE_DEADLINE, Mark.DISMISSED, None, NOW),
        ReminderMark(pc_old.id, Followup.WAITING_PC, Mark.DISMISSED, None, NOW),
        ReminderMark(uuid.UUID(int=9), Followup.WAITING_PC, Mark.DISMISSED, None, NOW),
    ]
    shown, hidden = rank(rows, marks, NOW)
    assert [n.id for n, _, _ in shown] == [term.id, design.id, pc.id]
    assert hidden == 1


async def test_marking_needs_the_scope_reading_needs() -> None:
    world = _world()
    await _tell(world, Followup.WAITING_PC, Stage.REMIND)
    (reminder,) = (await world.services.today.today(AN.context())).reminders
    bare = AN.context().model_copy(update={"scopes": frozenset()})
    with pytest.raises(PermissionDeniedError):
        await world.services.today.today(bare)
    with pytest.raises(PermissionDeniedError):
        await world.services.today.mark(bare, reminder.notification_id, MarkIn(mark="done"))


def test_a_snooze_says_for_how_long_and_nothing_else_does() -> None:
    with pytest.raises(ValueError, match="hours"):
        MarkIn(mark="snoozed")
    with pytest.raises(ValueError, match="hours"):
        MarkIn(mark="done", hours=2)
    with pytest.raises(ValueError):
        MarkIn(mark="snoozed", hours=73)


def _migration(revision: str) -> Any:
    path = next((REPO / "db" / "migrations" / "versions").glob(f"{revision}_*.py"))
    spec = importlib.util.spec_from_file_location(f"migration_{revision}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_holds_the_domains_sets() -> None:
    """`ck_reminder_marks_followup` and `ck_reminder_marks_customer_term`
    name exactly `REMINDERS` and `CUSTOMER_TERM`: the table's first list and
    what `57bbf61ae6b8` admitted after it (tickets 06 and 09)."""
    module = _migration("4bcfa82060fc")

    def listed(text: str) -> set[str]:
        return {v.strip().strip("'") for v in text.split(",")}

    admitted = set(_migration("57bbf61ae6b8")._NEW_REMINDERS)
    assert listed(module._REMINDERS) | admitted == {f.value for f in REMINDERS}
    assert listed(module._CUSTOMER_TERM) == {f.value for f in CUSTOMER_TERM}


# ---------------------------------------------------------------- SLA --


def _policy(world: World) -> SalesFollowups:
    return world.policies.followups


def test_an_orders_sla_is_its_reminder_and_its_escalation() -> None:
    policy = _policy(_world())
    received = datetime(2026, 10, 5, 1, 0, tzinfo=UTC)
    sla = sla_of(policy, CaseKind.ORDER, "in_review", received_at=received, due=None)
    assert sla is not None
    assert sla.warn_at == received + 4 * HOUR
    assert sla.due_at == received + 24 * HOUR
    # A confirmed order is late by no rule.
    assert sla_of(policy, CaseKind.ORDER, "confirmed", received_at=received, due=None) is None


def test_a_quotes_sla_is_the_end_of_its_due_day() -> None:
    policy = _policy(_world())
    received = datetime(2026, 10, 5, 1, 0, tzinfo=UTC)
    sla = sla_of(policy, CaseKind.QUOTE, "received", received_at=received, due=date(2026, 10, 9))
    assert sla is not None
    # Midnight after the 9th, giờ Việt Nam; warned 48 hours before.
    assert sla.due_at == datetime(2026, 10, 9, 17, 0, tzinfo=UTC)
    assert sla.warn_at == sla.due_at - 48 * HOUR
    assert sla_of(policy, CaseKind.QUOTE, "received", received_at=received, due=None) is None


async def test_the_work_list_carries_each_items_sla() -> None:
    world = _world()
    seen = await world.process_each(AN, ["M01"])
    order_id = seen["M01"][0].case_id
    assert order_id is not None
    items = (await world.services.overview.my_work(AN.context())).items
    (item,) = [i for i in items if i.id == str(order_id)]
    received = world.order(order_id).received_at
    assert item.sla_warn_at == received + 4 * HOUR
    assert item.sla_due_at == received + 24 * HOUR
