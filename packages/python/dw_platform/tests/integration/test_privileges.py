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
        ):
            # The count is irrelevant; being allowed to ask is the assertion.
            await conn.execute(sa.text(f"SELECT count(*) FROM {table}"))


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
