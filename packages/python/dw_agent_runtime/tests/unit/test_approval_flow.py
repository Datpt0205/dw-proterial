import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from dw_agent_runtime.adapters.run_store import RunRecord, RunStatus
from dw_agent_runtime.approval_flow import (
    ApprovalDecisionGuard,
    ApproveAndResumeService,
    ProposedDecision,
)
from dw_agent_runtime.contracts import RunContext
from dw_kernel.autonomy import AutonomyLevel
from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import FixedClock, SequentialIdGenerator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.ports import PlatformUnitOfWork
from dw_platform.domain.approval import ApprovalDecision, ApprovalRequest, ApprovalStatus
from dw_platform.domain.outbox import OutboxEvent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
REQUESTER = uuid.UUID(int=1)
APPROVER = uuid.UUID(int=2)


@dataclass
class FakeApprovalRepo:
    request: ApprovalRequest
    decisions: list[ApprovalDecision] = field(default_factory=list)

    async def get(self, approval_id: uuid.UUID) -> ApprovalRequest | None:
        return self.request if approval_id == self.request.id else None

    async def save(self, request: ApprovalRequest) -> None: ...

    async def add_decision(self, decision: ApprovalDecision) -> None:
        self.decisions.append(decision)


@dataclass
class FakeOutbox:
    """Keeps what was added and whether the UoW had already committed by then:
    an event added after the commit is one a crash between the two loses."""

    events: list[OutboxEvent] = field(default_factory=list)
    added_after_commit: list[OutboxEvent] = field(default_factory=list)
    committed: bool = False

    async def add(self, event: OutboxEvent) -> None:
        (self.added_after_commit if self.committed else self.events).append(event)

    async def list_unprocessed(self, limit: int = 100) -> list[OutboxEvent]:
        raise NotImplementedError("not exercised by ApproveAndResumeService")

    async def has_unprocessed(self, event_type: str, aggregate_id: uuid.UUID) -> bool:
        raise NotImplementedError("not exercised by ApproveAndResumeService")


@dataclass
class FakeUoW:
    approvals: FakeApprovalRepo
    outbox: FakeOutbox = field(default_factory=FakeOutbox)

    async def __aenter__(self) -> "FakeUoW":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def commit(self) -> None:
        self.outbox.committed = True

    async def rollback(self) -> None: ...


RUN_ID = uuid.UUID(int=20)


REQUESTER_SCOPES = frozenset({"crm.read"})
# The ADR-003 roll-up the requester started the run with: themselves plus one
# report. The approver's own subtree is deliberately a different set.
REQUESTER_OWNERS = frozenset({REQUESTER, uuid.UUID(int=41)})
# Deliberately not the A4 a fresh context would get, so a resume that re-resolved
# it instead of replaying the stamp would be caught.
REQUESTER_AUTONOMY: AutonomyLevel = "A3"


@dataclass
class FakeRunStore:
    status: RunStatus = RunStatus.WAITING_APPROVAL
    worker_version: str = "1.0.0"
    actor_scopes: frozenset[str] = REQUESTER_SCOPES
    actor_clearance: str = "confidential"
    actor_record_visibility: str = "restricted"
    actor_visible_owners: frozenset[uuid.UUID] | None = REQUESTER_OWNERS

    async def get(self, run_context: RunContext, run_id: uuid.UUID) -> RunRecord:
        return RunRecord(
            id=run_id,
            thread_id=uuid.UUID(int=21),
            status=self.status,
            worker_id="sales_chat",
            worker_version=self.worker_version,
            graph_version="1.0.0",
            prompt_bundle_version="1.0.0",
            toolset_version="1.0.0",
            policy_version="1.0.0",
            memory_policy_version="1.0.0",
            autonomy_level=REQUESTER_AUTONOMY,
            approval_policy_version="1.0.0",
            input={},
            result=None,
            error=None,
            approval_request_id=uuid.UUID(int=10),
            release_manifest_ref=None,
            requested_by=REQUESTER,
            actor_roles=frozenset({"member"}),
            actor_scopes=self.actor_scopes,
            actor_plan_id="starter",
            actor_clearance=self.actor_clearance,
            actor_record_visibility=self.actor_record_visibility,
            actor_visible_owners=self.actor_visible_owners,
        )


@dataclass
class FakeRunner:
    hosted: bool
    asked: list[tuple[str, str, str]] = field(default_factory=list)
    resumed: list[uuid.UUID] = field(default_factory=list)
    contexts: list[RunContext] = field(default_factory=list)

    def hosts(self, *, worker_id: str, worker_version: str, graph_version: str) -> bool:
        self.asked.append((worker_id, worker_version, graph_version))
        return self.hosted

    async def resume(
        self, *, run_context: RunContext, run_id: uuid.UUID, resume_payload: dict[str, Any]
    ) -> None:
        self.resumed.append(run_id)
        self.contexts.append(run_context)


def make_request(approval_type: str, run_id: uuid.UUID | None = None) -> ApprovalRequest:
    return ApprovalRequest(
        id=uuid.UUID(int=10),
        tenant_id=TenantId(uuid.UUID(int=100)),
        workspace_id=WorkspaceId(uuid.UUID(int=101)),
        approval_type=approval_type,
        requested_by=UserId(REQUESTER),
        reason="cần duyệt",
        payload={},
        run_id=run_id,
    )


def make_service(
    request: ApprovalRequest,
    prefixes: frozenset[str],
    runner: Any = None,
    repo: FakeApprovalRepo | None = None,
    run_status: RunStatus = RunStatus.WAITING_APPROVAL,
    outbox: FakeOutbox | None = None,
    guards: dict[str, ApprovalDecisionGuard] | None = None,
) -> ApproveAndResumeService:
    resolved = repo or FakeApprovalRepo(request=request)
    resolved_outbox = outbox or FakeOutbox()

    def uow_factory(context: AccessContext) -> PlatformUnitOfWork:
        return cast(PlatformUnitOfWork, FakeUoW(approvals=resolved, outbox=resolved_outbox))

    return ApproveAndResumeService(
        uow_factory=uow_factory,
        runner=cast(Any, runner),
        run_store=cast(Any, FakeRunStore(status=run_status)),
        clock=FixedClock(NOW),
        id_generator=SequentialIdGenerator(),
        strict_approval_prefixes=prefixes,
        decision_guards=guards or {},
    )


def make_context(principal: uuid.UUID) -> AccessContext:
    return AccessContext(
        tenant_id=uuid.UUID(int=100),
        workspace_id=uuid.UUID(int=101),
        principal_id=principal,
        roles=frozenset({"approver"}),
        scopes=frozenset({"approvals.decide"}),
        plan_id="professional",
    )


async def decide(
    service: ApproveAndResumeService, principal: uuid.UUID, comment: str
) -> ApprovalRequest:
    return await service.decide(
        approval_id=uuid.UUID(int=10),
        approve=True,
        comment=comment,
        context=make_context(principal),
        authorization=ScopeAuthorizationService(),
    )


async def test_strict_type_rejects_self_approval() -> None:
    service = make_service(make_request("sales_chat.email_send"), frozenset({"sales_chat."}))
    with pytest.raises(ConflictError, match="separation of duties"):
        await decide(service, REQUESTER, "ok")


async def test_strict_type_requires_a_comment() -> None:
    service = make_service(make_request("sales_chat.email_send"), frozenset({"sales_chat."}))
    with pytest.raises(ConflictError, match="review comment"):
        await decide(service, APPROVER, "   ")


async def test_strict_type_accepts_another_approver_with_a_comment() -> None:
    service = make_service(make_request("sales_chat.email_send"), frozenset({"sales_chat."}))
    request = await decide(service, APPROVER, "đã kiểm tra nội dung")
    assert request.status.value == "approved"


async def test_non_strict_type_allows_self_approval_without_comment() -> None:
    service = make_service(make_request("demo.dispatch"), frozenset({"sales_chat."}))
    request = await decide(service, REQUESTER, "")
    assert request.status.value == "approved"


async def test_a_host_that_cannot_resume_records_nothing() -> None:
    """A decision is spendable once, so it must not survive a refused resume."""
    request = make_request("demo.dispatch", run_id=RUN_ID)
    repo = FakeApprovalRepo(request=request)
    runner = FakeRunner(hosted=False)
    service = make_service(request, frozenset(), runner=runner, repo=repo)

    with pytest.raises(ConflictError, match="does not run the graph"):
        await decide(service, APPROVER, "")

    assert request.status.value == "pending"
    assert repo.decisions == []
    assert runner.resumed == []


async def test_the_guard_asks_about_everything_resume_needs() -> None:
    """The guard and resume() must ask one question, not two different ones.

    resume() replays both the graph the run started on and that worker
    version's settings. While the guard asked only about the graph, retiring a
    worker version let the decision commit and then failed the resume.
    """
    request = make_request("demo.dispatch", run_id=RUN_ID)
    runner = FakeRunner(hosted=True)
    service = make_service(request, frozenset(), runner=runner)

    await decide(service, APPROVER, "")

    assert runner.asked == [("sales_chat", "1.0.0", "1.0.0")]


async def test_a_run_no_longer_waiting_records_nothing() -> None:
    """The other precondition resume() enforces, checked before the write."""
    request = make_request("demo.dispatch", run_id=RUN_ID)
    repo = FakeApprovalRepo(request=request)
    runner = FakeRunner(hosted=True)
    service = make_service(
        request, frozenset(), runner=runner, repo=repo, run_status=RunStatus.FAILED
    )

    with pytest.raises(ConflictError, match="not waiting for approval"):
        await decide(service, APPROVER, "")

    assert request.status.value == "pending"
    assert repo.decisions == []
    assert runner.resumed == []


async def test_the_owning_host_decides_and_resumes() -> None:
    request = make_request("demo.dispatch", run_id=RUN_ID)
    repo = FakeApprovalRepo(request=request)
    runner = FakeRunner(hosted=True)
    service = make_service(request, frozenset(), runner=runner, repo=repo)

    decided = await decide(service, APPROVER, "")

    assert decided.status.value == "approved"
    assert len(repo.decisions) == 1
    assert runner.resumed == [RUN_ID]


async def test_the_resumed_run_carries_the_requesters_authority() -> None:
    """Separation of duties makes the approver a different person every time.

    Reading roles/scopes from their AccessContext handed the requester's agent
    whatever the approver happened to hold — either too much power, or too
    little to finish the turn the approval had already been spent on.
    """
    request = make_request("demo.dispatch", run_id=RUN_ID)
    runner = FakeRunner(hosted=True)
    service = make_service(request, frozenset(), runner=runner)

    await decide(service, APPROVER, "")

    resumed = runner.contexts[0]
    assert resumed.scopes == REQUESTER_SCOPES
    assert resumed.roles == frozenset({"member"})
    assert resumed.plan_id == "starter"
    assert resumed.actor_id == REQUESTER
    # Clearance is authority too: retrieval turns it into the set of document
    # classifications the run may read, so losing it here shrinks what the
    # second half of the turn can see compared with the first.
    assert resumed.clearance == "confidential"
    # So is the owner roll-up. Without it the resumed half of the turn read
    # the whole workspace while the first half stayed inside the subtree.
    assert resumed.record_visibility == "restricted"
    assert resumed.visible_owners == REQUESTER_OWNERS
    # And autonomy, from the run's own stamp. Not re-resolved from the tenant's
    # ceiling today, and not the approver's: resumed at None it would ask about
    # everything; resumed at a level read fresh it would be allowed whatever the
    # ceiling happens to be now rather than what the run was started under.
    assert resumed.autonomy_level == REQUESTER_AUTONOMY
    assert resumed.approval_policy_version == "1.0.0"

    approver = make_context(APPROVER)
    assert not (resumed.scopes & approver.scopes)
    assert not (resumed.roles & approver.roles)


def context_without_the_right(principal: uuid.UUID) -> AccessContext:
    """A plain seller: may ask the agent for things, may not decide them."""
    return AccessContext(
        tenant_id=uuid.UUID(int=100),
        workspace_id=uuid.UUID(int=101),
        principal_id=principal,
        roles=frozenset({"sales"}),
        scopes=frozenset(),
        plan_id="professional",
    )


async def test_the_requester_can_withdraw_without_the_decide_right() -> None:
    """Rejecting your OWN pending request is taking it back, not deciding it."""
    service = make_service(make_request("sales_chat.crm.add_person_note"), frozenset())
    request = await service.decide(
        approval_id=uuid.UUID(int=10),
        approve=False,
        comment="thôi, tôi nhầm",
        context=context_without_the_right(REQUESTER),
        authorization=ScopeAuthorizationService(),
    )
    assert request.status is ApprovalStatus.REJECTED


async def test_the_requester_still_cannot_approve_their_own_request() -> None:
    service = make_service(make_request("sales_chat.crm.add_person_note"), frozenset())
    with pytest.raises(PermissionDeniedError):
        await service.decide(
            approval_id=uuid.UUID(int=10),
            approve=True,
            comment="ok",
            context=context_without_the_right(REQUESTER),
            authorization=ScopeAuthorizationService(),
        )


async def test_a_bystander_without_the_right_cannot_reject_someone_elses() -> None:
    service = make_service(make_request("sales_chat.crm.add_person_note"), frozenset())
    with pytest.raises(PermissionDeniedError):
        await service.decide(
            approval_id=uuid.UUID(int=10),
            approve=False,
            comment="không liên quan tới tôi",
            context=context_without_the_right(APPROVER),
            authorization=ScopeAuthorizationService(),
        )


# ------------------------------------------- the stamped decide scope (ticket 10) --

MAKER = uuid.UUID(int=3)


def stamped(
    approval_type: str, *, scope: str, makers: tuple[uuid.UUID, ...] = ()
) -> ApprovalRequest:
    request = make_request(approval_type, run_id=RUN_ID)
    request.payload = {"decide_scope": scope, "makers": [str(m) for m in makers]}
    return request


def holding(principal: uuid.UUID, *scopes: str) -> AccessContext:
    return AccessContext(
        tenant_id=uuid.UUID(int=100),
        workspace_id=uuid.UUID(int=101),
        principal_id=principal,
        roles=frozenset({"member"}),
        scopes=frozenset(scopes),
        plan_id="professional",
    )


async def _decide_as(
    service: ApproveAndResumeService, context: AccessContext, **extra: Any
) -> ApprovalRequest:
    return await service.decide(
        approval_id=uuid.UUID(int=10),
        approve=True,
        comment="đã xem",
        context=context,
        authorization=ScopeAuthorizationService(),
        **extra,
    )


async def test_a_stamped_decide_scope_is_required_and_approvals_decide_is_not_it() -> None:
    """A Sales quote is decided with `sales.quote.approve`: the platform's
    approver authority (a manager, `approver_boost`) decides nothing there."""
    request = stamped("sales.quote", scope="sales.quote.approve")
    runner = FakeRunner(hosted=True)
    service = make_service(request, frozenset({"sales."}), runner=runner)

    with pytest.raises(PermissionDeniedError) as refused:
        await _decide_as(service, holding(APPROVER, "approvals.decide"))
    assert refused.value.details["action"] == "sales.quote.approve"
    assert request.status is ApprovalStatus.PENDING and runner.resumed == []

    decided = await _decide_as(service, holding(APPROVER, "sales.quote.approve"))
    assert decided.status is ApprovalStatus.APPROVED


async def test_every_maker_the_request_names_is_refused_not_only_the_requester() -> None:
    request = stamped("sales.order.cross_check", scope="sales.order.cross_check", makers=(MAKER,))
    service = make_service(request, frozenset({"sales."}), runner=FakeRunner(hosted=True))

    for maker in (REQUESTER, MAKER):
        with pytest.raises(ConflictError, match="tách nhiệm") as refused:
            await _decide_as(service, holding(maker, "sales.order.cross_check"))
        assert refused.value.details["rule"] == "maker_checker"
    assert request.status is ApprovalStatus.PENDING

    decided = await _decide_as(service, holding(APPROVER, "sales.order.cross_check"))
    assert decided.status is ApprovalStatus.APPROVED


async def test_unreadable_makers_fail_closed() -> None:
    request = stamped("sales.quote", scope="sales.quote.approve")
    request.payload["makers"] = "not a list"
    service = make_service(request, frozenset({"sales."}), runner=FakeRunner(hosted=True))

    with pytest.raises(ConflictError, match="makers"):
        await _decide_as(service, holding(APPROVER, "sales.quote.approve"))


@dataclass
class FakeGuard:
    refuse: bool
    seen: list[ProposedDecision] = field(default_factory=list)

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        self.seen.append(decision)
        if self.refuse:
            raise ConflictError("the subject moved on")


async def test_a_contexts_guard_refuses_before_anything_is_recorded() -> None:
    request = stamped("sales.quote", scope="sales.quote.approve")
    repo = FakeApprovalRepo(request=request)
    runner = FakeRunner(hosted=True)
    service = make_service(request, frozenset({"sales."}), runner=runner, repo=repo)
    guard = FakeGuard(refuse=True)
    service.decision_guards["sales."] = guard

    with pytest.raises(ConflictError, match="moved on"):
        await _decide_as(
            service,
            holding(APPROVER, "sales.quote.approve"),
            reasons={"price_below_policy_floor:1": "đã xem"},
            subject_version=7,
        )

    assert guard.seen == [
        ProposedDecision(
            approve=True,
            comment="đã xem",
            reasons={"price_below_policy_floor:1": "đã xem"},
            subject_version=7,
        )
    ]
    assert request.status is ApprovalStatus.PENDING
    assert repo.decisions == [] and runner.resumed == []


async def test_a_guard_is_asked_only_about_its_own_prefix() -> None:
    service = make_service(
        make_request("demo.dispatch", run_id=RUN_ID), frozenset(), runner=FakeRunner(hosted=True)
    )
    service.decision_guards["sales."] = FakeGuard(refuse=True)

    decided = await decide(service, APPROVER, "")

    assert decided.status is ApprovalStatus.APPROVED


# ------------------------------------------- run-less approvals: the hook --


async def test_a_runless_decision_announces_itself_inside_the_transaction() -> None:
    """Nothing resumes a run-less approval, so a context hears of its decision
    only through this event. Added after the commit, a crash between the two
    would leave a decision nobody ever acts on."""
    request = make_request("memory.review")
    outbox = FakeOutbox()
    repo = FakeApprovalRepo(request=request)
    service = make_service(request, frozenset(), repo=repo, outbox=outbox)

    await decide(service, APPROVER, "đã đọc")

    assert outbox.added_after_commit == []
    [event] = outbox.events
    assert event.event_type == "memory.review.decided"
    assert event.aggregate_id == request.id
    assert event.tenant_id == request.tenant_id
    assert event.workspace_id == request.workspace_id
    assert event.actor_id == APPROVER
    assert event.payload == {
        "approval_id": str(request.id),
        "decision_id": str(repo.decisions[0].id),
        "outcome": "approved",
        "decided_by": str(APPROVER),
    }


async def test_a_rejection_announces_the_rejection() -> None:
    request = make_request("memory.review")
    outbox = FakeOutbox()
    service = make_service(request, frozenset(), outbox=outbox)

    await service.decide(
        approval_id=request.id,
        approve=False,
        comment="không đúng",
        context=make_context(APPROVER),
        authorization=ScopeAuthorizationService(),
    )

    assert [event.payload["outcome"] for event in outbox.events] == ["rejected"]


async def test_a_decision_that_resumes_a_run_announces_nothing() -> None:
    """The run is that decision's consequence; a second channel for it would be
    a second consumer acting on one decision."""
    request = make_request("demo.dispatch", run_id=RUN_ID)
    outbox = FakeOutbox()
    service = make_service(request, frozenset(), runner=FakeRunner(hosted=True), outbox=outbox)

    await decide(service, APPROVER, "")

    assert outbox.events == []


class _Refuse:
    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        raise PermissionDeniedError("not cleared for this approval")


async def test_a_guard_registered_for_the_type_can_refuse_and_nothing_is_recorded() -> None:
    request = make_request("memory.review")
    repo = FakeApprovalRepo(request=request)
    outbox = FakeOutbox()
    service = make_service(
        request, frozenset(), repo=repo, outbox=outbox, guards={"memory.review": _Refuse()}
    )

    with pytest.raises(PermissionDeniedError, match="not cleared"):
        await decide(service, APPROVER, "ok")

    assert request.status is ApprovalStatus.PENDING
    assert repo.decisions == []
    assert outbox.events == []


async def test_a_guard_for_another_type_is_not_asked() -> None:
    service = make_service(
        make_request("demo.dispatch"), frozenset(), guards={"memory.review": _Refuse()}
    )

    decided = await decide(service, APPROVER, "")

    assert decided.status is ApprovalStatus.APPROVED


@dataclass
class PayloadRunner(FakeRunner):
    payloads: list[dict[str, Any]] = field(default_factory=list)

    async def resume(
        self, *, run_context: RunContext, run_id: uuid.UUID, resume_payload: dict[str, Any]
    ) -> None:
        await super().resume(run_context=run_context, run_id=run_id, resume_payload=resume_payload)
        self.payloads.append(resume_payload)


async def test_the_run_resumes_knowing_who_decided_on_which_version() -> None:
    """The run resumes as its requester; the decider is named in the payload,
    with the reasons and the version they decided on."""
    request = stamped("sales.quote", scope="sales.quote.approve")
    runner = PayloadRunner(hosted=True)
    service = make_service(request, frozenset({"sales."}), runner=runner)

    await _decide_as(
        service,
        holding(APPROVER, "sales.quote.approve"),
        reasons={"above_target_price:-": "khách đồng ý"},
        subject_version=4,
    )

    (payload,) = runner.payloads
    assert payload["decided_by"] == str(APPROVER)
    assert payload["reasons"] == {"above_target_price:-": "khách đồng ý"}
    assert payload["subject_version"] == 4
    assert runner.contexts[0].actor_id == REQUESTER


async def test_another_workspaces_request_is_not_found() -> None:
    request = stamped("sales.quote", scope="sales.quote.approve")
    request.workspace_id = WorkspaceId(uuid.UUID(int=999))
    service = make_service(request, frozenset({"sales."}), runner=FakeRunner(hosted=True))

    with pytest.raises(NotFoundError):
        await _decide_as(service, holding(APPROVER, "sales.quote.approve"))


def test_the_audience_sees_what_it_may_decide_and_what_it_asked_for() -> None:
    quote = stamped("sales.quote", scope="sales.quote.approve")
    plain = make_request("demo.dispatch")
    service = make_service(quote, frozenset())
    authz = ScopeAuthorizationService()

    manager = service.audience(holding(APPROVER, "approvals.decide"), authz)
    head = service.audience(holding(APPROVER, "sales.quote.approve"), authz)
    requester = service.audience(holding(REQUESTER), authz)
    viewer = service.audience(holding(uuid.UUID(int=77), "approvals.read"), authz)

    assert (manager.may_see(quote), manager.may_see(plain)) == (False, True)
    assert (head.may_see(quote), head.may_decide(plain)) == (True, False)
    assert (requester.may_see(quote), requester.may_decide(quote)) == (True, False)
    assert (viewer.may_see(quote), viewer.may_see(plain)) == (False, False)
