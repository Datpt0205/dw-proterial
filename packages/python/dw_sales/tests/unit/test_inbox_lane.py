"""DW1's mailbox lane, in one process (ticket 16).

The real Sales services, runner and DW1 graph over in-memory stores
(`open_world`), with the lane built over them as the worker builds it
(`InboxLane`). The platform's half, resolving DW1's service account from its
membership, is tested against PostgreSQL in `dw_platform`'s
`test_service_access.py` and in the worker's `test_sales_inbox_lane_db.py`;
here it is a fake that keeps the same contract (the ceiling cut, no role,
nobody outside the account's own workspace).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.identity import MembershipAccess
from dw_platform.domain.audit import system_actor
from dw_sales.application.inbox_lane import (
    LANE_CEILING,
    RETRY_FIRST,
    SALES_INBOX_LANE,
    InboxLane,
    dw1_subject,
)
from dw_sales.application.ports import SalesScope
from dw_sales.application.views import MessageDispositionView
from dw_sales.evals.graders import AN, CALLERS, GIANG
from dw_sales.evals.world import ALPHA, BETA, NOW, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
# DW1's service account in tenant alpha's workspace: a member, no email.
DW1_ACCOUNT = uuid.UUID(int=0xD1D1)
LANE_ACTION = "sales.message.processed_by_lane"


def _world(**options: object) -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS, **options)  # type: ignore[arg-type]


type Where = tuple[uuid.UUID, uuid.UUID]


def _where(scope: SalesScope) -> Where:
    return scope.tenant_id.value, scope.workspace_id.value


@dataclass
class Accounts:
    """`ServiceAccessPort` as the platform answers it
    (`SqlMembershipLookup.find_service_access`): the account's own membership,
    its scopes cut to the ceiling and no role; nobody anywhere else.

    ``holds`` is what the membership's roles give: the role `sales_dw1`, or
    more if someone added a role to the account by hand.
    """

    members: dict[tuple[str, Where], uuid.UUID] = field(
        default_factory=lambda: {(dw1_subject(ALPHA.tenant_id.value), _where(ALPHA)): DW1_ACCOUNT}
    )
    holds: frozenset[str] = frozenset({"sales.inbox.process"})
    ceilings: list[frozenset[str]] = field(default_factory=list)

    async def find_service_access(
        self,
        subject: str,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        ceiling: frozenset[str],
    ) -> MembershipAccess | None:
        self.ceilings.append(ceiling)
        user_id = self.members.get((subject, (tenant_id, workspace_id)))
        if user_id is None:
            return None
        return _access((tenant_id, workspace_id), user_id, self.holds & ceiling)


def _access(where: Where, user_id: uuid.UUID, scopes: frozenset[str]) -> MembershipAccess:
    return MembershipAccess(
        tenant_id=where[0],
        workspace_id=where[1],
        principal_id=user_id,
        roles=frozenset(),
        scopes=scopes,
        groups=frozenset(),
        clearance="internal",
        plan_id="professional",
        feature_flags=frozenset(),
    )


def _lane(
    world: World, accounts: Accounts | None = None, clock: FixedClock | None = None
) -> InboxLane:
    return InboxLane(
        world.store,
        world.inbox,
        world.services.dw1,
        accounts or Accounts(),
        clock or FixedClock(NOW),
        Uuid4Generator(),
    )


async def _mailbox(world: World, scope: SalesScope = ALPHA) -> list[str]:
    return [m.message_id for m in await world.inbox.list_messages(scope)]


def _dispositions(world: World, scope: SalesScope = ALPHA) -> dict[str, str]:
    return {k: v.disposition.kind.value for k, v in world.store.state(scope).messages.items()}


def _runs(world: World) -> list[tuple[uuid.UUID, str | None]]:
    """Every DW1 run, as (who it ran as, the message it was given)."""
    return [
        (run.context.actor_id, run.input["task"]["message_id"])
        for run in world.runtime.runs.rows.values()
    ]


# ------------------------------------------- 2. every new message, once --


async def test_each_new_message_is_processed_oldest_first_in_a_run_of_its_own() -> None:
    world = _world()
    mailbox = await _mailbox(world)

    tick = await _lane(world).tick(ALPHA)

    assert tick.processed == tuple(mailbox)
    assert tick.stopped is None
    assert set(_dispositions(world)) == set(mailbox)
    assert "not_yet_processed" not in _dispositions(world).values()
    # One run per message, in the mailbox's order, each as DW1's account.
    assert _runs(world) == [(DW1_ACCOUNT, message_id) for message_id in mailbox]


async def test_a_second_tick_finds_nothing_and_spends_no_run() -> None:
    world = _world()
    lane = _lane(world)
    await lane.tick(ALPHA)
    runs = len(world.runtime.runs.rows)

    tick = await lane.tick(ALPHA)

    assert tick.processed == ()
    assert len(world.runtime.runs.rows) == runs


async def test_a_message_a_person_processed_is_not_processed_again() -> None:
    """Acceptance 7: one already on a case and one routed to Sales alike."""
    world = _world()
    seen = await world.process_each(AN, ["M01", "M11"])
    assert seen["M01"][0].kind == "case_created"
    assert seen["M11"][0].kind == "routed_to_sales"
    before = dict(world.store.state(ALPHA).messages)

    tick = await _lane(world).tick(ALPHA)

    assert "M01" not in tick.processed and "M11" not in tick.processed
    for message_id in ("M01", "M11"):
        assert world.store.state(ALPHA).messages[message_id] == before[message_id]
        assert [m for _, m in _runs(world)].count(message_id) == 1


@dataclass
class PersonFirst:
    """`Dw1Runs.process` with a person pressing "DW xử lý" on one message
    between the lane's read of the mailbox and its own run on that message."""

    world: World
    message_id: str

    async def process(self, context: AccessContext, message_id: str) -> MessageDispositionView:
        if message_id == self.message_id:
            await self.world.services.dw1.process(AN.context(), message_id)
        return await self.world.services.dw1.process(context, message_id)


async def test_a_person_getting_there_first_meanwhile_keeps_the_message_on_one_case() -> None:
    """The idempotency key holds across the race: the lane's run is refused,
    the message stays on the one case the person's run opened."""
    world = _world()
    lane = _lane(world)
    lane.runs = PersonFirst(world, "M01")

    tick = await lane.tick(ALPHA)

    assert "M01" not in tick.processed
    m01 = world.store.state(ALPHA).messages["M01"].disposition
    assert m01.kind.value == "case_created"
    assert [s.case.message_id for s in world.store.state(ALPHA).orders.values()].count("M01") == 1
    # The person's run, and the lane's refused one.
    assert [actor for actor, m in _runs(world) if m == "M01"] == [AN.user_id, DW1_ACCOUNT]


@dataclass
class PersonMeanwhile:
    """A person presses "DW xử lý" on a later message while the lane's run
    works on an earlier one of the same tick."""

    world: World
    during: str
    pressed: str

    async def process(self, context: AccessContext, message_id: str) -> MessageDispositionView:
        if message_id == self.during:
            await self.world.process_each(AN, [self.pressed])
        return await self.world.services.dw1.process(context, message_id)


async def test_a_message_a_person_routes_during_the_tick_is_not_processed_again() -> None:
    """A routed message may be processed again, so the log's key would let the
    lane's run through: the lane reads the message again before its run."""
    world = _world()
    mailbox = await _mailbox(world)
    assert mailbox.index("M11") > 0
    lane = _lane(world)
    lane.runs = PersonMeanwhile(world, during=mailbox[0], pressed="M11")

    tick = await lane.tick(ALPHA)

    assert "M11" not in tick.processed
    assert [actor for actor, m in _runs(world) if m == "M11"] == [AN.user_id]
    assert not [e for e in world.audit() if e.action == LANE_ACTION and e.resource_id == "M11"]


# ------------------------------------------- 3. it audits as itself --


async def test_the_lane_audits_as_itself_naming_the_account_it_acted_under() -> None:
    world = _world()

    tick = await _lane(world).tick(ALPHA)

    audit = world.audit()
    lane_rows = [e for e in audit if e.action == LANE_ACTION]
    assert [e.resource_id for e in lane_rows] == list(tick.processed)
    for event in lane_rows:
        assert event.actor_id == system_actor(SALES_INBOX_LANE)
        assert event.details["actor"] == "system:sales_inbox"
        assert event.details["account_id"] == str(DW1_ACCOUNT)
    # Everything else the processing wrote names the account, never a person.
    people = {caller.user_id for caller in CALLERS}
    assert not [e for e in audit if e.actor_id.value in people]
    assert {e.actor_id.value for e in audit if e.action != LANE_ACTION} == {DW1_ACCOUNT}


# ----------------------------------- 4. sales.inbox.process, and only it --


async def test_the_lane_asks_for_the_inbox_scope_only() -> None:
    accounts = Accounts()
    await _lane(_world(), accounts).tick(ALPHA)

    assert accounts.ceilings == [frozenset({"sales.inbox.process"})] == [LANE_CEILING]


async def test_a_role_added_to_the_account_by_hand_widens_nothing_the_lane_carries() -> None:
    """The account given `sales_head` by hand: the runs still carry the
    inbox scope alone, so nothing the lane starts can prepare, cross-check,
    price or approve."""
    world = _world()
    accounts = Accounts(holds=GIANG.scopes)

    await _lane(world, accounts).tick(ALPHA)

    scopes = {run.context.scopes for run in world.runtime.runs.rows.values()}
    roles = {run.context.roles for run in world.runtime.runs.rows.values()}
    assert scopes == {frozenset({"sales.inbox.process"})}
    assert roles == {frozenset()}


async def test_an_account_without_the_inbox_scope_processes_nothing_and_spends_no_run() -> None:
    world = _world()

    tick = await _lane(world, Accounts(holds=frozenset())).tick(ALPHA)

    assert (tick.processed, tick.stopped) == ((), "not_permitted")
    assert world.runtime.runs.rows == {}
    assert _dispositions(world) == {}


async def test_a_workspace_without_dw1s_account_is_left_alone() -> None:
    world = _world()

    tick = await _lane(world, Accounts(members={})).tick(ALPHA)

    assert (tick.processed, tick.stopped) == ((), "no_account")
    assert world.runtime.runs.rows == {}


# --------------------------------------- 5. the plan's runs for the day --


class _ThreeRunsADay:
    def runs_per_day(self, plan_id: str) -> int | None:
        return 3

    def spend_usd_per_day(self, plan_id: str) -> Decimal | None:
        return None


async def test_over_the_plans_runs_the_rest_stays_unprocessed_and_visible() -> None:
    world = _world(allowance=_ThreeRunsADay())
    mailbox = await _mailbox(world)
    lane = _lane(world)

    first = await lane.tick(ALPHA)
    second = await lane.tick(ALPHA)

    assert (first.processed, first.stopped) == (tuple(mailbox[:3]), "quota")
    assert (second.processed, second.stopped) == ((), "quota")
    assert len(world.runtime.runs.rows) == 3
    # Visibly: the inbox shows the rest as "Chưa xử lý".
    shown = {
        m.message_id: m.disposition.kind for m in await world.services.inbox.messages(AN.context())
    }
    assert [m for m in mailbox if shown[m] == "not_yet_processed"] == mailbox[3:]


# ------------------------------------------------ 6. pausing stops it --


async def test_a_paused_workspace_is_skipped_until_the_head_resumes_dw1() -> None:
    world = _world()
    lane = _lane(world)
    await world.services.worker.pause(AN.context(), "Kiểm tra lại convert list")

    paused = await lane.tick(ALPHA)

    assert (paused.processed, paused.stopped) == ((), "paused")
    assert world.runtime.runs.rows == {}
    assert _dispositions(world) == {}

    await world.services.worker.resume(GIANG.context(), "Đã kiểm tra xong")
    resumed = await lane.tick(ALPHA)

    assert resumed.processed == tuple(await _mailbox(world))


@dataclass
class PausedAfter:
    """A PIC pauses DW1 while the lane is between two messages."""

    world: World
    after: str

    async def process(self, context: AccessContext, message_id: str) -> MessageDispositionView:
        view = await self.world.services.dw1.process(context, message_id)
        if message_id == self.after:
            await self.world.services.worker.pause(AN.context(), None)
        return view


async def test_a_pause_in_the_middle_of_a_tick_stops_it_at_the_next_message() -> None:
    world = _world()
    lane = _lane(world)
    mailbox = await _mailbox(world)
    lane.runs = PausedAfter(world, mailbox[1])

    tick = await lane.tick(ALPHA)

    assert (tick.processed, tick.stopped) == (tuple(mailbox[:2]), "paused")
    assert set(_dispositions(world)) == set(mailbox[:2])
    # Stopped before the third message's run, not by it: no run spent on it.
    assert [m for _, m in _runs(world)] == mailbox[:2]


# ------------------------------------------ 7. never across workspaces --


async def test_workspace_bs_tick_reads_bs_mailbox_only_and_writes_nothing_in_a() -> None:
    world = _world()
    accounts = Accounts(
        members={(dw1_subject(BETA.tenant_id.value), _where(BETA)): uuid.UUID(int=0xBEBE)}
    )

    tick = await _lane(world, accounts).tick(BETA)

    assert tick.processed == ()
    assert _dispositions(world, ALPHA) == {}
    assert world.store.state(ALPHA).orders == {}
    assert world.runtime.runs.rows == {}


async def test_alphas_account_is_nobody_in_beta() -> None:
    """The subject names the tenant: alpha's account is not resolved in beta."""
    world = _world()

    tick = await _lane(world).tick(BETA)

    assert tick.stopped == "no_account"


@dataclass
class AnswersForAlpha:
    """A lookup that answers for alpha's workspace whatever it is asked."""

    async def find_service_access(
        self,
        subject: str,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        ceiling: frozenset[str],
    ) -> MembershipAccess | None:
        return _access(_where(ALPHA), DW1_ACCOUNT, frozenset(ceiling))


async def test_a_context_for_another_workspace_is_refused_before_any_run() -> None:
    """Workspace B's tick handed workspace A's context processes nothing at
    all: neither B's mail under A's context nor A's mail in B's tick."""
    world = _world()
    lane = _lane(world)
    lane.access = AnswersForAlpha()

    tick = await lane.tick(BETA)

    assert (tick.processed, tick.stopped) == ((), "wrong_scope")
    assert world.runtime.runs.rows == {}
    assert _dispositions(world, ALPHA) == {}


# --------------------------------- a failing message waits, not a loop --


@dataclass
class FailsOn:
    """`Dw1Runs.process` with one message whose run fails unexpectedly."""

    world: World
    message_id: str
    failing: bool = True
    calls: list[str] = field(default_factory=list)

    async def process(self, context: AccessContext, message_id: str) -> MessageDispositionView:
        self.calls.append(message_id)
        if message_id == self.message_id and self.failing:
            raise RuntimeError("the attachment reader crashed")
        return await self.world.services.dw1.process(context, message_id)


async def test_a_failing_message_does_not_hold_up_the_rest_nor_spend_a_run_every_tick() -> None:
    world = _world()
    clock = FixedClock(NOW)
    lane = _lane(world, clock=clock)
    mailbox = await _mailbox(world)
    # The newest: no later message depends on it having been read.
    bad = mailbox[-1]
    failing = FailsOn(world, bad)
    lane.runs = failing

    first = await lane.tick(ALPHA)
    assert first.processed == tuple(mailbox[:-1])

    # The next tick, a minute on: it waits out its delay.
    clock.advance_to(NOW + RETRY_FIRST / 5)
    await lane.tick(ALPHA)
    assert failing.calls.count(bad) == 1

    # Past the delay it is tried again, and processed once it can be.
    failing.failing = False
    clock.advance_to(NOW + RETRY_FIRST)
    again = await lane.tick(ALPHA)
    assert again.processed == (bad,)
    assert failing.calls.count(bad) == 2


async def test_the_delay_doubles_and_is_forgotten_once_the_message_has_a_disposition() -> None:
    world = _world()
    clock = FixedClock(NOW)
    lane = _lane(world, clock=clock)
    bad = (await _mailbox(world))[-1]
    failing = FailsOn(world, bad)
    lane.runs = failing
    await lane.tick(ALPHA)

    clock.advance_to(NOW + RETRY_FIRST)
    await lane.tick(ALPHA)  # the second failure: it waits twice as long now
    clock.advance_to(NOW + RETRY_FIRST + RETRY_FIRST)
    await lane.tick(ALPHA)
    assert failing.calls.count(bad) == 2

    # A person processes it: the lane forgets it.
    await world.process_each(AN, [bad])
    await lane.tick(ALPHA)
    assert lane._retry == {}
