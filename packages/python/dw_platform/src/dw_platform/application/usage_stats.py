"""F6 — per-usecase usage and cost, read from the model-usage ledger.

The ledger (``platform.model_usage_ledger``) is the source of truth: every
model call lands there with a ``worker_id`` (the usecase key), a ``run_id``
(one invocation), tokens and a priced-or-NULL cost. This service only GROUPs
what is already written — nothing here meters anything; the meters live at
the gateway and the LangChain seam. Numbers exist from the day metering was
deployed; history before that is not reconstructible and the screen says so.

Same two rails as the admin console: a ``platform.*`` scope an Org Admin
holds, and every read runs under the caller's tenant RLS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol

from dw_kernel.ports import UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.ports import AuthorizationPort

USAGE_READ = "platform.usage.read"
_RES_USAGE = "usage"

# The ranges the screen offers. A free integer would invite an unindexed
# year-long scan on a partitioned table; three sizes answer the question.
ALLOWED_DAY_RANGES = (7, 30, 90)
DEFAULT_DAYS = 30


@dataclass(frozen=True, slots=True)
class UsecaseUsage:
    """One usecase's totals inside the window."""

    worker_id: str
    # Distinct run ids — one click / one turn / one queued job each.
    runs: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    # Sum over the priced calls; None when NO call in the window was priced.
    cost_usd: float | None
    unpriced_calls: int
    last_used_at: datetime | None


@dataclass(frozen=True, slots=True)
class DailyUsage:
    """One usecase's runs and cost on one day — the frequency series."""

    day: date
    worker_id: str
    runs: int
    cost_usd: float


@dataclass(frozen=True, slots=True)
class ToolUsage:
    tool_name: str
    calls: int
    failed: int


@dataclass(frozen=True, slots=True)
class UsageOverview:
    days: int
    since: datetime
    usecases: list[UsecaseUsage] = field(default_factory=list)
    daily: list[DailyUsage] = field(default_factory=list)
    tools: list[ToolUsage] = field(default_factory=list)


class UsageStatsRepositoryPort(Protocol):
    """The three GROUP BYs, behind a port so the service tests without SQL."""

    async def usecases(self, context: AccessContext, since: datetime) -> list[UsecaseUsage]: ...

    async def daily(self, context: AccessContext, since: datetime) -> list[DailyUsage]: ...

    async def tools(self, context: AccessContext, since: datetime) -> list[ToolUsage]: ...


@dataclass(frozen=True)
class UsageStatsService:
    repo: UsageStatsRepositoryPort
    authz: AuthorizationPort
    clock: UtcClock

    async def overview(self, context: AccessContext, days: int) -> UsageOverview:
        await self.authz.require(context=context, action=USAGE_READ, resource_type=_RES_USAGE)
        window = days if days in ALLOWED_DAY_RANGES else DEFAULT_DAYS
        since = self.clock.now() - timedelta(days=window)
        return UsageOverview(
            days=window,
            since=since,
            usecases=await self.repo.usecases(context, since),
            daily=await self.repo.daily(context, since),
            tools=await self.repo.tools(context, since),
        )


# Referenced by nothing at runtime, exported for tests and the seed script:
# every id the meters stamp today, so a rename is caught by a failing test
# rather than by a row quietly starting a second bucket.
KNOWN_USECASES: frozenset[str] = frozenset(
    {
        "sales_chat",
        "lead_scoring",
        "sales_research",
        "sales_signals",
        "sales_orchestrator",
        "signal_analyst",
        "person_research",
        "account_enrich",
        "tender_portal",
        "tender_bidders",
        "tender_prefs",
        "sales_crm.account_enrich",
        "sales_crm.stakeholder_extract",
        "sales_crm.stakeholder_arrange",
        "sales_crm.stakeholder_digest",
    }
)
