"""DW1's thresholds for what applies itself (Sales ticket 44, dw_sales ADR 0015).

Each tick asks which workspaces have Sales cases and hands each to
`dw_sales.application.autonomy.ThresholdLane`, which sets every step's
threshold again from the workspace's labelled cases, decides whether its
audits stop it, and stores both with the lane's audit rows. This module only
paces it and keeps one workspace's failure from costing the others their tick.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from dw_sales.application.ports import SalesScope
from dw_sales.domain.autonomy import StepThreshold
from dw_worker.consumers.scope_failures import raise_if_failed

logger = logging.getLogger("dw_worker.sales_auto_apply")

# Hourly. ADR 0015 asks for at least nightly; an hour costs one indexed read
# per workspace, and an audit that stops a step takes effect within it.
INTERVAL_SECONDS = 3600.0


class ThresholdsLane(Protocol):
    """One tick in one workspace (`ThresholdLane.tick`)."""

    async def tick(self, scope: SalesScope) -> Sequence[StepThreshold]: ...


class ScopesPort(Protocol):
    """Every workspace with a Sales case (`SqlFollowupScopes.scopes`)."""

    async def scopes(self) -> Sequence[SalesScope]: ...


def build_sales_auto_apply_consumer(
    lane: ThresholdsLane, scopes: ScopesPort
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        failed = 0
        for scope in await scopes.scopes():
            try:
                stored = await lane.tick(scope)
            except Exception:
                # Broad on purpose, like the loop's own: the next workspace
                # still gets its tick.
                logger.exception("sales_auto_apply: the tick failed in one workspace")
                failed += 1
                continue
            stopped = sum(1 for t in stored if t.stopped)
            if stopped:
                logger.warning("sales_auto_apply: %d step(s) stopped by their audits", stopped)
        raise_if_failed("sales_auto_apply", failed)

    return consume
