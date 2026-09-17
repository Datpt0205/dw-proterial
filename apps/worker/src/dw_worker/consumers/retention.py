"""Retention: one pass over the tables, on a slow cadence.

The rules and the batching live in the adapter; what this file decides is only
how often, and the answer is hourly. Retention is a size control, not a
correctness one - a row that outlives its window by an hour harms nobody, and a
delete loop running every few seconds spends a connection to discover that.

A failed pass is logged and retried next hour rather than escalated. There is no
partial state to repair: each table's batch is its own statement, and whatever
was deleted stays deleted.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

logger = logging.getLogger("dw_worker.retention")


class RetentionPrunePort(Protocol):
    """One pass of whatever this deployment considers expired.

    Declared here, by the consumer that needs it, rather than imported from the
    package that happens to implement it: the loop owns the cadence, and every
    rule about *what* expires belongs to the adapter behind this port. A context
    that ships its own retention rules satisfies this and is wired in at the
    composition root.
    """

    async def prune(self) -> None: ...


# One hour. Slow enough that the job is invisible, frequent enough that a day's
# expiries never accumulate into a backlog the batch ceiling cannot drain.
INTERVAL_SECONDS = 3600.0


def build_retention_consumer(prune: RetentionPrunePort) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        try:
            await prune.prune()
        except Exception:
            # Broad and logged: this is housekeeping, and housekeeping that can
            # take the worker down is worse than housekeeping that skips an hour.
            logger.exception("retention pass failed; the next tick will try again")

    return consume
