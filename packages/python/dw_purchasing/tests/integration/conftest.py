"""Purchasing integration fixtures: a disposable migrated database on local
Postgres (`make infra-up`). Fails loudly when the database is unreachable.

Every test seeds its own tenants and workspaces (fresh ids). The runtime role
(`dw_app`) does the work: the migrator holds BYPASSRLS, so a test run as the
migrator would prove nothing about isolation.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls, database_urls, recreate_database, run_alembic
from purchasing_harness import Tenancy
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

TEST_DB = "dw_test_purchasing"


@pytest.fixture(scope="session")
def purchasing_db() -> DatabaseUrls:
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
async def app_sessions(
    purchasing_db: DatabaseUrls,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(purchasing_db.app, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def migrator(purchasing_db: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(purchasing_db.migrator, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def tenancy(migrator: AsyncEngine) -> Tenancy:
    alpha, beta = uuid.uuid4(), uuid.uuid4()
    rows = (
        (alpha, uuid.uuid4(), "mua-hang"),
        (alpha, uuid.uuid4(), "ke-toan"),
        (beta, uuid.uuid4(), "mua-hang"),
    )
    async with migrator.begin() as conn:
        for tenant in (alpha, beta):
            await conn.execute(
                sa.text("INSERT INTO platform.tenants (id, slug, name) VALUES (:t, :s, :s)"),
                {"t": tenant, "s": f"t-{tenant.hex[:12]}"},
            )
        for tenant, workspace, slug in rows:
            await conn.execute(
                sa.text(
                    "INSERT INTO platform.workspaces (id, tenant_id, slug, name)"
                    " VALUES (:w, :t, :s, :s)"
                ),
                {"w": workspace, "t": tenant, "s": slug},
            )
    (a1, a2, b) = ((t, w) for t, w, _ in rows)
    return Tenancy(alpha=a1, alpha_other=a2, beta=b)
