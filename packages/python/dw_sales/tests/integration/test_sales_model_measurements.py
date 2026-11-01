"""`platform.model_step_measurements` (migration 2d97d03c937a, moved by
315c7ae4844f; dw_sales ADR 0005, addendum of 2026-10-23) against a real
database, as `dw_app`.

The store a model step's switch is held to: written by the attesting lane
with its audit event in one transaction, read under the tenant's RLS only
(another tenant's pass never readies this tenant's step), append-only for
the application role, and a CHECK that a passing row meets its bar. The
migration goes down and up again on a database of its own.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

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

from dw_agent_runtime.adapters.model_measurements import SqlMeasurementLog, SqlModelMeasurements
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.domain.audit import system_actor
from dw_sales.application.model_readiness import ATTEST_LANE, ModelAttestation, ModelReadiness
from dw_sales.application.ports import SalesScope
from dw_sales.domain.order_checks import ModelStep
from dw_sales.testing.measurements import FixedStepModel

pytestmark = pytest.mark.integration

_MODEL = "qwen3.5-9b-dw"
_AT = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
_STEP = ModelStep.MESSAGE_INTENT
_PROMPT = "sales.message_intent@1.0.0"


def _attestation(
    sessions: async_sessionmaker[AsyncSession], at: datetime = _AT
) -> ModelAttestation:
    return ModelAttestation(
        SqlMeasurementLog(sessions, audit=SqlAuditRepository), FixedClock(at), Uuid4Generator()
    )


async def _attest(
    sessions: async_sessionmaker[AsyncSession],
    scope: SalesScope,
    value: float,
    *,
    at: datetime = _AT,
    model: str = _MODEL,
) -> uuid.UUID:
    row = await _attestation(sessions, at).attest(
        scope, _STEP, model=model, value=value, held=True, dataset="sales_intent@1.0.0"
    )
    return row.measurement_id


async def test_the_lane_writes_the_row_and_its_audit_event_and_the_latest_is_read_back(
    app_sessions: async_sessionmaker[AsyncSession], migrator: AsyncEngine, world: World
) -> None:
    store = SqlModelMeasurements(app_sessions)
    first = await _attest(app_sessions, world.alpha, 0.95)
    later = await _attest(app_sessions, world.alpha, 0.5, at=_AT + timedelta(hours=1))

    latest = await store.latest(world.alpha, _STEP, model=_MODEL, prompt=_PROMPT)
    assert latest is not None and latest.measurement_id == later and not latest.passed
    assert (latest.value, latest.bar) == (0.5, 0.9)
    assert latest.recorded_by == f"system:{ATTEST_LANE}"
    # Read from another workspace of the same tenant: the rows are the tenant's.
    other = await store.latest(world.alpha_other, _STEP, model=_MODEL, prompt=_PROMPT)
    assert other is not None and other.measurement_id == later
    assert await store.latest(world.alpha, _STEP, model="other", prompt=_PROMPT) is None

    async with migrator.connect() as conn:
        audited = (
            await conn.execute(
                sa.text(
                    "SELECT resource_id, actor_id FROM platform.audit_events"
                    " WHERE tenant_id = :t AND action = 'sales.model_step.measured'"
                ),
                {"t": world.alpha.tenant_id.value},
            )
        ).all()
    assert {row.resource_id for row in audited} == {str(first), str(later)}
    assert {row.actor_id for row in audited} == {system_actor(ATTEST_LANE).value}


async def test_another_tenants_pass_never_readies_this_tenants_step(
    app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    await _attest(app_sessions, world.beta, 0.99)
    store = SqlModelMeasurements(app_sessions)
    assert await store.latest(world.alpha, _STEP, model=_MODEL, prompt=_PROMPT) is None
    readiness = ModelReadiness(store, FixedStepModel(_MODEL))
    assert not (await readiness.check(world.alpha, _STEP)).ready
    assert (await readiness.check(world.beta, _STEP)).ready


async def test_a_row_written_for_another_tenant_is_refused_by_the_policy(
    app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    """The scope binds alpha; a row naming beta does not pass WITH CHECK."""
    async with app_sessions() as session, session.begin():
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(world.alpha.tenant_id.value)},
        )
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                sa.text(
                    "INSERT INTO platform.model_step_measurements (id, tenant_id, workspace_id,"
                    " step, model, prompt, metric, value, bar, passed, dataset, measured_at,"
                    " recorded_by) VALUES (:id, :t, :w, 'message_intent', 'm', :p,"
                    " 'all.kind_accuracy', 0.95, 0.9, true, 'sales_intent@1.0.0', now(),"
                    " 'system:sales_model_attest')"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": world.beta.tenant_id.value,
                    "w": world.beta.workspace_id.value,
                    "p": _PROMPT,
                },
            )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE platform.model_step_measurements SET passed = true",
        "DELETE FROM platform.model_step_measurements",
    ],
)
async def test_the_application_can_neither_rewrite_nor_remove_a_measurement(
    app_sessions: async_sessionmaker[AsyncSession], world: World, statement: str
) -> None:
    await _attest(app_sessions, world.alpha, 0.5)
    async with app_sessions() as session, session.begin():
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(world.alpha.tenant_id.value)},
        )
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text(statement))


async def test_a_passing_row_below_its_bar_is_refused_by_the_database(
    migrator: AsyncEngine, world: World
) -> None:
    with pytest.raises(IntegrityError, match="ck_model_step_measurements_passed"):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO platform.model_step_measurements (id, tenant_id, workspace_id,"
                    " step, model, prompt, metric, value, bar, passed, dataset, measured_at,"
                    " recorded_by) VALUES (:id, :t, :w, 'message_intent', 'm', :p,"
                    " 'all.kind_accuracy', 0.5, 0.9, true, 'sales_intent@1.0.0', now(),"
                    " 'system:sales_model_attest')"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": world.alpha.tenant_id.value,
                    "w": world.alpha.workspace_id.value,
                    "p": _PROMPT,
                },
            )


# ------------------------------------------------------------- migration --

_DB = "dw_test_sales_measurements_migration"
_REVISION = "2d97d03c937a"
_BEFORE = "e8192ed5cc59"


@pytest.fixture
async def own_database() -> AsyncIterator[DatabaseUrls]:
    urls = database_urls(_DB)
    await recreate_database(urls.admin, _DB)
    result = run_alembic(["upgrade", _REVISION], urls.migrator)
    assert result.returncode == 0, result.stderr
    yield urls


async def _exists(urls: DatabaseUrls) -> bool:
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            found = await conn.scalar(
                sa.text("SELECT to_regclass('sales.model_step_measurements') IS NOT NULL")
            )
    finally:
        await engine.dispose()
    return bool(found)


async def test_the_migration_goes_down_and_up_again(own_database: DatabaseUrls) -> None:
    assert await _exists(own_database)
    down = run_alembic(["downgrade", _BEFORE], own_database.migrator)
    assert down.returncode == 0, down.stderr
    assert not await _exists(own_database)
    up = run_alembic(["upgrade", _REVISION], own_database.migrator)
    assert up.returncode == 0, up.stderr
    assert await _exists(own_database)
