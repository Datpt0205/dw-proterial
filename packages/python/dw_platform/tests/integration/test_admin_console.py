"""Integration: the Org Admin console — workspaces, roles, tenant settings.

Same rails as membership admin: an entry point needs a ``platform.*`` scope a
plain member lacks, and every write is bounded to the caller's tenant by RLS. The
cross-tenant test is the one that matters: an admin of one company must never see
or touch another's workspaces.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.admin_console_repo import SqlAdminConsoleRepository
from dw_platform.application.access_context import AccessContext
from dw_platform.application.admin_console import (
    AdminConsoleService,
    ArchiveWorkspace,
    CreateWorkspace,
    RenameWorkspace,
    UpdateTenantSettings,
)
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.testing.seed_env import seed_test_env

pytestmark = pytest.mark.integration

ALPHA = uuid.UUID("d6b43d0e-c3c6-5dbc-bc08-150621bd9a5d")
ALPHA_WS = uuid.UUID("64764894-718d-5558-ba17-9a2949214063")
ADMIN_SCOPES = frozenset(
    {
        "platform.members.read",
        "platform.workspaces.write",
        "platform.roles.read",
        "platform.tenant.settings.write",
    }
)


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


def _admin(tenant: uuid.UUID = ALPHA, workspace: uuid.UUID = ALPHA_WS) -> AccessContext:
    return AccessContext(
        tenant_id=tenant,
        workspace_id=workspace,
        principal_id=uuid.uuid4(),
        roles=frozenset({"org_admin"}),
        scopes=ADMIN_SCOPES,
        plan_id="professional",
    )


def _service(engine: AsyncEngine) -> AdminConsoleService:
    repo = SqlAdminConsoleRepository(async_sessionmaker(engine, expire_on_commit=False))
    return AdminConsoleService(repo, ScopeAuthorizationService(), SystemClock(), Uuid4Generator())


async def _new_tenant(migrator: AsyncEngine, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    async with migrator.begin() as conn:
        await conn.execute(
            sa.insert(tables.tenants).values(id=tenant_id, slug=slug, name=slug.upper())
        )
        await conn.execute(
            sa.insert(tables.workspaces).values(
                id=workspace_id, tenant_id=tenant_id, slug="main", name="Main"
            )
        )
    return tenant_id, workspace_id


async def test_workspace_create_list_rename_archive(app_engine: AsyncEngine) -> None:
    svc = _service(app_engine)

    created = await svc.create_workspace(
        _admin(), CreateWorkspace(name="Miền Bắc", slug="mien-bac")
    )
    assert created.slug == "mien-bac"

    listed = await svc.list_workspaces(_admin())
    mine = next(w for w in listed if w.workspace_id == created.workspace_id)
    assert mine.name == "Miền Bắc"
    assert mine.member_count == 0  # brand new, nobody in it yet
    assert mine.archived is False

    renamed = await svc.rename_workspace(
        _admin(), RenameWorkspace(workspace_id=created.workspace_id, name="Miền Bắc 2")
    )
    assert renamed.name == "Miền Bắc 2"

    await svc.archive_workspace(_admin(), ArchiveWorkspace(workspace_id=created.workspace_id))
    after = next(
        w for w in await svc.list_workspaces(_admin()) if w.workspace_id == created.workspace_id
    )
    assert after.archived is True  # archived, not deleted — the row survives


async def test_a_slug_is_unique_within_the_tenant(app_engine: AsyncEngine) -> None:
    svc = _service(app_engine)
    await svc.create_workspace(_admin(), CreateWorkspace(name="Team A", slug="dup-team"))
    with pytest.raises(ConflictError):
        await svc.create_workspace(_admin(), CreateWorkspace(name="Team B", slug="dup-team"))


async def test_workspaces_never_cross_tenants(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    """The rail that matters: an admin of one tenant neither sees nor renames a
    workspace in another, even given its id."""
    beta, beta_ws = await _new_tenant(migrator_engine, f"beta-{uuid.uuid4().hex[:8]}")
    svc = _service(app_engine)

    alpha_ws = await svc.create_workspace(
        _admin(), CreateWorkspace(name="Alpha team", slug="a-team")
    )
    beta_admin = _admin(tenant=beta, workspace=beta_ws)
    beta_ws2 = await svc.create_workspace(
        beta_admin, CreateWorkspace(name="Beta team", slug="b-team")
    )

    alpha_ids = {w.workspace_id for w in await svc.list_workspaces(_admin())}
    beta_ids = {w.workspace_id for w in await svc.list_workspaces(beta_admin)}
    assert alpha_ws.workspace_id in alpha_ids and beta_ws2.workspace_id not in alpha_ids
    assert beta_ws2.workspace_id in beta_ids and alpha_ws.workspace_id not in beta_ids

    # Beta's admin cannot rename Alpha's workspace even by id — it reads as absent.
    with pytest.raises(NotFoundError):
        await svc.rename_workspace(
            beta_admin, RenameWorkspace(workspace_id=alpha_ws.workspace_id, name="hijacked")
        )


async def test_a_plain_member_cannot_manage_workspaces(app_engine: AsyncEngine) -> None:
    svc = _service(app_engine)
    member = AccessContext(
        tenant_id=ALPHA,
        workspace_id=ALPHA_WS,
        principal_id=uuid.uuid4(),
        roles=frozenset({"sales"}),
        scopes=frozenset({"crm.account.read"}),
        plan_id="professional",
    )
    with pytest.raises(PermissionDeniedError):
        await svc.create_workspace(member, CreateWorkspace(name="Nope", slug="nope"))


async def test_roles_read_lists_the_catalog(app_engine: AsyncEngine) -> None:
    svc = _service(app_engine)
    roles = {r.key: r for r in await svc.list_roles(_admin())}
    assert "org_admin" in roles
    assert "platform.members.write" in roles["org_admin"].scopes
    assert "sales" in roles and "crm.account.write" in roles["sales"].scopes


async def test_tenant_settings_get_and_update(app_engine: AsyncEngine) -> None:
    svc = _service(app_engine)
    before = await svc.get_tenant_settings(_admin())
    assert before.slug == "tenant-alpha"

    updated = await svc.update_tenant_settings(
        _admin(),
        UpdateTenantSettings(name="FDX Corp", timezone="Asia/Ho_Chi_Minh", locale="vi-VN"),
    )
    assert updated.name == "FDX Corp"
    assert updated.timezone == "Asia/Ho_Chi_Minh"
    assert updated.locale == "vi-VN"

    again = await svc.get_tenant_settings(_admin())
    assert again.name == "FDX Corp" and again.locale == "vi-VN"
