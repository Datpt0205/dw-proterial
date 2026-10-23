"""`sales.step_outcomes` (migration 4bca401bcb3a, slice 3 "AI activity")
against a real database, as `dw_app` wherever isolation is the question.

What DW1's model steps did: written in the unit of work that writes the
case, read under tenant AND workspace RLS only, append-only for the
application role on every partition, a month made ahead by the platform's
partition function with its row security and revokes, a month past its term
dropped by `sales.drop_expired_step_outcomes` and nothing else, and a row
that holds anything but codes and counts refused by its CHECKs. The
migration goes down and up again on a database of its own.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any, get_args

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls, database_urls, recreate_database, run_alembic
from sales_harness import World
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from dw_kernel.ports import FixedClock
from dw_platform.retention_policy import (
    AuditRetention,
    ChannelDeliveryRetention,
    CheckpointRetention,
    KnowledgeRetention,
    OffboardingExportRetention,
    RetentionClass,
    RetentionPolicy,
)
from dw_sales.adapters.persistence.activity import (
    RETENTION_KEY,
    SqlStepActivityReader,
    SqlStepOutcomeRetention,
)
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.activity_ports import StepRowFilter
from dw_sales.application.ports import SalesScope
from dw_sales.domain.activity import StepOutcome, StepResult
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_checks import ModelStep

pytestmark = pytest.mark.integration

_AT = datetime.now(UTC).replace(microsecond=0)
_FAR = datetime(2000, 1, 1, tzinfo=UTC)
_TO = datetime(2100, 1, 1, tzinfo=UTC)


def _row(case_id: uuid.UUID, *, at: datetime = _AT, line_no: int = 1) -> StepOutcome:
    return StepOutcome(
        outcome_id=uuid.uuid4(),
        occurred_at=at,
        message_id="M01",
        lane=CaseKind.ORDER,
        case_id=case_id,
        line_no=line_no,
        step=ModelStep.DESCRIPTION_ATTRIBUTES,
        result="refused",
        automatic=False,
        reason_code="text_uncovered",
        refusals={},
        prompt="sales.description_attributes@1.0.0",
        model_profile="onprem",
        model="qwen3.5-9b-dw",
        calls=1,
        duration_ms=640,
    )


async def _write(
    uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, *rows: StepOutcome, commit: bool = True
) -> None:
    async with uow(scope) as work:
        await work.step_activity.append(rows)
        if commit:
            await work.commit()


# ------------------------------------------------------ the domain's sets --


async def _constraint(conn: Any, name: str) -> str:
    definition = await conn.scalar(
        sa.text(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
            " JOIN pg_namespace n ON n.oid = c.connamespace"
            " WHERE n.nspname = 'sales' AND c.conname = :name"
        ),
        {"name": name},
    )
    assert definition is not None, f"no constraint {name}"
    return str(definition)


@pytest.mark.parametrize(
    ("name", "values"),
    [
        ("ck_step_outcomes_step", {s.value for s in ModelStep}),
        ("ck_step_outcomes_result", set(get_args(StepResult))),
        ("ck_step_outcomes_lane", {k.value for k in CaseKind}),
    ],
)
async def test_each_check_holds_exactly_the_domains_values(
    migrator: AsyncEngine, name: str, values: set[str]
) -> None:
    async with migrator.connect() as conn:
        definition = await _constraint(conn, name)
    assert set(re.findall(r"'([a-z_]+)'::text", definition)) == values


# ---------------------------------------------------------------- the rows --


async def test_rows_are_written_with_the_unit_of_work_and_read_back_in_order(
    uow: SqlSalesUnitOfWorkFactory, app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    case_id = uuid.uuid4()
    rolled_back = _row(case_id, line_no=9)
    await _write(uow, world.alpha, rolled_back, commit=False)
    second, first = _row(case_id, line_no=2), _row(case_id, line_no=1, at=_AT.replace(year=2025))
    await _write(uow, world.alpha, second, first)

    read = await SqlStepActivityReader(app_sessions).for_case(world.alpha, CaseKind.ORDER, case_id)

    # Nothing of a transaction that did not commit; oldest first.
    assert [r.outcome_id for r in read] == [first.outcome_id, second.outcome_id]
    assert read[1] == second
    assert (
        await SqlStepActivityReader(app_sessions).for_case(world.alpha, CaseKind.QUOTE, case_id)
        == []
    )


async def test_another_tenant_or_workspace_reads_none_of_them(
    uow: SqlSalesUnitOfWorkFactory, app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    case_id = uuid.uuid4()
    await _write(uow, world.alpha, _row(case_id))
    reader = SqlStepActivityReader(app_sessions)

    for scope in (world.beta, world.alpha_other):
        assert await reader.for_case(scope, CaseKind.ORDER, case_id) == []
        assert await reader.between(scope, _FAR, _TO, None) == []
    assert len(await reader.between(world.alpha, _FAR, _TO, CaseKind.ORDER)) >= 1
    assert await reader.between(world.alpha, _FAR, _TO, CaseKind.QUOTE) == []


# ------------------------------------------------- the case lists' filter --


def _outcome(
    case_id: uuid.UUID | None,
    step: ModelStep,
    *,
    automatic: bool,
    result: StepResult,
    reason: str | None = None,
    refusals: dict[str, int] | None = None,
    lane: CaseKind = CaseKind.ORDER,
    at: datetime = _AT,
) -> StepOutcome:
    # Validated as a written row is: what the table's CHECKs also refuse.
    return StepOutcome.model_validate(
        {
            **_row(uuid.uuid4(), at=at).model_dump(),
            "case_id": case_id,
            "lane": lane,
            "step": step,
            "automatic": automatic,
            "result": result,
            "reason_code": reason,
            "refusals": refusals or {},
        }
    )


async def test_the_case_filter_in_sql_keeps_what_the_domain_filter_keeps(
    uow: SqlSalesUnitOfWorkFactory, app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    """`SqlStepActivityReader.cases` against `StepRowFilter.matches`, the one
    definition of what a case list narrowed by the activity page keeps: by
    step and lane, in the window, by who carried the item, by result, and by
    a reason that is the item's own or refused inside it. Another tenant or
    workspace reads no case."""
    described, quoted = ModelStep.DESCRIPTION_ATTRIBUTES, ModelStep.RFQ_EXTRACTION
    rows = [
        _outcome(
            uuid.uuid4(), described, automatic=False, result="refused", reason="text_uncovered"
        ),
        _outcome(
            uuid.uuid4(),
            described,
            automatic=True,
            result="accepted",
            refusals={"span_not_found": 2},
        ),
        _outcome(
            uuid.uuid4(),
            described,
            automatic=False,
            result="unavailable",
            at=_AT - timedelta(days=3),
        ),
        _outcome(uuid.uuid4(), quoted, automatic=True, result="accepted", lane=CaseKind.QUOTE),
        # A routed message's row names no case: no list shows it.
        _outcome(None, described, automatic=False, result="refused", reason="text_uncovered"),
    ]
    await _write(uow, world.alpha, *rows)
    reader = SqlStepActivityReader(app_sessions)
    day = (_AT - timedelta(days=1), _AT + timedelta(days=1))
    filters = [
        StepRowFilter(described, CaseKind.ORDER, *day),
        StepRowFilter(described, CaseKind.ORDER, *day, handled_by="person"),
        StepRowFilter(described, CaseKind.ORDER, *day, handled_by="dw1"),
        StepRowFilter(described, CaseKind.ORDER, *day, result="refused"),
        StepRowFilter(described, CaseKind.ORDER, *day, result="unavailable"),
        StepRowFilter(described, CaseKind.ORDER, *day, reason_code="text_uncovered"),
        StepRowFilter(described, CaseKind.ORDER, *day, reason_code="span_not_found"),
        StepRowFilter(described, CaseKind.ORDER, _AT - timedelta(days=4), day[1]),
        StepRowFilter(quoted, CaseKind.QUOTE, *day),
        StepRowFilter(quoted, CaseKind.ORDER, *day),
    ]

    for narrowed in filters:
        expected = {r.case_id for r in rows if r.case_id is not None and narrowed.matches(r)}
        assert await reader.cases(world.alpha, narrowed) == expected, narrowed
    # The comparison can fail: the filters keep different, non-empty sets.
    assert len({frozenset(await reader.cases(world.alpha, f)) for f in filters}) >= 5
    for scope in (world.beta, world.alpha_other):
        assert await reader.cases(scope, filters[0]) == frozenset()


async def test_the_case_filter_is_carried_by_an_index_led_by_the_tenant(
    migrator: AsyncEngine,
) -> None:
    """RLS supplies `tenant_id` and `workspace_id`; the query names the step
    and the window: an index carries them in that order."""
    async with migrator.connect() as conn:
        definition = await conn.scalar(
            sa.text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'sales'"
                " AND indexname = 'ix_step_outcomes_tenant_id_workspace_id_step_occurred_at'"
            )
        )
    assert definition is not None
    assert definition.endswith("(tenant_id, workspace_id, step, occurred_at)")


async def test_a_connection_that_never_scopes_itself_reads_nothing_even_by_partition_name(
    uow: SqlSalesUnitOfWorkFactory, sales_app_engine: AsyncEngine, world: World
) -> None:
    await _write(uow, world.alpha, _row(uuid.uuid4()))
    async with sales_app_engine.connect() as conn:
        for table in ("sales.step_outcomes", "sales.step_outcomes_default"):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0


async def test_a_row_written_for_another_tenant_is_refused_by_the_policy(
    app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    async with app_sessions() as session, session.begin():
        for key, value in (
            ("app.tenant_id", world.alpha.tenant_id.value),
            ("app.workspace_id", world.alpha.workspace_id.value),
        ):
            await session.execute(
                sa.text("SELECT set_config(:k, :v, true)"), {"k": key, "v": str(value)}
            )
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                sa.text(
                    "INSERT INTO sales.step_outcomes (id, tenant_id, workspace_id, occurred_at,"
                    " message_id, step, result, automatic, refusals, prompt, model_profile,"
                    " calls) VALUES (:id, :t, :w, now(), 'M01', 'message_intent', 'accepted',"
                    " true, '{}', 'sales.message_intent@1.0.0', 'onprem', 0)"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": world.beta.tenant_id.value,
                    "w": world.beta.workspace_id.value,
                },
            )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE sales.step_outcomes SET automatic = true",
        "DELETE FROM sales.step_outcomes",
        "UPDATE sales.step_outcomes_default SET automatic = true",
        "DELETE FROM sales.step_outcomes_default",
    ],
)
async def test_the_application_can_neither_rewrite_nor_remove_a_row(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
    statement: str,
) -> None:
    await _write(uow, world.alpha, _row(uuid.uuid4()))
    async with app_sessions() as session, session.begin():
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(world.alpha.tenant_id.value)},
        )
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text(statement))


@pytest.mark.parametrize(
    ("refusals", "accepted"),
    [
        ('{"price_unparsed": 2}', True),
        ('{"Price": 1}', False),
        ('{"price_unparsed": 0}', False),
        ('{"price_unparsed": "0.95"}', False),
        ("[]", False),
    ],
)
async def test_refusals_are_reason_codes_and_counts_and_nothing_else(
    migrator: AsyncEngine, world: World, refusals: str, accepted: bool
) -> None:
    statement = sa.text(
        "INSERT INTO sales.step_outcomes (id, tenant_id, workspace_id, occurred_at, message_id,"
        " step, result, automatic, refusals, prompt, model_profile, calls) VALUES (:id, :t, :w,"
        " now(), 'M01', 'rfq_extraction', 'accepted', true, CAST(:r AS jsonb),"
        " 'sales.rfq_extraction@1.0.0', 'onprem', 0)"
    )
    values = {
        "id": uuid.uuid4(),
        "t": world.alpha.tenant_id.value,
        "w": world.alpha.workspace_id.value,
        "r": refusals,
    }
    if accepted:
        async with migrator.begin() as conn:
            await conn.execute(statement, values)
        return
    with pytest.raises(IntegrityError, match="ck_step_outcomes_refusals"):
        async with migrator.begin() as conn:
            await conn.execute(statement, values)


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ("'accepted', true, 'text_uncovered', 0, NULL", "ck_step_outcomes_outcome"),
        ("'refused', false, NULL, 0, NULL", "ck_step_outcomes_outcome"),
        ("'unavailable', false, 'x', 0, NULL", "ck_step_outcomes_outcome"),
        ("'accepted', true, NULL, 1, NULL", "ck_step_outcomes_duration"),
        # Not automatic: an automatic 'kept' also breaks `_outcome`, and
        # PostgreSQL reports the first CHECK by name.
        ("'kept', false, NULL, 0, NULL", "ck_step_outcomes_result"),
    ],
)
async def test_a_row_that_does_not_say_what_happened_is_refused(
    migrator: AsyncEngine, world: World, columns: str, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.step_outcomes (id, tenant_id, workspace_id, occurred_at,"
                    " message_id, step, result, automatic, reason_code, calls, duration_ms,"
                    " refusals, prompt, model_profile) VALUES (:id, :t, :w, now(), 'M01',"
                    f" 'message_intent', {columns}, '{{}}', 'sales.message_intent@1.0.0',"
                    " 'onprem')"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": world.alpha.tenant_id.value,
                    "w": world.alpha.workspace_id.value,
                },
            )


@pytest.mark.parametrize(
    ("message_id", "accepted"), [("M" * 512, True), ("M" * 513, False), ("M 1", False)]
)
async def test_a_message_id_is_held_to_the_domains_bound(
    migrator: AsyncEngine, world: World, message_id: str, accepted: bool
) -> None:
    """`StepOutcome.message_id`'s `^[!-~]{1,512}$`. PostgreSQL's regex bounds
    a repetition at 255, so the CHECK states the length on its own: written
    as the domain writes it, every insert failed to evaluate the CHECK."""
    statement = sa.text(
        "INSERT INTO sales.step_outcomes (id, tenant_id, workspace_id, occurred_at, message_id,"
        " step, result, automatic, refusals, prompt, model_profile, calls) VALUES (:id, :t, :w,"
        " now(), :m, 'message_intent', 'accepted', true, '{}', 'sales.message_intent@1.0.0',"
        " 'onprem', 0)"
    )
    values = {
        "id": uuid.uuid4(),
        "t": world.alpha.tenant_id.value,
        "w": world.alpha.workspace_id.value,
        "m": message_id,
    }
    if accepted:
        async with migrator.begin() as conn:
            await conn.execute(statement, values)
        return
    with pytest.raises(IntegrityError, match="ck_step_outcomes_message_id"):
        async with migrator.begin() as conn:
            await conn.execute(statement, values)


async def test_rows_leave_with_their_workspace(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    world: World,
) -> None:
    """Offboarding purges `platform.workspaces`; the rows cascade with it."""
    await _write(uow, world.alpha_other, _row(uuid.uuid4()))
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text("DELETE FROM platform.workspaces WHERE id = :w"),
            {"w": world.alpha_other.workspace_id.value},
        )
        left = await conn.scalar(
            sa.text("SELECT count(*) FROM sales.step_outcomes WHERE workspace_id = :w"),
            {"w": world.alpha_other.workspace_id.value},
        )
    assert left == 0


# ------------------------------------------------------- partitions, term --


async def _partition_facts(conn: Any, name: str) -> Any:
    return (
        await conn.execute(
            sa.text(
                "SELECT c.relrowsecurity, c.relforcerowsecurity,"
                " (SELECT pg_get_expr(p.polqual, p.polrelid) FROM pg_policy p"
                "  WHERE p.polrelid = c.oid AND p.polname = 'tenant_isolation_' || c.relname)"
                "  AS qual,"
                " has_table_privilege('dw_app', c.oid, 'SELECT') AS can_select,"
                " has_table_privilege('dw_app', c.oid, 'INSERT') AS can_insert,"
                " has_table_privilege('dw_app', c.oid, 'UPDATE') AS can_update,"
                " has_table_privilege('dw_app', c.oid, 'DELETE') AS can_delete"
                " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'sales' AND c.relname = :name"
            ),
            {"name": name},
        )
    ).one_or_none()


async def test_the_platforms_partition_function_makes_this_months_partition_policed(
    migrator: AsyncEngine,
) -> None:
    async with migrator.begin() as conn:
        await conn.execute(sa.text("SELECT platform.ensure_time_partitions(1)"))
    month = f"step_outcomes_{date.today():%Y_%m}"
    async with migrator.connect() as conn:
        for name in (month, "step_outcomes_default", "step_outcomes"):
            facts = await _partition_facts(conn, name)
            assert facts is not None, name
            assert facts.relrowsecurity and facts.relforcerowsecurity, name
            assert "app.tenant_id" in facts.qual and "app.workspace_id" in facts.qual, name
            assert "app.workspace_scope" in facts.qual, name
            assert (facts.can_select, facts.can_insert) == (True, True), name
            assert (facts.can_update, facts.can_delete) == (False, False), name


def _policy(days: int | None, *, enforced: bool = True) -> RetentionPolicy:
    return RetentionPolicy(
        schema_version="1.0",
        policy_id="retention",
        policy_version="9.9.9",
        classes={"default": RetentionClass(days=730, description="giữ")},
        knowledge=KnowledgeRetention(
            deleted_grace_days=30, orphan_evidence_grace_days=7, superseded_versions_kept=5
        ),
        audit=AuditRetention(
            months_ahead=1,
            enforced=enforced,
            tables={RETENTION_KEY: RetentionClass(days=days, description="một năm")},
        ),
        checkpoints=CheckpointRetention(superseded_days=7, idle_thread_days=730),
        channel_deliveries=ChannelDeliveryRetention(pending_expiry_days=7),
        offboarding_exports=OffboardingExportRetention(retain_days=30),
        batch_limit=1000,
    )


async def _month_exists(conn: Any, name: str) -> bool:
    return bool(await conn.scalar(sa.text("SELECT to_regclass(:n) IS NOT NULL"), {"n": name}))


async def test_the_retention_lane_drops_a_month_past_its_term_and_nothing_else(
    migrator: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    async with migrator.begin() as conn:
        # A month long past, made the only way a month is made, with a row.
        await conn.execute(
            sa.text("SELECT platform._ensure_one_partition('sales.step_outcomes', '2020-01-01')")
        )
        await conn.execute(sa.text("SELECT platform.ensure_time_partitions(1)"))
        await conn.execute(
            sa.text(
                "INSERT INTO sales.step_outcomes (id, tenant_id, workspace_id, occurred_at,"
                " message_id, step, result, automatic, refusals, prompt, model_profile, calls)"
                " VALUES (:id, :t, :w, '2020-01-15T00:00:00Z', 'M01', 'message_intent',"
                " 'accepted', true, '{}', 'sales.message_intent@1.0.0', 'onprem', 0)"
            ),
            {
                "id": uuid.uuid4(),
                "t": world.alpha.tenant_id.value,
                "w": world.alpha.workspace_id.value,
            },
        )
    now = datetime(2026, 10, 23, tzinfo=UTC)
    current = f"sales.step_outcomes_{date.today():%Y_%m}"

    # No term, or a term not enforced: nothing goes.
    for policy in (_policy(None), _policy(365, enforced=False)):
        await SqlStepOutcomeRetention(app_sessions, policy, FixedClock(now)).prune()
        async with migrator.connect() as conn:
            assert await _month_exists(conn, "sales.step_outcomes_2020_01")

    # A year: January 2020 goes, as `dw_app`; this month and the DEFAULT stay.
    await SqlStepOutcomeRetention(app_sessions, _policy(365), FixedClock(now)).prune()
    async with migrator.connect() as conn:
        assert not await _month_exists(conn, "sales.step_outcomes_2020_01")
        assert await _month_exists(conn, current)
        assert await _month_exists(conn, "sales.step_outcomes_default")


async def test_the_drop_function_takes_no_table_name_and_null_drops_nothing(
    sales_app_engine: AsyncEngine,
) -> None:
    async with sales_app_engine.begin() as conn:
        dropped = (
            await conn.execute(sa.text("SELECT sales.drop_expired_step_outcomes(NULL)"))
        ).all()
    assert dropped == []
    async with sales_app_engine.connect() as conn:
        signature = await conn.scalar(
            sa.text(
                "SELECT pg_get_function_identity_arguments(p.oid) FROM pg_proc p"
                " JOIN pg_namespace n ON n.oid = p.pronamespace"
                " WHERE n.nspname = 'sales' AND p.proname = 'drop_expired_step_outcomes'"
            )
        )
        public = await conn.scalar(
            sa.text(
                "SELECT has_function_privilege('public',"
                " 'sales.drop_expired_step_outcomes(timestamptz)', 'EXECUTE')"
            )
        )
    assert signature == "cutoff timestamp with time zone"
    assert public is False


# ------------------------------------------------------------- migration --

_DB = "dw_test_sales_step_outcomes_migration"
_REVISION = "4bca401bcb3a"
_BEFORE = "2d97d03c937a"


@pytest.fixture
async def own_database() -> AsyncIterator[DatabaseUrls]:
    urls = database_urls(_DB)
    await recreate_database(urls.admin, _DB)
    result = run_alembic(["upgrade", _REVISION], urls.migrator)
    assert result.returncode == 0, result.stderr
    yield urls


async def _parents(urls: DatabaseUrls) -> str:
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return str(
                await conn.scalar(
                    sa.text(
                        "SELECT prosrc FROM pg_proc p JOIN pg_namespace n"
                        " ON n.oid = p.pronamespace WHERE n.nspname = 'platform'"
                        " AND p.proname = 'ensure_time_partitions'"
                    )
                )
            )
    finally:
        await engine.dispose()


async def test_the_migration_goes_down_and_up_again(own_database: DatabaseUrls) -> None:
    assert "sales.step_outcomes" in await _parents(own_database)

    down = run_alembic(["downgrade", _BEFORE], own_database.migrator)
    assert down.returncode == 0, down.stderr
    body = await _parents(own_database)
    assert "sales.step_outcomes" not in body and "sales.case_events" in body

    up = run_alembic(["upgrade", _REVISION], own_database.migrator)
    assert up.returncode == 0, up.stderr
    assert "sales.step_outcomes" in await _parents(own_database)
