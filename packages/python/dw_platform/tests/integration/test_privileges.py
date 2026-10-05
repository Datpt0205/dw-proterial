"""Integration: what the application role may and may not do.

A schema with no grants passes every health check and fails on the first real
query — the probe runs ``SELECT 1``, which needs no table privilege. That is
exactly how a baseline built with ``pg_dump --no-privileges`` shipped once:
green everywhere, and an application that could not read a row.

So the privilege model is asserted, not assumed. Three claims:

* ``dw_app`` can read and write the tables it serves;
* ``dw_app`` CANNOT rewrite the audit log — append-only is a grant, not a
  convention somebody could code around;
* ``dw_app`` cannot touch the provisioning record, which belongs to a different
  role making a different decision.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration


@pytest.fixture
async def app_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    """A connection as the runtime role, not as the migrator.

    The migrator holds BYPASSRLS and owns every object, so a test that connects
    as the migrator proves nothing about what the application is allowed to do.
    """
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_the_application_can_read_the_tables_it_serves(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        for table in (
            "platform.tenants",
            "platform.workspaces",
            "platform.users",
            "platform.memberships",
            "knowledge.documents",
            "memory.items",
            *_SALES_TABLES,
        ):
            # The count is irrelevant; being allowed to ask is the assertion.
            await conn.execute(sa.text(f"SELECT count(*) FROM {table}"))


# Migration 621864952a54. A context's schema is granted like the platform's.
_SALES_TABLES = (
    "sales.order_cases",
    "sales.order_revisions",
    "sales.order_lines",
    "sales.order_findings",
    "sales.quote_cases",
    "sales.messages",
    "sales.artifacts",
    "sales.source_served",
    "sales.worker_state",
    "sales.case_events",
)


async def test_the_application_writes_the_sales_tables_it_serves(db_urls: DatabaseUrls) -> None:
    """Asked of the catalog: the case tables take every verb, the records that
    are facts about the past take no UPDATE, and the case event log, every
    partition included, takes no UPDATE or DELETE, like the audit log."""
    migrator = create_async_engine(db_urls.migrator, poolclass=NullPool)
    try:
        async with migrator.connect() as conn:
            held = {
                (row.tbl, row.verb)
                for row in await conn.execute(
                    sa.text(
                        """
                        SELECT c.relname AS tbl, v.verb
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'])
                            AS v(verb)
                        WHERE n.nspname = 'sales' AND c.relkind IN ('r', 'p')
                          AND has_table_privilege('dw_app', c.oid, v.verb)
                        """
                    )
                )
            }
    finally:
        await migrator.dispose()

    every = {"SELECT", "INSERT", "UPDATE", "DELETE"}
    for table in ("order_cases", "order_revisions", "order_lines", "order_findings"):
        assert {verb for tbl, verb in held if tbl == table} == every, table
    for table in ("quote_cases", "messages", "worker_state"):
        assert {verb for tbl, verb in held if tbl == table} == every, table
    for table in ("artifacts", "source_served"):
        assert {verb for tbl, verb in held if tbl == table} == every - {"UPDATE"}, table
    event_tables = {tbl for tbl, _ in held if tbl.startswith("case_events")}
    assert {"case_events", "case_events_default"} <= event_tables
    for table in event_tables:
        assert {verb for tbl, verb in held if tbl == table} == {"SELECT", "INSERT"}, table


async def test_the_application_cannot_rewrite_the_audit_log(app_engine: AsyncEngine) -> None:
    """Append-only, enforced by the database.

    An UPDATE that the code would never issue is still an UPDATE the database
    must refuse: credentials reach further than the code that was reviewed.
    """
    async with app_engine.connect() as conn:
        with pytest.raises(Exception, match="permission denied"):
            await conn.execute(sa.text("UPDATE platform.audit_events SET action = 'x'"))
        await conn.rollback()
        with pytest.raises(Exception, match="permission denied"):
            await conn.execute(sa.text("DELETE FROM platform.audit_events"))


_CATALOGUE = ("platform.roles", "platform.permission_sets")


async def test_the_application_cannot_rewrite_the_role_catalogue(app_engine: AsyncEngine) -> None:
    """Which scopes a membership carries changes in migrations alone.

    No application code writes these tables, so a write under application
    credentials could only be someone widening a role past a
    separation-of-duty rule (migration 648e2f7c3edb).
    """
    async with app_engine.connect() as conn:
        for table in _CATALOGUE:
            await conn.execute(sa.text(f"SELECT count(*) FROM {table}"))
            await conn.rollback()
            for statement in (
                f"UPDATE {table} SET scopes = scopes || '[\"platform.admin\"]'::jsonb",
                f"DELETE FROM {table}",
                f"INSERT INTO {table} (key, name, scopes) VALUES ('probe', 'Probe', '[]')",
            ):
                with pytest.raises(Exception, match="permission denied"):
                    await conn.execute(sa.text(statement))
                await conn.rollback()


async def test_no_application_role_can_write_the_role_catalogue(db_urls: DatabaseUrls) -> None:
    """Asked of the catalog, so every verb and every runtime role is covered,
    `dw_provisioner` included: it is granted SELECT on roles and no more."""
    migrator = create_async_engine(db_urls.migrator, poolclass=NullPool)
    try:
        async with migrator.connect() as conn:
            writable = (
                await conn.execute(
                    sa.text(
                        """
                        SELECT r.rolname, t.tbl, v.verb
                        FROM pg_roles r
                        CROSS JOIN unnest(CAST(:tables AS text[])) AS t(tbl)
                        CROSS JOIN unnest(ARRAY['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE'])
                            AS v(verb)
                        WHERE r.rolname IN ('dw_app', 'dw_provisioner', 'dw_agent_ro')
                          AND has_table_privilege(r.rolname, t.tbl, v.verb)
                        """
                    ),
                    {"tables": list(_CATALOGUE)},
                )
            ).all()
    finally:
        await migrator.dispose()
    assert writable == []


async def test_the_application_cannot_read_the_provisioning_record(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as conn:
        with pytest.raises(Exception, match="permission denied"):
            await conn.execute(sa.text("SELECT count(*) FROM platform.provisioning_audit"))


async def test_a_table_added_later_is_readable_without_a_new_grant(
    app_engine: AsyncEngine, db_urls: DatabaseUrls
) -> None:
    """Default privileges carry, so "somebody forgot the GRANT" cannot ship.

    Written as a real table created by the migrator, because that is the case
    that goes wrong: every later migration adds tables, and each one relying on
    a hand-written grant is one release away from the failure above.
    """
    migrator = create_async_engine(db_urls.migrator, poolclass=NullPool)
    try:
        async with migrator.begin() as conn:
            await conn.execute(sa.text("CREATE TABLE platform.grant_probe (id uuid PRIMARY KEY)"))
        async with app_engine.connect() as conn:
            await conn.execute(sa.text("SELECT count(*) FROM platform.grant_probe"))
        async with migrator.begin() as conn:
            await conn.execute(sa.text("DROP TABLE platform.grant_probe"))
    finally:
        await migrator.dispose()
