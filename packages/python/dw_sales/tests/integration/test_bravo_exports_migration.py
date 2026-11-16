"""Migration 7c6ad2350566 (ticket 03) on a database that already holds a
YCBG export of ticket 16, read and still queued: both come across to
`sales.bravo_exports` as the screen ``ycbg``, each outcome's ``ycbg_no`` as
its ``key``, the queued one's file with it; the old tables are gone. On its
own database, stopped at the revision before."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls, database_urls, recreate_database, run_alembic
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from dw_platform.testing.seed_env import seed_test_env, sid

pytestmark = pytest.mark.integration

_DB = "dw_test_sales_bravo_exports_migration"
_BEFORE = "acb2a1fbb213"
_REVISION = "7c6ad2350566"
_TENANT = sid("tenant", "tenant-alpha")
_WORKSPACE = sid("workspace", "tenant-alpha:main")
_AT = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
_SHA = "d" * 64


async def _at_the_revision_before() -> DatabaseUrls:
    urls = database_urls(_DB)
    await recreate_database(urls.admin, _DB)
    result = run_alembic(["upgrade", _BEFORE], urls.migrator)
    assert result.returncode == 0, result.stderr
    await seed_test_env(urls.migrator)
    return urls


async def test_ticket_16s_exports_come_across_as_the_ycbg_screen() -> None:
    urls = await _at_the_revision_before()
    read, queued = uuid.uuid4(), uuid.uuid4()
    case_id = uuid.uuid4()
    outcomes = [{"ycbg_no": "RFQ261110-002", "outcome": "recorded", "case_id": str(case_id)}]
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            for export_id, status, kept in ((read, "read", outcomes), (queued, "queued", [])):
                await conn.execute(
                    sa.text(
                        "INSERT INTO sales.ycbg_exports (id, tenant_id, workspace_id, status,"
                        " uploaded_by, uploaded_at, file_name, file_sha256, file_size, outcomes)"
                        " VALUES (:id, :t, :w, :status, :by, :at, 'y.xlsx', :sha, 3,"
                        " CAST(:outcomes AS jsonb))"
                    ),
                    {
                        "id": export_id,
                        "t": _TENANT,
                        "w": _WORKSPACE,
                        "status": status,
                        "by": uuid.uuid4(),
                        "at": _AT,
                        "sha": _SHA,
                        "outcomes": json.dumps(kept),
                    },
                )
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.ycbg_export_files (tenant_id, workspace_id, export_id,"
                    " content) VALUES (:t, :w, :id, :content)"
                ),
                {"t": _TENANT, "w": _WORKSPACE, "id": queued, "content": b"abc"},
            )

        result = run_alembic(["upgrade", _REVISION], urls.migrator)
        assert result.returncode == 0, result.stderr

        async with engine.connect() as conn:
            rows = {
                row.id: row
                for row in await conn.execute(
                    sa.text("SELECT id, screen, status, outcomes FROM sales.bravo_exports")
                )
            }
            files = await conn.scalar(
                sa.text("SELECT count(*) FROM sales.bravo_export_files WHERE export_id = :id"),
                {"id": queued},
            )
            old = await conn.scalar(
                sa.text(
                    "SELECT count(*) FROM pg_tables WHERE schemaname = 'sales'"
                    " AND tablename IN ('ycbg_exports', 'ycbg_export_files')"
                )
            )
    finally:
        await engine.dispose()

    assert {row.screen for row in rows.values()} == {"ycbg"}
    assert rows[read].outcomes == [
        {"key": "RFQ261110-002", "outcome": "recorded", "case_id": str(case_id)}
    ]
    assert rows[queued].status == "queued" and rows[queued].outcomes == []
    assert (files, old) == (1, 0)
