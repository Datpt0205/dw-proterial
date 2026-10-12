"""Integration: a service account's access, as ``dw_app`` on Postgres.

``SqlMembershipLookup.find_service_access`` is how a context's digital worker
acting on its own (Sales' mailbox lane, ticket 16) gets an access context: by
its own subject, from its own membership, the way sign-in reads one, and cut
to the caller's ceiling with no role carried. What it must never do: resolve
the account in a workspace or a tenant it is not a member of, resolve it
through an external identity, or hand a role (``platform_admin``) past the
ceiling.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

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

from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup

pytestmark = pytest.mark.integration

# A stand-in ceiling: `member` holds it, `platform_admin` passes it by role.
_CEILING = frozenset({"knowledge.write"})


@pytest.fixture
async def migrator(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.migrator, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def lookup(db_urls: DatabaseUrls) -> AsyncIterator[SqlMembershipLookup]:
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    yield SqlMembershipLookup(async_sessionmaker(engine, class_=AsyncSession))
    await engine.dispose()


async def _tenant(migrator: AsyncEngine, *, status: str = "active") -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    async with migrator.begin() as conn:
        await conn.execute(
            sa.insert(tables.tenants).values(
                id=tenant_id, slug=f"t-{tenant_id.hex[:8]}", name="T", status=status
            )
        )
        await conn.execute(
            sa.insert(tables.workspaces).values(
                id=workspace_id, tenant_id=tenant_id, slug="main", name="Main"
            )
        )
        await conn.execute(
            sa.insert(tables.entitlements).values(
                id=uuid.uuid4(), tenant_id=tenant_id, plan_id="professional"
            )
        )
    return tenant_id, workspace_id


async def _account(
    migrator: AsyncEngine, where: tuple[uuid.UUID, uuid.UUID], *, roles: list[str]
) -> tuple[uuid.UUID, str]:
    """A service account (a user with no email) and its membership in ``where``."""
    user_id = uuid.uuid4()
    subject = f"service|probe|{user_id}"
    async with migrator.begin() as conn:
        await conn.execute(
            sa.insert(tables.users).values(
                id=user_id, subject=subject, display_name="Tài khoản dịch vụ (thử)"
            )
        )
        await conn.execute(
            sa.insert(tables.memberships).values(
                id=uuid.uuid4(),
                tenant_id=where[0],
                workspace_id=where[1],
                user_id=user_id,
                role_keys=roles,
            )
        )
    return user_id, subject


async def test_the_account_holds_its_membership_cut_to_the_ceiling_and_no_role(
    migrator: AsyncEngine, lookup: SqlMembershipLookup
) -> None:
    where = await _tenant(migrator)
    user_id, subject = await _account(migrator, where, roles=["member"])

    access = await lookup.find_service_access(subject, *where, _CEILING)

    assert access is not None
    assert (access.tenant_id, access.workspace_id, access.principal_id) == (*where, user_id)
    assert access.scopes == _CEILING
    assert access.roles == frozenset()
    assert access.plan_id == "professional"


async def test_platform_admin_on_the_account_passes_nothing_past_the_ceiling(
    migrator: AsyncEngine, lookup: SqlMembershipLookup
) -> None:
    """A role stands in for scopes (platform_admin passes every check), so a
    context cut to a ceiling carries none, whatever the membership was given."""
    where = await _tenant(migrator)
    _, subject = await _account(migrator, where, roles=["platform_admin", "member"])

    access = await lookup.find_service_access(subject, *where, _CEILING)

    assert access is not None
    assert access.roles == frozenset()
    assert access.scopes <= _CEILING


async def test_the_account_is_nobody_in_another_workspace_or_tenant(
    migrator: AsyncEngine, lookup: SqlMembershipLookup
) -> None:
    home = await _tenant(migrator)
    other = await _tenant(migrator)
    _, subject = await _account(migrator, home, roles=["member"])
    # The same tenant's second workspace, where it has no membership.
    second_workspace = uuid.uuid4()
    async with migrator.begin() as conn:
        await conn.execute(
            sa.insert(tables.workspaces).values(
                id=second_workspace, tenant_id=home[0], slug="second", name="Second"
            )
        )

    assert await lookup.find_service_access(subject, *other, _CEILING) is None
    assert await lookup.find_service_access(subject, home[0], second_workspace, _CEILING) is None
    # Nor its home workspace named under another tenant.
    assert await lookup.find_service_access(subject, other[0], home[1], _CEILING) is None


async def test_a_locked_tenant_resolves_no_account(
    migrator: AsyncEngine, lookup: SqlMembershipLookup
) -> None:
    where = await _tenant(migrator, status="locked")
    _, subject = await _account(migrator, where, roles=["member"])

    assert await lookup.find_service_access(subject, *where, _CEILING) is None


async def test_it_is_found_by_its_own_subject_never_through_an_external_identity(
    migrator: AsyncEngine, lookup: SqlMembershipLookup
) -> None:
    """A subject an identity provider issued for the account resolves nothing
    here: the account signs in nowhere, and its subject is the only key."""
    where = await _tenant(migrator)
    user_id, subject = await _account(migrator, where, roles=["member"])
    issued = f"kc-{uuid.uuid4()}"
    async with migrator.begin() as conn:
        await conn.execute(
            sa.insert(tables.external_identities).values(
                id=uuid.uuid4(),
                user_id=user_id,
                issuer="https://issuer.test/realms/dw",
                subject=issued,
                provider="keycloak",
            )
        )

    assert await lookup.find_service_access(issued, *where, _CEILING) is None
    assert await lookup.find_service_access(subject, *where, _CEILING) is not None
