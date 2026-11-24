"""A customer's worked pairs dropped past the tenant's term (Sales ticket 41),
per workspace with Sales cases.

Each tick asks one workspace's lane
(`dw_sales.application.salesorder_pairs.WorkedPairRetention`) to drop the
pairs older than its tenant's `learning.salesorder_pairs_kept_days`: the term
is the tenant's rule, so it is read in each scope, and the DELETE is that
scope's under RLS. Hourly, as every retention lane: a pair that outlives its
term by an hour harms nobody.

This module only paces it and keeps one workspace's failure from costing the
others their tick.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from dw_sales.application.ports import SalesScope

logger = logging.getLogger("dw_worker.sales_pairs_retention")


class ScopesPort(Protocol):
    """Every workspace with a Sales case (`SqlFollowupScopes.scopes`)."""

    async def scopes(self) -> Sequence[SalesScope]: ...


class PairsRetentionLane(Protocol):
    async def tick(self, scope: SalesScope) -> int: ...


def build_sales_pairs_retention_consumer(
    lane: PairsRetentionLane,
    scopes: ScopesPort,
    name: str = "sales_salesorder_pairs_retention",
) -> Callable[[], Awaitable[None]]:
    """Paces any per-workspace retention lane; ``name`` is the lane's, for
    the log (the shadow readings' too, ticket 67)."""

    async def consume() -> None:
        for scope in await scopes.scopes():
            try:
                dropped = await lane.tick(scope)
            except Exception:
                # Broad on purpose: a row kept an hour longer is retried next
                # tick, and the other workspaces still get theirs.
                logger.exception("%s: one workspace failed", name)
                continue
            if dropped:
                logger.info("%s: dropped %d row(s)", name, dropped)

    return consume
