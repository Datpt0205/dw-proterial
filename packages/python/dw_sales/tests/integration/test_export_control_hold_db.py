"""The export-control hold against PostgreSQL (Sales ticket 78, migration
fa17832cd08d): what `SqlFollowupStore.cases` reads, and what the database
admits.

M03 is stored held on an open `missing_noc_esf`. The store reads
`export_held` from the current revision's findings and the order's status,
the same answer `OrderCase.awaits_export_control` gives the case the
repository rebuilds; acknowledged, superseded or in a status the PIC may not
decide it in, it reads False. Another tenant's tick reads none of it.

Rows are changed by the migrator straight in the columns the domain writes,
so each read is tested on its own (the flows are
`test_export_control_hold_followup.py`'s, over the same domain).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from pg_test_db import database_urls, recreate_database, run_alembic
from sales_harness import OrderRun, World, run_mailbox
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from dw_kernel.pagination import PageQuery, page_request
from dw_platform.testing.seed_env import seed_test_env, sid
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.followups import LOADED, STAND_IN_STAGE, FollowupKey, SentFollowup
from dw_sales.application.overview_ports import OpenOrder, WorkFilter
from dw_sales.application.ports import SalesScope
from dw_sales.domain.followups import WaitingCase

pytestmark = pytest.mark.integration

T1 = datetime(2026, 10, 19, 3, 0, tzinfo=UTC)
_FINDING = (
    "UPDATE sales.order_findings SET disposition = :d, disposition_reason = :r,"
    " disposition_by = CAST(:by AS uuid), disposition_at = :at"
    " WHERE code = 'missing_noc_esf' AND revision_id IN"
    " (SELECT id FROM sales.order_revisions WHERE case_id = :id)"
)


@pytest.fixture
async def held_run(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    world: World,
) -> OrderRun:
    """M03 (no NOC/ESF on file) and M01 (the clean order), both opened by
    Sales (`in_review`: DW1 leaves them `checked`)."""
    run = await run_mailbox(uow, app_sessions, world.alpha, frozenset({"M01", "M03"}))
    for message_id in ("M01", "M03"):
        await _set(
            migrator,
            "UPDATE sales.order_cases SET status = 'in_review' WHERE id = :id",
            id=_id(run, message_id),
        )
    return run


def _id(run: OrderRun, message_id: str) -> uuid.UUID:
    case = run.outcomes[message_id].case
    assert case is not None
    return case.case_id


async def _set(migrator: AsyncEngine, statement: str, **values: object) -> None:
    async with migrator.begin() as conn:
        await conn.execute(sa.text(statement), values)


async def _read(
    uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, case_id: uuid.UUID
) -> WaitingCase | None:
    async with uow(scope) as work:
        found = await work.followups.cases(LOADED, received_since=T1 + timedelta(days=999))
    return next((c for c in found if c.case_id == case_id), None)


async def _awaits(uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, case_id: uuid.UUID) -> bool:
    async with uow(scope) as work:
        stored = await work.orders.get(case_id)
    assert stored is not None
    return stored.case.awaits_export_control


async def test_a_held_order_reads_as_held_and_a_clean_one_does_not(
    uow: SqlSalesUnitOfWorkFactory, world: World, held_run: OrderRun
) -> None:
    held, clean = _id(held_run, "M03"), _id(held_run, "M01")
    for case_id, expected in ((held, True), (clean, False)):
        read = await _read(uow, world.alpha, case_id)
        assert read is not None, case_id
        assert read.export_held is expected
        # The SQL and the domain give one answer.
        assert await _awaits(uow, world.alpha, case_id) is expected


async def _work_list(
    uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, *, export_holds: bool
) -> dict[uuid.UUID, bool]:
    """The orders the work list's SQL admits for someone with no other step,
    and whether each reads held."""
    wanted = WorkFilter(
        principal_id=uuid.UUID(int=0xFEED),
        order_statuses=frozenset(),
        quote_statuses=frozenset(),
        cross_checks=False,
        approvals=False,
        export_holds=export_holds,
        message_owners=frozenset(),
    )
    request = page_request(limit=200, cursor=None, query=PageQuery(key="test.export_holds"))
    async with uow(scope) as work:
        page = await work.overview.work_page(wanted, request)
    return {e.row.case_id: e.row.export_held for e in page.items if isinstance(e.row, OpenOrder)}


async def test_the_work_list_admits_the_held_order_to_the_export_control_pic_alone(
    uow: SqlSalesUnitOfWorkFactory, migrator: AsyncEngine, world: World, held_run: OrderRun
) -> None:
    """Ticket 78 review: "Việc của tôi" reads the hold with the follow-ups'
    expression, whoever is assigned; acknowledged, the order leaves it, and
    another tenant's list never has it."""
    held = _id(held_run, "M03")
    assert await _work_list(uow, world.alpha, export_holds=True) == {held: True}
    assert await _work_list(uow, world.alpha, export_holds=False) == {}
    assert await _work_list(uow, world.beta, export_holds=True) == {}
    await _set(
        migrator,
        _FINDING,
        d="accepted",
        r="Đã nhận NOC và ESF năm nay",
        by=str(uuid.UUID(int=0xA1)),
        at=T1,
        id=held,
    )
    assert await _work_list(uow, world.alpha, export_holds=True) == {}


async def test_an_acknowledged_hold_reads_as_not_held(
    uow: SqlSalesUnitOfWorkFactory, migrator: AsyncEngine, world: World, held_run: OrderRun
) -> None:
    held = _id(held_run, "M03")
    await _set(
        migrator,
        _FINDING,
        d="accepted",
        r="Đã nhận NOC và ESF năm nay",
        by=str(uuid.UUID(int=0xA1)),
        at=T1,
        id=held,
    )
    read = await _read(uow, world.alpha, held)
    assert read is not None and not read.export_held
    assert not await _awaits(uow, world.alpha, held)


async def test_a_hold_on_a_superseded_revision_only_is_not_read(
    uow: SqlSalesUnitOfWorkFactory, migrator: AsyncEngine, world: World, held_run: OrderRun
) -> None:
    held = _id(held_run, "M03")
    await _set(
        migrator,
        "UPDATE sales.order_revisions SET superseded_at = :at WHERE case_id = :id",
        at=T1,
        id=held,
    )
    read = await _read(uow, world.alpha, held)
    assert read is not None and not read.export_held


@pytest.mark.parametrize(
    ("status", "held"),
    [
        ("in_review", True),
        ("prepared", True),
        ("uploaded_to_bravo", True),
        ("cross_checked", True),
        ("change_review", True),
        # Before Sales opens it, and before DW1 checked it.
        ("checked", False),
        ("received", False),
    ],
)
async def test_the_hold_is_read_only_where_the_pic_may_decide_it(
    uow: SqlSalesUnitOfWorkFactory,
    migrator: AsyncEngine,
    world: World,
    held_run: OrderRun,
    status: str,
    held: bool,
) -> None:
    case_id = _id(held_run, "M03")
    await _set(
        migrator, "UPDATE sales.order_cases SET status = :s WHERE id = :id", s=status, id=case_id
    )
    async with uow(world.alpha) as work:
        found = await work.followups.cases({**LOADED}, received_since=T1 - timedelta(days=9999))
    read = next(c for c in found if c.case_id == case_id)
    assert read.export_held is held


async def test_another_tenants_tick_reads_none_of_the_hold(
    uow: SqlSalesUnitOfWorkFactory, world: World, held_run: OrderRun
) -> None:
    held = _id(held_run, "M03")
    async with uow(world.beta) as work:
        found = await work.followups.cases(LOADED, received_since=T1 - timedelta(days=9999))
    assert held not in {c.case_id for c in found}


async def test_the_record_and_the_feeds_marks_take_the_hold(
    uow: SqlSalesUnitOfWorkFactory, migrator: AsyncEngine, world: World
) -> None:
    key = FollowupKey("export_control_hold", "notify", str(uuid.uuid4()), T1)
    async with uow(world.alpha) as work:
        assert await work.followups.record(SentFollowup(key, 1, T1))
        await work.commit()
    async with migrator.connect() as conn:
        definition = await conn.scalar(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conname = 'ck_reminder_marks_followup'"
            )
        )
    assert "'export_control_hold'" in str(definition)


async def test_the_heads_stand_in_is_recorded_apart_from_the_hold(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    """Ticket 78 review (migration d217eda10ac8): the heads' notice and the
    export-control PIC's are two records of one revision; either read back
    alone leaves the other owed."""
    subject = str(uuid.uuid4())
    hold = FollowupKey("export_control_hold", "notify", subject, T1)
    stood_in = FollowupKey("export_control_hold", STAND_IN_STAGE, subject, T1)
    async with uow(world.alpha) as work:
        assert await work.followups.record(SentFollowup(stood_in, 1, T1))
        await work.commit()
    async with uow(world.alpha) as work:
        assert await work.followups.already_sent([hold, stood_in]) == {stood_in}
        assert await work.followups.record(SentFollowup(hold, 1, T1))
        await work.commit()
    async with uow(world.alpha) as work:
        assert await work.followups.already_sent([hold, stood_in]) == {hold, stood_in}


# ------------------------------------------------- the migration itself --

_DB = "dw_test_sales_export_control_hold_migration"
_BEFORE = "0662b6f0a31c"
_REVISION = "fa17832cd08d"
_TENANT = sid("tenant", "tenant-alpha")
_WORKSPACE = sid("workspace", "tenant-alpha:main")
_CHECKS = ("ck_followup_deliveries_followup", "ck_reminder_marks_followup")


async def _admitted(url: str) -> dict[str, bool]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            found = {
                check: "'export_control_hold'"
                in str(
                    await conn.scalar(
                        sa.text(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :c"
                        ),
                        {"c": check},
                    )
                )
                for check in _CHECKS
            }
    finally:
        await engine.dispose()
    return found


async def test_the_migration_admits_the_hold_on_both_tables_and_downgrades_cleanly() -> None:
    """Upgrade admits `export_control_hold` on the record and the marks, and
    keeps every value they held; downgrade deletes the rows of it the old
    checks cannot hold and takes the value back out; upgrade again admits it."""
    urls = database_urls(_DB)
    await recreate_database(urls.admin, _DB)
    assert run_alembic(["upgrade", _BEFORE], urls.migrator).returncode == 0
    await seed_test_env(urls.migrator)
    assert await _admitted(urls.migrator) == dict.fromkeys(_CHECKS, False)

    result = run_alembic(["upgrade", _REVISION], urls.migrator)
    assert result.returncode == 0, result.stderr
    assert await _admitted(urls.migrator) == dict.fromkeys(_CHECKS, True)
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.followup_deliveries (id, tenant_id, workspace_id,"
                    " followup, stage, subject, since, recipients, sent_at) VALUES"
                    " (:id, :t, :w, 'export_control_hold', 'notify', :s1, :at, 1, :at),"
                    " (:other, :t, :w, 'waiting_pcs_price', 'remind', :s2, :at, 1, :at)"
                ),
                {
                    "id": uuid.uuid4(),
                    "s1": str(uuid.uuid4()),
                    "s2": str(uuid.uuid4()),
                    "other": uuid.uuid4(),
                    "t": _TENANT,
                    "w": _WORKSPACE,
                    "at": T1,
                },
            )
    finally:
        await engine.dispose()

    result = run_alembic(["downgrade", _BEFORE], urls.migrator)
    assert result.returncode == 0, result.stderr
    assert await _admitted(urls.migrator) == dict.fromkeys(_CHECKS, False)
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            left = (
                (await conn.execute(sa.text("SELECT followup FROM sales.followup_deliveries")))
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()
    assert left == ["waiting_pcs_price"]

    assert run_alembic(["upgrade", _REVISION], urls.migrator).returncode == 0
    assert await _admitted(urls.migrator) == dict.fromkeys(_CHECKS, True)


_STAND_IN_DB = "dw_test_sales_followup_stand_in_migration"
_STAND_IN = "d217eda10ac8"


async def _stages(url: str) -> str:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return str(
                await conn.scalar(
                    sa.text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                        " WHERE conname = 'ck_followup_deliveries_stage'"
                    )
                )
            )
    finally:
        await engine.dispose()


async def test_the_stand_in_stage_migration_keeps_every_stage_and_downgrades_cleanly() -> None:
    """Upgrade adds `stand_in` to the stages and keeps the rest; downgrade
    deletes the stand-in records and takes the value out; up again admits it."""
    urls = database_urls(_STAND_IN_DB)
    await recreate_database(urls.admin, _STAND_IN_DB)
    assert run_alembic(["upgrade", _REVISION], urls.migrator).returncode == 0
    await seed_test_env(urls.migrator)
    before = await _stages(urls.migrator)
    assert "'stand_in'" not in before

    result = run_alembic(["upgrade", _STAND_IN], urls.migrator)
    assert result.returncode == 0, result.stderr
    after = await _stages(urls.migrator)
    assert "'stand_in'" in after
    for stage in ("remind", "escalate", "warn", "brief", "notify"):
        assert f"'{stage}'" in after, stage
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.followup_deliveries (id, tenant_id, workspace_id,"
                    " followup, stage, subject, since, recipients, sent_at) VALUES"
                    " (:a, :t, :w, 'export_control_hold', 'stand_in', :s, :at, 1, :at),"
                    " (:b, :t, :w, 'export_control_hold', 'notify', :s, :at, 1, :at)"
                ),
                {
                    "a": uuid.uuid4(),
                    "b": uuid.uuid4(),
                    "s": str(uuid.uuid4()),
                    "t": _TENANT,
                    "w": _WORKSPACE,
                    "at": T1,
                },
            )
    finally:
        await engine.dispose()

    result = run_alembic(["downgrade", _REVISION], urls.migrator)
    assert result.returncode == 0, result.stderr
    assert await _stages(urls.migrator) == before
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            left = (
                (await conn.execute(sa.text("SELECT stage FROM sales.followup_deliveries")))
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()
    assert left == ["notify"]

    assert run_alembic(["upgrade", _STAND_IN], urls.migrator).returncode == 0
    assert "'stand_in'" in await _stages(urls.migrator)
