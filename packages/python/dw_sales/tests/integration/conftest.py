"""Sales integration fixtures: a disposable migrated database on local Postgres.

Requires `make infra-up`. Fails loudly when the database is unreachable:
integration tests never silently skip.

Every test seeds its own tenants and workspaces (fresh ids), because the
database is shared by the whole session and a reused id collides on
`uq_workspaces_tenant_slug`. The runtime role (`dw_app`) does the work: the
migrator owns every table and holds BYPASSRLS, so a test run as the migrator
would prove nothing about isolation.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from pg_test_db import DatabaseUrls, database_urls, recreate_database, run_alembic
from sales_harness import TEST_DB, OrderRun, QuoteRun, World, run_m10, run_mailbox, seed_world
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory


@pytest.fixture(scope="session")
def sales_db() -> DatabaseUrls:
    urls = database_urls(TEST_DB)
    try:
        asyncio.run(recreate_database(urls.admin, TEST_DB))
    except (OSError, OperationalError, InterfaceError) as exc:
        pytest.fail(f"Postgres unreachable at {urls.admin!r}: run `make infra-up`. Error: {exc}")
    result = run_alembic(["upgrade", "head"], urls.migrator)
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")
    return urls


@pytest.fixture
async def app_sessions(sales_db: DatabaseUrls) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(sales_db.app, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def migrator(sales_db: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(sales_db.migrator, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def uow(app_sessions: async_sessionmaker[AsyncSession]) -> SqlSalesUnitOfWorkFactory:
    return SqlSalesUnitOfWorkFactory(app_sessions, audit=SqlAuditRepository)


@pytest.fixture
async def world(migrator: AsyncEngine) -> World:
    return await seed_world(migrator)


@pytest.fixture
async def order_run(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
) -> OrderRun:
    return await run_mailbox(uow, app_sessions, world.alpha)


@pytest.fixture
async def quote_run(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
) -> QuoteRun:
    return await run_m10(uow, app_sessions, world.alpha)


@pytest.fixture
async def sales_app_engine(sales_db: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    """A bare connection as dw_app, for asking what an unscoped caller sees."""
    engine = create_async_engine(sales_db.app, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def small_run(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
) -> OrderRun:
    """M01 (the clean order), M02 (one finding) and M11 (routed to Sales):
    enough for the tests that need a stored case, not the whole mailbox."""
    return await run_mailbox(uow, app_sessions, world.alpha, frozenset({"M01", "M02", "M11"}))
