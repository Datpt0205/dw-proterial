"""DW2's drop folder: each `.eml` file stored in its own mailbox (ADR 0014).

Each tick hands the one workspace this host stores DW2's mail for to
`dw_purchasing.application.mail_drop.MailDrop`, which decides everything:
which files are new, which may still be arriving, which are past the
mailbox's term, what is stored and what is refused. This module only paces
it. DW2's automation lane then finds the stored messages like any other.
Counts only: no file name or word of a mail is logged here.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from dw_platform.application.rule_versions import ContextScope
from dw_purchasing.application.mail_drop import DropTick

logger = logging.getLogger("dw_worker.purchasing_mail_drop")

# As DW1's: a mail reaches the folder seconds to minutes after it arrives.
INTERVAL_SECONDS = 60.0


class DropLane(Protocol):
    async def tick(self, scope: ContextScope) -> DropTick: ...


def build_purchasing_mail_drop_consumer(
    drop: DropLane, scope: ContextScope
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        tick = await drop.tick(scope)
        if tick.stored:
            logger.info("purchasing_mail_drop: stored %d mail(s)", len(tick.stored))
        if tick.already_stored:
            logger.info(
                "purchasing_mail_drop: %d file(s) held mail already stored",
                len(tick.already_stored),
            )
        if tick.refused:
            logger.warning("purchasing_mail_drop: refused %d file(s)", len(tick.refused))

    return consume
