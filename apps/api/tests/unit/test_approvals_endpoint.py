"""The approvals routes over the real `ApproveAndResumeService` with a fake store.

What the page reads (`required_scope`, `can_decide`, `requested_by_me`) and that the server
refuses a decision the page would have locked, called directly over HTTP with
no page in front of it (ADR 0004). Tenant isolation of the read is the
database's job, covered against a real one by `dw_agent_runtime`'s
`test_approval_decider_scope.py`.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager

from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_api.bootstrap import ApiContainer
from dw_api.health import CheckState, HealthService
from dw_api.main import create_app
from dw_api.settings import ApiSettings
from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.pagination import Page, PageRequest
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.entitlement import DEFAULT_PLANS, PlanEntitlementService
from dw_platform.application.identity import DbAccessContextFactory, MembershipAccess
from dw_platform.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    decided_event_type,
)
from dw_platform.domain.outbox import OutboxEvent

pytestmark = pytest.mark.unit

SECRET = "unit-test-secret-0123456789abcdef"
TENANT = uuid.uuid4()
WORKSPACE = uuid.uuid4()
VIEWER = uuid.uuid4()
SOMEONE_ELSE = uuid.uuid4()
BOARD_SCOPE = "demo.approve.board"


@dataclass
class FakeMembershipLookup:
    scopes: frozenset[str]
    roles: frozenset[str] = frozenset({"approver"})

    async def find_access(
        self, subject: str, issuer: str, tenant_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> MembershipAccess | None:
        if tenant_id != TENANT or workspace_id != WORKSPACE:
            return None
        return MembershipAccess(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            principal_id=VIEWER,
            roles=self.roles,
            scopes=self.scopes,
            groups=frozenset(),
            clearance="internal",
            plan_id="professional",
            feature_flags=frozenset(),
        )


@dataclass
class FakeApprovalRepo:
    """Honours the port: `save` refuses a stale version like the SQL one."""

    request: ApprovalRequest
    decisions: list[ApprovalDecision] = field(default_factory=list)
    saved_version: int = 1

    async def get(self, request_id: uuid.UUID) -> ApprovalRequest | None:
        return self.request if request_id == self.request.id else None

    async def save(self, request: ApprovalRequest) -> None:
        if request.version - 1 != self.saved_version:
            raise ConflictError("approval request was modified concurrently")
        self.saved_version = request.version

    async def add_decision(self, decision: ApprovalDecision) -> None:
        self.decisions.append(decision)

    async def add(self, request: ApprovalRequest) -> None:
        raise NotImplementedError("not exercised by the approvals routes")

    async def list_pending(self, request: PageRequest) -> Page[Any]:
        pending = self.request.status is ApprovalStatus.PENDING
        return Page(items=(self.request,) if pending else (), next_cursor=None)


@dataclass
class FakeOutbox:
    """A request with no run announces its decision through the outbox."""

    events: list[OutboxEvent] = field(default_factory=list)

    async def add(self, event: OutboxEvent) -> None:
        self.events.append(event)

    async def list_unprocessed(self, limit: int = 100) -> list[OutboxEvent]:
        raise NotImplementedError("not exercised by the approvals routes")

    async def has_unprocessed(self, event_type: str, aggregate_id: uuid.UUID) -> bool:
        raise NotImplementedError("not exercised by the approvals routes")


@dataclass
class FakeUoW:
    approvals: FakeApprovalRepo
    outbox: FakeOutbox

    async def __aenter__(self) -> "FakeUoW":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class RunnerThatMustNotRun:
    """These requests carry no run; reaching the runner would be a bug."""

    def hosts(self, **_: Any) -> bool:
        raise AssertionError("no run to host")

    async def resume(self, **_: Any) -> None:
        raise AssertionError("no run to resume")


def make_request(*, requested_by: uuid.UUID, required_scope: str | None) -> ApprovalRequest:
    return ApprovalRequest(
        id=uuid.uuid4(),
        tenant_id=TenantId(TENANT),
        workspace_id=WorkspaceId(WORKSPACE),
        approval_type="demo.action.approve",
        requested_by=UserId(requested_by),
        reason="cần duyệt",
        required_scope=required_scope,
    )


def make_container(
    repo: FakeApprovalRepo,
    scopes: frozenset[str],
    outbox: FakeOutbox | None = None,
    roles: frozenset[str] = frozenset({"approver"}),
) -> ApiContainer:
    resolved_outbox = outbox or FakeOutbox()

    async def ok_probe() -> CheckState:
        return "ok"

    def uow_factory(context: AccessContext) -> Any:
        return FakeUoW(approvals=repo, outbox=resolved_outbox)

    return ApiContainer(
        settings=ApiSettings(profile="test", dev_secret=SECRET),
        engine=None,
        health_service=HealthService(probes={"database": ok_probe}),
        token_verifier=DevTokenVerifier(SECRET),
        access_context_factory=DbAccessContextFactory(FakeMembershipLookup(scopes, roles)),
        identity_bootstrap=None,
        uow_factory=uow_factory,
        authorization=ScopeAuthorizationService(),
        entitlement=PlanEntitlementService(DEFAULT_PLANS),
        approval_flow=ApproveAndResumeService(
            uow_factory=uow_factory,
            runner=RunnerThatMustNotRun(),  # type: ignore[arg-type]
            run_store=None,  # type: ignore[arg-type]
            clock=SystemClock(),
            id_generator=Uuid4Generator(),
        ),
    )


async def _call(
    container: ApiContainer, method: str, path: str, body: dict[str, Any] | None = None
) -> httpx.Response:
    token = DevTokenVerifier(SECRET).issue("dev|approver", email="approver@fpt.com")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(TENANT),
        "X-Workspace-Id": str(WORKSPACE),
    }
    app = create_app(container)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(
                method, f"/api/v1/approvals{path}", headers=headers, json=body
            )


@pytest.mark.parametrize(
    ("requested_by", "required_scope", "mine"),
    [(SOMEONE_ELSE, BOARD_SCOPE, False), (VIEWER, None, True)],
)
async def test_the_view_carries_the_stamp_and_whose_request_it_is(
    requested_by: uuid.UUID, required_scope: str | None, mine: bool
) -> None:
    request = make_request(requested_by=requested_by, required_scope=required_scope)
    container = make_container(FakeApprovalRepo(request), frozenset({"approvals.read"}))

    response = await _call(container, "GET", f"/{request.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["required_scope"] == required_scope
    assert body["requested_by_me"] is mine
    # A boolean, not an id: no other member's identity reaches the browser.
    assert str(requested_by) not in response.text


PLATFORM_ADMIN = frozenset({"platform_admin"})


@pytest.mark.parametrize(
    ("roles", "scopes", "required_scope", "can_decide"),
    [
        (frozenset({"approver"}), {"approvals.decide", BOARD_SCOPE}, BOARD_SCOPE, True),
        (frozenset({"approver"}), {"approvals.decide"}, BOARD_SCOPE, False),
        (frozenset({"approver"}), set(), None, False),
        (PLATFORM_ADMIN, {"platform.admin"}, BOARD_SCOPE, False),
        (PLATFORM_ADMIN, {"platform.admin", BOARD_SCOPE}, BOARD_SCOPE, True),
        (PLATFORM_ADMIN, {"platform.admin"}, None, True),
    ],
    ids=[
        "holder",
        "decide-right-only",
        "no-decide-right",
        "admin-without-stamp",
        "admin-with-stamp",
        "admin-unstamped",
    ],
)
async def test_can_decide_is_the_servers_answer_in_the_list_and_the_detail(
    roles: frozenset[str], scopes: set[str], required_scope: str | None, can_decide: bool
) -> None:
    """ADR 0004: the session's `hasScope` passes `platform_admin` on every scope, so
    the page locks on this instead, built from the checks `decide` runs."""
    request = make_request(requested_by=SOMEONE_ELSE, required_scope=required_scope)
    container = make_container(
        FakeApprovalRepo(request), frozenset({"approvals.read", *scopes}), roles=roles
    )

    detail = await _call(container, "GET", f"/{request.id}")
    listed = await _call(container, "GET", "")

    assert detail.status_code == 200
    assert detail.json()["can_decide"] is can_decide
    assert [item["can_decide"] for item in listed.json()["items"]] == [can_decide]


async def test_platform_admin_without_the_stamp_is_refused_over_http() -> None:
    """The page's lock and the server's refusal are one answer: a 403 naming the
    stamp, nothing recorded."""
    request = make_request(requested_by=SOMEONE_ELSE, required_scope=BOARD_SCOPE)
    repo = FakeApprovalRepo(request)
    container = make_container(repo, frozenset({"platform.admin"}), roles=PLATFORM_ADMIN)

    response = await _call(
        container, "POST", f"/{request.id}/decisions", {"approve": True, "comment": ""}
    )

    assert response.status_code == 403
    assert response.json()["details"]["action"] == BOARD_SCOPE
    assert repo.decisions == []
    assert request.status is ApprovalStatus.PENDING


async def test_the_server_refuses_a_decision_the_page_would_have_locked() -> None:
    """No page in front: `approvals.decide` without the stamp is a 403, and
    nothing is recorded."""
    request = make_request(requested_by=SOMEONE_ELSE, required_scope=BOARD_SCOPE)
    repo = FakeApprovalRepo(request)
    container = make_container(repo, frozenset({"approvals.read", "approvals.decide"}))

    response = await _call(
        container, "POST", f"/{request.id}/decisions", {"approve": True, "comment": ""}
    )

    assert response.status_code == 403
    assert repo.decisions == []
    assert request.status is ApprovalStatus.PENDING


async def test_a_holder_of_the_stamp_decides_over_http() -> None:
    request = make_request(requested_by=SOMEONE_ELSE, required_scope=BOARD_SCOPE)
    repo = FakeApprovalRepo(request)
    outbox = FakeOutbox()
    container = make_container(
        repo, frozenset({"approvals.read", "approvals.decide", BOARD_SCOPE}), outbox
    )

    response = await _call(
        container, "POST", f"/{request.id}/decisions", {"approve": True, "comment": "đồng ý"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["required_scope"] == BOARD_SCOPE
    assert len(repo.decisions) == 1
    # No run to resume, so the decision is announced once, in its own transaction.
    assert [e.event_type for e in outbox.events] == [decided_event_type("demo.action.approve")]
