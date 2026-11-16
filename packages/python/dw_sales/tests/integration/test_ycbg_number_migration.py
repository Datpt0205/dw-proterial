"""Migration 10d5dfc1a3f1 (ticket 16) on a database that already holds a YCBG
number recorded before Bravo's shape.

The migration does not break on it and does not rewrite it: the constraint is
added NOT VALID, the row is still there and readable, and every write to it
from then on is refused (fail closed), as is a new row of the old shape. On a
database whose rows all fit, the constraint is validated (asked in
`test_ycbg_exports_db.py`). On its own database, stopped at the revision before.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls, database_urls, recreate_database, run_alembic
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from dw_platform.testing.seed_env import seed_test_env, sid

pytestmark = pytest.mark.integration

_DB = "dw_test_sales_ycbg_number_migration"
_BEFORE = "3d139b41fec1"
_REVISION = "10d5dfc1a3f1"
_TENANT = sid("tenant", "tenant-alpha")
_WORKSPACE = sid("workspace", "tenant-alpha:main")
_AT = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


async def _at_the_revision_before() -> DatabaseUrls:
    urls = database_urls(_DB)
    await recreate_database(urls.admin, _DB)
    result = run_alembic(["upgrade", _BEFORE], urls.migrator)
    assert result.returncode == 0, result.stderr
    await seed_test_env(urls.migrator)
    return urls


def _body(ycbg_no: str) -> str:
    message_id = f"M-{uuid.uuid4().hex[:8]}"
    return (
        f'{{"request": {{"message_id": "{message_id}", "customer_code": "KMH"}},'
        f' "ycbg": {{"ycbg_no": "{ycbg_no}"}}}}'
    )


async def _insert(urls: DatabaseUrls, ycbg_no: str) -> uuid.UUID:
    """A quote case row holding ``ycbg_no``, as the migrator writes it."""
    case_id = uuid.uuid4()
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.quote_cases (id, tenant_id, workspace_id, case_version,"
                    " status, body, received_at)"
                    " VALUES (:id, :t, :w, 3, 'sent_to_design', CAST(:body AS jsonb), :at)"
                ),
                {"id": case_id, "t": _TENANT, "w": _WORKSPACE, "body": _body(ycbg_no), "at": _AT},
            )
    finally:
        await engine.dispose()
    return case_id


async def _refused(urls: DatabaseUrls, statement: str, **params: object) -> str | None:
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text(statement), params)
    except IntegrityError as exc:
        return getattr(exc.orig.__cause__, "constraint_name", None)  # type: ignore[union-attr]
    finally:
        await engine.dispose()
    return None


async def test_an_old_number_survives_the_migration_and_is_refused_every_write() -> None:
    urls = await _at_the_revision_before()
    old = await _insert(urls, "YCBG-2609-030")
    fits = await _insert(urls, "RFQ260930-030")

    result = run_alembic(["upgrade", _REVISION], urls.migrator)
    assert result.returncode == 0, result.stderr
    assert "1 quote case(s) hold a YCBG number" in result.stdout + result.stderr

    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            validated = await conn.scalar(
                sa.text(
                    "SELECT convalidated FROM pg_constraint"
                    " WHERE conname = 'ck_quote_cases_ycbg_no'"
                )
            )
            held = await conn.scalar(
                sa.text("SELECT ycbg_no FROM sales.quote_cases WHERE id = :id"), {"id": old}
            )
    finally:
        await engine.dispose()
    assert validated is False
    assert held == "YCBG-2609-030"

    touch = "UPDATE sales.quote_cases SET case_version = case_version + 1 WHERE id = :id"
    assert await _refused(urls, touch, id=old) == "ck_quote_cases_ycbg_no"
    assert await _refused(urls, touch, id=fits) is None
    with pytest.raises(IntegrityError):
        await _insert(urls, "RFQ2611-2")

    assert run_alembic(["downgrade", _BEFORE], urls.migrator).returncode == 0
    assert await _refused(urls, touch, id=old) is None
