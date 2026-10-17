"""What the API's composition root turns on for a held memory.

The approval flow's own tests prove that a strict prefix and a decision guard
are enforced when they are configured. This proves they ARE configured in the
container the API serves: without it, deleting the two lines from
`bootstrap/runtime.py` would leave every other test green while anyone with
`approvals.decide` approved a restricted memory they cannot read, or their own.

It also decides a review the memory service opened (`review_request`) through
that wired flow, as a Sales role and as the platform's approver. A Sales role
holds `approvals.decide` for its own stamped types (`ac31ff0f2087`), so an
unstamped `memory.review` was theirs to decide; the stamp is what takes it
away. Only the unit of work is faked, and it honours the repository's
visibility rule (`ApprovalAudience.may_see`) as `visible_to` does in SQL.
`apps/worker/tests/integration/test_memory_review_db.py` walks the same
refusal against Postgres.
"""

import dataclasses
import uuid
from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from dw_agent_runtime.approval_flow import ApproveAndResumeService, ProposedDecision
from dw_api.bootstrap import build_container
from dw_api.settings import ApiSettings
from dw_kernel.errors import NotFoundError, PermissionDeniedError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_memory.contracts import MemoryType
from dw_memory.policy import MemoryCandidate
from dw_memory.review import (
    MEMORY_REVIEW,
    MEMORY_REVIEW_DECIDED,
    MEMORY_REVIEW_SCOPE,
    review_request,
)
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience, ScopeAuthorizationService
from dw_platform.application.ports import PlatformUnitOfWork
from dw_platform.domain.approval import ApprovalDecision, ApprovalRequest, ApprovalStatus
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.outbox import OutboxEvent

pytestmark = pytest.mark.unit


def _approval_flow() -> ApproveAndResumeService:
    # As `scripts/generate_contracts.py` builds it: engines and clients are
    # lazy, so a placeholder database is enough to compose the runtime.
    container = build_container(
        ApiSettings(
            profile="test",
            database_url="postgresql+asyncpg://wiring:wiring@localhost:5432/wiring",
            dev_secret="wiring-test-secret-0123456789abcdef",
            s3_endpoint_url="http://localhost:9000",
            s3_access_key="wiring",
            s3_secret_key="wiring",
            model_provider="mock",
        )
    )
    flow = container.approval_flow
    assert flow is not None
    return flow


async def test_the_api_decides_memory_reviews_strictly_and_only_with_clearance() -> None:
    flow = _approval_flow()
    assert flow.is_strict(MEMORY_REVIEW)

    tenant, workspace = uuid.uuid4(), uuid.uuid4()
    request = ApprovalRequest(
        id=uuid.uuid4(),
        tenant_id=TenantId(tenant),
        workspace_id=WorkspaceId(workspace),
        approval_type=MEMORY_REVIEW,
        requested_by=UserId(uuid.uuid4()),
        reason="held for review",
        payload={"candidate_id": str(uuid.uuid4()), "classification": "restricted"},
    )
    guard = flow.decision_guards.get(MEMORY_REVIEW)
    assert guard is not None
    with pytest.raises(PermissionDeniedError):
        await guard.check(
            request,
            ProposedDecision(approve=True, comment="", reasons={}, subject_version=None),
            AccessContext(
                tenant_id=tenant,
                workspace_id=workspace,
                principal_id=uuid.uuid4(),
                roles=frozenset({"approver"}),
                scopes=frozenset({"approvals.decide"}),
                clearance="internal",
                plan_id="professional",
            ),
        )


# ------------------------------------------------------ who may decide --

TENANT, WORKSPACE = uuid.uuid4(), uuid.uuid4()
PROPOSER = uuid.uuid4()

# What a membership of `member` plus each Sales decider holds: the roles'
# scopes as migrations 68305ebe4a83, ac31ff0f2087 and later Sales revisions
# write them, cut to what matters here. Each holds `approvals.decide`.
_MEMBER = frozenset({"approvals.read", "memory.read", "runs.read"})
SALES_DECIDERS = {
    "sales_pic": _MEMBER
    | {"approvals.decide", "sales.case.read", "sales.order.cross_check", "sales.quote.prepare"},
    "sales_head": _MEMBER
    | {"approvals.decide", "sales.case.read", "sales.quote.approve", "sales.rules.approve"},
    "sales_quote_approver": _MEMBER | {"approvals.decide", "sales.quote.approve"},
}
# `approver` after 445f93c2ea2a.
APPROVER = _MEMBER | {"approvals.pending", "approvals.decide", MEMORY_REVIEW_SCOPE}


@dataclass
class _Approvals:
    request: ApprovalRequest
    decisions: list[ApprovalDecision] = field(default_factory=list)

    async def get(
        self, approval_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> ApprovalRequest | None:
        found = (
            approval_id == self.request.id
            and workspace_id == self.request.workspace_id.value
            and audience.may_see(self.request)
        )
        return self.request if found else None

    async def save(self, request: ApprovalRequest) -> None: ...

    async def add_decision(self, decision: ApprovalDecision) -> None:
        self.decisions.append(decision)


@dataclass
class _Outbox:
    events: list[OutboxEvent] = field(default_factory=list)

    async def add(self, event: OutboxEvent) -> None:
        self.events.append(event)


@dataclass
class _Audit:
    events: list[AuditEvent] = field(default_factory=list)

    async def append(self, event: AuditEvent) -> None:
        self.events.append(event)


@dataclass
class _UoW:
    approvals: _Approvals
    outbox: _Outbox = field(default_factory=_Outbox)
    audit: _Audit = field(default_factory=_Audit)

    async def __aenter__(self) -> "_UoW":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


def _held_review() -> ApprovalRequest:
    """The approval `MemoryService._open_review` writes for a held candidate."""
    return review_request(
        approval_id=uuid.uuid4(),
        context=AccessContext(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            principal_id=PROPOSER,
            roles=frozenset({"member"}),
            scopes=_MEMBER,
            plan_id="professional",
        ),
        candidate_id=uuid.uuid4(),
        candidate=MemoryCandidate(
            worker_id="demo",
            memory_type=MemoryType.COMMITMENT,
            content="Anh An cam kết gửi hợp đồng trước thứ Sáu.",
            subject_refs=("crm:account:1",),
            classification="internal",
        ),
        reason="one source is too few to write alone",
    )


def _person(role: str, scopes: frozenset[str]) -> AccessContext:
    return AccessContext(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        principal_id=uuid.uuid4(),
        roles=frozenset({"member", role}),
        scopes=scopes,
        clearance="restricted",
        plan_id="professional",
    )


async def _decide(uow: _UoW, context: AccessContext) -> None:
    """Approve, through the flow the API wires, over `uow`."""

    def uow_factory(context: AccessContext) -> PlatformUnitOfWork:
        return cast(PlatformUnitOfWork, uow)

    flow = dataclasses.replace(_approval_flow(), uow_factory=uow_factory)
    await flow.decide(
        approval_id=uow.approvals.request.id,
        approve=True,
        comment="đã đối chiếu biên bản",
        context=context,
        authorization=ScopeAuthorizationService(),
    )


def test_a_held_memory_is_stamped_with_the_review_scope() -> None:
    assert _held_review().required_scope == MEMORY_REVIEW_SCOPE


@pytest.mark.parametrize("role", sorted(SALES_DECIDERS))
async def test_a_sales_role_with_approvals_decide_does_not_find_a_memory_review(
    role: str,
) -> None:
    request = _held_review()
    uow = _UoW(_Approvals(request))

    # Not found rather than refused: a stamped request its decider may not see
    # is absent (ADR 0011 amendment), so a 403 does not confirm it exists.
    with pytest.raises(NotFoundError):
        await _decide(uow, _person(role, SALES_DECIDERS[role]))

    assert request.status is ApprovalStatus.PENDING
    assert (uow.approvals.decisions, uow.outbox.events, uow.audit.events) == ([], [], [])


async def test_the_platform_approver_decides_a_memory_review() -> None:
    request = _held_review()
    approver = _person("approver", APPROVER)

    uow = _UoW(_Approvals(request))

    await _decide(uow, approver)

    assert request.status is ApprovalStatus.APPROVED
    [decision] = uow.approvals.decisions
    assert decision.decided_by.value == approver.principal_id
    [event] = uow.outbox.events
    assert event.event_type == MEMORY_REVIEW_DECIDED
