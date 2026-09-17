"""The usage-stats service: scope gate first, window clamped to known sizes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from dw_kernel.errors import PermissionDeniedError
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.usage_stats import (
    USAGE_READ,
    DailyUsage,
    ToolUsage,
    UsageStatsService,
    UsecaseUsage,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _Repo:
    def __init__(self) -> None:
        self.asked_since: datetime | None = None

    async def usecases(self, context: AccessContext, since: datetime) -> list[UsecaseUsage]:
        self.asked_since = since
        return [
            UsecaseUsage(
                worker_id="sales_chat",
                runs=3,
                model_calls=9,
                input_tokens=1000,
                output_tokens=200,
                cost_usd=0.01,
                unpriced_calls=0,
                last_used_at=_NOW,
            )
        ]

    async def daily(self, context: AccessContext, since: datetime) -> list[DailyUsage]:
        return []

    async def tools(self, context: AccessContext, since: datetime) -> list[ToolUsage]:
        return []


def _context(scopes: frozenset[str]) -> AccessContext:
    return AccessContext(
        tenant_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        roles=frozenset({"org_admin"}),
        scopes=scopes,
        plan_id="pro",
    )


async def test_the_scope_is_the_door() -> None:
    service = UsageStatsService(repo=_Repo(), authz=ScopeAuthorizationService(), clock=_Clock())
    with pytest.raises(PermissionDeniedError):
        await service.overview(_context(frozenset({"platform.members.read"})), 30)

    view = await service.overview(_context(frozenset({USAGE_READ})), 30)
    assert view.usecases[0].worker_id == "sales_chat"


async def test_an_unknown_window_falls_back_to_thirty_days() -> None:
    repo = _Repo()
    service = UsageStatsService(repo=repo, authz=ScopeAuthorizationService(), clock=_Clock())
    view = await service.overview(_context(frozenset({USAGE_READ})), 13)
    assert view.days == 30
    assert repo.asked_since is not None
    assert (_NOW - repo.asked_since).days == 30
