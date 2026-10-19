"""DW1's follow-ups against PostgreSQL (ticket 42, migration d2b1394c67b1):
what the database owns.

- The record is unique on (follow-up, stage, subject, since) in a workspace:
  a second record of one key writes nothing, whichever worker writes it.
- Row security: a workspace reads its own records and cases only; another
  tenant's tick finds nothing of this one's.
- The cases the lane reads carry their status's entry time from the event
  log, and the read crosses no workspace.
- `sales.followup_scopes()` lists every workspace with a case, ids only.
- The CHECKs hold whatever writes the row; dw_app may not UPDATE a record.
- `sales_followups` is a key `sales.rule_versions` accepts.

Owed when Docker is back (ticket 42).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa
from sales_harness import T0, OrderRun, World
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_sales.adapters.persistence.followups import SqlFollowupScopes
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.followups import BRIEF, LOADED, FollowupKey, SentFollowup
from dw_sales.domain.dispositions import CaseKind

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 19, 3, 0, tzinfo=UTC)


def _key(
    subject: str, *, followup: str = "order_unconfirmed", stage: str = "remind"
) -> FollowupKey:
    return FollowupKey(followup, stage, subject, NOW - timedelta(hours=5))


async def test_one_key_is_recorded_once(uow: SqlSalesUnitOfWorkFactory, world: World) -> None:
    key = _key(str(uuid.uuid4()))
    for expected in (True, False):
        async with uow(world.alpha) as work:
            assert await work.followups.record(SentFollowup(key, 1, NOW)) is expected
            await work.commit()
    async with uow(world.alpha) as work:
        assert await work.followups.already_sent([key]) == {key}


async def test_another_workspace_and_another_tenant_see_no_record(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    key = _key(str(uuid.uuid4()))
    async with uow(world.alpha) as work:
        await work.followups.record(SentFollowup(key, 1, NOW))
        await work.commit()
    for scope in (world.alpha_other, world.beta):
        async with uow(scope) as work:
            assert await work.followups.already_sent([key]) == frozenset()
            # And recording the same key there is its own row, not a refusal.
            assert await work.followups.record(SentFollowup(key, 1, NOW))
            await work.commit()


async def test_the_lane_reads_its_own_workspaces_cases_with_their_status_entry(
    uow: SqlSalesUnitOfWorkFactory, world: World, order_run: OrderRun
) -> None:
    async with uow(world.alpha) as work:
        mine = await work.followups.cases(LOADED, received_since=NOW)
    assert mine, "the mailbox run opened open order cases"
    assert {c.kind for c in mine} == {CaseKind.ORDER}
    for case in mine:
        # Every case of the run was checked at T0 (`persist_outcome`).
        assert case.status_since >= T0 or case.status_since == case.received_at
    for scope in (world.alpha_other, world.beta):
        async with uow(scope) as work:
            assert await work.followups.cases(LOADED, received_since=T0 - timedelta(days=999)) == []


async def test_the_scopes_list_ids_of_workspaces_with_cases(
    app_sessions: async_sessionmaker[AsyncSession], world: World, order_run: OrderRun
) -> None:
    scopes = await SqlFollowupScopes(app_sessions).scopes()
    assert world.alpha in scopes
    assert world.beta not in scopes


async def test_old_brief_records_are_deleted_and_nothing_else(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    old = FollowupKey(BRIEF, "brief", "2026-09-01", NOW - timedelta(days=48))
    today = FollowupKey(BRIEF, "brief", "2026-10-19", NOW)
    case = _key(str(uuid.uuid4()))
    async with uow(world.alpha) as work:
        for key in (old, today, case):
            await work.followups.record(SentFollowup(key, 1, NOW))
        assert await work.followups.forget_briefs_before(date(2026, 9, 14)) == 1
        await work.commit()
    async with uow(world.alpha) as work:
        assert await work.followups.already_sent([old, today, case]) == {today, case}


@pytest.mark.parametrize(
    ("followup", "stage", "subject"),
    [
        ("order_reminder", "remind", str(uuid.uuid4())),
        ("order_unconfirmed", "nag", str(uuid.uuid4())),
        ("morning_brief", "remind", "2026-10-19"),
        ("order_unconfirmed", "brief", str(uuid.uuid4())),
        ("order_unconfirmed", "remind", "PO-1; DROP"),
    ],
)
async def test_the_checks_refuse_what_the_lane_never_writes(
    uow: SqlSalesUnitOfWorkFactory, world: World, followup: str, stage: str, subject: str
) -> None:
    with pytest.raises(IntegrityError):
        async with uow(world.alpha) as work:
            await work.followups.record(
                SentFollowup(FollowupKey(followup, stage, subject, NOW), 1, NOW)
            )
            await work.commit()


async def test_the_application_may_not_edit_a_record(
    app_sessions: async_sessionmaker[AsyncSession], uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    async with uow(world.alpha) as work:
        await work.followups.record(SentFollowup(_key(str(uuid.uuid4())), 1, NOW))
        await work.commit()
    with pytest.raises(DBAPIError, match="permission denied"):
        async with app_sessions() as session, session.begin():
            await session.execute(sa.text("UPDATE sales.followup_deliveries SET recipients = 9"))


async def test_a_tenant_version_of_the_followups_is_a_key_the_table_takes(
    migrator: AsyncEngine,
) -> None:
    async with migrator.connect() as conn:
        check = await conn.scalar(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conname = 'ck_rule_versions_key'"
            )
        )
    assert "sales_followups" in str(check)
