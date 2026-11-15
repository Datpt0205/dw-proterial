"""Each step's threshold in PostgreSQL (ticket 44, migration efc46a50e75e).

`sales.step_thresholds` holds one row per workspace, step, prompt and model
profile, narrowed by tenant and workspace like every case table. The worker's
`sales_auto_apply` lane replaces the rows it measured (`save`, an upsert, with
its audit rows in the same transaction); the gate reads one (`threshold`),
the head's view all of them (`thresholds`). `dw_app` holds no DELETE: a
threshold leaves only with its tenant's workspaces.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.adapters.persistence.uow import AuditFactory
from dw_sales.application.ports import SalesScope
from dw_sales.domain.autonomy import StepThreshold, Tier
from dw_sales.domain.order_checks import ModelStep

_TS = sa.TIMESTAMP(timezone=True)

# Mirrors the migration; constraints, policies and grants are the migration's.
step_thresholds = sa.Table(
    "step_thresholds",
    tables.metadata,
    sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("step", sa.Text, primary_key=True),
    sa.Column("prompt", sa.Text, primary_key=True),
    sa.Column("model_profile", sa.Text, primary_key=True),
    sa.Column("tier", sa.Text, nullable=False),
    sa.Column("target", sa.Float, nullable=False),
    sa.Column("needed", sa.Integer, nullable=False),
    sa.Column("cases", sa.Integer, nullable=False),
    sa.Column("threshold", sa.Float),
    sa.Column("accepted", sa.Integer, nullable=False),
    sa.Column("errors", sa.Integer, nullable=False),
    sa.Column("audits", sa.Integer, nullable=False),
    sa.Column("audit_errors", sa.Integer, nullable=False),
    sa.Column("stopped", sa.Boolean, nullable=False),
    sa.Column("computed_at", _TS, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
)
_T = step_thresholds
_MEASURED = (
    "tier",
    "target",
    "needed",
    "cases",
    "threshold",
    "accepted",
    "errors",
    "audits",
    "audit_errors",
    "stopped",
    "computed_at",
)


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


def _values(scope: SalesScope, threshold: StepThreshold) -> dict[str, object]:
    return {
        **scope_values(scope),
        "step": threshold.step.value,
        "prompt": threshold.prompt,
        "model_profile": threshold.model_profile,
        "tier": threshold.tier.value,
        "target": threshold.target,
        "needed": threshold.needed,
        "cases": threshold.cases,
        "threshold": threshold.threshold,
        "accepted": threshold.accepted,
        "errors": threshold.errors,
        "audits": threshold.audits,
        "audit_errors": threshold.audit_errors,
        "stopped": threshold.stopped,
        "computed_at": threshold.computed_at,
    }


def _threshold(row: RowMapping) -> StepThreshold:
    return StepThreshold(
        step=ModelStep(row["step"]),
        prompt=row["prompt"],
        model_profile=row["model_profile"],
        tier=Tier(row["tier"]),
        target=row["target"],
        needed=row["needed"],
        cases=row["cases"],
        threshold=row["threshold"],
        accepted=row["accepted"],
        errors=row["errors"],
        audits=row["audits"],
        audit_errors=row["audit_errors"],
        stopped=row["stopped"],
        computed_at=row["computed_at"],
    )


@dataclass(frozen=True)
class SqlStepThresholds:
    """Implements `StepThresholdStorePort`, each call one short transaction
    bound to the scope it is asked about."""

    session_factory: async_sessionmaker[AsyncSession]
    # The platform audit repository over the session, as the unit of work
    # takes it: the lane's audit rows commit with the thresholds.
    audit: AuditFactory

    async def threshold(
        self, scope: SalesScope, step: ModelStep, prompt: str, model_profile: str
    ) -> StepThreshold | None:
        query = sa.select(_T).where(
            _T.c.step == step.value, _T.c.prompt == prompt, _T.c.model_profile == model_profile
        )
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            row = (await session.execute(query)).mappings().first()
        return None if row is None else _threshold(row)

    async def thresholds(self, scope: SalesScope) -> Sequence[StepThreshold]:
        query = sa.select(_T).order_by(_T.c.step, _T.c.computed_at)
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            return [_threshold(row) for row in (await session.execute(query)).mappings()]

    async def save(
        self,
        scope: SalesScope,
        thresholds: Sequence[StepThreshold],
        audits: Sequence[AuditEvent],
    ) -> None:
        if not thresholds:
            return
        statement = insert(_T).values([_values(scope, t) for t in thresholds])
        statement = statement.on_conflict_do_update(
            constraint="pk_step_thresholds",
            set_={name: statement.excluded[name] for name in _MEASURED},
        )
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            await session.execute(statement)
            repository = self.audit(session)
            for event in audits:
                await repository.append(event)
