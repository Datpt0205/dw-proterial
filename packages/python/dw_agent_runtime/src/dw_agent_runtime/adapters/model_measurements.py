"""Live measurements of every context's model steps in PostgreSQL
(`dw_agent_runtime.model.readiness`; Sales' migration 2d97d03c937a, moved to
`platform` by the ADR 0013/0014 lift).

`platform.model_step_measurements` is narrowed by tenant only, like the rules
a measurement backs: RLS keeps one tenant's rows from another, and nothing
here names a tenant beyond binding the scope. `dw_app` may SELECT and
INSERT, never UPDATE or DELETE: a measurement is a fact about the past.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.adapters import runtime_tables
from dw_agent_runtime.model.readiness import MeasuredScope, ModelMeasurement
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.ports import AuditRepositoryPort
from dw_platform.domain.audit import AuditEvent

_M = runtime_tables.model_step_measurements
AuditFactory = Callable[[AsyncSession], AuditRepositoryPort]


def _bound(scope: MeasuredScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


def _measurement(row: RowMapping) -> ModelMeasurement:
    return ModelMeasurement(
        measurement_id=row["id"],
        step=row["step"],
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
        self, scope: MeasuredScope, step: str, *, model: str, prompt: str
    ) -> ModelMeasurement | None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            row = (
                (
                    await session.execute(
                        sa.select(_M)
                        .where(_M.c.step == str(step), _M.c.model == model, _M.c.prompt == prompt)
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
        self, scope: MeasuredScope, measurement: ModelMeasurement, event: AuditEvent
    ) -> None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            await session.execute(
                sa.insert(_M).values(
                    id=measurement.measurement_id,
                    tenant_id=scope.tenant_id.value,
                    workspace_id=scope.workspace_id.value,
                    step=measurement.step,
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
