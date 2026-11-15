"""Labelled cases in PostgreSQL (ticket 43, migration eac4fabdb31a).

`sales.labelled_cases` is append-only and range-partitioned by month on
`decided_at`, narrowed by tenant and workspace like every case table. `dw_app`
may SELECT and INSERT, never UPDATE or DELETE: a person's decision is a fact
about the past. A row leaves only with its month's partition, dropped by
`sales.drop_expired_labelled_cases` once the whole month is older than the
term `configs/policies/retention@*.yaml` gives the table
(`SqlLabelledCaseRetention`, the worker's `sales_labelled_cases_retention`
lane), or with its tenant's workspaces when the tenant is offboarded.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ports import UtcClock
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.retention_policy import RetentionPolicy
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.application.autonomy import VersionKey
from dw_sales.application.labelled_cases import MAX_READ, StepLabels
from dw_sales.application.ports import SalesScope
from dw_sales.domain.autonomy import LabelledScore
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.labelled_cases import LabelledCase
from dw_sales.domain.order_checks import ModelStep

_LOG = logging.getLogger("dw_sales.labelled_cases")

_TS = sa.TIMESTAMP(timezone=True)

# Mirrors the migration; constraints, policies and grants are the migration's.
labelled_cases = sa.Table(
    "labelled_cases",
    tables.metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("decided_at", _TS, primary_key=True),
    sa.Column("step", sa.Text, nullable=False),
    sa.Column("lane", sa.Text, nullable=False),
    sa.Column("case_id", UUID(as_uuid=True)),
    sa.Column("customer_code", sa.Text),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("attachment_id", sa.Text),
    sa.Column("line_no", sa.Integer),
    sa.Column("field", sa.Text, nullable=False),
    # `none_as_null`: a rejection keeps SQL NULL, never the JSON `null`.
    sa.Column("proposed", JSONB(none_as_null=True), nullable=False),
    sa.Column("kept", JSONB(none_as_null=True)),
    sa.Column("verdict", sa.Text, nullable=False),
    sa.Column("prompt", sa.Text, nullable=False),
    sa.Column("model_profile", sa.Text),
    sa.Column("rules", sa.Text),
    sa.Column("decided_by", UUID(as_uuid=True), nullable=False),
    # Ticket 44 (migration efc46a50e75e).
    sa.Column("confidence", sa.Float),
    sa.Column("gate", sa.Text),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
)
_L = labelled_cases

# The term's key in the retention policy's partitioned tables (`audit.tables`).
RETENTION_KEY = "sales.labelled_cases"
_DROP = sa.text("SELECT sales.drop_expired_labelled_cases(:cutoff)")


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


def _values(scope: SalesScope, case: LabelledCase) -> dict[str, object]:
    return {
        "id": case.label_id,
        **scope_values(scope),
        "decided_at": case.decided_at,
        "step": case.step.value,
        "lane": case.lane.value,
        "case_id": case.case_id,
        "customer_code": case.customer_code,
        "message_id": case.message_id,
        "attachment_id": case.attachment_id,
        "line_no": case.line_no,
        "field": case.field,
        "proposed": case.proposed,
        "kept": case.kept,
        "verdict": case.verdict,
        "prompt": case.prompt,
        "model_profile": case.model_profile,
        "rules": case.rules,
        "decided_by": case.decided_by,
        "confidence": case.confidence,
        "gate": case.gate,
    }


def _case(row: RowMapping) -> LabelledCase:
    # `verdict` is derived from the two values (the CHECK holds the column to
    # the same rule), so it is not read back.
    return LabelledCase(
        label_id=row["id"],
        decided_at=row["decided_at"],
        step=ModelStep(row["step"]),
        lane=CaseKind(row["lane"]),
        case_id=row["case_id"],
        customer_code=row["customer_code"],
        message_id=row["message_id"],
        attachment_id=row["attachment_id"],
        line_no=row["line_no"],
        field=row["field"],
        proposed=row["proposed"],
        kept=row["kept"],
        prompt=row["prompt"],
        model_profile=row["model_profile"],
        rules=row["rules"],
        decided_by=row["decided_by"],
        confidence=row["confidence"],
        gate=row["gate"],
    )


class SqlLabelledCaseLog:
    """Implements `LabelledCaseLogPort` in the unit of work's transaction."""

    def __init__(self, session: AsyncSession, scope: SalesScope) -> None:
        self._session = session
        self._scope = scope

    async def append(self, cases: Sequence[LabelledCase]) -> None:
        if cases:
            await self._session.execute(
                sa.insert(_L), [_values(self._scope, case) for case in cases]
            )


@dataclass(frozen=True)
class SqlLabelledCaseReader:
    """Implements `LabelledCaseReadPort`: one short read per call, bound to
    the scope it is asked about, each carried by an index led by `tenant_id`
    (the migration's `ix_labelled_cases_*`)."""

    session_factory: async_sessionmaker[AsyncSession]

    async def latest(
        self,
        scope: SalesScope,
        step: ModelStep,
        *,
        customer_code: str | None = None,
        limit: int = MAX_READ,
    ) -> Sequence[LabelledCase]:
        query = sa.select(_L).where(_L.c.step == step.value)
        if customer_code is not None:
            query = query.where(_L.c.customer_code == customer_code)
        query = query.order_by(_L.c.decided_at.desc(), _L.c.id.desc()).limit(
            max(0, min(limit, MAX_READ))
        )
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            return [_case(row) for row in (await session.execute(query)).mappings()]

    async def counts(self, scope: SalesScope) -> Mapping[ModelStep, StepLabels]:
        query = sa.select(_L.c.step, _L.c.verdict, sa.func.count()).group_by(
            _L.c.step, _L.c.verdict
        )
        counted: dict[ModelStep, StepLabels] = {}
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            for step, verdict, count in (await session.execute(query)).all():
                found = ModelStep(step)
                counted[found] = counted.get(found, StepLabels()).counted(verdict, count)
        return counted

    async def gated(self, scope: SalesScope) -> Mapping[VersionKey, Sequence[LabelledScore]]:
        """Implements `GatedLabelsPort`: the confidence, verdict and gate of
        every case of a gated result, by step, prompt and model profile.
        Three short columns per case, read whole: a threshold is set from all
        of them, and they are bounded by the table's 365-day term."""
        query = sa.select(
            _L.c.step, _L.c.prompt, _L.c.model_profile, _L.c.confidence, _L.c.verdict, _L.c.gate
        ).where(_L.c.gate.is_not(None), _L.c.model_profile.is_not(None))
        found: dict[VersionKey, list[LabelledScore]] = {}
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            for step, prompt, profile, confidence, verdict, gate in (
                await session.execute(query)
            ).all():
                found.setdefault((ModelStep(step), prompt, profile), []).append(
                    LabelledScore(confidence=confidence, verdict=verdict, gate=gate)
                )
        return found


@dataclass(frozen=True)
class SqlLabelledCaseRetention:
    """Implements `dw_worker.consumers.retention.RetentionPrunePort`: drops
    the months of `sales.labelled_cases` wholly older than the policy's term,
    as `SqlStepOutcomeRetention` does for the step rows. The partitions are
    created ahead by the platform's `partitions` lane. A table with no term,
    or a policy not enforced, reaches the function as NULL, which drops
    nothing."""

    session_factory: async_sessionmaker[AsyncSession]
    policy: RetentionPolicy
    clock: UtcClock

    async def prune(self) -> None:
        cutoff = self.policy.audit.cutoff_for(RETENTION_KEY, now=self.clock.now())
        async with self.session_factory() as session, session.begin():
            dropped = list((await session.scalars(_DROP, {"cutoff": cutoff})).all())
        if dropped:
            _LOG.info(
                "dropped expired labelled case partitions",
                extra={"partitions": dropped, "policy_version": self.policy.policy_version},
            )
