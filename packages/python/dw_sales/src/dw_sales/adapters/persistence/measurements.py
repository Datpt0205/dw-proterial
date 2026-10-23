"""Live measurements of DW1's model steps in PostgreSQL (dw_sales ADR 0005,
addendum of 2026-10-23, migration 2d97d03c937a).

`sales.model_step_measurements` is narrowed by tenant only, like the rules a
measurement backs: RLS keeps one tenant's rows from another, and nothing here
names a tenant beyond binding the scope. `dw_app` may SELECT and INSERT, never
UPDATE or DELETE: a measurement is a fact about the past.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.adapters.persistence.uow import AuditFactory
from dw_sales.application.model_readiness import ModelMeasurement
from dw_sales.application.ports import SalesScope
from dw_sales.domain.order_checks import ModelStep

_M = tables.model_step_measurements


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


def _measurement(row: RowMapping) -> ModelMeasurement:
    return ModelMeasurement(
        measurement_id=row["id"],
        step=ModelStep(row["step"]),
        model=row["model"],
        prompt=row["prompt"],
        metric=row["metric"],
        value=float(row["value"]),
        bar=float(row["bar"]),
        passed=row["passed"],
        dataset=row["dataset"],
        measured_at=row["measured_at"],
        recorded_by=row["recorded_by"],
    )


@dataclass(frozen=True)
class SqlModelMeasurements:
    """Implements `ModelMeasurementsPort`: one short read per call, bound to
    the scope it is asked about."""

    session_factory: async_sessionmaker[AsyncSession]

    async def latest(
        self, scope: SalesScope, step: ModelStep, *, model: str, prompt: str
    ) -> ModelMeasurement | None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            row = (
                (
                    await session.execute(
                        sa.select(_M)
                        .where(_M.c.step == step.value, _M.c.model == model, _M.c.prompt == prompt)
                        .order_by(_M.c.measured_at.desc(), _M.c.id.desc())
                        .limit(1)
                    )
                )
                .mappings()
                .first()
            )
        return None if row is None else _measurement(row)


@dataclass(frozen=True)
class SqlMeasurementLog:
    """Implements `MeasurementLogPort`: the row and its audit event in one
    transaction under the scope's tenant, or neither."""

    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    async def record(
        self, scope: SalesScope, measurement: ModelMeasurement, event: AuditEvent
    ) -> None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            await session.execute(
                sa.insert(_M).values(
                    id=measurement.measurement_id,
                    **scope_values(scope),
                    step=measurement.step.value,
                    model=measurement.model,
                    prompt=measurement.prompt,
                    metric=measurement.metric,
                    # As the column holds it: four places, exactly.
                    value=Decimal(str(measurement.value)),
                    bar=Decimal(str(measurement.bar)),
                    passed=measurement.passed,
                    dataset=measurement.dataset,
                    measured_at=measurement.measured_at,
                    recorded_by=measurement.recorded_by,
                )
            )
            await self.audit(session).append(event)
