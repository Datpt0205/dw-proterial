# ruff: noqa: E501 - SQL kept on the lines a reader runs it from
"""The gateway's ledger on a migrated PostgreSQL, as `dw_app` under RLS
(ticket 63 check 6; CLAUDE.md: negative tests for cross-tenant reads and
writes are mandatory). Requires `make infra-up`; fails loudly without it."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from pg_test_db import (
    TENANT_A,
    TENANT_B,
    WORKSPACE_A,
    WORKSPACE_B,
    database_urls,
    recreate_database,
    run_alembic,
)
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from dw_bravo.approval_token import ApprovalClaims
from dw_bravo_gateway.adapters.postgres import SqlLedger

pytestmark = pytest.mark.integration

TEST_DB = "dw_test_bravo_gateway"
NOW = datetime(2026, 11, 21, 3, tzinfo=UTC)


@pytest.fixture(scope="module")
def urls() -> object:
    urls = database_urls(TEST_DB)
    try:
        asyncio.run(recreate_database(urls.admin, TEST_DB))
    except (OSError, OperationalError, InterfaceError) as exc:
        pytest.fail(f"Postgres unreachable at {urls.admin!r}: run `make infra-up`. {exc}")
    result = run_alembic(["upgrade", "head"], urls.migrator)
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")

    async def seed() -> None:
        engine = create_async_engine(urls.migrator)
        async with engine.begin() as conn:
            for tenant, workspace in ((TENANT_A, WORKSPACE_A), (TENANT_B, WORKSPACE_B)):
                await conn.execute(
                    sa.text("INSERT INTO platform.tenants (id, slug, name) VALUES (:id, :s, :s)"),
                    {"id": tenant, "s": f"t{tenant.int:x}"},
                )
                await conn.execute(
                    sa.text(
                        "INSERT INTO platform.workspaces (id, tenant_id, slug, name)"
                        " VALUES (:id, :t, 'main', 'Main')"
                    ),
                    {"id": workspace, "t": tenant},
                )
        await engine.dispose()

    asyncio.run(seed())
    return urls


@pytest.fixture
async def sessions(urls: object) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(urls.app)  # type: ignore[attr-defined]
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def claims(tenant: uuid.UUID = TENANT_A, workspace: uuid.UUID = WORKSPACE_A) -> ApprovalClaims:
    return ApprovalClaims(
        approval_id=uuid.uuid4(),
        tenant_id=tenant,
        workspace_id=workspace,
        kind="so.line.set_quantity@1",
        content_hash="a" * 64,
        bravo_user_id=2413,
        employee_code="NV001",
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
        key_id="k1",
    )


async def test_an_approval_id_is_claimed_once_and_settled_once(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    ledger, approved = SqlLedger(sessions), claims()

    assert await ledger.claim(approved) is True
    assert await ledger.claim(approved) is False
    await ledger.settle(approved, "written", {"statements": 2})
    with pytest.raises(RuntimeError):
        await ledger.settle(approved, "in_doubt", {})

    entry = await ledger.find(approved)
    assert entry is not None and (entry.status, entry.detail) == ("written", {"statements": 2})


async def test_another_tenants_token_neither_sees_nor_takes_the_approval(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    ledger, approved = SqlLedger(sessions), claims()
    await ledger.claim(approved)
    other = claims(TENANT_B, WORKSPACE_B)
    other = ApprovalClaims(**{**other.__dict__, "approval_id": approved.approval_id})

    assert await ledger.find(other) is None
    with pytest.raises(RuntimeError):
        await ledger.settle(other, "written", {})
    assert (await ledger.find(approved)).status == "claimed"  # type: ignore[union-attr]


async def test_a_row_for_another_tenant_cannot_be_written_from_this_scope(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, session.begin():
        await session.execute(
            sa.text(
                "SELECT set_config('app.tenant_id', :t, true), set_config('app.workspace_id', :w, true)"
            ),
            {"t": str(TENANT_A), "w": str(WORKSPACE_A)},
        )
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                sa.text(
                    "INSERT INTO bravo.write_ledger (tenant_id, workspace_id, approval_id, kind,"
                    " content_hash, bravo_user_id, status, claimed_at)"
                    " VALUES (:t, :w, :a, 'so.create@1', :h, 1, 'claimed', now())"
                ),
                {"t": TENANT_B, "w": WORKSPACE_B, "a": uuid.uuid4(), "h": "b" * 64},
            )


async def test_a_spent_approval_cannot_be_deleted(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    approved = claims()
    await SqlLedger(sessions).claim(approved)
    async with sessions() as session, session.begin():
        await session.execute(
            sa.text(
                "SELECT set_config('app.tenant_id', :t, true), set_config('app.workspace_id', :w, true)"
            ),
            {"t": str(TENANT_A), "w": str(WORKSPACE_A)},
        )
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(
                sa.text("DELETE FROM bravo.write_ledger WHERE approval_id = :a"),
                {"a": approved.approval_id},
            )


async def test_an_unscoped_connection_reads_nothing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await SqlLedger(sessions).claim(claims())
    async with sessions() as session, session.begin():
        count = await session.scalar(sa.text("SELECT count(*) FROM bravo.write_ledger"))
    assert count == 0
