"""Migration 445f93c2ea2a: every `memory.review` carries the `memory.review` stamp.

On a database of its own, stopped at the revision before it: rows the memory
service wrote unstamped are stamped by the upgrade (pending and decided alike,
since the stamp also decides who may read one), the CHECK it adds then holds,
and the downgrade takes both back so the code before it finds its reviews.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls, database_urls, recreate_database, run_alembic
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from dw_platform.testing.seed_env import seed_test_env, sid

pytestmark = pytest.mark.integration

_DB = "dw_test_memory_review_stamp_migration"
_BEFORE = "271bdb87af91"
_TENANT = sid("tenant", "tenant-alpha")
_WORKSPACE = sid("workspace", "tenant-alpha:main")


async def _at_the_revision_before() -> DatabaseUrls:
    urls = database_urls(_DB)
    await recreate_database(urls.admin, _DB)
    result = run_alembic(["upgrade", _BEFORE], urls.migrator)
    assert result.returncode == 0, result.stderr
    await seed_test_env(urls.migrator)
    return urls


async def _insert(urls: DatabaseUrls, status: str) -> uuid.UUID:
    approval_id = uuid.uuid4()
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO platform.approval_requests"
                    " (id, tenant_id, workspace_id, approval_type, requested_by, payload, status)"
                    " VALUES (:id, :t, :w, 'memory.review', :u, '{}'::jsonb, :s)"
                ),
                {"id": approval_id, "t": _TENANT, "w": _WORKSPACE, "u": uuid.uuid4(), "s": status},
            )
    finally:
        await engine.dispose()
    return approval_id


async def _stamps(urls: DatabaseUrls, *ids: uuid.UUID) -> list[str | None]:
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return [
                (
                    await conn.execute(
                        sa.text(
                            "SELECT required_scope FROM platform.approval_requests WHERE id = :id"
                        ),
                        {"id": approval_id},
                    )
                ).scalar_one()
                for approval_id in ids
            ]
    finally:
        await engine.dispose()


async def test_reviews_written_unstamped_are_stamped_and_unstamped_on_downgrade() -> None:
    urls = await _at_the_revision_before()
    pending = await _insert(urls, "pending")
    decided = await _insert(urls, "approved")

    upgraded = run_alembic(["upgrade", "head"], urls.migrator)
    assert upgraded.returncode == 0, upgraded.stderr
    assert await _stamps(urls, pending, decided) == ["memory.review", "memory.review"]

    downgraded = run_alembic(["downgrade", _BEFORE], urls.migrator)
    assert downgraded.returncode == 0, downgraded.stderr
    assert await _stamps(urls, pending, decided) == [None, None]
