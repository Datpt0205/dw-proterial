"""Migration ac31ff0f2087: a Sales approval's stamp moves from the payload's
`decide_scope` into the platform's `required_scope` column.

On a database of its own, stopped at the revision before it: rows written the
way ticket 10 wrote them are upgraded, and a malformed stamp stops the upgrade
rather than leave a Sales request unstamped (and so shown to every member).
"""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls, database_urls, recreate_database, run_alembic
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from dw_platform.testing.seed_env import seed_test_env, sid

pytestmark = pytest.mark.integration

_DB = "dw_test_sales_stamp_migration"
_BEFORE = "9c8b75ac5f91"
_TENANT = sid("tenant", "tenant-alpha")
_WORKSPACE = sid("workspace", "tenant-alpha:main")


async def _at_the_revision_before() -> DatabaseUrls:
    urls = database_urls(_DB)
    await recreate_database(urls.admin, _DB)
    result = run_alembic(["upgrade", _BEFORE], urls.migrator)
    assert result.returncode == 0, result.stderr
    return urls


async def _insert(urls: DatabaseUrls, payload: dict[str, object], **columns: object) -> uuid.UUID:
    await seed_test_env(urls.migrator)
    approval_id = uuid.uuid4()
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO platform.approval_requests"
                    " (id, tenant_id, workspace_id, approval_type, requested_by, payload,"
                    "  status, required_scope)"
                    " VALUES (:id, :t, :w, 'sales.quote', :u, CAST(:p AS jsonb), :s, :rs)"
                ),
                {
                    "id": approval_id,
                    "t": _TENANT,
                    "w": _WORKSPACE,
                    "u": uuid.uuid4(),
                    "p": json.dumps(payload),
                    "s": columns.get("status", "pending"),
                    "rs": columns.get("required_scope"),
                },
            )
    finally:
        await engine.dispose()
    return approval_id


async def _row(urls: DatabaseUrls, approval_id: uuid.UUID) -> sa.Row[tuple[object, ...]]:
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return (
                await conn.execute(
                    sa.text(
                        "SELECT payload, required_scope FROM platform.approval_requests"
                        " WHERE id = :id"
                    ),
                    {"id": approval_id},
                )
            ).one()
    finally:
        await engine.dispose()


async def test_the_stamp_moves_into_the_column_and_back_on_downgrade() -> None:
    urls = await _at_the_revision_before()
    pending = await _insert(urls, {"decide_scope": "sales.quote.approve", "makers": []})
    decided = await _insert(urls, {"decide_scope": "sales.order.cross_check"}, status="approved")

    assert run_alembic(["upgrade", "head"], urls.migrator).returncode == 0

    for approval_id, scope in (
        (pending, "sales.quote.approve"),
        (decided, "sales.order.cross_check"),
    ):
        row = await _row(urls, approval_id)
        assert row.required_scope == scope
        assert "decide_scope" not in row.payload
        assert row.payload["required_scope"] == scope

    assert run_alembic(["downgrade", _BEFORE], urls.migrator).returncode == 0
    row = await _row(urls, pending)
    assert row.payload["decide_scope"] == "sales.quote.approve"
    assert "required_scope" not in row.payload


async def test_a_malformed_stamp_stops_the_upgrade() -> None:
    urls = await _at_the_revision_before()
    approval_id = await _insert(urls, {"decide_scope": "Sales Quote Approve"})

    result = run_alembic(["upgrade", "head"], urls.migrator)

    assert result.returncode != 0
    assert "not a scope name" in result.stderr + result.stdout
    row = await _row(urls, approval_id)
    assert row.required_scope is None
    assert row.payload["decide_scope"] == "Sales Quote Approve"
