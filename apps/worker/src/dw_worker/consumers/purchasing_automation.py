"""DW2's automation lane: each step taken on its own as far as the tenant's
switches let it. Each tick hands every workspace with work to
`dw_purchasing.application.automation_lane.AutomationLane`, which decides
everything; this module only paces it and keeps one workspace's failure
from costing the others their tick."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Final, Protocol

from dw_purchasing.application.automation_lane import Tick

logger = logging.getLogger("dw_worker.purchasing_automation")

INTERVAL_SECONDS: Final = 60.0


class AutomationLanePort(Protocol):
    async def due(self) -> Sequence[tuple[uuid.UUID, uuid.UUID]]: ...

    async def tick(self, tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> Tick: ...


def build_purchasing_automation_consumer(
    lane: AutomationLanePort,
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        for tenant_id, workspace_id in await lane.due():
            try:
                tick = await lane.tick(tenant_id, workspace_id)
            except Exception:
                # Broad on purpose, like the loop's own: the next workspace
                # still gets its tick.
                logger.exception("purchasing_automation: the tick failed in one workspace")
                continue
            if tick.done:
                logger.info("purchasing_automation: %s", "; ".join(tick.done))

    return consume
