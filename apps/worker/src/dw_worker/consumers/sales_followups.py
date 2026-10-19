"""DW1's follow-ups and morning brief (Sales ticket 42).

Each tick asks which workspaces have Sales cases and hands each to
`dw_sales.application.followups.FollowupLane`, which decides everything: the
tenant's resolved timings, the pause, what is owed, quiet hours, who is told,
and the record that keeps each reminder to once. This module only paces it
and keeps one workspace's failure from costing the others their tick.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from dw_sales.application.followups import FollowupTick
from dw_sales.application.ports import SalesScope

logger = logging.getLogger("dw_worker.sales_followups")

# About five minutes: a reminder is owed by the hour, so a tick a few minutes
# late is on time, and a brief due at 07:30 goes out by 07:35.
INTERVAL_SECONDS = 300.0


class FollowupsLane(Protocol):
    """One tick in one workspace (`FollowupLane.tick`)."""

    async def tick(self, scope: SalesScope) -> FollowupTick: ...


class ScopesPort(Protocol):
    """Every workspace with a Sales case (`SqlFollowupScopes.scopes`)."""

    async def scopes(self) -> Sequence[SalesScope]: ...


def build_sales_followups_consumer(
    lane: FollowupsLane, scopes: ScopesPort
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        for scope in await scopes.scopes():
            try:
                tick = await lane.tick(scope)
            except Exception:
                # Broad on purpose, like the loop's own: the next workspace
                # still gets its tick.
                logger.exception("sales_followups: the tick failed in one workspace")
                continue
            if tick.sent:
                logger.info("sales_followups: %d notification(s) sent", len(tick.sent))
            if tick.deferred:
                logger.info("sales_followups: %d deferred to working hours", tick.deferred)

    return consume
