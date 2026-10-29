"""The outbox's stopped events, told to a person (2026-10-29).

Each tick hands over to `dw_platform.application.background_failures.
OutboxAlarms`, which finds every event that spent its attempts and tells the
tenant's administrators, once per event. This module only paces it.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

logger = logging.getLogger("dw_worker.outbox_alarms")

# Five minutes: an event spends its attempts over about seven, so a stopped
# one is told within minutes of stopping, and a quiet sweep costs one query.
INTERVAL_SECONDS = 300.0


class AlarmsPort(Protocol):
    async def sweep(self) -> int: ...


def build_outbox_alarms_consumer(alarms: AlarmsPort) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        found = await alarms.sweep()
        if found:
            logger.warning("outbox_alarms: %d stopped event(s) waiting for a person", found)

    return consume
