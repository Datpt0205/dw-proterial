"""Integration: the approvals inbox filters as `ApprovalAudience.may_see` decides.

The inbox's filter is SQL (`SqlApprovalRepository.list_pending`) and the
single-request read and the decision ask the Python rule; two copies of one
rule have to agree, so this asks the database for every caller and request
in a small matrix and compares (failure-modes #2). A request stamped with
its own decide scope is listed to holders of that scope and to its
requester, never to a holder of `approvals.decide` alone.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.pagination import PageQuery, page_request
from dw_platform.adapters.persistence.repositories import SqlApprovalRepository
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.domain.approval import ApprovalAudience, ApprovalRequest

pytestmark = pytest.mark.integration


@pytest.fixture
async def sessions(db_urls: DatabaseUrls) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def test_the_inbox_lists_exactly_what_the_audience_may_see(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    tenant, workspace, elsewhere = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    asker, manager, head, viewer = (uuid.uuid4() for _ in range(4))

    def request(approval_type: str, payload: dict[str, object], ws: uuid.UUID) -> ApprovalRequest:
        return ApprovalRequest(
            id=uuid.uuid4(),
            tenant_id=TenantId(tenant),
            workspace_id=WorkspaceId(ws),
            approval_type=approval_type,
            requested_by=UserId(asker),
            reason="test",
            payload=payload,
        )

    requests = [
        request("sales.quote", {"decide_scope": "sales.quote.approve"}, workspace),
        request("demo.dispatch", {}, workspace),
        request("sales.quote", {"decide_scope": "sales.quote.approve"}, elsewhere),
    ]
    scope = TenantScope(tenant_id=tenant, workspace_id=workspace)
    async with tenant_session(sessions, scope) as session:
        for each in requests:
            await SqlApprovalRepository(session).add(each)

    audiences = {
        "asker": ApprovalAudience(asker, workspace, frozenset({"approvals.read"})),
        "manager": ApprovalAudience(manager, workspace, frozenset({"approvals.decide"})),
        "head": ApprovalAudience(head, workspace, frozenset({"sales.quote.approve"})),
        "viewer": ApprovalAudience(viewer, workspace, frozenset({"approvals.read"})),
        "admin": ApprovalAudience(viewer, workspace, frozenset(), unrestricted=True),
    }
    page = page_request(limit=50, cursor=None, query=PageQuery(key="approvals.pending"))
    for name, audience in audiences.items():
        async with tenant_session(sessions, scope) as session:
            listed = await SqlApprovalRepository(session).list_pending(page, audience)
        expected = {r.id for r in requests if audience.may_see(r)}
        assert {r.id for r in listed.items} == expected, name

    # The matrix is not vacuous: each answer differs from some other.
    sales, plain, _ = requests
    assert audiences["head"].may_see(sales) and not audiences["manager"].may_see(sales)
    assert audiences["manager"].may_see(plain) and not audiences["viewer"].may_see(plain)
    assert audiences["asker"].may_see(sales) and not audiences["admin"].may_see(requests[2])
