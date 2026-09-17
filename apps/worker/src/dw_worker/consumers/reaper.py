"""One owner for abandoned job rows, across every queue this context has.

A killed worker leaves its row at `running`. Every one of these tables carries a
partial unique index that refuses a second active job for the same account, so
the stranded row does not merely look untidy - it blocks the account. A person
pressing the button again is told a scan is already running, and no scan is.
That is why this is a precondition of the duplicate check rather than a
background tidy-up.

Gathered here rather than left in three claim loops for two reasons. Two of the
five queues had no periodic caller at all - a research run and a signal scan
were reaped by nobody - and the three that did only reaped on the tick that also
claimed, so a queue with nothing to claim still reaped while a queue that was
busy reaped on every job. One consumer on its own cadence gives every table the
same treatment and puts all five windows in one place to read.

Each window is the job's own: five minutes for a pass that makes ten model
calls, twenty for a compile that drives a browser, and long enough for a
research run that its slowest healthy round is never mistaken for a dead worker.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from dw_kernel.ports import UtcClock

logger = logging.getLogger("dw_worker.reaper")


class StaleReaperPort(Protocol):
    """The one method every job queue already offers.

    Structural rather than a shared base class: job queues are unrelated
    repositories over unrelated tables, and the only thing this consumer needs
    from them is the ability to settle what a dead worker left behind.
    """

    async def reap_stale(self, *, older_than: datetime) -> Sequence[Any]: ...


@dataclass(frozen=True)
class ReapTarget:
    """One queue, and how long its slowest healthy job may go quiet."""

    name: str
    queue: StaleReaperPort
    stale_after: timedelta


# How often the sweep runs. Far apart on purpose: reaping is a repair, and a
# repair that runs every few seconds spends a connection saying nothing is
# broken. Two minutes still returns a blocked account well inside the time a
# person takes to press the button again.
INTERVAL_SECONDS = 120.0


def build_reaper_consumer(
    targets: Sequence[ReapTarget], clock: UtcClock
) -> Callable[[], Awaitable[None]]:
    """Return a consumer that settles abandoned rows in every queue it was given.

    One queue failing does not stop the others: they are separate tables with
    separate blocked accounts behind them, and a sweep that gave up on the first
    error would leave the rest blocked for the sake of tidy control flow.
    """

    async def consume() -> None:
        now = clock.now()
        for target in targets:
            try:
                reaped = await target.queue.reap_stale(older_than=now - target.stale_after)
            except Exception:
                logger.exception("reaping %s failed", target.name)
                continue
            if reaped:
                logger.warning("reaped %d abandoned %s row(s)", len(reaped), target.name)

    return consume
