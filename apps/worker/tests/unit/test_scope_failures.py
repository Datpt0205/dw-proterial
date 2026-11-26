"""A lane that catches one scope's failure still says so after the last scope
(Sales ticket 84).

Each of these lanes keeps serving the other workspaces when one fails, and
each has to end its tick by raising, or `run_worker` records a clean tick and
`DwLaneStale` never fires for a lane that fails in one workspace every time.
The lanes with a test of their own for this (followups, inbox, skill replay,
rule drafts, reaper, pairs retention, channel delivery) are not repeated here.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any

import pytest

from dw_worker.consumers.purchasing_automation import build_purchasing_automation_consumer
from dw_worker.consumers.retention import build_retention_consumer
from dw_worker.consumers.sales_auto_apply import build_sales_auto_apply_consumer
from dw_worker.consumers.sales_learning import (
    build_sales_examples_consumer,
    build_sales_prompt_optimiser_consumer,
)
from dw_worker.consumers.scope_failures import ScopesFailedError

pytestmark = pytest.mark.unit

FIRST, SECOND = object(), object()


class _Scopes:
    async def scopes(self) -> list[object]:
        return [FIRST, SECOND]


class _Lane:
    """Fails in FIRST; answers ``result`` in every other scope."""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.ticked: list[object] = []

    async def tick(self, *scope: object) -> Any:
        self.ticked.append(scope[0])
        if scope[0] is FIRST:
            raise RuntimeError("database away")
        return self.result


class _Due(_Lane):
    async def due(self) -> list[tuple[object, uuid.UUID]]:
        return [(FIRST, uuid.uuid4()), (SECOND, uuid.uuid4())]


async def _no_prune(_: object) -> None: ...


def _builders() -> list[tuple[str, _Lane, Callable[[], Awaitable[None]]]]:
    auto = _Lane([])
    purchasing = _Due(SimpleNamespace(done=[]))
    examples = _Lane(0)
    optimiser = _Lane(SimpleNamespace(reason="nothing new", proposed=0))
    return [
        ("auto_apply", auto, build_sales_auto_apply_consumer(auto, _Scopes())),  # type: ignore[arg-type]
        ("purchasing", purchasing, build_purchasing_automation_consumer(purchasing)),  # type: ignore[arg-type]
        (
            "examples",
            examples,
            build_sales_examples_consumer(examples, _Scopes(), _no_prune, lambda: None),  # type: ignore[arg-type]
        ),
        ("optimiser", optimiser, build_sales_prompt_optimiser_consumer(optimiser, _Scopes())),  # type: ignore[arg-type]
    ]


@pytest.mark.parametrize("case", range(len(_builders())), ids=[b[0] for b in _builders()])
async def test_a_lane_serves_every_scope_then_raises_for_the_one_that_failed(case: int) -> None:
    _, lane, consume = _builders()[case]
    with pytest.raises(ScopesFailedError, match="1 scope"):
        await consume()
    assert lane.ticked == [FIRST, SECOND]


async def test_a_retention_pass_that_fails_is_not_swallowed() -> None:
    """The `partitions` lane is built this way; its failure sends rows into the
    DEFAULT partition, so it must not read as a clean tick."""

    class _Prune:
        async def prune(self) -> None:
            raise RuntimeError("lock timeout")

    with pytest.raises(RuntimeError, match="lock timeout"):
        await build_retention_consumer(_Prune())()
