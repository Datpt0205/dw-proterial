"""Every tenant table has RLS — asked of the catalog, not of the migrations.

`scripts/verify_invariants.py` reads migration TEXT, which is the right thing
for a check that runs without a database and catches a `CREATE TABLE` that
forgot its policy. It cannot see a table the text never names.

A partition is exactly that table. `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`
on a partitioned parent applies its policies to rows reached THROUGH the parent;
a partition addressed by its own name uses its own settings. Both default
partitions had none, and `dw_app` holds SELECT on them, so this returned every
tenant's rows with no `app.tenant_id` set at all:

    SELECT count(*) FROM platform.audit_events_default;

Found by trying it. This test is what makes the next one fail loudly — including
a partition added months from now, which Postgres will not police on its own.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration

# Schemas that hold tenant data. A new one belongs here the day it is created.
_TENANT_SCHEMAS = ("platform", "knowledge", "memory")

_TENANT_TABLES = sa.text(
    """
    SELECT n.nspname AS schema, c.relname AS name,
           c.relrowsecurity AS enabled, c.relforcerowsecurity AS forced
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r', 'p')
      AND n.nspname = ANY(:schemas)
      AND EXISTS (
          SELECT 1 FROM pg_attribute a
          WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
      )
    ORDER BY 1, 2
    """
)

_POLICIES = sa.text(
    "SELECT schemaname, tablename FROM pg_policies WHERE schemaname = ANY(:schemas)"
)


@pytest.fixture
async def session(db_urls: DatabaseUrls) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(db_urls.migrator, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as opened:
            yield opened
    finally:
        await engine.dispose()


async def test_rls_covers_every_tenant_table(session: AsyncSession) -> None:
    """Including partitions, which the text-based checker cannot see."""
    rows = (await session.execute(_TENANT_TABLES, {"schemas": list(_TENANT_SCHEMAS)})).all()
    assert rows, "found no tenant tables at all — the query is wrong, not the schema"

    missing = [f"{r.schema}.{r.name}" for r in rows if not r.enabled]
    forced_off = [f"{r.schema}.{r.name}" for r in rows if r.enabled and not r.forced]

    assert missing == [], f"tenant tables without RLS enabled: {missing}"
    # FORCE is what stops the owning role reading straight past the policy, and
    # the owner is who runs migrations and maintenance.
    assert forced_off == [], f"tenant tables with RLS but not FORCEd: {forced_off}"


async def test_every_tenant_table_actually_has_a_policy(session: AsyncSession) -> None:
    """RLS with no policy denies everything, which is safe and unusable — and
    RLS with a policy on the parent only is what this suite exists to catch."""
    rows = (await session.execute(_TENANT_TABLES, {"schemas": list(_TENANT_SCHEMAS)})).all()
    policed = {
        (r.schemaname, r.tablename)
        for r in (await session.execute(_POLICIES, {"schemas": list(_TENANT_SCHEMAS)})).all()
    }

    without = [f"{r.schema}.{r.name}" for r in rows if (r.schema, r.name) not in policed]

    assert without == [], f"tenant tables with no policy of their own: {without}"


async def test_a_partition_cannot_be_read_around_its_parent(
    db_urls: DatabaseUrls, session: AsyncSession
) -> None:
    """The leak itself, reproduced end to end.

    Written as `dw_app` over its OWN connection rather than `SET ROLE`: the
    migrator cannot assume that role, and more to the point the runtime never
    does either — it connects as `dw_app`, which is the identity whose reach
    this is about.
    """
    tenant = uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO platform.audit_events"
            " (id, tenant_id, workspace_id, actor_id, action, resource_type,"
            "  resource_id, occurred_at)"
            " VALUES (gen_random_uuid(), :t, gen_random_uuid(), gen_random_uuid(),"
            "         'rls.probe', 'probe', 'x', now())"
        ),
        {"t": tenant},
    )
    await session.commit()

    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            # No `app.tenant_id` set at all — the state a connection is in before
            # anything scopes it, and the state a bug would leave it in.
            through_parent = (
                await conn.execute(sa.text("SELECT count(*) FROM platform.audit_events"))
            ).scalar_one()
            direct = (
                await conn.execute(sa.text("SELECT count(*) FROM platform.audit_events_default"))
            ).scalar_one()
    finally:
        await engine.dispose()

    assert through_parent == 0
    assert direct == 0, "the partition returned rows the parent refused"
