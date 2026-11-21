"""The `bravo_sync` lane (sales ticket 50): Bravo's facts copied into DW.

Every 10 minutes from 07:00 to 19:00 Vietnam time, what changed since each
table's cursor; once a night (19:00-07:00) the whole table, which is how a
row Bravo deleted is seen. Between those, a tick does nothing. The tick
itself is `dw_bravo.sync.BravoSync`, which decides when a full pass is due.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Final, Protocol

from dw_bravo.sync import VIETNAM

logger = logging.getLogger(__name__)

BRAVO_SYNC_INTERVAL_SECONDS: Final = 10 * 60


class SyncPort(Protocol):
    async def tick(self, now: datetime) -> Mapping[str, str]: ...


def due(now: datetime, last_night_run: datetime | None) -> bool:
    """Working hours, or one tick a night."""
    local = now.astimezone(VIETNAM)
    if 7 <= local.hour < 19:
        return True
    return last_night_run is None or (now - last_night_run).total_seconds() > 12 * 3600


def build_bravo_sync_consumer(
    sync: SyncPort, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> Callable[[], Awaitable[None]]:
    night: list[datetime] = []

    async def consume() -> None:
        now = clock()
        if not due(now, night[-1] if night else None):
            return
        local = now.astimezone(VIETNAM)
        if not 7 <= local.hour < 19:
            night[:] = [now]
        said = await sync.tick(now)
        logger.info("bravo_sync: %s", "; ".join(f"{t}: {s}" for t, s in said.items()))

    return consume
