"""`updated_at` is maintained by the database — and yields to a deliberate value.

Two claims that sound like one:

* an UPDATE that never mentions `updated_at` gets `now()` anyway, so the column
  cannot go stale because a writer forgot;
* an UPDATE that states a value keeps it, so a repair, a backfill, or a test
  that has to place a row in the past can still do so.

The second is not a nicety. `_reap_stale_thread` settles a run whose process is
gone by comparing `updated_at` against a threshold, and the only way to reach
that branch is to age a row. While the trigger overwrote everything, no role
could — and the test covering a bug that once locked a conversation for ever
could not run at all.

Driven through the migrator, because this is a property of the schema rather
than of any application path.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration

# A time nothing in the suite could produce by accident, so an assertion that
# sees it is seeing the value this test wrote.
LONG_AGO = datetime(2019, 3, 4, 5, 6, 7, tzinfo=UTC)


@pytest.fixture
async def migrator_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.migrator, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _insert_agent_store_row(conn: AsyncConnection) -> uuid.UUID:
    """`platform.agent_store` carries the trigger and has no foreign keys."""
    tenant_id = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO platform.agent_store"
            " (tenant_id, namespace, key, value, created_at, updated_at)"
            " VALUES (:tenant, ARRAY['probe'], :key, '{}'::jsonb, now(), now())"
        ),
        {"tenant": str(tenant_id), "key": "touch"},
    )
    return tenant_id


async def test_an_update_that_forgets_the_column_still_gets_now(
    migrator_engine: AsyncEngine,
) -> None:
    async with migrator_engine.begin() as conn:
        tenant_id = await _insert_agent_store_row(conn)
        await conn.execute(
            sa.text(
                "UPDATE platform.agent_store SET updated_at = :long_ago WHERE tenant_id = :tenant"
            ),
            {"long_ago": LONG_AGO, "tenant": str(tenant_id)},
        )
        # Now the forgetful writer: value changes, timestamp is not mentioned.
        await conn.execute(
            sa.text(
                "UPDATE platform.agent_store SET value = '{\"a\": 1}'::jsonb"
                " WHERE tenant_id = :tenant"
            ),
            {"tenant": str(tenant_id)},
        )
        touched = await conn.scalar(
            sa.text("SELECT updated_at FROM platform.agent_store WHERE tenant_id = :tenant"),
            {"tenant": str(tenant_id)},
        )
        assert touched is not None and touched > LONG_AGO


async def test_an_update_that_states_a_time_keeps_it(migrator_engine: AsyncEngine) -> None:
    async with migrator_engine.begin() as conn:
        tenant_id = await _insert_agent_store_row(conn)
        await conn.execute(
            sa.text(
                "UPDATE platform.agent_store SET updated_at = :long_ago WHERE tenant_id = :tenant"
            ),
            {"long_ago": LONG_AGO, "tenant": str(tenant_id)},
        )
        stored = await conn.scalar(
            sa.text("SELECT updated_at FROM platform.agent_store WHERE tenant_id = :tenant"),
            {"tenant": str(tenant_id)},
        )
        assert stored == LONG_AGO
