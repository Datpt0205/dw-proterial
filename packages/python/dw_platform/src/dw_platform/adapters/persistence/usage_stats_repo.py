"""SQL implementation of the F6 usage-stats repository.

Reads go through ``tenant_session`` so RLS bounds them to the caller's tenant,
and every query also filters ``tenant_id`` explicitly — the belt beside the
RLS brace, same as the admin console.

The three fact tables belong to the agent runtime, and dw_platform must not
import dw_agent_runtime (the dependency points the other way), so the columns
this reader needs are declared here as their own lightweight metadata. A
drift between these declarations and the real DDL fails loudly in the
integration test, not silently in production.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.naming import NAMING_CONVENTION
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_platform.application.usage_stats import DailyUsage, ToolUsage, UsecaseUsage

_metadata = sa.MetaData(schema="platform", naming_convention=NAMING_CONVENTION)

# Partial declarations on purpose: only what the GROUP BYs read.
_ledger = sa.Table(
    "model_usage_ledger",
    _metadata,
    sa.Column("tenant_id", PGUUID(as_uuid=True)),
    sa.Column("run_id", PGUUID(as_uuid=True)),
    sa.Column("worker_id", sa.String(64)),
    sa.Column("input_tokens", sa.BigInteger),
    sa.Column("output_tokens", sa.BigInteger),
    sa.Column("cost_usd", sa.Numeric(12, 6)),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

_tool_executions = sa.Table(
    "tool_executions",
    _metadata,
    sa.Column("tenant_id", PGUUID(as_uuid=True)),
    sa.Column("tool_name", sa.Text),
    sa.Column("status", sa.Text),
    sa.Column("started_at", sa.DateTime(timezone=True)),
)

# A row without a worker id cannot be blamed on a usecase; it still spent
# money, so it shows under one honest bucket instead of vanishing.
_UNATTRIBUTED = "(unattributed)"


@dataclass(frozen=True)
class SqlUsageStatsRepository:
    """Implements ``UsageStatsRepositoryPort``."""

    session_factory: async_sessionmaker[AsyncSession]

    async def usecases(self, context: AccessContext, since: datetime) -> list[UsecaseUsage]:
        usecase = sa.func.coalesce(_ledger.c.worker_id, _UNATTRIBUTED).label("worker_id")
        query = (
            sa.select(
                usecase,
                sa.func.count(sa.distinct(_ledger.c.run_id)).label("runs"),
                sa.func.count().label("model_calls"),
                sa.func.coalesce(sa.func.sum(_ledger.c.input_tokens), 0).label("input_tokens"),
                sa.func.coalesce(sa.func.sum(_ledger.c.output_tokens), 0).label("output_tokens"),
                sa.func.sum(_ledger.c.cost_usd).label("cost_usd"),
                sa.func.count().filter(_ledger.c.cost_usd.is_(None)).label("unpriced_calls"),
                sa.func.max(_ledger.c.created_at).label("last_used_at"),
            )
            .where(_ledger.c.tenant_id == context.tenant_id)
            .where(_ledger.c.created_at >= since)
            .group_by(usecase)
            .order_by(sa.desc(sa.text("cost_usd")).nulls_last(), sa.desc(sa.text("runs")))
        )
        scope = TenantScope.from_access_context(context)
        async with tenant_session(self.session_factory, scope) as session:
            rows = (await session.execute(query)).all()
        return [
            UsecaseUsage(
                worker_id=row.worker_id,
                runs=int(row.runs),
                model_calls=int(row.model_calls),
                input_tokens=int(row.input_tokens),
                output_tokens=int(row.output_tokens),
                cost_usd=float(row.cost_usd) if row.cost_usd is not None else None,
                unpriced_calls=int(row.unpriced_calls),
                last_used_at=row.last_used_at,
            )
            for row in rows
        ]

    async def daily(self, context: AccessContext, since: datetime) -> list[DailyUsage]:
        day = sa.func.date_trunc("day", _ledger.c.created_at).label("day")
        usecase = sa.func.coalesce(_ledger.c.worker_id, _UNATTRIBUTED).label("worker_id")
        query = (
            sa.select(
                day,
                usecase,
                sa.func.count(sa.distinct(_ledger.c.run_id)).label("runs"),
                sa.func.coalesce(sa.func.sum(_ledger.c.cost_usd), 0).label("cost_usd"),
            )
            .where(_ledger.c.tenant_id == context.tenant_id)
            .where(_ledger.c.created_at >= since)
            .group_by(day, usecase)
            .order_by(day)
        )
        scope = TenantScope.from_access_context(context)
        async with tenant_session(self.session_factory, scope) as session:
            rows = (await session.execute(query)).all()
        return [
            DailyUsage(
                day=row.day.date(),
                worker_id=row.worker_id,
                runs=int(row.runs),
                cost_usd=float(row.cost_usd),
            )
            for row in rows
        ]

    async def tools(self, context: AccessContext, since: datetime) -> list[ToolUsage]:
        query = (
            sa.select(
                _tool_executions.c.tool_name,
                sa.func.count().label("calls"),
                sa.func.count().filter(_tool_executions.c.status != "succeeded").label("failed"),
            )
            .where(_tool_executions.c.tenant_id == context.tenant_id)
            .where(_tool_executions.c.started_at >= since)
            .group_by(_tool_executions.c.tool_name)
            .order_by(sa.desc(sa.text("calls")))
        )
        scope = TenantScope.from_access_context(context)
        async with tenant_session(self.session_factory, scope) as session:
            rows = (await session.execute(query)).all()
        return [
            ToolUsage(tool_name=row.tool_name, calls=int(row.calls), failed=int(row.failed))
            for row in rows
        ]
