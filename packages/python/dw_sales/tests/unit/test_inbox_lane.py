"""DW1's mailbox lane, in one process (ticket 16), queueing since ticket 25.

The real Sales services, runner and DW1 graph over in-memory stores
(`open_world`), with the lane built over them as the worker builds it
(`InboxLane`) and the worker's processing lane draining what it queued
(`ProcessingDrain`). The platform's half, resolving DW1's service account from
its membership, is tested against PostgreSQL in `dw_platform`'s
`test_service_access.py` and in the worker's `test_sales_inbox_lane_db.py`;
here it is a fake that keeps the same contract (the ceiling cut, no role,
nobody outside the account's own workspace).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from dw_kernel.pagination import Page, PageRequest
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.identity import MembershipAccess
from dw_platform.domain.audit import AuditEntry, AuditEvent, system_actor
from dw_sales.application.case_store import SalesUnitOfWork
from dw_sales.application.inbox_lane import (
    LANE_CEILING,
    RETRY_FIRST,
    SALES_INBOX_LANE,
    InboxLane,
    LaneTick,
    dw1_subject,
    retry_delay,
)
from dw_sales.application.ports import SalesScope
from dw_sales.application.processing import (
    SALES_PROCESSING_LANE,
    ProcessingDrain,
    ProcessingService,
)
from dw_sales.application.views import MessageDispositionView
from dw_sales.evals.graders import AN, CALLERS, GIANG
from dw_sales.evals.world import (
    ALPHA,
    BETA,
    NOW,
    Directory,
    MemoryStore,
    SampleSet,
    World,
    open_world,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
# DW1's service account in tenant alpha's workspace: a member, no email.
DW1_ACCOUNT = uuid.UUID(int=0xD1D1)
QUEUED_BY_LANE = "sales.message.queued_by_lane"


def _world(**options: object) -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS, **options)  # type: ignore[arg-type]


type Where = tuple[uuid.UUID, uuid.UUID]


def _where(scope: SalesScope) -> Where:
    return scope.tenant_id.value, scope.workspace_id.value


@dataclass
class Accounts:
    """`ServiceAccessPort` as the platform answers it
    (`SqlMembershipLookup.find_service_access`): the account's own membership,
    its scopes cut to the ceiling and no role; nobody anywhere else. And
    `RequesterAccessPort` for the drain: the account by its user id, the same
    way, and the eval's people as the world's directory answers for them.

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

    async def find_linked_access(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        ceiling: frozenset[str],
    ) -> MembershipAccess | None:
        where = (tenant_id, workspace_id)
        if where in [w for (_, w), u in self.members.items() if u == user_id]:
            return _access(where, user_id, self.holds & ceiling)
        return await Directory(CALLERS).find_linked_access(
            user_id, tenant_id, workspace_id, ceiling
        )


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


@dataclass
class Setup:
    """The lane, and the worker's drain of what it queues, over one world."""

    world: World
    accounts: Accounts = field(default_factory=Accounts)
    runs: object | None = None
    processing: ProcessingService | None = None

    @property
    def clock(self) -> FixedClock:
        """The world's clock: the lane, the drain and the services read it."""
        return self.world.store.clock

    @property
    def lane(self) -> InboxLane:
        world = self.world
        return InboxLane(
            world.store,
            world.inbox,
            self.processing or world.services.processing,
            self.accounts,
            self.clock,
        )

    @property
    def drain(self) -> ProcessingDrain:
        world = self.world
        return ProcessingDrain(
            world.store,
            world.store,
            self.runs or world.services.dw1,  # type: ignore[arg-type]
            self.accounts,
            world.store.clock,
            Uuid4Generator(),
            channels=self.lane,
        )

    async def tick(self, scope: SalesScope = ALPHA) -> LaneTick:
        """One lane tick, then the drain until nothing is due."""
        tick = await self.lane.tick(scope)
        drain = self.drain
        while await drain.drain_one():
            pass
        return tick


async def _mailbox(world: World, scope: SalesScope = ALPHA) -> list[str]:
    return [m.message_id for m in await world.inbox.list_messages(scope)]


def _dispositions(world: World, scope: SalesScope = ALPHA) -> dict[str, str]:
    return {k: v.disposition.kind.value for k, v in world.store.state(scope).messages.items()}


def _jobs(world: World, scope: SalesScope = ALPHA) -> dict[str, tuple[str, str | None]]:
    return {k: (j.status, j.error) for k, j in world.store.state(scope).jobs.items()}


def _runs(world: World) -> list[tuple[uuid.UUID, str | None]]:
    """Every DW1 run, as (who it ran as, the message it was given)."""
    return [
        (run.context.actor_id, run.input["task"]["message_id"])
        for run in world.runtime.runs.rows.values()
    ]


# ------------------------------------------- 2. every new message, once --


async def test_each_new_message_is_queued_oldest_first_and_run_once_as_the_account() -> None:
    world = _world()
    mailbox = await _mailbox(world)

    tick = await Setup(world).tick()

    assert tick.queued == tuple(mailbox)
    assert tick.stopped is None
    assert {j.requested_by for j in world.store.state(ALPHA).jobs.values()} == {DW1_ACCOUNT}
    assert set(_dispositions(world)) == set(mailbox)
    assert "not_yet_processed" not in _dispositions(world).values()
    assert set(_jobs(world).values()) == {("done", None)}
    # One run per message, in the mailbox's order, each as DW1's account.
    assert _runs(world) == [(DW1_ACCOUNT, message_id) for message_id in mailbox]


async def test_the_lanes_runs_are_recorded_on_its_own_channel_and_a_persons_on_the_web() -> None:
    """A trace tells a run the lane queued from one a person pressed for."""
    world = _world()
    await world.services.processing.enqueue(AN.context(), "M01")

    await Setup(world).tick()

    channels = {
        run.input["task"]["message_id"]: run.context.channel
        for run in world.runtime.runs.rows.values()
    }
    assert channels.pop("M01") == "web"
    assert channels and set(channels.values()) == {SALES_INBOX_LANE}


async def test_a_second_tick_queues_nothing_and_spends_no_run() -> None:
    world = _world()
    setup = Setup(world)
    await setup.tick()
    runs = len(world.runtime.runs.rows)

    tick = await setup.tick()

    assert tick.queued == ()
    assert len(world.runtime.runs.rows) == runs


async def test_a_message_already_queued_is_not_queued_again_before_it_runs() -> None:
    world = _world()
    setup = Setup(world)
    await setup.lane.tick(ALPHA)
    jobs = dict(world.store.state(ALPHA).jobs)

    again = await setup.lane.tick(ALPHA)

    assert again.queued == ()
    assert world.store.state(ALPHA).jobs == jobs


async def test_a_message_a_person_processed_is_not_queued_again() -> None:
    """Acceptance 7: one already on a case and one routed to Sales alike."""
    world = _world()
    seen = await world.process_each(AN, ["M01", "M11"])
    assert seen["M01"][0].kind == "case_created"
    assert seen["M11"][0].kind == "routed_to_sales"
    before = dict(world.store.state(ALPHA).messages)

    tick = await Setup(world).tick()

    assert "M01" not in tick.queued and "M11" not in tick.queued
    for message_id in ("M01", "M11"):
        assert world.store.state(ALPHA).messages[message_id] == before[message_id]
        assert [m for _, m in _runs(world)].count(message_id) == 1


async def test_a_person_and_the_lane_queueing_one_message_queue_it_once() -> None:
    """The (workspace, message_id) key holds across the race: whoever asks
    second is handed the job the first queued, and the message runs once."""
    world = _world()
    queued = await world.services.processing.enqueue(AN.context(), "M01")

    tick = await Setup(world).tick()

    assert "M01" not in tick.queued
    job = world.store.state(ALPHA).jobs["M01"]
    assert (job.job_id, job.requested_by, job.status) == (queued.job_id, AN.user_id, "done")
    assert [actor for actor, m in _runs(world) if m == "M01"] == [AN.user_id]


async def test_the_lane_meeting_a_job_a_person_queued_writes_no_lane_row() -> None:
    """The lane's row explains a job the lane queued. Handed a person's job,
    the lane queued nothing, and a row would claim the person's job as its own."""
    world = _world()
    processing = world.services.processing
    queued = await processing.enqueue(AN.context(), "M01")

    met = await processing.enqueue(AN.context(), "M01", lane=SALES_INBOX_LANE)

    assert met.job_id == queued.job_id
    assert not [e for e in world.audit() if e.action == QUEUED_BY_LANE]


@dataclass
class PersonFirst:
    """`Dw1Runs.process` with a person pressing on one message (in a run of
    their own, as before ticket 25) just before the drain's run of it."""

    world: World
    message_id: str

    async def process(
        self, context: AccessContext, message_id: str, *, channel: str
    ) -> MessageDispositionView:
        if message_id == self.message_id:
            await self.world.services.dw1.process(AN.context(), message_id)
        return await self.world.services.dw1.process(context, message_id, channel=channel)


async def test_a_run_that_meets_a_message_processed_meanwhile_fails_and_keeps_one_case() -> None:
    world = _world()
    setup = Setup(world, runs=PersonFirst(world, "M01"))

    await setup.tick()

    m01 = world.store.state(ALPHA).messages["M01"].disposition
    assert m01.kind.value == "case_created"
    assert [s.case.message_id for s in world.store.state(ALPHA).orders.values()].count("M01") == 1
    assert _jobs(world)["M01"] == ("failed", "conflict")
    # The person's run, and the drain's refused one as the account.
    assert [actor for actor, m in _runs(world) if m == "M01"] == [AN.user_id, DW1_ACCOUNT]


# ------------------------------------------- 3. it audits as itself --


class _LaneRowRefused:
    """The world's units of work, with an audit store that refuses the lane's
    own row: as a write failing between the job and that row would."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def __call__(self, scope: SalesScope) -> SalesUnitOfWork:
        work = self.store(scope)
        held = work.audit

        class Refusing:
            async def append(self, event: AuditEvent) -> None:
                if event.action == QUEUED_BY_LANE:
                    raise RuntimeError("the audit store refused the lane's row")
                await held.append(event)

            async def list_page(
                self,
                request: PageRequest,
                *,
                workspace_id: uuid.UUID,
                support_grant_id: uuid.UUID | None = None,
            ) -> Page[AuditEntry]:
                return await held.list_page(
                    request, workspace_id=workspace_id, support_grant_id=support_grant_id
                )

            async def list_for_run(
                self, run_id: uuid.UUID, *, workspace_id: uuid.UUID, limit: int = 100
            ) -> list[AuditEvent]:
                return await held.list_for_run(run_id, workspace_id=workspace_id, limit=limit)

        work.audit = Refusing()  # type: ignore[misc]
        return work


async def test_a_job_the_lane_queued_is_never_left_without_the_lanes_audit_row() -> None:
    """The row is written in the job's transaction: when it cannot be, nothing
    is queued, rather than a job naming DW1's account that no lane row explains."""
    world = _world()
    refusing = _LaneRowRefused(world.store)
    processing = replace(world.services.processing, uow=refusing)
    setup = Setup(world, processing=processing)
    lane = replace(setup.lane, uow=refusing)

    with pytest.raises(RuntimeError, match="lane's row"):
        await lane.tick(ALPHA)

    assert world.store.state(ALPHA).jobs == {}


async def test_both_lanes_audit_as_themselves_naming_the_account_it_acted_under() -> None:
    world = _world()

    tick = await Setup(world).tick()

    audit = world.audit()
    queued = [e for e in audit if e.action == QUEUED_BY_LANE]
    assert [e.resource_id for e in queued] == list(tick.queued)
    for event in queued:
        assert event.actor_id == system_actor(SALES_INBOX_LANE)
        assert event.details["actor"] == "system:sales_inbox"
        assert event.details["account_id"] == str(DW1_ACCOUNT)
    ran = [e for e in audit if e.action == "sales.message.processing_done"]
    assert sorted(e.resource_id for e in ran) == sorted(tick.queued)
    for event in ran:
        assert event.actor_id == system_actor(SALES_PROCESSING_LANE)
        assert event.details["requested_by"] == str(DW1_ACCOUNT)
    # Everything else the queueing and processing wrote names the account,
    # never a person.
    lanes = {system_actor(SALES_INBOX_LANE), system_actor(SALES_PROCESSING_LANE)}
    people = {caller.user_id for caller in CALLERS}
    assert not [e for e in audit if e.actor_id.value in people]
    assert {e.actor_id.value for e in audit if e.actor_id not in lanes} == {DW1_ACCOUNT}


# ----------------------------------- 4. sales.inbox.process, and only it --


async def test_the_lane_asks_for_the_inbox_scope_only() -> None:
    accounts = Accounts()
    await Setup(_world(), accounts).lane.tick(ALPHA)

    assert accounts.ceilings == [frozenset({"sales.inbox.process"})] == [LANE_CEILING]


async def test_a_role_added_to_the_account_by_hand_widens_nothing_a_run_carries() -> None:
    """The account given `sales_head` by hand: the runs still carry the
    inbox scope alone, so nothing the lane starts can prepare, cross-check,
    price or approve."""
    world = _world()

    await Setup(world, Accounts(holds=GIANG.scopes)).tick()

    scopes = {run.context.scopes for run in world.runtime.runs.rows.values()}
    roles = {run.context.roles for run in world.runtime.runs.rows.values()}
    assert scopes == {frozenset({"sales.inbox.process"})}
    assert roles == {frozenset()}


async def test_an_account_without_the_inbox_scope_queues_nothing_and_spends_no_run() -> None:
    world = _world()

    tick = await Setup(world, Accounts(holds=frozenset())).tick()

    assert (tick.queued, tick.stopped) == ((), "not_permitted")
    assert world.runtime.runs.rows == {}
    assert _dispositions(world) == {} and _jobs(world) == {}


async def test_a_workspace_without_dw1s_account_is_left_alone() -> None:
    world = _world()

    tick = await Setup(world, Accounts(members={})).tick()

    assert (tick.queued, tick.stopped) == ((), "no_account")
    assert world.runtime.runs.rows == {}


# --------------------------------------- 5. the plan's runs for the day --


class _ThreeRunsADay:
    def runs_per_day(self, plan_id: str) -> int | None:
        return 3

    def spend_usd_per_day(self, plan_id: str) -> Decimal | None:
        return None


async def test_over_the_plans_runs_the_rest_fail_quota_and_stay_unprocessed_and_visible() -> None:
    world = _world(allowance=_ThreeRunsADay())
    mailbox = await _mailbox(world)
    setup = Setup(world)

    first = await setup.tick()
    second = await setup.tick()

    assert first.queued == tuple(mailbox)
    # Failed jobs wait out their delay: the next tick queues nothing.
    assert second.queued == ()
    assert len(world.runtime.runs.rows) == 3
    assert [m for m in mailbox if _jobs(world)[m] == ("failed", "quota")] == mailbox[3:]
    # Visibly: the inbox shows the rest as "Chưa xử lý", and why.
    shown = {m.message_id: m for m in await world.services.inbox.messages(AN.context())}
    assert [m for m in mailbox if shown[m].disposition.kind == "not_yet_processed"] == mailbox[3:]
    assert {shown[m].processing.error for m in mailbox[3:]} == {"quota"}  # type: ignore[union-attr]


# ------------------------------------------------ 6. pausing stops it --


async def test_a_paused_workspace_is_skipped_until_the_head_resumes_dw1() -> None:
    world = _world()
    setup = Setup(world)
    await world.services.worker.pause(AN.context(), "Kiểm tra lại convert list")

    paused = await setup.tick()

    assert (paused.queued, paused.stopped) == ((), "paused")
    assert world.runtime.runs.rows == {}
    assert _dispositions(world) == {} and _jobs(world) == {}

    await world.services.worker.resume(GIANG.context(), "Đã kiểm tra xong")
    resumed = await setup.tick()

    assert resumed.queued == tuple(await _mailbox(world))


@dataclass
class PausedAfter:
    """A PIC pauses DW1 while the drain is between two messages."""

    world: World
    after: str

    async def process(
        self, context: AccessContext, message_id: str, *, channel: str
    ) -> MessageDispositionView:
        view = await self.world.services.dw1.process(context, message_id, channel=channel)
        if message_id == self.after:
            await self.world.services.worker.pause(AN.context(), None)
        return view


async def test_a_pause_while_the_queue_drains_fails_the_rest_paused() -> None:
    world = _world()
    mailbox = await _mailbox(world)
    setup = Setup(world, runs=PausedAfter(world, mailbox[1]))

    await setup.tick()

    assert set(_dispositions(world)) == set(mailbox[:2])
    assert {_jobs(world)[m] for m in mailbox[2:]} == {("failed", "paused")}
    # The rest were refused before any processing: no disposition, no case.
    assert all(m not in _dispositions(world) for m in mailbox[2:])


# ------------------------------------------ 7. never across workspaces --


async def test_workspace_bs_tick_reads_bs_mailbox_only_and_writes_nothing_in_a() -> None:
    world = _world()
    accounts = Accounts(
        members={(dw1_subject(BETA.tenant_id.value), _where(BETA)): uuid.UUID(int=0xBEBE)}
    )

    tick = await Setup(world, accounts).tick(BETA)

    assert tick.queued == ()
    assert _dispositions(world, ALPHA) == {} and _jobs(world, ALPHA) == {}
    assert world.store.state(ALPHA).orders == {}
    assert world.runtime.runs.rows == {}


async def test_alphas_account_is_nobody_in_beta() -> None:
    """The subject names the tenant: alpha's account is not resolved in beta."""
    world = _world()

    tick = await Setup(world).lane.tick(BETA)

    assert tick.stopped == "no_account"


@dataclass
class AnswersForAlpha(Accounts):
    """A lookup that answers for alpha's workspace whatever it is asked."""

    async def find_service_access(
        self,
        subject: str,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        ceiling: frozenset[str],
    ) -> MembershipAccess | None:
        return _access(_where(ALPHA), DW1_ACCOUNT, frozenset(ceiling))

    async def find_linked_access(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        ceiling: frozenset[str],
    ) -> MembershipAccess | None:
        return _access(_where(ALPHA), user_id, frozenset(ceiling))


async def test_a_context_for_another_workspace_is_refused_before_anything_is_queued() -> None:
    """Workspace B's tick handed workspace A's context queues nothing at all:
    neither B's mail under A's context nor A's mail in B's tick."""
    world = _world()

    tick = await Setup(world, AnswersForAlpha()).lane.tick(BETA)

    assert (tick.queued, tick.stopped) == ((), "wrong_scope")
    assert world.runtime.runs.rows == {}
    assert _jobs(world, ALPHA) == {} and _jobs(world, BETA) == {}


async def test_the_drain_refuses_a_context_for_another_workspace_before_any_run() -> None:
    world = _world()
    async with world.store(BETA) as work:
        await work.jobs.enqueue("M01", AN.user_id, NOW, uuid.uuid4())
        await work.commit()
    setup = Setup(world, AnswersForAlpha())

    while await setup.drain.drain_one():
        pass

    assert world.runtime.runs.rows == {}
    assert _jobs(world, BETA)["M01"] == ("failed", "not_permitted")


# --------------------------------- a failing message waits, not a loop --


@dataclass
class FailsOn:
    """`Dw1Runs.process` with one message whose run fails unexpectedly."""

    world: World
    message_id: str
    failing: bool = True
    calls: list[str] = field(default_factory=list)

    async def process(
        self, context: AccessContext, message_id: str, *, channel: str
    ) -> MessageDispositionView:
        self.calls.append(message_id)
        if message_id == self.message_id and self.failing:
            raise RuntimeError("the attachment reader crashed")
        return await self.world.services.dw1.process(context, message_id, channel=channel)


async def test_a_failing_message_does_not_hold_up_the_rest_nor_spend_a_run_every_tick() -> None:
    world = _world()
    mailbox = await _mailbox(world)
    # The newest: no later message depends on it having been read.
    bad = mailbox[-1]
    failing = FailsOn(world, bad)
    setup = Setup(world, runs=failing)

    first = await setup.tick()
    assert first.queued == tuple(mailbox)
    assert _jobs(world)[bad] == ("failed", "error")
    assert set(_dispositions(world)) == set(mailbox[:-1])

    # The next tick, a minute on: it waits out its delay.
    setup.clock.advance_to(NOW + RETRY_FIRST / 5)
    await setup.tick()
    assert failing.calls.count(bad) == 1

    # Past the delay it is queued again, and processed once it can be.
    failing.failing = False
    setup.clock.advance_to(NOW + RETRY_FIRST)
    again = await setup.tick()
    assert again.queued == (bad,)
    assert failing.calls.count(bad) == 2
    assert _jobs(world)[bad] == ("done", None)


async def test_the_delay_doubles_with_each_failure_and_is_forgotten_once_done() -> None:
    world = _world()
    bad = (await _mailbox(world))[-1]
    failing = FailsOn(world, bad)
    setup = Setup(world, runs=failing)
    await setup.tick()

    setup.clock.advance_to(NOW + RETRY_FIRST)
    await setup.tick()  # the second failure: it waits twice as long now
    assert world.store.state(ALPHA).jobs[bad].failures == 2
    setup.clock.advance_to(NOW + RETRY_FIRST + RETRY_FIRST)
    await setup.tick()
    assert failing.calls.count(bad) == 2

    failing.failing = False
    setup.clock.advance_to(NOW + RETRY_FIRST + retry_delay(2))
    await setup.tick()
    assert world.store.state(ALPHA).jobs[bad].failures == 0


def test_the_delay_is_capped() -> None:
    assert retry_delay(1) == RETRY_FIRST
    assert retry_delay(2) == RETRY_FIRST * 2
    assert retry_delay(10_000) == timedelta(hours=6)
