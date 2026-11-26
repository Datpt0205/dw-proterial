"""The worker's `sales_pc_replies` lane: PC's mail read while an order waits on
PC, and its dates proposed to the PIC (Sales ticket 77,
`dw_sales.application.pc_replies.PcReplyLane`). It reads nothing where the
tenant's `model_assist.pc_reply` is off, which it is unless a version says."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Final, Protocol

from dw_sales.application.pc_replies import PcReplyTick

logger = logging.getLogger("dw_worker.sales_pc_replies")

# PC answers within hours; a few minutes late costs nothing.
INTERVAL_SECONDS: Final = 300


class PcReplyTicker(Protocol):
    async def tick(self) -> PcReplyTick: ...


def build_sales_pc_replies_consumer(lane: PcReplyTicker) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        tick = await lane.tick()
        if tick.read:
            logger.info(
                "sales_pc_replies: read %d mail(s) of PC's, %d proposed dates",
                tick.read,
                tick.proposed,
            )

    return consume
