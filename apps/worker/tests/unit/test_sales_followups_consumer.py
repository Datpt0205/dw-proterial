"""DW1's follow-ups in the worker loop (Sales ticket 42): every workspace
the database lists gets its tick, and one failing costs the others nothing.
What a tick does is `dw_sales`' (`test_followups_lane.py`); the record and
the scopes against Postgres are `test_sales_followups_db.py`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.application.followups import FollowupTick
from dw_sales.application.ports import SalesScope
from dw_worker.consumers.sales_followups import build_sales_followups_consumer

pytestmark = pytest.mark.unit

A = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
B = SalesScope(TenantId(uuid.UUID(int=3)), WorkspaceId(uuid.UUID(int=4)))


class _Lane:
    def __init__(self, failing: SalesScope | None = None) -> None:
        self.failing = failing
        self.ticked: list[SalesScope] = []

    async def tick(self, scope: SalesScope) -> FollowupTick:
        self.ticked.append(scope)
        if scope == self.failing:
            raise RuntimeError("the database went away")
        return FollowupTick(sent=("k",), deferred=1)


class _Scopes:
    def __init__(self, scopes: Sequence[SalesScope]) -> None:
        self.held = list(scopes)

    async def scopes(self) -> Sequence[SalesScope]:
        return self.held


async def test_every_workspace_with_cases_gets_its_tick_even_when_one_fails() -> None:
    lane = _Lane(failing=A)

    await build_sales_followups_consumer(lane, _Scopes([A, B]))()

    assert lane.ticked == [A, B]


async def test_the_workspaces_are_asked_again_on_every_tick() -> None:
    """A tenant whose first case arrives after start-up is visited next tick."""
    lane, scopes = _Lane(), _Scopes([A])
    consume = build_sales_followups_consumer(lane, scopes)
    await consume()
    scopes.held.append(B)
    await consume()
    assert lane.ticked == [A, A, B]
