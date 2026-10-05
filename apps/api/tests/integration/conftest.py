"""The Sales API against a real database, signed in as the demo personas.

Requires `make infra-up`. Fails loudly when Postgres is unreachable:
integration tests never silently skip.

One disposable database for the session: migrated, then seeded with the
platform's dev tenants and users and the Sales roles on top (ticket 11), so
every request resolves its access context the way production does, from the
membership rows, as `dw_app`. The app is built per test with the real
composition (`dw_api.bootstrap.wiring.build_sales`): the mocks are bound to the
demo tenant, so each test starts from an empty `sales` schema, cleared by
`clean_sales`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls, database_urls, recreate_database, run_alembic
from sales_api_harness import Api, build_app
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from dw_platform.testing.seed_env import seed_test_env
from dw_sales.testing.seed_personas import seed_sales_personas

TEST_DB = "dw_test_sales_api"

# Everything a test writes: Sales state, notifications and spent keys. The
# audit log is append-only and stays; every test reads its own rows by id.
_CLEAR = (
    "TRUNCATE sales.order_cases, sales.quote_cases, sales.messages, sales.artifacts,"
    " sales.source_served, sales.worker_state, sales.case_events,"
    " platform.notifications, platform.idempotency_keys CASCADE"
)


@pytest.fixture(scope="session")
def sales_api_db() -> DatabaseUrls:
    urls = database_urls(TEST_DB)
    try:
        asyncio.run(recreate_database(urls.admin, TEST_DB))
    except (OSError, OperationalError, InterfaceError) as exc:
        pytest.fail(f"Postgres unreachable at {urls.admin!r}: run `make infra-up`. Error: {exc}")
    result = run_alembic(["upgrade", "head"], urls.migrator)
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")

    async def seed() -> None:
        await seed_test_env(urls.migrator)
        await seed_sales_personas(urls.migrator)

    asyncio.run(seed())
    return urls


@pytest.fixture
async def migrator(sales_api_db: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(sales_api_db.migrator, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def clean_sales(migrator: AsyncEngine) -> None:
    async with migrator.begin() as conn:
        await conn.execute(sa.text(_CLEAR))


@pytest.fixture
async def api(sales_api_db: DatabaseUrls, clean_sales: None) -> AsyncIterator[Api]:
    async with build_app(sales_api_db.app) as built:
        yield built
