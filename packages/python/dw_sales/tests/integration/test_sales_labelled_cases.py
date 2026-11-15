"""`sales.labelled_cases` (migration eac4fabdb31a, ticket 43) against a real
database, as `dw_app` wherever isolation is the question.

What a person kept of a model's proposal: written in the unit of work of
the decision, read under tenant AND workspace RLS only (newest first, and
counted per step), append-only for the application role on every
partition, a month made ahead by the platform's partition function with its
row security and revokes, a month past its term dropped by
`sales.drop_expired_labelled_cases` and nothing else, and a row whose
verdict says other than its two values refused by its CHECK. The migration
goes down and up again on a database of its own.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

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
from dw_sales.adapters.persistence.labelled_cases import (
    RETENTION_KEY,
    SqlLabelledCaseReader,
    SqlLabelledCaseRetention,
)
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.labelled_cases import StepLabels
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.labelled_cases import LabelledCase
from dw_sales.domain.order_checks import ModelStep

pytestmark = pytest.mark.integration

_AT = datetime.now(UTC).replace(microsecond=0)
_PERSON = uuid.UUID(int=0xA1)


def _case(
    *,
    step: ModelStep = ModelStep.CHANGE_REQUEST,
    proposed: Any = "2500",
    kept: Any = "2500",
    at: datetime = _AT,
    customer: str = "NRV",
) -> LabelledCase:
    return LabelledCase(
        label_id=uuid.uuid4(),
        decided_at=at,
        step=step,
        lane=CaseKind.ORDER,
        case_id=uuid.uuid4(),
        customer_code=customer,
        message_id="R1",
        attachment_id=None,
        line_no=2,
        field="quantity",
        proposed=proposed,
        kept=kept,
        prompt="sales.change_request@1.0.0",
        model_profile="onprem",
        rules="sales_order_rules@1.5.2",
        decided_by=_PERSON,
    )


async def _write(
    uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, *cases: LabelledCase, commit: bool = True
) -> None:
    async with uow(scope) as work:
        await work.labelled_cases.append(cases)
        if commit:
            await work.commit()


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


async def test_the_step_check_holds_exactly_the_domains_steps(migrator: AsyncEngine) -> None:
    async with migrator.connect() as conn:
        definition = await _constraint(conn, "ck_labelled_cases_step")
    assert set(re.findall(r"'([a-z_]+)'::text", definition)) == {s.value for s in ModelStep}


# ---------------------------------------------------------------- the rows --


async def test_cases_are_written_with_the_unit_of_work_and_read_back_newest_first(
    uow: SqlSalesUnitOfWorkFactory, app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    rolled_back = _case()
    await _write(uow, world.alpha, rolled_back, commit=False)
    older = _case(at=_AT - timedelta(days=1), kept="2600")
    newer = _case(kept=None)
    layout = _case(
        step=ModelStep.LAYOUT_PROPOSAL,
        proposed={"kind": "pdf", "unit_price": "Price"},
        kept={"kind": "pdf", "unit_price": "Price"},
        customer="KMH",
    )
    await _write(uow, world.alpha, older, newer, layout)
    reader = SqlLabelledCaseReader(app_sessions)

    read = await reader.latest(world.alpha, ModelStep.CHANGE_REQUEST)

    # Nothing of a transaction that did not commit; newest first; read back
    # as written, a rejection's NULL included.
    assert [c.label_id for c in read] == [newer.label_id, older.label_id]
    assert read == [newer, older]
    assert (read[0].verdict, read[1].verdict) == ("rejected", "corrected")
    assert await reader.latest(world.alpha, ModelStep.CHANGE_REQUEST, limit=1) == [newer]
    assert await reader.latest(world.alpha, ModelStep.LAYOUT_PROPOSAL, customer_code="KMH") == [
        layout
    ]
    assert await reader.latest(world.alpha, ModelStep.LAYOUT_PROPOSAL, customer_code="NRV") == []
    counts = await reader.counts(world.alpha)
    assert counts[ModelStep.CHANGE_REQUEST] == StepLabels(corrected=1, rejected=1)
    assert counts[ModelStep.LAYOUT_PROPOSAL] == StepLabels(confirmed=1)


async def test_another_tenant_or_workspace_reads_none_of_them(
    uow: SqlSalesUnitOfWorkFactory, app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    await _write(uow, world.alpha, _case(step=ModelStep.RFQ_EXTRACTION))
    reader = SqlLabelledCaseReader(app_sessions)

    for scope in (world.beta, world.alpha_other):
        assert await reader.latest(scope, ModelStep.RFQ_EXTRACTION) == []
        assert ModelStep.RFQ_EXTRACTION not in await reader.counts(scope)
    assert len(await reader.latest(world.alpha, ModelStep.RFQ_EXTRACTION)) >= 1


async def test_a_connection_that_never_scopes_itself_reads_nothing_even_by_partition_name(
    uow: SqlSalesUnitOfWorkFactory, sales_app_engine: AsyncEngine, world: World
) -> None:
    await _write(uow, world.alpha, _case())
    async with sales_app_engine.connect() as conn:
        for table in ("sales.labelled_cases", "sales.labelled_cases_default"):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0


_INSERT = (
    "INSERT INTO sales.labelled_cases (id, tenant_id, workspace_id, decided_at, step, lane,"
    " message_id, field, proposed, kept, verdict, prompt, decided_by) VALUES (:id, :t, :w,"
    " now(), 'change_request', 'order', 'R1', 'quantity', CAST(:p AS jsonb),"
    " CAST(:k AS jsonb), :v, 'sales.change_request@1.0.0', :by)"
)


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
                sa.text(_INSERT),
                {
                    "id": uuid.uuid4(),
                    "t": world.beta.tenant_id.value,
                    "w": world.beta.workspace_id.value,
                    "p": '"2500"',
                    "k": '"2500"',
                    "v": "confirmed",
                    "by": _PERSON,
                },
            )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE sales.labelled_cases SET verdict = 'confirmed'",
        "DELETE FROM sales.labelled_cases",
        "UPDATE sales.labelled_cases_default SET verdict = 'confirmed'",
        "DELETE FROM sales.labelled_cases_default",
    ],
)
async def test_the_application_can_neither_rewrite_nor_remove_a_case(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
    statement: str,
) -> None:
    await _write(uow, world.alpha, _case())
    async with app_sessions() as session, session.begin():
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(world.alpha.tenant_id.value)},
        )
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text(statement))


@pytest.mark.parametrize(
    ("proposed", "kept", "verdict", "accepted"),
    [
        ('"2500"', '"2500"', "confirmed", True),
        ('"2500"', '"2600"', "corrected", True),
        ('"2500"', None, "rejected", True),
        ('{"a": 1, "b": 2}', '{"b": 2, "a": 1}', "confirmed", True),
        # A verdict its values do not say.
        ('"2500"', '"2600"', "confirmed", False),
        ('"2500"', '"2500"', "corrected", False),
        ('"2500"', '"2500"', "rejected", False),
        ('"2500"', None, "corrected", False),
        ('"2500"', '"2500"', "kept", False),
    ],
)
async def test_the_verdict_is_held_to_the_two_values(
    migrator: AsyncEngine,
    world: World,
    proposed: str,
    kept: str | None,
    verdict: str,
    accepted: bool,
) -> None:
    """`verdict_of` in the table: rejected exactly when nothing was kept,
    confirmed exactly when the kept value is the proposal."""
    values = {
        "id": uuid.uuid4(),
        "t": world.alpha.tenant_id.value,
        "w": world.alpha.workspace_id.value,
        "p": proposed,
        "k": kept,
        "v": verdict,
        "by": _PERSON,
    }
    if accepted:
        async with migrator.begin() as conn:
            await conn.execute(sa.text(_INSERT), values)
        return
    with pytest.raises(IntegrityError, match="ck_labelled_cases_verdict"):
        async with migrator.begin() as conn:
            await conn.execute(sa.text(_INSERT), values)


@pytest.mark.parametrize(
    ("proposed", "constraint"),
    [("null", "ck_labelled_cases_values"), (f'"{"x" * 16_400}"', "ck_labelled_cases_values")],
)
async def test_a_value_is_bounded_and_a_proposal_is_never_empty(
    migrator: AsyncEngine, world: World, proposed: str, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(_INSERT),
                {
                    "id": uuid.uuid4(),
                    "t": world.alpha.tenant_id.value,
                    "w": world.alpha.workspace_id.value,
                    "p": proposed,
                    "k": None,
                    "v": "rejected",
                    "by": _PERSON,
                },
            )


async def test_cases_leave_with_their_workspace(
    uow: SqlSalesUnitOfWorkFactory, migrator: AsyncEngine, world: World
) -> None:
    """Offboarding purges `platform.workspaces`; the rows cascade with it."""
    await _write(uow, world.alpha_other, _case())
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text("DELETE FROM platform.workspaces WHERE id = :w"),
            {"w": world.alpha_other.workspace_id.value},
        )
        left = await conn.scalar(
            sa.text("SELECT count(*) FROM sales.labelled_cases WHERE workspace_id = :w"),
            {"w": world.alpha_other.workspace_id.value},
        )
    assert left == 0


async def test_the_step_reads_are_carried_by_an_index_led_by_the_tenant(
    migrator: AsyncEngine,
) -> None:
    async with migrator.connect() as conn:
        definitions = {
            row.indexname: row.indexdef
            for row in await conn.execute(
                sa.text(
                    "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'sales'"
                    " AND tablename = 'labelled_cases'"
                )
            )
        }
    assert definitions["ix_labelled_cases_tenant_id_workspace_id_step_decided_at_id"].endswith(
        "(tenant_id, workspace_id, step, decided_at, id)"
    )
    assert definitions["ix_labelled_cases_tenant_id_workspace_id_customer_code_step"].endswith(
        "(tenant_id, workspace_id, customer_code, step, decided_at, id)"
    )


# ------------------------------------------------------- partitions, term --


async def test_the_platforms_partition_function_makes_this_months_partition_policed(
    migrator: AsyncEngine,
) -> None:
    async with migrator.begin() as conn:
        await conn.execute(sa.text("SELECT platform.ensure_time_partitions(1)"))
    month = f"labelled_cases_{date.today():%Y_%m}"
    async with migrator.connect() as conn:
        for name in (month, "labelled_cases_default", "labelled_cases"):
            facts = (
                await conn.execute(
                    sa.text(
                        "SELECT c.relrowsecurity, c.relforcerowsecurity,"
                        " (SELECT pg_get_expr(p.polqual, p.polrelid) FROM pg_policy p"
                        "  WHERE p.polrelid = c.oid AND p.polname = 'tenant_isolation_' ||"
                        "  c.relname) AS qual,"
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
        await conn.execute(
            sa.text("SELECT platform._ensure_one_partition('sales.labelled_cases', '2020-01-01')")
        )
        await conn.execute(sa.text("SELECT platform.ensure_time_partitions(1)"))
        await conn.execute(
            sa.text(_INSERT.replace("now()", "'2020-01-15T00:00:00Z'")),
            {
                "id": uuid.uuid4(),
                "t": world.alpha.tenant_id.value,
                "w": world.alpha.workspace_id.value,
                "p": '"2500"',
                "k": '"2500"',
                "v": "confirmed",
                "by": _PERSON,
            },
        )
    now = datetime(2026, 11, 16, tzinfo=UTC)
    current = f"sales.labelled_cases_{date.today():%Y_%m}"

    # No term, or a term not enforced: nothing goes.
    for policy in (_policy(None), _policy(365, enforced=False)):
        await SqlLabelledCaseRetention(app_sessions, policy, FixedClock(now)).prune()
        async with migrator.connect() as conn:
            assert await _month_exists(conn, "sales.labelled_cases_2020_01")

    # A year: January 2020 goes, as `dw_app`; this month and the DEFAULT stay.
    await SqlLabelledCaseRetention(app_sessions, _policy(365), FixedClock(now)).prune()
    async with migrator.connect() as conn:
        assert not await _month_exists(conn, "sales.labelled_cases_2020_01")
        assert await _month_exists(conn, current)
        assert await _month_exists(conn, "sales.labelled_cases_default")


async def test_the_drop_function_is_not_publics_and_null_drops_nothing(
    sales_app_engine: AsyncEngine,
) -> None:
    async with sales_app_engine.begin() as conn:
        dropped = (
            await conn.execute(sa.text("SELECT sales.drop_expired_labelled_cases(NULL)"))
        ).all()
        public = await conn.scalar(
            sa.text(
                "SELECT has_function_privilege('public',"
                " 'sales.drop_expired_labelled_cases(timestamptz)', 'EXECUTE')"
            )
        )
    assert dropped == [] and public is False


# ------------------------------------------------------------- migration --

_DB = "dw_test_sales_labelled_cases_migration"
_REVISION = "eac4fabdb31a"
_BEFORE = "80584b911796"


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
    assert "sales.labelled_cases" in await _parents(own_database)

    down = run_alembic(["downgrade", _BEFORE], own_database.migrator)
    assert down.returncode == 0, down.stderr
    body = await _parents(own_database)
    assert "sales.labelled_cases" not in body and "purchasing.mailbox_files" in body

    up = run_alembic(["upgrade", _REVISION], own_database.migrator)
    assert up.returncode == 0, up.stderr
    assert "sales.labelled_cases" in await _parents(own_database)
