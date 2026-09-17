"""Integration: Permission Sets add scopes on top of a role (ADR-001 Phase 3).

The seed gives Diệu (an AM) the ``approver_boost`` set, so her resolved access
carries ``approvals.decide`` her role does not — the whole point. An admin can
assign another set and it shows up; a set carrying a ``platform.*`` scope is
refused to anyone but a platform admin (no escalation).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_kernel.errors import NotFoundError, PermissionDeniedError
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.admin_console_repo import SqlAdminConsoleRepository
from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup
from dw_platform.application.access_context import AccessContext
from dw_platform.application.admin_console import AdminConsoleService, SetPermissionSets
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.testing.seed_env import seed_test_env

pytestmark = pytest.mark.integration

ALPHA = uuid.UUID("d6b43d0e-c3c6-5dbc-bc08-150621bd9a5d")
ALPHA_WS = uuid.UUID("64764894-718d-5558-ba17-9a2949214063")
ISSUER = "https://issuer.test/realms/dw"
ADMIN_SCOPES = frozenset({"platform.members.read", "platform.members.write", "platform.roles.read"})


@pytest.fixture
async def app_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    await seed_test_env(db_urls.migrator)
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def migrator_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.migrator, poolclass=NullPool)
    yield engine
    await engine.dispose()


def _admin() -> AccessContext:
    return AccessContext(
        tenant_id=ALPHA,
        workspace_id=ALPHA_WS,
        principal_id=uuid.uuid4(),
        roles=frozenset({"org_admin"}),
        scopes=ADMIN_SCOPES,
        plan_id="professional",
    )


def _service(engine: AsyncEngine) -> AdminConsoleService:
    repo = SqlAdminConsoleRepository(async_sessionmaker(engine, expire_on_commit=False))
    return AdminConsoleService(repo, ScopeAuthorizationService(), SystemClock(), Uuid4Generator())


async def _uid(engine: AsyncEngine, subject: str) -> uuid.UUID:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        row = (
            await session.execute(
                sa.select(tables.users.c.id).where(tables.users.c.subject == subject)
            )
        ).scalar_one()
    return uuid.UUID(str(row))


def _lookup(engine: AsyncEngine) -> SqlMembershipLookup:
    return SqlMembershipLookup(async_sessionmaker(engine, expire_on_commit=False))


async def test_a_seeded_permission_set_adds_a_scope_the_role_lacks(
    app_engine: AsyncEngine,
) -> None:
    access = await _lookup(app_engine).find_access("dev|dieu.hoang", ISSUER, ALPHA, ALPHA_WS)
    assert access is not None
    # From the approver_boost set, not from the AM role.
    assert "approvals.decide" in access.scopes


async def test_admin_assigns_a_set_and_it_takes_effect(app_engine: AsyncEngine) -> None:
    an = await _uid(app_engine, "dev|an.nguyen")
    before = await _lookup(app_engine).find_access("dev|an.nguyen", ISSUER, ALPHA, ALPHA_WS)
    assert before is not None and "crm.broadcast.write" not in before.scopes

    await _service(app_engine).set_permission_sets(
        _admin(), SetPermissionSets(user_id=an, permission_set_keys=frozenset({"broadcaster"}))
    )

    after = await _lookup(app_engine).find_access("dev|an.nguyen", ISSUER, ALPHA, ALPHA_WS)
    assert after is not None and "crm.broadcast.write" in after.scopes


async def test_unknown_set_is_refused(app_engine: AsyncEngine) -> None:
    an = await _uid(app_engine, "dev|an.nguyen")
    with pytest.raises(NotFoundError):
        await _service(app_engine).set_permission_sets(
            _admin(), SetPermissionSets(user_id=an, permission_set_keys=frozenset({"ghost"}))
        )


async def _set_restricted(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            sa.update(tables.tenants)
            .where(tables.tenants.c.id == ALPHA)
            .values(record_visibility="restricted")
        )


async def test_platform_admin_sees_everything_in_a_restricted_tenant(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    """ADR-003 roll-up must honour the platform-admin bypass. Chi is a
    platform_admin with no place in the reporting tree, so her subtree is only
    herself. Before the fix, a restricted tenant narrowed her to that subtree and
    she saw no records at all; the bypass gives her the whole workspace (None)."""
    await _set_restricted(migrator_engine)

    chi = await _lookup(app_engine).find_access("dev|chi.le", ISSUER, ALPHA, ALPHA_WS)
    assert chi is not None
    assert chi.record_visibility == "restricted"
    assert chi.visible_owners is None  # sees everything, not just her own subtree


async def test_restricted_tenant_still_narrows_a_plain_rep(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    """The bypass is only for the admin: a plain sales rep is still rolled up to
    their own subtree, so the fix does not widen anyone it should not."""
    await _set_restricted(migrator_engine)

    an = await _lookup(app_engine).find_access("dev|an.nguyen", ISSUER, ALPHA, ALPHA_WS)
    assert an is not None
    assert an.visible_owners is not None
    assert an.visible_owners == frozenset({an.principal_id})


async def test_org_admin_cannot_assign_an_administrative_set(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    """No escalation: a set carrying a platform.* scope is a platform-admin act."""
    an = await _uid(app_engine, "dev|an.nguyen")
    async with migrator_engine.begin() as conn:
        await conn.execute(
            sa.insert(tables.permission_sets).values(
                key="superpowers", name="Superpowers", scopes=["platform.members.write"]
            )
        )

    with pytest.raises(PermissionDeniedError, match="administrative"):
        await _service(app_engine).set_permission_sets(
            _admin(),
            SetPermissionSets(user_id=an, permission_set_keys=frozenset({"superpowers"})),
        )
