"""DW1's drop folder (Sales ticket 43): each `.eml` file stored in its mailbox.

Each tick hands the one workspace this host stores mail for to
`dw_sales.application.mail_drop.MailDrop`, which decides everything: which
files are new, which may still be arriving, what is stored and what is
refused. This module only paces it. The `sales_inbox` lane then finds the
stored messages like any other and queues them.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from dw_sales.application.mail_drop import DropTick
from dw_sales.application.ports import SalesScope

logger = logging.getLogger("dw_worker.sales_mail_drop")

# A mail reaches the folder seconds to minutes after it arrives (OneDrive's
# sync); a minute here is noise beside that, and matches the inbox lane's.
INTERVAL_SECONDS = 60.0


class DropLane(Protocol):
    async def tick(self, scope: SalesScope) -> DropTick: ...


def build_sales_mail_drop_consumer(
    drop: DropLane, scope: SalesScope
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        tick = await drop.tick(scope)
        if tick.stored:
            logger.info("sales_mail_drop: stored %d mail(s)", len(tick.stored))
        if tick.already_stored:
            logger.info(
                "sales_mail_drop: %d file(s) held mail already stored", len(tick.already_stored)
            )
        if tick.refused:
            logger.warning("sales_mail_drop: refused %d file(s)", len(tick.refused))

    return consume
