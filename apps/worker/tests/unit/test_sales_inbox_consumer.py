"""DW1's mailbox lane in the worker loop (ticket 16): its pacing and its
isolation. What a tick does is `dw_sales`' (`test_inbox_lane.py`); the whole
lane against Postgres is `tests/integration/test_sales_inbox_lane_db.py`."""

from __future__ import annotations

import uuid

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.application.inbox_lane import LaneTick
from dw_sales.application.ports import SalesScope
from dw_worker.consumers.sales_inbox import build_sales_inbox_consumer

pytestmark = pytest.mark.unit

A = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
B = SalesScope(TenantId(uuid.UUID(int=3)), WorkspaceId(uuid.UUID(int=4)))


class _Lane:
    def __init__(self, failing: SalesScope | None = None) -> None:
        self.failing = failing
        self.ticked: list[SalesScope] = []

    async def tick(self, scope: SalesScope) -> LaneTick:
        self.ticked.append(scope)
        if scope == self.failing:
            raise RuntimeError("the database went away")
        return LaneTick(processed=("M01",))


async def test_every_workspace_gets_its_tick_even_when_one_fails() -> None:
    lane = _Lane(failing=A)

    await build_sales_inbox_consumer(lane, [A, B])()

    assert lane.ticked == [A, B]
