"""An order's cross-check passed on Bravo's matching read-back (Sales ticket
81): every workspace ticked, one's failure costing the others nothing; the
lane registered only where the worker reaches a Bravo gateway."""

from __future__ import annotations

import uuid

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.application.cross_check_on_match import OnMatchTick
from dw_sales.application.ports import SalesScope
from dw_worker.consumers.sales_cross_check_on_match import (
    build_sales_cross_check_on_match_consumer,
)
from dw_worker.consumers.scope_failures import ScopesFailedError

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
        async def tick(self, scope: SalesScope) -> OnMatchTick:
            ticked.append(scope)
            if scope == first:
                raise RuntimeError("gateway away")
            return OnMatchTick({"applied": 1}, passed=1)

    with pytest.raises(ScopesFailedError):
        await build_sales_cross_check_on_match_consumer(_Lane(), _Scopes())()
    assert ticked == [first, second]


def test_the_lane_runs_only_where_the_worker_reaches_a_gateway() -> None:
    from test_worker import bare_settings

    from dw_worker.main import build_registry

    db = "postgresql+asyncpg://dw:dw@localhost/dw"
    assert "sales_cross_check_on_match" not in build_registry(bare_settings(database_url=db)).all()
    registry = build_registry(
        bare_settings(
            database_url=db,
            s3_endpoint_url="http://localhost:9000",
            bravo_gateway_url="http://bravo-gateway:8080",
            bravo_tenant_id=uuid.uuid4(),
        )
    )
    assert "sales_cross_check_on_match" in registry.all()
    assert registry.interval_for("sales_cross_check_on_match", 5.0) == 300.0
