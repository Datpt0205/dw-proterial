"""The `sales_pc_replies` consumer raises when a workspace's read raised, after
the lane read the others, so `run_worker` records no clean tick and
`DwLaneStale` can fire (Sales ticket 84)."""

from __future__ import annotations

import pytest

from dw_sales.application.pc_replies import PcReplyTick
from dw_worker.consumers.sales_pc_replies import build_sales_pc_replies_consumer
from dw_worker.consumers.scope_failures import ScopesFailedError

pytestmark = pytest.mark.unit


class _Lane:
    def __init__(self, tick: PcReplyTick) -> None:
        self._tick = tick

    async def tick(self) -> PcReplyTick:
        return self._tick


async def test_a_workspace_that_failed_makes_the_tick_raise() -> None:
    consume = build_sales_pc_replies_consumer(_Lane(PcReplyTick(read=1, proposed=1, failed=1)))
    with pytest.raises(ScopesFailedError, match="sales_pc_replies"):
        await consume()


async def test_a_tick_with_no_failure_is_clean() -> None:
    await build_sales_pc_replies_consumer(_Lane(PcReplyTick(read=2, proposed=1)))()
