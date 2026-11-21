"""The `bravo_watch` lane (sales ticket 65): one tick when its schedule says.

Every 30 minutes from 07:00 to 19:00 Vietnam time, and once at night (the
02:00 half hour); the registry's interval is the 30 minutes, and a tick
outside those hours does nothing. The tick itself is
`dw_bravo.watch_lane.BravoWatch`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Final, Protocol
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

BRAVO_WATCH_INTERVAL_SECONDS: Final = 30 * 60
_VIETNAM: Final = ZoneInfo("Asia/Ho_Chi_Minh")


class WatchPort(Protocol):
    async def tick(self, now: datetime) -> object: ...


def due(now: datetime) -> bool:
    local = now.astimezone(_VIETNAM)
    return 7 <= local.hour < 19 or (local.hour == 2 and local.minute < 30)


def build_bravo_watch_consumer(
    watch: WatchPort, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        now = clock()
        if not due(now):
            return
        await watch.tick(now)

    return consume
