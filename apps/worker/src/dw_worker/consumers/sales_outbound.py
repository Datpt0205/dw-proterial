"""The worker's `sales_outbound` lane: "Gửi cho khách" written to each
person's outbox folder and their flows' receipts read back
(`dw_sales.application.outbound_mail.OutboundLane`). Locally, a stand-in for
the flows may answer every job (`FakeFlow`); never where deployed."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Final, Protocol

from dw_sales.adapters.outbox_folder import FakeFlow
from dw_sales.application.outbound_mail import OutboundTick

logger = logging.getLogger("dw_worker.sales_outbound")

INTERVAL_SECONDS: Final = 30


class OutboundTicker(Protocol):
    async def tick(self) -> OutboundTick: ...


def build_sales_outbound_consumer(
    lane: OutboundTicker, fake_flow: FakeFlow | None = None
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        tick = await lane.tick()
        if fake_flow is not None and fake_flow.run():
            # The stand-in answered: read its receipts at once, not a tick later.
            tick = await lane.tick()
        if tick.written or tick.settled:
            logger.info(
                "sales_outbound: wrote %d job(s), settled %d mail(s)", tick.written, tick.settled
            )

    return consume
