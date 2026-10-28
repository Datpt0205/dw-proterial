"""`sales.export_control_screenings` (migration 1a21c3a78c93) against a real
database, as `dw_app` wherever isolation is the question: the latest result
per customer and step, replaced in place with its audit row, under tenant AND
workspace RLS, never deleted by the application, and refused by its CHECKs
where the domain refuses it."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
import sqlalchemy as sa
from sales_harness import World, seed_world
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.adapters.persistence.tenant_session import TenantScope, bind_tenant
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.persistence.export_control import SqlExportControlUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.domain.export_control import (
    OUTCOMES,
    Evidence,
    ScreeningRecord,
    ScreeningStep,
)

pytestmark = pytest.mark.integration

AT = datetime(2026, 10, 1, 3, tzinfo=UTC)
_DOCUMENTED = {("noc", "received"), ("esf", "approved")}
_FILE = "CAST(:f AS uuid)"
_INSERT = (
    "INSERT INTO sales.export_control_screenings (tenant_id, workspace_id,"
    " customer_code, step, outcome, checked_on, fiscal_year, answers,"
    " evidence_file_id, evidence_sha256, evidence_content_type, evidence_size,"
    " recorded_by, recorded_at) VALUES (:t, :w, :c, :s, :o, '2026-10-01',"
    f" CAST(:fy AS integer), CAST(:a AS jsonb), {_FILE},"
    f" CASE WHEN {_FILE} IS NULL THEN NULL ELSE repeat('a', 64) END,"
    f" CASE WHEN {_FILE} IS NULL THEN NULL ELSE 'application/pdf' END,"
    f" CASE WHEN {_FILE} IS NULL THEN NULL ELSE 9 END, gen_random_uuid(), now())"
)
WHO = uuid.UUID(int=0xEC)


@pytest.fixture
async def world(migrator: AsyncEngine) -> World:
    return await seed_world(migrator)


@pytest.fixture
def screenings(app_sessions: async_sessionmaker[AsyncSession]) -> SqlExportControlUnitOfWorkFactory:
    return SqlExportControlUnitOfWorkFactory(app_sessions, audit=SqlAuditRepository)


def _record(step: ScreeningStep, outcome: str, **fields: object) -> ScreeningRecord:
    return ScreeningRecord.model_validate(
        {
            "customer_code": "VLX",
            "step": step,
            "outcome": outcome,
            "checked_on": date(2026, 10, 1),
            "recorded_by": WHO,
            "recorded_at": AT,
            **fields,
        }
    )


def _audit(scope: SalesScope, record: ScreeningRecord) -> AuditEvent:
    return AuditEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(scope.tenant_id.value),
        workspace_id=WorkspaceId(scope.workspace_id.value),
        actor_id=UserId(WHO),
        action=f"sales.export_control.{record.step.value}.{record.outcome}",
        resource_type="sales_customer",
        resource_id=record.customer_code,
        occurred_at=AT,
        details={},
    )


async def _put(
    factory: SqlExportControlUnitOfWorkFactory, scope: SalesScope, record: ScreeningRecord
) -> None:
    async with factory(scope) as work:
        await work.screenings.put(record)
        await work.audit.append(_audit(scope, record))
        await work.commit()


async def _read(
    factory: SqlExportControlUnitOfWorkFactory, scope: SalesScope
) -> list[ScreeningRecord]:
    async with factory(scope) as work:
        return list(await work.screenings.records())


async def test_a_result_replaces_the_last_of_its_step_and_keeps_the_others(
    world: World, screenings: SqlExportControlUnitOfWorkFactory
) -> None:
    await _put(screenings, world.alpha, _record(ScreeningStep.DENIAL_LIST, "clear"))
    await _put(screenings, world.alpha, _record(ScreeningStep.DENIAL_LIST, "match"))
    pdf = Evidence(
        file_id=uuid.uuid4(), sha256="b" * 64, content_type="application/pdf", size_bytes=9
    )
    noc = _record(ScreeningStep.NOC, "received", evidence=pdf)
    await _put(screenings, world.alpha, noc)

    held = {r.step: r for r in await _read(screenings, world.alpha)}
    assert held[ScreeningStep.DENIAL_LIST].outcome == "match"
    assert held[ScreeningStep.NOC] == noc


async def test_another_workspace_and_another_tenant_read_nothing(
    world: World, screenings: SqlExportControlUnitOfWorkFactory
) -> None:
    await _put(screenings, world.alpha, _record(ScreeningStep.DENIAL_LIST, "match"))
    assert await _read(screenings, world.alpha_other) == []
    assert await _read(screenings, world.beta) == []


async def test_the_application_cannot_delete_a_result(
    world: World,
    screenings: SqlExportControlUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _put(screenings, world.alpha, _record(ScreeningStep.DENIAL_LIST, "clear"))
    async with app_sessions() as session, session.begin():
        await bind_tenant(
            session,
            TenantScope(
                tenant_id=world.alpha.tenant_id.value, workspace_id=world.alpha.workspace_id.value
            ),
        )
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text("DELETE FROM sales.export_control_screenings"))


async def test_the_checks_hold_the_outcomes_the_domain_names(migrator: AsyncEngine) -> None:
    """Every outcome outside `OUTCOMES` is refused by the table, and every one
    inside is taken: the two lists cannot drift apart quietly."""
    world = await seed_world(migrator)
    t, w = world.alpha.tenant_id.value, world.alpha.workspace_id.value
    steps = [s.value for s in ScreeningStep]
    every = {o for outs in OUTCOMES.values() for o in outs} | {"approved", "bogus"}
    for step in steps:
        for outcome in sorted(every):
            allowed = outcome in OUTCOMES[ScreeningStep(step)]
            row = {
                "t": t,
                "w": w,
                "c": f"C{abs(hash((step, outcome))) % 10_000:04d}",
                "s": step,
                "o": outcome,
                "fy": 2026 if step == "esf" else None,
                "a": '{"rf01": false}' if step == "red_flag" else "{}",
                "f": uuid.uuid4()
                if (step, outcome) in {("noc", "received"), ("esf", "approved")}
                else None,
            }
            statement = sa.text(_INSERT)
            async with migrator.connect() as conn:
                transaction = await conn.begin()
                try:
                    if allowed:
                        await conn.execute(statement, row)
                    else:
                        with pytest.raises(IntegrityError):
                            await conn.execute(statement, row)
                finally:
                    await transaction.rollback()


async def test_a_received_noc_without_its_document_is_refused(migrator: AsyncEngine) -> None:
    world = await seed_world(migrator)
    async with migrator.connect() as conn:
        transaction = await conn.begin()
        try:
            with pytest.raises(IntegrityError, match="ck_export_control_screenings_evidence"):
                await conn.execute(
                    sa.text(
                        "INSERT INTO sales.export_control_screenings (tenant_id, workspace_id,"
                        " customer_code, step, outcome, checked_on, recorded_by, recorded_at)"
                        " VALUES (:t, :w, 'VLX', 'noc', 'received', '2026-10-01',"
                        " gen_random_uuid(), now())"
                    ),
                    {"t": world.alpha.tenant_id.value, "w": world.alpha.workspace_id.value},
                )
        finally:
            await transaction.rollback()
