"""DW2's RFQs sent from the buyers' own mailboxes, through the outbox share.

Each tick hands the one workspace this host serves DW2 for to
`dw_purchasing.application.rfq_mail.RfqMailLane`, which decides everything:
which jobs to write, which receipts are DW2's, which mails stalled. This
module only paces it. Counts only: no address or word of a mail is logged.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from dw_platform.application.rule_versions import ContextScope
from dw_purchasing.application.rfq_mail import OutboundTick

logger = logging.getLogger("dw_worker.purchasing_outbound")

# As DW1's: a person waits for their flow, which runs on OneDrive's pace.
INTERVAL_SECONDS = 30.0


class OutboundLane(Protocol):
    async def tick(self, scope: ContextScope) -> OutboundTick: ...


def build_purchasing_outbound_consumer(
    lane: OutboundLane, scope: ContextScope
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        tick = await lane.tick(scope)
        if tick.written or tick.settled:
            logger.info(
                "purchasing_outbound: wrote %d, settled %d mail(s)", tick.written, tick.settled
            )

    return consume
