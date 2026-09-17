"""Model usage to the database ledger, and to telemetry, without choosing.

Traces are sampled; an invoice is not. A vendor trace is the right place to look
at one call and the wrong place to answer "what did this tenant cost last
month", so both recorders run - the composite exists because that is an "and",
not an "or", and a wiring that had to pick one would eventually pick wrong.

The ledger is append-only by grant (`dw_app` may INSERT and SELECT, migration
0024) and tenant-scoped by RLS, so this binds the tenant like every other write
path rather than trusting the row it is about to insert.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.adapters.runtime_tables import model_usage_ledger
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.gateway import ModelUsage, UsageRecorderPort
from dw_agent_runtime.ports import ModelRequest
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session

_LOG = logging.getLogger("dw_agent_runtime.usage")


@dataclass(frozen=True)
class SqlUsageRecorder:
    """Implements ``UsageRecorderPort`` on ``platform.model_usage_ledger``."""

    session_factory: async_sessionmaker[AsyncSession]
    id_generator: IdGenerator
    clock: UtcClock

    async def record(
        self, run_context: RunContext, request: ModelRequest, usage: ModelUsage
    ) -> None:
        scope = TenantScope(
            tenant_id=run_context.tenant_id,
            workspace_id=run_context.workspace_id,
            principal_id=run_context.actor_id,
        )
        async with tenant_session(self.session_factory, scope) as session:
            await session.execute(
                sa.insert(model_usage_ledger).values(
                    id=self.id_generator.new_uuid(),
                    tenant_id=run_context.tenant_id,
                    workspace_id=run_context.workspace_id,
                    run_id=run_context.run_id,
                    worker_id=run_context.worker_id,
                    task=request.task,
                    prompt_id=request.prompt_id,
                    prompt_version=request.prompt_version,
                    provider=usage.provider,
                    model=usage.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    # NULL, not 0, when the provider reported no cost. A zero in
                    # a cost column reads as "this call was free", which is a
                    # different claim from "nobody priced it" - and the second
                    # one is what an unpriced route means. Decimal, not float,
                    # because the column is numeric and money that rounds
                    # differently per row is not money.
                    cost_usd=Decimal(str(usage.cost_usd)) if usage.cost_usd else None,
                    created_at=self.clock.now(),
                )
            )


@dataclass(frozen=True)
class CompositeUsageRecorder:
    """Fans one call's usage out to every recorder, and lets none of them win.

    A recorder that raises would take the run down over bookkeeping, and one
    that raises must not stop the others from getting the record either. So each
    is tried, each failure is logged, and the caller is never told - the model
    answer it is holding is already paid for.
    """

    recorders: Sequence[UsageRecorderPort]

    async def record(
        self, run_context: RunContext, request: ModelRequest, usage: ModelUsage
    ) -> None:
        for recorder in self.recorders:
            try:
                await recorder.record(run_context, request, usage)
            except Exception:
                _LOG.warning(
                    "usage recorder %s failed for run %s",
                    type(recorder).__name__,
                    run_context.run_id,
                    exc_info=True,
                )
