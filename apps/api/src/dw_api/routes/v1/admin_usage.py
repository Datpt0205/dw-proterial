"""F6 — per-usecase AI usage and cost for the Org Admin.

One read endpoint over the model-usage ledger, grouped by usecase, by day
and by tool. The service enforces ``platform.usage.read`` and every query
runs under the caller's tenant RLS — an Org Admin sees their tenant's bill
and nobody else's.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from dw_api.dependencies.auth import RequireAccessContext
from dw_api.dependencies.services import RequireContainer
from dw_kernel.errors import InfrastructureError
from dw_platform.application.usage_stats import DEFAULT_DAYS, UsageStatsService

router = APIRouter(prefix="/admin/usage", tags=["admin"])


class UsecaseUsageView(BaseModel):
    worker_id: str
    runs: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    # None = every call in the window ran on an unpriced route.
    cost_usd: float | None
    unpriced_calls: int
    last_used_at: datetime | None


class DailyUsageView(BaseModel):
    day: date
    worker_id: str
    runs: int
    cost_usd: float


class ToolUsageView(BaseModel):
    tool_name: str
    calls: int
    failed: int


class UsageOverviewView(BaseModel):
    days: int
    since: datetime
    usecases: list[UsecaseUsageView]
    daily: list[DailyUsageView]
    tools: list[ToolUsageView]


def _service(container: RequireContainer) -> UsageStatsService:
    if container.usage_stats is None:
        raise InfrastructureError("database is not configured")
    return container.usage_stats


@router.get("", response_model=UsageOverviewView)
async def usage_overview(
    context: RequireAccessContext,
    container: RequireContainer,
    days: int = Query(default=DEFAULT_DAYS, ge=1, le=365),
) -> UsageOverviewView:
    overview = await _service(container).overview(context, days)
    return UsageOverviewView(
        days=overview.days,
        since=overview.since,
        usecases=[
            UsecaseUsageView(
                worker_id=u.worker_id,
                runs=u.runs,
                model_calls=u.model_calls,
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cost_usd=u.cost_usd,
                unpriced_calls=u.unpriced_calls,
                last_used_at=u.last_used_at,
            )
            for u in overview.usecases
        ],
        daily=[
            DailyUsageView(day=d.day, worker_id=d.worker_id, runs=d.runs, cost_usd=d.cost_usd)
            for d in overview.daily
        ],
        tools=[
            ToolUsageView(tool_name=t.tool_name, calls=t.calls, failed=t.failed)
            for t in overview.tools
        ],
    )
