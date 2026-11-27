"""The gateway's writes waiting for a person, counted across tenants (ticket 84,
migration fc8d358317fe): `bravo.writes_needing_a_person()` read by `dw_app`
with no tenant bound, which reads no ledger row through RLS.

The session database is shared, so each test measures what its own rows add.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_sales.adapters.persistence.bravo_ledger_health import SqlBravoLedgerHealth
from dw_sales.application.ports import SalesScope

pytestmark = pytest.mark.integration

_INSERT = sa.text(
    "INSERT INTO bravo.write_ledger (tenant_id, workspace_id, approval_id, kind,"
    " content_hash, bravo_user_id, status, claimed_at, settled_at)"
    " VALUES (:t, :w, :a, 'so.line.set_quantity@1', :h, 2413, :status, :claimed, :settled)"
)


async def _ledger_row(
    migrator: AsyncEngine,
    scope: SalesScope,
    status: str,
    claimed_ago: timedelta,
    settled_after: timedelta = timedelta(0),
) -> None:
    claimed = datetime.now(UTC) - claimed_ago
    async with migrator.begin() as conn:
        await conn.execute(
            _INSERT,
            {
                "t": scope.tenant_id.value,
                "w": scope.workspace_id.value,
                "a": uuid.uuid4(),
                "h": "a" * 64,
                "status": status,
                "claimed": claimed,
                "settled": None if status == "claimed" else claimed + settled_after,
            },
        )


async def test_rows_waiting_for_a_person_in_every_tenant_are_counted_and_nothing_else(
    migrator: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    health = SqlBravoLedgerHealth(app_sessions)
    before = await health.needing_a_person()

    minute, hour = timedelta(minutes=1), timedelta(hours=1)
    # Counted: two tenants, so the count is not one tenant's under RLS.
    await _ledger_row(migrator, world.alpha, "in_doubt", minute)
    await _ledger_row(migrator, world.beta, "reconcile_failed", minute)
    await _ledger_row(migrator, world.beta, "claimed", hour)
    # Not counted: settled cleanly, or a claim the gateway is still within.
    await _ledger_row(migrator, world.alpha, "written", minute)
    await _ledger_row(migrator, world.alpha, "refused", minute)
    await _ledger_row(migrator, world.alpha, "claimed", minute)

    assert await health.needing_a_person() == before + 3

    async with app_sessions() as session:
        visible = await session.scalar(sa.text("SELECT count(*) FROM bravo.write_ledger"))
    assert visible == 0, "dw_app with no tenant bound reads no row itself"


async def test_a_claim_that_went_stale_stays_counted_once_it_settles(
    migrator: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    """Migration 5895c4d8683e: the alert fires on a rise, so a stale claim
    settling late must not lower the count and cancel a new one's rise."""
    health = SqlBravoLedgerHealth(app_sessions)
    before = await health.needing_a_person()

    hour = timedelta(hours=1)
    # Hung on Bravo for 20 minutes, then written: it was told, it stays told.
    await _ledger_row(migrator, world.alpha, "written", hour, timedelta(minutes=20))
    # Written 2 minutes after the claim: never stale, never counted.
    await _ledger_row(migrator, world.alpha, "written", hour, timedelta(minutes=2))

    assert await health.needing_a_person() == before + 1


async def test_only_dw_app_may_ask_and_the_function_runs_as_its_owner(
    migrator: AsyncEngine,
) -> None:
    async with migrator.connect() as conn:
        row = (
            await conn.execute(
                sa.text(
                    "SELECT p.prosecdef,"
                    " has_function_privilege('public', p.oid, 'EXECUTE') AS public_exec,"
                    " has_function_privilege('dw_app', p.oid, 'EXECUTE') AS app_exec"
                    " FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
                    " WHERE n.nspname = 'bravo' AND p.proname = 'writes_needing_a_person'"
                )
            )
        ).one()
    assert row.prosecdef and row.app_exec and not row.public_exec
