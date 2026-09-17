"""The workspace roster against a real database, under the app role.

Owners and assignees are stored as bare user ids, so this query is what turns
them into people. It is worth an integration test rather than a fake for one
reason: it reads across the tenancy boundary by design - ``platform.users`` has
no tenant column and carries every user in the deployment - and only real RLS
proves that the join off ``memberships`` keeps a caller inside their own tenant.
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
from dw_platform.adapters.persistence.directory import SqlWorkspaceDirectory
from dw_platform.application.access_context import AccessContext
from dw_platform.testing.seed_env import seed_test_env

pytestmark = pytest.mark.integration


@pytest.fixture
async def migrator_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.migrator, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    yield engine
    await engine.dispose()


async def workspace_of(engine: AsyncEngine, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with engine.connect() as conn:
        tenant_id = (
            await conn.execute(sa.select(tables.tenants.c.id).where(tables.tenants.c.slug == slug))
        ).scalar_one()
        workspace_id = (
            await conn.execute(
                sa.select(tables.workspaces.c.id).where(
                    tables.workspaces.c.tenant_id == tenant_id,
                    # The seed's own workspace. The admin-console tests create
                    # more inside this same tenant, so "the one workspace" stopped
                    # being a thing that exists and this asked for it by name.
                    tables.workspaces.c.slug == "main",
                )
            )
        ).scalar_one()
    return tenant_id, workspace_id


def context_for(tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> AccessContext:
    return AccessContext(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        principal_id=uuid.uuid4(),
        roles=frozenset({"member"}),
        scopes=frozenset({"directory.read"}),
        groups=frozenset(),
        clearance="internal",
        plan_id="professional",
        feature_flags=frozenset(),
    )


async def test_the_roster_is_the_callers_workspace_only(
    db_urls: DatabaseUrls, migrator_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    await seed_test_env(db_urls.migrator)
    alpha = await workspace_of(migrator_engine, "tenant-alpha")
    beta = await workspace_of(migrator_engine, "tenant-beta")

    directory = SqlWorkspaceDirectory(
        async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    )

    alpha_members = await directory.list_members(context_for(*alpha))
    beta_members = await directory.list_members(context_for(*beta))

    alpha_names = {member.display_name for member in alpha_members}
    beta_names = {member.display_name for member in beta_members}

    assert "Nguyễn Văn An" in alpha_names
    assert "Phạm Quốc Bảo" in beta_names
    # platform.users holds every user in the deployment, so a query that read it
    # before narrowing would put Beta's people in Alpha's picker.
    assert alpha_names.isdisjoint(beta_names)


async def test_members_carry_the_fields_a_picker_needs(
    db_urls: DatabaseUrls, migrator_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    await seed_test_env(db_urls.migrator)
    alpha = await workspace_of(migrator_engine, "tenant-alpha")

    directory = SqlWorkspaceDirectory(
        async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    )
    members = await directory.list_members(context_for(*alpha))

    an = next(m for m in members if m.display_name == "Nguyễn Văn An")
    assert an.email == "an.nguyen@alpha.local"
    assert "member" in an.role_keys
    assert an.department == "kinh-doanh"
    # The picker order must not shuffle between requests, which is what this
    # asserts — by asking twice, not by comparing against Python's `sorted`.
    #
    # That comparison is what used to be here, and it was the wrong oracle:
    # Postgres orders by its collation, which is linguistic and case-blind,
    # while Python compares code points and so puts every capitalised name
    # before every lowercase one. The two happened to agree while all the
    # seeded names were capitalised Vietnamese, and disagreed the moment a
    # lowercase ASCII name existed in the workspace.
    again = await directory.list_members(context_for(*alpha))
    assert [m.display_name for m in again] == [m.display_name for m in members]


async def test_candidates_never_leak_another_tenants_identities(
    db_urls: DatabaseUrls, migrator_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    """The grant picker suggests people already in the caller's tenant. A fresh
    (empty) workspace inside Alpha therefore lists Alpha's people as candidates —
    but Beta's roster must never appear, however the picker is opened."""
    await seed_test_env(db_urls.migrator)
    alpha_tenant, _ = await workspace_of(migrator_engine, "tenant-alpha")

    directory = SqlWorkspaceDirectory(
        async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    )
    # A brand-new workspace in Alpha: nobody is a member yet, so every Alpha
    # identity is a candidate — the widest the query ever goes.
    candidates = await directory.list_candidates(context_for(alpha_tenant, uuid.uuid4()))

    names = {c.display_name for c in candidates}
    assert "Nguyễn Văn An" in names  # an Alpha identity is suggested
    # Beta belongs to another company; its people must not surface here.
    assert "Phạm Quốc Bảo" not in names
    assert all(c.email is None or "beta" not in c.email for c in candidates)


async def test_an_empty_workspace_returns_nothing_rather_than_everyone(
    db_urls: DatabaseUrls, migrator_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    """A workspace nobody belongs to must not fall back to the whole tenant."""
    await seed_test_env(db_urls.migrator)
    alpha_tenant, _ = await workspace_of(migrator_engine, "tenant-alpha")

    directory = SqlWorkspaceDirectory(
        async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    )
    members = await directory.list_members(context_for(alpha_tenant, uuid.uuid4()))

    assert members == []
