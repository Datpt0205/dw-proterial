"""An order's cross-check passed on Bravo's matching read-back (Sales ticket
81, dw_sales ADR 0016, Proposed; off unless the tenant's order rules say
`cross_check_on_match`).

Each tick asks which workspaces have Sales cases and hands each to
`dw_sales.application.cross_check_on_match.CrossCheckOnMatchLane`, which
reads each order in Bravo whose rules stamped the switch once per case
version, through the gateway, and routes it. This module only paces it and
keeps one workspace's failure from costing the others their tick.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from dw_sales.application.cross_check_on_match import OnMatchTick
from dw_sales.application.ports import SalesScope
from dw_worker.consumers.scope_failures import raise_if_failed

logger = logging.getLogger("dw_worker.sales_cross_check_on_match")

# Every five minutes: an order entered in Bravo waits on its cross-check for
# hours, and each version is read once, so a tick costs one indexed read per
# workspace unless an order is new.
INTERVAL_SECONDS = 300.0


class OnMatchLane(Protocol):
    """One tick in one workspace (`CrossCheckOnMatchLane.tick`)."""

    async def tick(self, scope: SalesScope) -> OnMatchTick: ...


class ScopesPort(Protocol):
    """Every workspace with a Sales case (`SqlFollowupScopes.scopes`)."""

    async def scopes(self) -> Sequence[SalesScope]: ...


def build_sales_cross_check_on_match_consumer(
    lane: OnMatchLane, scopes: ScopesPort
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        failed = 0
        for scope in await scopes.scopes():
            try:
                done = await lane.tick(scope)
            except Exception:
                # Broad on purpose, like the loop's own: the next workspace
                # still gets its tick.
                logger.exception("sales_cross_check_on_match: the tick failed in one workspace")
                failed += 1
                continue
            if done.passed:
                logger.info("sales_cross_check_on_match: %d order(s) passed", done.passed)
        raise_if_failed("sales_cross_check_on_match", failed)

    return consume
