"""Integration: idempotent seed, membership lookup, UoW with tenant context."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup
from dw_platform.adapters.persistence.uow import SqlPlatformUnitOfWorkFactory
from dw_platform.application.access_context import AccessContext
from dw_platform.application.identity import MembershipAccess
from dw_platform.domain.approval import ApprovalRequest, DecisionOutcome
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.outbox import OutboxEvent
from dw_platform.testing.seed_env import seed_test_env

pytestmark = pytest.mark.integration

NOW = datetime(2026, 7, 23, 11, 0, tzinfo=UTC)

# Roles and plans are owned by migration 0143, not the seed, so they are not
# listed here — a migrated database already has them and the seed leaves them
# untouched.
SEED_TABLES = ("tenants", "workspaces", "users", "memberships", "entitlements")


@pytest.fixture
async def migrator_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.migrator, poolclass=NullPool)
    yield engine
    await engine.dispose()


async def test_membership_lookup_confirms_and_denies(
    db_urls: DatabaseUrls, migrator_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    await seed_test_env(db_urls.migrator)
    async with migrator_engine.connect() as conn:
        alpha_id = (
            await conn.execute(
                sa.select(tables.tenants.c.id).where(tables.tenants.c.slug == "tenant-alpha")
            )
        ).scalar_one()
        alpha_ws = (
            await conn.execute(
                sa.select(tables.workspaces.c.id).where(
                    tables.workspaces.c.tenant_id == alpha_id,
                    # The seed's own workspace. The admin-console tests create
                    # more inside this same tenant, so "the one workspace" stopped
                    # being a thing that exists and this asked for it by name.
                    tables.workspaces.c.slug == "main",
                )
            )
        ).scalar_one()
        beta_id = (
            await conn.execute(
                sa.select(tables.tenants.c.id).where(tables.tenants.c.slug == "tenant-beta")
            )
        ).scalar_one()
        beta_ws = (
            await conn.execute(
                sa.select(tables.workspaces.c.id).where(
                    tables.workspaces.c.tenant_id == beta_id,
                    # The seed's own workspace. The admin-console tests create
                    # more inside this same tenant, so "the one workspace" stopped
                    # being a thing that exists and this asked for it by name.
                    tables.workspaces.c.slug == "main",
                )
            )
        ).scalar_one()

    lookup = SqlMembershipLookup(
        async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    )

    access = await lookup.find_access("dev|an.nguyen", "dw-dev", alpha_id, alpha_ws)
    assert access is not None
    assert access.plan_id == "professional"
    assert "knowledge.write" in access.scopes
    assert "knowledge_search" in access.feature_flags

    # Same verified subject, foreign tenant → fail closed.
    assert await lookup.find_access("dev|an.nguyen", "dw-dev", beta_id, beta_ws) is None
    assert await lookup.find_access("dev|nobody", "dw-dev", alpha_id, alpha_ws) is None


async def test_sales_roles_resolve_to_the_authority_they_claim(
    db_urls: DatabaseUrls, migrator_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    """The workbench branches on role names; this pins what each one may do.

    Hiding a link is navigation, so the guarantee that matters is the scope set a
    role resolves to. Executive is the one that has to be checked rather than
    assumed: it is the only tier whose read-only character is a permission
    boundary and not a layout choice.
    """
    await seed_test_env(db_urls.migrator)
    async with migrator_engine.connect() as conn:
        alpha_id = (
            await conn.execute(
                sa.select(tables.tenants.c.id).where(tables.tenants.c.slug == "tenant-alpha")
            )
        ).scalar_one()
        alpha_ws = (
            await conn.execute(
                sa.select(tables.workspaces.c.id).where(
                    tables.workspaces.c.tenant_id == alpha_id,
                    # The seed's own workspace. The admin-console tests create
                    # more inside this same tenant, so "the one workspace" stopped
                    # being a thing that exists and this asked for it by name.
                    tables.workspaces.c.slug == "main",
                )
            )
        ).scalar_one()

    lookup = SqlMembershipLookup(
        async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    )

    async def access_for(subject: str) -> MembershipAccess:
        found = await lookup.find_access(subject, "dw-dev", alpha_id, alpha_ws)
        assert found is not None, subject
        return found

    sales = await access_for("dev|an.nguyen")
    assert "crm.lead.write" in sales.scopes
    assert "approvals.decide" not in sales.scopes
    assert "intel.portal.write" not in sales.scopes
    # Spec 013's role table puts a BD outside the Report tab entirely. Hiding
    # the tab is navigation; this is the gate.
    assert "crm.report.read" not in sales.scopes

    # Account manager is an organisational split, not a permission one: the title
    # itself carries a salesperson's authority and none of a manager's. What she
    # holds on top - `approvals.decide` - arrives from the `approver_boost`
    # permission set the seed assigns to HER, which is the distinction worth
    # asserting. Stated about her own scopes rather than as equality with another
    # seeded user, because a permission set granted to that user by another test
    # would otherwise fail this one for no reason a reader could act on.
    account_manager = await access_for("dev|dieu.hoang")
    assert "crm.lead.write" in account_manager.scopes
    # The Report tab opens for an AM (their own rows) but they cannot change
    # what everyone else sees.
    assert "crm.report.read" in account_manager.scopes
    assert "crm.report.write" not in account_manager.scopes
    assert "approvals.decide" in account_manager.scopes, "from the set, not the role"
    assert "intel.portal.write" not in account_manager.scopes, "still not a manager"

    manager = await access_for("dev|binh.tran")
    assert {"approvals.decide", "intel.portal.write"} <= manager.scopes
    assert sales.scopes < manager.scopes

    # Director sits above manager on the reporting tree the seed builds, and the
    # one thing the title adds is the workspace-wide dashboard: a manager reads
    # their own subtree, a director reads the whole floor. Everything else a
    # manager may do, a director may do.
    director = await access_for("dev|giang.do")
    assert manager.scopes < director.scopes
    # What the title adds is workspace-wide READING - the whole floor's numbers,
    # the whole floor's records. Asserted by the shape of the scope rather than
    # by listing them, so the next thing leadership learns to read across the
    # workspace does not fail an assertion that is about the org chart.
    #
    # The shape is ".read", not ".all.read": `crm.lead.team.read` is a
    # workspace-wide read that has never been spelled that way, and pinning the
    # narrower spelling made this assertion fail on a scope it was written to
    # allow. One named exception since spec 013: `crm.report.write` edits a
    # report DEFINITION - a shared view of the floor's numbers rather than a
    # customer record, and the Chief Sales Director owns which columns the floor
    # reads. Named rather than folded into the shape, so a second write scope
    # arriving at this tier still fails here.
    added = director.scopes - manager.scopes
    assert all(scope.endswith(".read") or scope == "crm.report.write" for scope in added), sorted(
        added
    )
    assert "crm.dashboard.all.read" in director.scopes
    assert "crm.records.all.read" in director.scopes
    assert "crm.report.write" in director.scopes

    executive = await access_for("dev|ha.vu")
    assert "crm.account.read" in executive.scopes
    # The tier writes no customer data. Two exceptions, both named: talking to
    # the assistant, and editing a report definition (spec 013 role table -
    # leadership decides which columns the floor reads). Neither reaches a
    # record, so the guarantee below still holds: what the assistant proposes
    # stops at the approval spine.
    assert not any(
        scope.endswith(".write")
        for scope in executive.scopes - {"sales_chat.write", "crm.report.write"}
    )
    assert "sales_chat.write" in executive.scopes
    assert "approvals.decide" not in executive.scopes

    admin = await access_for("dev|chi.le")
    assert "platform.admin" in admin.scopes


async def test_uow_persists_approval_audit_outbox_under_rls(
    db_urls: DatabaseUrls, migrator_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    await seed_test_env(db_urls.migrator)
    async with migrator_engine.connect() as conn:
        alpha_id = (
            await conn.execute(
                sa.select(tables.tenants.c.id).where(tables.tenants.c.slug == "tenant-alpha")
            )
        ).scalar_one()
        alpha_ws = (
            await conn.execute(
                sa.select(tables.workspaces.c.id).where(
                    tables.workspaces.c.tenant_id == alpha_id,
                    # The seed's own workspace. The admin-console tests create
                    # more inside this same tenant, so "the one workspace" stopped
                    # being a thing that exists and this asked for it by name.
                    tables.workspaces.c.slug == "main",
                )
            )
        ).scalar_one()

    context = AccessContext(
        tenant_id=alpha_id,
        workspace_id=alpha_ws,
        principal_id=uuid.uuid4(),
        roles=frozenset({"member"}),
        scopes=frozenset({"demo.write"}),
        plan_id="professional",
    )
    factory = SqlPlatformUnitOfWorkFactory(
        async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    )

    request = ApprovalRequest(
        id=uuid.uuid4(),
        tenant_id=TenantId(alpha_id),
        workspace_id=WorkspaceId(alpha_ws),
        approval_type="demo.dispatch",
        requested_by=UserId(context.principal_id),
        reason="integration test",
    )
    async with factory(context) as uow:
        await uow.approvals.add(request)
        await uow.audit.append(
            AuditEvent(
                id=uuid.uuid4(),
                tenant_id=TenantId(alpha_id),
                workspace_id=WorkspaceId(alpha_ws),
                actor_id=UserId(context.principal_id),
                action="approval.requested",
                resource_type="approval_request",
                resource_id=str(request.id),
                occurred_at=NOW,
            )
        )
        await uow.outbox.add(
            OutboxEvent(
                id=uuid.uuid4(),
                tenant_id=TenantId(alpha_id),
                workspace_id=WorkspaceId(alpha_ws),
                event_type="platform.approval.requested",
                schema_version="1.0",
                aggregate_id=request.id,
                occurred_at=NOW,
            )
        )
        await uow.commit()

    # Read back + decide in a second transaction.
    async with factory(context) as uow:
        loaded = await uow.approvals.get(request.id)
        assert loaded is not None and loaded.status.value == "pending"
        decision = loaded.decide(
            decision_id=uuid.uuid4(),
            decided_by=UserId(context.principal_id),
            outcome=DecisionOutcome.APPROVED,
            decided_at=NOW,
        )
        await uow.approvals.save(loaded)
        await uow.approvals.add_decision(decision)
        await uow.commit()

    async with factory(context) as uow:
        final = await uow.approvals.get(request.id)
        assert final is not None and final.status.value == "approved"
        pending_outbox = await uow.outbox.list_unprocessed()
        assert any(e.aggregate_id == request.id for e in pending_outbox)
