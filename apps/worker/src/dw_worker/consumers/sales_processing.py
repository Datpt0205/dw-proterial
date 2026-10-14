"""DW1's processing queue (Sales ticket 25): "DW xử lý" run in the worker.

Each tick drains due jobs one at a time through
`dw_sales.application.processing.ProcessingDrain`, which decides everything:
whose access, the run, how the job settles. This module only paces it: at
most `BATCH` jobs a tick, so a full mailbox cannot keep the lane from the
loop's shutdown event for long, and the next tick takes the rest.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Final, Protocol

logger = logging.getLogger("dw_worker.sales_processing")

# A queue consumer: the loop's poll interval would leave a pressed button
# waiting; a few seconds is what the page's polling shows.
INTERVAL_SECONDS: Final = 3.0
# Jobs per tick. Each is a DW1 run reading every file of one message in the
# reader sandbox, one file at a time: seconds each.
BATCH: Final = 10


class ProcessingLane(Protocol):
    """One job (`ProcessingDrain.drain_one`): False when none was due."""

    async def drain_one(self) -> bool: ...


def build_sales_processing_consumer(lane: ProcessingLane) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        handled = 0
        while handled < BATCH and await lane.drain_one():
            handled += 1
        if handled:
            logger.info("sales_processing: %d job(s) run", handled)

    return consume
