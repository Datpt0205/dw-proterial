"""Integration: the reporting hierarchy and the roll-up resolver (ADR-003).

The seed builds a real tree in Alpha — Giang (director) over Bình (manager) over
An and Diệu — so ``visible_owner_ids`` has a subtree to roll up. The tests that
matter: the roll-up is exactly self + descendants, a cycle is refused, and the
tree never crosses a tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_kernel.errors import DomainError, NotFoundError, PermissionDeniedError
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.hierarchy_repo import SqlHierarchyRepository
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.hierarchy import HierarchyService, SetManager
from dw_platform.testing.seed_env import seed_test_env

pytestmark = pytest.mark.integration

ALPHA = uuid.UUID("d6b43d0e-c3c6-5dbc-bc08-150621bd9a5d")
ALPHA_WS = uuid.UUID("64764894-718d-5558-ba17-9a2949214063")
BETA = uuid.UUID("6634f09a-d1d7-54a6-aa23-f3f018f41f28")
BETA_WS = uuid.UUID("eda6af16-a0c4-55d3-be0b-163414390572")
ADMIN_SCOPES = frozenset({"platform.members.read", "platform.members.write"})


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


def _service(engine: AsyncEngine) -> HierarchyService:
    repo = SqlHierarchyRepository(async_sessionmaker(engine, expire_on_commit=False))
    return HierarchyService(repo, ScopeAuthorizationService(), SystemClock(), Uuid4Generator())


def _ctx(
    principal: uuid.UUID,
    *,
    tenant: uuid.UUID = ALPHA,
    workspace: uuid.UUID = ALPHA_WS,
    scopes: frozenset[str] = ADMIN_SCOPES,
) -> AccessContext:
    return AccessContext(
        tenant_id=tenant,
        workspace_id=workspace,
        principal_id=principal,
        roles=frozenset({"org_admin"}),
        scopes=scopes,
        plan_id="professional",
    )


async def _uid(engine: AsyncEngine, subject: str) -> uuid.UUID:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        row = (
            await session.execute(
                sa.select(tables.users.c.id).where(tables.users.c.subject == subject)
            )
        ).scalar_one()
    return uuid.UUID(str(row))


async def test_visible_owner_ids_rolls_up_the_subtree(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    giang = await _uid(migrator_engine, "dev|giang.do")
    binh = await _uid(migrator_engine, "dev|binh.tran")
    an = await _uid(migrator_engine, "dev|an.nguyen")
    dieu = await _uid(migrator_engine, "dev|dieu.hoang")
    svc = _service(app_engine)

    # A rep sees only their own records.
    assert await svc.visible_owner_ids(_ctx(an)) == frozenset({an})
    # Their manager rolls up to the whole team.
    assert await svc.visible_owner_ids(_ctx(binh)) == frozenset({binh, an, dieu})
    # The director sees the manager and, through them, the reps.
    assert {giang, binh, an, dieu} <= await svc.visible_owner_ids(_ctx(giang))


async def test_set_and_clear_a_manager(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    an = await _uid(migrator_engine, "dev|an.nguyen")
    giang = await _uid(migrator_engine, "dev|giang.do")
    svc = _service(app_engine)

    await svc.set_manager(_ctx(an), SetManager(user_id=an, manager_user_id=giang))
    tree = {m.user_id: m.manager_user_id for m in await svc.get_tree(_ctx(an))}
    assert tree[an] == giang

    await svc.set_manager(_ctx(an), SetManager(user_id=an, manager_user_id=None))
    tree = {m.user_id: m.manager_user_id for m in await svc.get_tree(_ctx(an))}
    assert tree[an] is None


async def test_a_cycle_is_refused(app_engine: AsyncEngine, migrator_engine: AsyncEngine) -> None:
    """Bình reports to Giang; making Giang report to An (Bình's report) would
    close a loop, so it is refused."""
    an = await _uid(migrator_engine, "dev|an.nguyen")
    giang = await _uid(migrator_engine, "dev|giang.do")
    svc = _service(app_engine)

    with pytest.raises(DomainError, match="cycle"):
        await svc.set_manager(_ctx(giang), SetManager(user_id=giang, manager_user_id=an))


async def test_self_manager_and_unknown_manager_are_refused(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    an = await _uid(migrator_engine, "dev|an.nguyen")
    svc = _service(app_engine)

    with pytest.raises(DomainError):
        await svc.set_manager(_ctx(an), SetManager(user_id=an, manager_user_id=an))
    with pytest.raises(NotFoundError):
        await svc.set_manager(_ctx(an), SetManager(user_id=an, manager_user_id=uuid.uuid4()))


async def test_a_plain_member_cannot_edit_the_hierarchy(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    an = await _uid(migrator_engine, "dev|an.nguyen")
    member = _ctx(an, scopes=frozenset({"crm.account.read"}))
    svc = _service(app_engine)
    with pytest.raises(PermissionDeniedError):
        await svc.set_manager(member, SetManager(user_id=an, manager_user_id=None))


async def test_the_tree_and_roll_up_never_cross_tenants(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    bao = await _uid(migrator_engine, "dev|bao.pham")  # a Beta member
    an = await _uid(migrator_engine, "dev|an.nguyen")  # an Alpha member
    svc = _service(app_engine)

    alpha_tree = {m.user_id for m in await svc.get_tree(_ctx(an))}
    assert an in alpha_tree and bao not in alpha_tree

    # A Beta admin's roll-up contains only Beta members.
    beta_owners = await svc.visible_owner_ids(_ctx(bao, tenant=BETA, workspace=BETA_WS))
    assert bao in beta_owners and an not in beta_owners
