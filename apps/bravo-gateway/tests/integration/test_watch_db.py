# ruff: noqa: E501 - SQL kept on the lines a reader runs it from
"""The change watch's tables on a migrated PostgreSQL (ticket 65): the
lane's history and pauses, a baseline accepted only by a holder of the
right and only for the latest fingerprint, nothing of one tenant visible to
another, and the gateway reading a pause. Requires `make infra-up`."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from pg_test_db import (
    TENANT_A,
    TENANT_B,
    WORKSPACE_A,
    database_urls,
    recreate_database,
    run_alembic,
)
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from dw_bravo.watch import Component, Fingerprint
from dw_bravo.watch_lane import digest_of
from dw_bravo_gateway.adapters.postgres import SqlPauses
from dw_kernel.errors import ConflictError, PermissionDeniedError
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_sales.adapters.persistence.bravo_watch import SqlBravoWatch
from dw_sales.application.bravo_watch import BravoWatchService

pytestmark = pytest.mark.integration

TEST_DB = "dw_test_bravo_watch"
NOW = datetime(2026, 11, 21, 3, tzinfo=UTC)
HEAD = uuid.UUID(int=0xA11)
FP = Fingerprint("production", NOW, (Component("columns", "B30BizDocDetailSO", "c1"),))


@pytest.fixture(scope="module")
def urls() -> object:
    urls = database_urls(TEST_DB)
    asyncio.run(recreate_database(urls.admin, TEST_DB))
    result = run_alembic(["upgrade", "head"], urls.migrator)
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")

    async def seed() -> None:
        engine = create_async_engine(urls.migrator)
        async with engine.begin() as conn:
            for tenant in (TENANT_A, TENANT_B):
                await conn.execute(
                    sa.text("INSERT INTO platform.tenants (id, slug, name) VALUES (:id, :s, :s)"),
                    {"id": tenant, "s": f"t{tenant.int:x}"},
                )
            await conn.execute(
                sa.text(
                    "INSERT INTO platform.workspaces (id, tenant_id, slug, name) VALUES (:id, :t, 'main', 'Main')"
                ),
                {"id": WORKSPACE_A, "t": TENANT_A},
            )
        await engine.dispose()

    asyncio.run(seed())
    return urls


@pytest.fixture
async def sessions(urls: object) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(urls.app)  # type: ignore[attr-defined]
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class _Clock:
    def now(self) -> datetime:
        return NOW


class _Ids:
    def new_uuid(self) -> uuid.UUID:
        return uuid.uuid4()


def _context(*scopes: str) -> AccessContext:
    return AccessContext(
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        principal_id=HEAD,
        roles=frozenset(),
        scopes=frozenset(scopes),
        plan_id="professional",
    )


def _service(sessions: async_sessionmaker[AsyncSession]) -> tuple[BravoWatchService, SqlBravoWatch]:
    store = SqlBravoWatch(sessions, SqlAuditRepository)
    service = BravoWatchService(store, ScopeAuthorizationService(), _Clock(), _Ids())
    return service, store


async def test_the_lane_keeps_a_fingerprint_once_and_merges_pause_reasons(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    service, store = _service(sessions)
    lane = store.for_tenant(TENANT_A)

    first = await lane.record(FP, digest_of(FP))
    again = await lane.record(FP, digest_of(FP))
    await lane.pause({"so.line.set_quantity@1": ["column changed"]}, first, NOW)
    await lane.pause({"so.line.set_quantity@1": ["trigger changed", "column changed"]}, first, NOW)

    assert first == again
    assert await lane.baseline("production") is None
    assert await lane.last_read("production") == NOW
    state = await service.state(_context("sales.bravo.watch.read"))
    pause = next(p for p in state.pauses if p.kind == "so.line.set_quantity@1")
    assert sorted(pause.reasons) == ["column changed", "trigger changed"]
    assert await SqlPauses(sessions).paused(TENANT_A, "so.line.set_quantity@1")
    assert not await SqlPauses(sessions).paused(TENANT_B, "so.line.set_quantity@1")


async def test_accepting_needs_the_right_and_lifts_every_pause_with_its_audit(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    service, store = _service(sessions)
    lane = store.for_tenant(TENANT_A)
    fingerprint = await lane.record(FP, digest_of(FP))
    await lane.pause({"so.create@1": ["no baseline accepted yet"]}, fingerprint, NOW)

    with pytest.raises(PermissionDeniedError):
        await service.accept(_context("sales.bravo.watch.read"), fingerprint, "UAT replay passed")
    assert (await service.state(_context("sales.bravo.watch.read"))).pauses != ()

    lifted = await service.accept(
        _context("sales.bravo.watch.accept"), fingerprint, "UAT replay R3 matched"
    )

    assert "so.create@1" in lifted
    state = await service.state(_context("sales.bravo.watch.read"))
    assert state.pauses == () and state.baseline_fingerprint == fingerprint
    assert await lane.baseline("production") == FP
    async with sessions() as session, session.begin():
        await session.execute(
            sa.text(
                "SELECT set_config('app.tenant_id', :t, true), set_config('app.workspace_id', :w, true)"
            ),
            {"t": str(TENANT_A), "w": str(WORKSPACE_A)},
        )
        audited = await session.scalar(
            sa.text(
                "SELECT count(*) FROM platform.audit_events WHERE action = 'sales.bravo.watch.baseline_accepted'"
            )
        )
    assert audited == 1


async def test_only_the_latest_fingerprint_can_be_accepted(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    service, store = _service(sessions)
    lane = store.for_tenant(TENANT_A)
    newer = Fingerprint(
        "production",
        NOW + timedelta(hours=1),
        (Component("columns", "B30BizDocDetailSO", "c9"),),
    )
    old = await lane.record(FP, digest_of(FP))
    await lane.record(newer, digest_of(newer))

    with pytest.raises(ConflictError):
        await service.accept(_context("sales.bravo.watch.accept"), old, "stale")


async def test_another_tenant_sees_and_accepts_nothing_of_this_one(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    service, store = _service(sessions)
    lane = store.for_tenant(TENANT_A)
    later = Fingerprint("production", NOW + timedelta(hours=2), (Component("columns", "X", "z"),))
    fingerprint = await lane.record(later, digest_of(later))
    await lane.pause({"so.create@1": ["x"]}, fingerprint, NOW)
    other = AccessContext(
        tenant_id=TENANT_B,
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        roles=frozenset(),
        scopes=frozenset({"sales.bravo.watch.read", "sales.bravo.watch.accept"}),
        plan_id="professional",
    )

    state = await service.state(other)
    assert state.pauses == () and state.latest_fingerprint is None
    with pytest.raises(ConflictError):
        await service.accept(other, fingerprint, "not mine")
    assert await SqlPauses(sessions).paused(TENANT_A, "so.create@1")


async def test_the_history_and_the_baselines_are_append_only(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    for statement in (
        "UPDATE bravo.watch_fingerprints SET digest = digest",
        "DELETE FROM bravo.watch_baselines",
    ):
        async with sessions() as session, session.begin():
            await session.execute(
                sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_A)}
            )
            with pytest.raises(DBAPIError, match="permission denied"):
                await session.execute(sa.text(statement))
