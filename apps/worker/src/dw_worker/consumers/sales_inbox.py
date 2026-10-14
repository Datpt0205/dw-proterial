"""DW1's mailbox lane (Sales ticket 16): new mail processed without a click.

Each tick hands every workspace whose mailbox this host reads to
`dw_sales.application.inbox_lane.InboxLane`, which decides everything: DW1's
own access context, the pause switch, which messages to queue (ticket 25:
the `sales_processing` lane runs them). This module only paces it and keeps
one workspace's failure from costing the others their tick.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from dw_sales.application.inbox_lane import LaneTick
from dw_sales.application.ports import SalesScope

logger = logging.getLogger("dw_worker.sales_inbox")

# The mock mailbox's cadence (decided 2026-10-12); a real mailbox adapter
# picks its own when it arrives.
INTERVAL_SECONDS = 60.0


class MailboxLane(Protocol):
    """One tick in one workspace (`InboxLane.tick`)."""

    async def tick(self, scope: SalesScope) -> LaneTick: ...


def build_sales_inbox_consumer(
    lane: MailboxLane, scopes: Sequence[SalesScope]
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        for scope in scopes:
            try:
                tick = await lane.tick(scope)
            except Exception:
                # Broad on purpose, like the loop's own: the next workspace
                # still gets its tick.
                logger.exception("sales_inbox: the tick failed in one workspace")
                continue
            if tick.queued:
                logger.info("sales_inbox: DW1 queued %d message(s)", len(tick.queued))
            if tick.stopped is not None:
                logger.info("sales_inbox: stopped early in a workspace: %s", tick.stopped)

    return consume
