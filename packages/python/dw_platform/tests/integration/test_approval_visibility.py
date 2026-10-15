"""Integration: who sees a stamped approval (ADR 0004, amendment 2026-10-07).

A request stamped with `required_scope` is listed and served only to someone who
may decide it (`approvals.decide` and the stamp, `platform_admin` passing the
first and never the second) and to its requester. Everyone else in the
workspace finds nothing, the same as a request that never existed. An unstamped
request stays visible to every member, as before.

Real Postgres, because the filter is SQL (`repositories.visible_to`) while the
decision and the page ask the Python rule (`ApprovalAudience.may_see`): two
copies of one rule have to agree, so every reader is checked against a table
written out here AND against the Python rule (failure-modes #2). The last
decision on a request (`latest_decision`, which carries the decider's comment)
is read under the same rule.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.pagination import PageQuery, PageRequest
from dw_platform.adapters.persistence.approval_queries import SqlPendingApprovalQuery
from dw_platform.adapters.persistence.repositories import SqlApprovalRepository
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.adapters.persistence.uow import SqlPlatformUnitOfWorkFactory
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience, ScopeAuthorizationService
from dw_platform.domain.approval import ApprovalDecision, ApprovalRequest, DecisionOutcome

pytestmark = pytest.mark.integration

BOARD = "demo.approve.board"
_PREFIX = "demo.visibility."
_PAGE = PageRequest(limit=50, after=None, query=PageQuery(key="test.approval_visibility"))
_AUTHZ = ScopeAuthorizationService()


@pytest.fixture
async def sessions(db_urls: DatabaseUrls) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


def _caller(
    tenant: uuid.UUID, workspace: uuid.UUID, *scopes: str, admin: bool = False
) -> AccessContext:
    return AccessContext(
        tenant_id=tenant,
        workspace_id=workspace,
        principal_id=uuid.uuid4(),
        roles=frozenset({"platform_admin"} if admin else {"member"}),
        scopes=frozenset({"approvals.read", *scopes}),
        plan_id="professional",
    )


async def _raise(
    sessions: async_sessionmaker[AsyncSession],
    requester: AccessContext,
    required_scope: str | None,
) -> ApprovalRequest:
    request = ApprovalRequest(
        id=uuid.uuid4(),
        tenant_id=TenantId(requester.tenant_id),
        workspace_id=WorkspaceId(requester.workspace_id),
        approval_type=f"{_PREFIX}dispatch",
        requested_by=UserId(requester.principal_id),
        reason="test",
        payload={"note": "the decider's working material"},
        required_scope=required_scope,
    )
    async with SqlPlatformUnitOfWorkFactory(sessions)(requester) as uow:
        await uow.approvals.add(request)
        await uow.commit()
    return request


async def _reads(
    sessions: async_sessionmaker[AsyncSession],
    caller: AccessContext,
    requests: list[ApprovalRequest],
) -> tuple[set[uuid.UUID], set[uuid.UUID], set[uuid.UUID], int]:
    """What `caller` finds through every reader: the inbox, by id, and the
    context-facing pending query (rows and count)."""
    audience = ApprovalAudience.of(caller, _AUTHZ)
    async with SqlPlatformUnitOfWorkFactory(sessions)(caller) as uow:
        inbox = await uow.approvals.list_pending(
            _PAGE, workspace_id=caller.workspace_id, audience=audience
        )
        by_id = {
            r.id
            for r in requests
            if await uow.approvals.get(r.id, workspace_id=caller.workspace_id, audience=audience)
        }
    total, rows = await SqlPendingApprovalQuery(sessions, _AUTHZ).list_pending_by_type_prefix(
        caller, prefix=_PREFIX, limit=50
    )
    return {r.id for r in inbox.items}, by_id, {r.id for r in rows}, total


async def test_a_stamped_approval_is_seen_by_its_deciders_and_its_requester_only(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    tenant, workspace = uuid.uuid4(), uuid.uuid4()
    requester = _caller(tenant, workspace)
    stamped = await _raise(sessions, requester, BOARD)
    unstamped = await _raise(sessions, requester, None)
    requests = [stamped, unstamped]

    both, unstamped_only = {stamped.id, unstamped.id}, {unstamped.id}
    expected = {
        "requester": (requester, both),
        "member": (_caller(tenant, workspace), unstamped_only),
        "decide-right-only": (_caller(tenant, workspace, "approvals.decide"), unstamped_only),
        "stamp-without-decide-right": (_caller(tenant, workspace, BOARD), unstamped_only),
        "board": (_caller(tenant, workspace, "approvals.decide", BOARD), both),
        "admin-without-stamp": (_caller(tenant, workspace, admin=True), unstamped_only),
        "admin-with-stamp": (_caller(tenant, workspace, BOARD, admin=True), both),
    }

    for name, (caller, visible) in expected.items():
        inbox, by_id, queried, total = await _reads(sessions, caller, requests)
        assert inbox == visible, f"inbox: {name}"
        assert by_id == visible, f"by id: {name}"
        assert queried == visible and total == len(visible), f"pending query: {name}"
        # The SQL and the rule the decision asks are one answer.
        audience = ApprovalAudience.of(caller, _AUTHZ)
        assert {r.id for r in requests if audience.may_see(r)} == visible, f"may_see: {name}"


async def test_the_audience_does_not_widen_across_workspaces(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The holder of the stamp in W2 does not see W1's stamped request: the
    audience narrows within the workspace filter, never beside it."""
    tenant = uuid.uuid4()
    requester = _caller(tenant, uuid.uuid4())
    stamped = await _raise(sessions, requester, BOARD)
    elsewhere = _caller(tenant, uuid.uuid4(), "approvals.decide", BOARD)

    inbox, by_id, queried, total = await _reads(sessions, elsewhere, [stamped])

    assert (inbox, by_id, queried, total) == (set(), set(), set(), 0)


async def test_a_decision_is_read_by_the_requests_audience_in_its_workspace_only(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """`latest_decision` returns the decider's comment, so it is `get`'s rule
    or nothing: another tenant (even under this workspace's id, which UUIDs do
    not tie to a tenant), another workspace of this tenant, and someone in the
    workspace the stamp keeps out all read no decision."""
    tenant, workspace = uuid.uuid4(), uuid.uuid4()
    requester = _caller(tenant, workspace)
    stamped = await _raise(sessions, requester, BOARD)
    board = _caller(tenant, workspace, "approvals.decide", BOARD)
    decision = ApprovalDecision(
        id=uuid.uuid4(),
        request_id=stamped.id,
        tenant_id=TenantId(tenant),
        workspace_id=WorkspaceId(workspace),
        decided_by=UserId(board.principal_id),
        outcome=DecisionOutcome.REJECTED,
        comment="the head's reason, for this workspace only",
        decided_at=datetime.now(UTC),
    )
    async with SqlPlatformUnitOfWorkFactory(sessions)(board) as uow:
        await uow.approvals.add_decision(decision)
        await uow.commit()

    async def read(caller: AccessContext) -> ApprovalDecision | None:
        # The repository itself: the unit of work's port does not carry this
        # read, which contexts reach through their own narrow port.
        async with tenant_session(sessions, TenantScope.from_access_context(caller)) as session:
            return await SqlApprovalRepository(session).latest_decision(
                stamped.id,
                workspace_id=caller.workspace_id,
                audience=ApprovalAudience.of(caller, _AUTHZ),
            )

    other_tenant = uuid.uuid4()
    nothing = {
        "other tenant, this workspace id": _caller(
            other_tenant, workspace, "approvals.decide", BOARD
        ),
        "other tenant, its own workspace": _caller(
            other_tenant, uuid.uuid4(), "approvals.decide", BOARD
        ),
        "this tenant, another workspace": _caller(tenant, uuid.uuid4(), "approvals.decide", BOARD),
        "this workspace, outside the stamp": _caller(tenant, workspace, "approvals.decide"),
    }
    for name, caller in nothing.items():
        assert await read(caller) is None, name

    assert await read(board) == decision
    assert await read(requester) == decision
