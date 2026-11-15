"""The replay lane of proposed DW1 skill versions (Sales ticket 40): every
workspace ticked, one's failure costing the others nothing; registered only
where DW1's agent with skills is, which needs a model server."""

from __future__ import annotations

import uuid

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.application.ports import SalesScope
from dw_worker.consumers.sales_skill_replay import build_sales_skill_replay_consumer

pytestmark = pytest.mark.unit


def _scope() -> SalesScope:
    return SalesScope(TenantId(uuid.uuid4()), WorkspaceId(uuid.uuid4()))


async def test_one_workspace_failing_costs_the_others_nothing() -> None:
    first, second = _scope(), _scope()
    ticked: list[SalesScope] = []

    class _Scopes:
        async def scopes(self) -> list[SalesScope]:
            return [first, second]

    class _Lane:
        async def tick(self, scope: SalesScope) -> int:
            ticked.append(scope)
            if scope == first:
                raise RuntimeError("model down")
            return 1

    await build_sales_skill_replay_consumer(_Lane(), _Scopes())()
    assert ticked == [first, second]


def test_the_lane_is_not_registered_without_a_model() -> None:
    from test_worker import bare_settings

    from dw_worker.main import build_registry

    settings = bare_settings(
        database_url="postgresql+asyncpg://dw:dw@localhost/dw",
        s3_endpoint_url="http://localhost:9000",
        sales_inbox_lane=False,
    )
    registry = build_registry(settings)
    # DW1 is wired (its examples lane runs) but no model server is.
    assert "sales_examples" in registry.all()
    assert "sales_skill_replay" not in registry.all()
