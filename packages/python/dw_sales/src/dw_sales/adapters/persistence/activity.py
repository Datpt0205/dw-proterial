"""What DW1's model steps did, in PostgreSQL (slice 3, migration 4bca401bcb3a).

`sales.step_outcomes` is append-only and range-partitioned by month on
`occurred_at`, narrowed by tenant and workspace like every case table. `dw_app`
may SELECT and INSERT, never UPDATE or DELETE: a row is a fact about the past.
A row leaves only with its month's partition, dropped by
`sales.drop_expired_step_outcomes` once the whole month is older than the term
`configs/policies/retention@*.yaml` gives the table (`SqlStepOutcomeRetention`,
the worker's `sales_step_outcomes_retention` lane), or with its tenant's
workspaces when the tenant is offboarded (`ON DELETE CASCADE`).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ports import UtcClock
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.retention_policy import RetentionPolicy
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.application.activity_ports import StepRowFilter
from dw_sales.application.ports import SalesScope
from dw_sales.domain.activity import StepOutcome
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_checks import ModelStep

_LOG = logging.getLogger("dw_sales.activity")

_TS = sa.TIMESTAMP(timezone=True)

# Mirrors the migration; constraints, policies and grants are the migration's.
step_outcomes = sa.Table(
    "step_outcomes",
    tables.metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("occurred_at", _TS, primary_key=True),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("lane", sa.Text),
    sa.Column("case_id", UUID(as_uuid=True)),
    sa.Column("line_no", sa.Integer),
    sa.Column("step", sa.Text, nullable=False),
    sa.Column("result", sa.Text, nullable=False),
    sa.Column("automatic", sa.Boolean, nullable=False),
    sa.Column("reason_code", sa.Text),
    sa.Column("refusals", JSONB, nullable=False),
    sa.Column("prompt", sa.Text, nullable=False),
    sa.Column("model_profile", sa.Text, nullable=False),
    sa.Column("model", sa.Text),
    sa.Column("calls", sa.Integer, nullable=False),
    sa.Column("duration_ms", sa.Integer),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
)
_S = step_outcomes

# The term's key in the retention policy's partitioned tables (`audit.tables`).
RETENTION_KEY = "sales.step_outcomes"
_DROP = sa.text("SELECT sales.drop_expired_step_outcomes(:cutoff)")


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


def _values(scope: SalesScope, row: StepOutcome) -> dict[str, object]:
    return {
        "id": row.outcome_id,
        **scope_values(scope),
        "occurred_at": row.occurred_at,
        "message_id": row.message_id,
        "lane": row.lane.value if row.lane is not None else None,
        "case_id": row.case_id,
        "line_no": row.line_no,
        "step": row.step.value,
        "result": row.result,
        "automatic": row.automatic,
        "reason_code": row.reason_code,
        "refusals": dict(row.refusals),
        "prompt": row.prompt,
        "model_profile": row.model_profile,
        "model": row.model,
        "calls": row.calls,
        "duration_ms": row.duration_ms,
    }


def _outcome(row: RowMapping) -> StepOutcome:
    return StepOutcome(
        outcome_id=row["id"],
        occurred_at=row["occurred_at"],
        message_id=row["message_id"],
        lane=CaseKind(row["lane"]) if row["lane"] is not None else None,
        case_id=row["case_id"],
        line_no=row["line_no"],
        step=ModelStep(row["step"]),
        result=row["result"],
        automatic=row["automatic"],
        reason_code=row["reason_code"],
        refusals=row["refusals"],
        prompt=row["prompt"],
        model_profile=row["model_profile"],
        model=row["model"],
        calls=row["calls"],
        duration_ms=row["duration_ms"],
    )


class SqlStepActivityLog:
    """Implements `StepActivityLogPort` in the unit of work's transaction."""

    def __init__(self, session: AsyncSession, scope: SalesScope) -> None:
        self._session = session
        self._scope = scope

    async def append(self, rows: Sequence[StepOutcome]) -> None:
        if rows:
            await self._session.execute(sa.insert(_S), [_values(self._scope, row) for row in rows])


@dataclass(frozen=True)
class SqlStepActivityReader:
    """Implements `StepActivityReadPort`: one short read per call, bound to
    the scope it is asked about. Each read is carried by an index led by
    `tenant_id` (the migration's `ix_step_outcomes_*`)."""

    session_factory: async_sessionmaker[AsyncSession]

    async def for_case(
        self, scope: SalesScope, kind: CaseKind, case_id: uuid.UUID
    ) -> Sequence[StepOutcome]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            rows = (
                await session.execute(
                    sa.select(_S)
                    .where(_S.c.case_id == case_id, _S.c.lane == kind.value)
                    .order_by(_S.c.occurred_at, _S.c.id)
                )
            ).mappings()
            return [_outcome(row) for row in rows]

    async def between(
        self, scope: SalesScope, start: datetime, end: datetime, lane: CaseKind | None
    ) -> Sequence[StepOutcome]:
        query = sa.select(_S).where(_S.c.occurred_at >= start, _S.c.occurred_at < end)
        if lane is not None:
            query = query.where(_S.c.lane == lane.value)
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            rows = (await session.execute(query.order_by(_S.c.occurred_at, _S.c.id))).mappings()
            return [_outcome(row) for row in rows]

    async def cases(self, scope: SalesScope, rows: StepRowFilter) -> frozenset[uuid.UUID]:
        """`StepRowFilter.matches` in SQL, held to it by
        `test_sales_step_outcomes.py`: carried by
        `ix_step_outcomes_tenant_id_workspace_id_step_occurred_at`."""
        query = (
            sa.select(_S.c.case_id)
            .distinct()
            .where(
                _S.c.step == rows.step.value,
                _S.c.lane == rows.lane.value,
                _S.c.case_id.is_not(None),
                _S.c.occurred_at >= rows.start,
                _S.c.occurred_at < rows.end,
            )
        )
        if rows.handled_by is not None:
            query = query.where(_S.c.automatic.is_(rows.handled_by == "dw1"))
        if rows.result is not None:
            query = query.where(_S.c.result == rows.result)
        if rows.reason_code is not None:
            query = query.where(
                sa.or_(
                    _S.c.reason_code == rows.reason_code,
                    _S.c.refusals.has_key(rows.reason_code),
                )
            )
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            return frozenset((await session.scalars(query)).all())


@dataclass(frozen=True)
class SqlStepOutcomeRetention:
    """Implements `dw_worker.consumers.retention.RetentionPrunePort`: drops
    the months of `sales.step_outcomes` wholly older than the policy's term.

    The partitions themselves are created ahead by the platform's
    `partitions` lane (`platform.ensure_time_partitions`, which names this
    table since migration 4bca401bcb3a). The term is the policy file's: a
    table with no term, or a policy not enforced, reaches the function as
    NULL, which drops nothing.
    """

    session_factory: async_sessionmaker[AsyncSession]
    policy: RetentionPolicy
    clock: UtcClock

    async def prune(self) -> None:
        cutoff = self.policy.audit.cutoff_for(RETENTION_KEY, now=self.clock.now())
        async with self.session_factory() as session, session.begin():
            dropped = list((await session.scalars(_DROP, {"cutoff": cutoff})).all())
        if dropped:
            _LOG.info(
                "dropped expired step outcome partitions",
                extra={"partitions": dropped, "policy_version": self.policy.policy_version},
            )
