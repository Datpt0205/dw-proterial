"""DW2's automation lane against a real database: its service account
resolved by the platform like any member and cut to the lane's scopes, the
workspaces with work found through the one cross-tenant read, a request
read from the mailbox and sent to its approver as the account, the lane's
own audit rows, and another tenant untouched."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from purchasing_harness import Tenancy
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.domain.audit import system_actor
from dw_purchasing.adapters.assembly import automation_lane, build_purchasing
from dw_purchasing.application.automation_lane import LANE, LANE_CEILING, dw2_subject
from dw_purchasing.application.ports import NoNotices
from dw_purchasing.testing.seed_accounts import seed_dw2_account

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[5]
NOW = datetime(2026, 11, 2, 1, 0, tzinfo=UTC)


async def _seed(migrator: AsyncEngine, tenancy: Tenancy) -> dict[uuid.UUID, uuid.UUID]:
    """DW2's account in both tenants, each tenant on a plan (a tenant with no
    plan resolves no account, as the platform's lookup refuses it)."""
    async with migrator.begin() as conn:
        for tenant in (tenancy.alpha[0], tenancy.beta[0]):
            await conn.execute(
                sa.text(
                    "INSERT INTO platform.entitlements (id, tenant_id, plan_id, feature_overrides)"
                    " VALUES (:id, :t, 'professional', '[]'::jsonb) ON CONFLICT DO NOTHING"
                ),
                {"id": uuid.uuid4(), "t": tenant},
            )
        return await seed_dw2_account(conn, [tenancy.alpha, tenancy.beta])


def _lane(sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy) -> object:
    services = build_purchasing(
        demo_scope=tenancy.alpha,
        configs=REPO / "configs",
        session_factory=sessions,
        audit=SqlAuditRepository,
        approvals=SqlApprovalRepository,
        authorization=ScopeAuthorizationService(),
        model=None,
        clock=FixedClock(NOW),
        ids=Uuid4Generator(),
        deployed=False,
        notices=NoNotices(),
    )
    return automation_lane(
        services=services,
        session_factory=sessions,
        audit=SqlAuditRepository,
        approvals=SqlApprovalRepository,
        access=SqlMembershipLookup(sessions),
        mailboxes=(tenancy.alpha,),
        notices=NoNotices(),
        clock=FixedClock(NOW),
        ids=Uuid4Generator(),
    )


async def test_the_account_is_resolved_and_cut_to_the_lanes_scopes(
    app_sessions: async_sessionmaker[AsyncSession], migrator: AsyncEngine, tenancy: Tenancy
) -> None:
    users = await _seed(migrator, tenancy)
    lookup = SqlMembershipLookup(app_sessions)
    access = await lookup.find_service_access(
        dw2_subject(tenancy.alpha[0]), *tenancy.alpha, LANE_CEILING
    )
    assert access is not None and access.principal_id == users[tenancy.alpha[0]]
    assert access.scopes == LANE_CEILING
    # The account approves nothing, whatever it is asked for.
    wider = await lookup.find_service_access(
        dw2_subject(tenancy.alpha[0]),
        *tenancy.alpha,
        LANE_CEILING | {"purchasing.approve.tier1", "approvals.decide"},
    )
    assert wider is not None and wider.scopes == LANE_CEILING
    # Another tenant's subject finds nothing here.
    assert (
        await lookup.find_service_access(dw2_subject(tenancy.beta[0]), *tenancy.alpha, LANE_CEILING)
        is None
    )


async def test_a_received_case_is_sent_as_the_account_and_the_lane_audits_as_itself(
    app_sessions: async_sessionmaker[AsyncSession], migrator: AsyncEngine, tenancy: Tenancy
) -> None:
    from dw_purchasing.adapters.mock.inbox import MockInbox  # noqa: F401 (the demo mailbox)
    from dw_purchasing.adapters.persistence.store import SqlPurchasingStore
    from dw_purchasing.domain.cases import CaseStatus
    from dw_purchasing.testing.world import caller

    users = await _seed(migrator, tenancy)
    lane = _lane(app_sessions, tenancy)
    services = lane.services  # type: ignore[attr-defined]
    me = caller(tenancy.alpha)
    form = json.loads(
        json.dumps(
            {
                "pr_no": "PR-2611-030",
                "department": "Kho",
                "requester": "Trần Văn Kho",
                "budget_code": "CC-WH-01",
                "currency": "VND",
                "lines": [{"line_no": 1, "description": "Pallet", "quantity": "2", "unit": "cái"}],
            }
        )
    )
    from dw_purchasing.domain.requests import PurchaseRequest

    received = await services.requests.submit_form(me, PurchaseRequest.model_validate(form))
    other = await services.requests.submit_form(
        caller(tenancy.beta), PurchaseRequest.model_validate(form)
    )
    due = await lane.due()  # type: ignore[attr-defined]
    assert tenancy.alpha in due and tenancy.beta in due

    await lane.tick(*tenancy.alpha)  # type: ignore[attr-defined]

    store = SqlPurchasingStore(app_sessions, SqlAuditRepository, SqlApprovalRepository)
    async with store(me) as work:
        sent = await work.cases.get(received.case_id)
    assert sent is not None and sent.status is CaseStatus.AWAITING_APPROVAL
    assert sent.approval is not None and sent.approval.submitted_by == users[tenancy.alpha[0]]
    async with store(caller(tenancy.beta)) as work:
        untouched = await work.cases.get(other.case_id)
    assert untouched is not None and untouched.status is CaseStatus.RECEIVED
    async with migrator.connect() as conn:
        actors = {
            row.action: row.actor_id
            for row in await conn.execute(
                sa.text(
                    "SELECT action, actor_id FROM platform.audit_events WHERE resource_id = :id"
                ),
                {"id": str(received.case_id)},
            )
        }
    assert actors["purchasing.automation.submitted"] == system_actor(LANE).value
    assert actors["purchasing.request.submitted"] == users[tenancy.alpha[0]]
    assert uuid.UUID(int=0) not in actors.values()
