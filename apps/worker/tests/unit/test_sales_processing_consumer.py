"""DW1's processing queue in the worker loop (Sales ticket 25): its pacing.
What a job does is `dw_sales`' (`test_processing_queue.py`)."""

from __future__ import annotations

import pytest

from dw_worker.consumers.sales_processing import BATCH, build_sales_processing_consumer

pytestmark = pytest.mark.unit


class _Lane:
    def __init__(self, due: int) -> None:
        self.due = due
        self.asked = 0

    async def drain_one(self) -> bool:
        self.asked += 1
        if self.due == 0:
            return False
        self.due -= 1
        return True


async def test_a_tick_runs_what_is_due_and_stops_when_nothing_is() -> None:
    lane = _Lane(due=3)

    await build_sales_processing_consumer(lane)()

    assert (lane.due, lane.asked) == (0, 4)


async def test_a_tick_runs_at_most_a_batch_and_leaves_the_rest_to_the_next() -> None:
    lane = _Lane(due=BATCH + 5)

    await build_sales_processing_consumer(lane)()

    assert (lane.due, lane.asked) == (5, BATCH)
