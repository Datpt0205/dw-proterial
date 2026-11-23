"""DW's copy of Bravo's read tables on a migrated PostgreSQL (ticket 50,
ffd0c95da906): rows kept and replaced by Bravo's Id, a full pass marking
what it did not see as gone (and a row that comes back unmarked), errors
said per table, and one tenant's copy neither seen nor written by another.
Requires `make infra-up`."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from pg_test_db import TENANT_A, TENANT_B, database_urls, recreate_database, run_alembic
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dw_bravo.sync import SyncRow
from dw_sales.adapters.persistence.bravo_mirror import SqlBravoMirror

pytestmark = pytest.mark.integration

TEST_DB = "dw_test_bravo_mirror"
DAY = datetime(2026, 11, 21, 3, tzinfo=UTC)
NIGHT = datetime(2026, 11, 21, 14, tzinfo=UTC)


def _rv(n: int) -> str:
    return f"0x{n:016X}"


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
        await engine.dispose()

    asyncio.run(seed())
    return urls


@pytest.fixture
async def mirror(urls: object) -> AsyncIterator[SqlBravoMirror]:
    engine = create_async_engine(urls.app)  # type: ignore[attr-defined]
    yield SqlBravoMirror(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


async def test_a_full_pass_marks_what_it_did_not_see_and_a_row_that_returns_is_unmarked(
    mirror: SqlBravoMirror,
) -> None:
    store = mirror.for_tenant(TENANT_A)
    await store.keep(
        "B20LME", [SyncRow(1, _rv(1), {"Code": "A"}), SyncRow(2, _rv(2), {"Code": "B"})], NIGHT
    )
    await store.finish(
        "B20LME", last_row_version=_rv(2), at=NIGHT, full_pass_seen=frozenset({1, 2})
    )
    await store.keep("B20LME", [SyncRow(1, _rv(3), {"Code": "A2"})], DAY)

    await store.finish("B20LME", last_row_version=_rv(3), at=DAY, full_pass_seen=frozenset({1}))

    [state] = [s for s in await mirror.state(TENANT_A) if s.table == "B20LME"]
    assert (state.rows, state.gone, state.last_read_at) == (1, 1, DAY)
    cursor = await store.cursor("B20LME")
    assert (cursor.last_row_version, cursor.last_full_at) == (_rv(3), DAY)

    await store.keep("B20LME", [SyncRow(2, _rv(4), {"Code": "B"})], DAY)
    [state] = [s for s in await mirror.state(TENANT_A) if s.table == "B20LME"]
    assert (state.rows, state.gone) == (2, 0)


async def test_an_error_is_said_and_cleared_by_the_next_read(mirror: SqlBravoMirror) -> None:
    store = mirror.for_tenant(TENANT_A)

    await store.failed("B20BlackList", "Bravo did not answer: timeout", DAY)
    [state] = [s for s in await mirror.state(TENANT_A) if s.table == "B20BlackList"]
    assert state.last_error == "Bravo did not answer: timeout"
    await store.finish("B20BlackList", last_row_version=None, at=DAY, full_pass_seen=None)

    [state] = [s for s in await mirror.state(TENANT_A) if s.table == "B20BlackList"]
    assert state.last_error is None and state.last_read_at == DAY


async def test_another_tenant_neither_sees_nor_marks_a_copy(mirror: SqlBravoMirror) -> None:
    await mirror.for_tenant(TENANT_A).keep("B20ExportControlList", [SyncRow(7, _rv(7), {})], DAY)

    assert all(
        s.table != "B20ExportControlList" or s.rows == 0 for s in await mirror.state(TENANT_B)
    )
    other = mirror.for_tenant(TENANT_B)
    await other.finish(
        "B20ExportControlList", last_row_version=None, at=NIGHT, full_pass_seen=frozenset()
    )

    [mine] = [s for s in await mirror.state(TENANT_A) if s.table == "B20ExportControlList"]
    assert (mine.rows, mine.gone) == (1, 0)
