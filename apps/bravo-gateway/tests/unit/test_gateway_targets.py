"""Every read and write goes to the tenant's Bravo target now, and a target
the gateway holds no logins for refuses, never falling back (ticket 85)."""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest
from gateway_fakes import (
    SET_QUANTITY,
    FakeBravo,
    gateway,
    targets,
    token,
)

from dw_bravo.contract import SalesOrderState
from dw_bravo_gateway.api import create_app
from dw_bravo_gateway.targets import TargetBravo, Targets

pytestmark = pytest.mark.unit


class _Orders:
    def __init__(self, so_no: str) -> None:
        self.so_no = so_no

    async def sales_order(self, so_no: str) -> SalesOrderState:
        return SalesOrderState(so_id=1, so_no=self.so_no, lines=())


def _two(current: str | None) -> tuple[Targets, FakeBravo, FakeBravo]:
    """UAT and production, each its own Bravo, the tenant's rule naming ``current``."""
    uat, production = gateway(), gateway()
    production.pipeline.target = "production"
    production.pipeline.switches = uat.switches
    uat.switches.target_ = current  # type: ignore[assignment]
    routed = Targets(
        uat.pipeline.tenant_id,
        uat.switches,
        {
            "uat": TargetBravo(uat.pipeline, orders=_Orders("SO-UAT")),  # type: ignore[arg-type]
            "production": TargetBravo(production.pipeline, orders=_Orders("SO-PROD")),  # type: ignore[arg-type]
        },
    )
    return routed, uat.bravo, production.bravo


def _client(routed: Targets) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(routed)), base_url="http://gw"
    )


_READ = {"query": {"kind": "so.by_number", "version": 1, "content": {"so_no": "X"}}}


@pytest.mark.parametrize(("current", "so_no"), [("uat", "SO-UAT"), ("production", "SO-PROD")])
async def test_a_read_goes_to_the_current_target_and_names_it(current: str, so_no: str) -> None:
    routed, _, _ = _two(current)
    async with _client(routed) as c:
        response = await c.post("/v1/reads", json=_READ)

    assert response.status_code == 200
    assert response.json()["so_no"] == so_no
    assert response.headers["Bravo-Target"] == current


async def test_a_write_lands_in_the_current_target_only() -> None:
    routed, uat, production = _two("production")

    result = await routed.execute(SET_QUANTITY, token(SET_QUANTITY))

    assert result.outcome == "written"
    assert len(production.batches) == 1 and uat.batches == []


async def test_a_target_without_logins_refuses_and_never_falls_back() -> None:
    routed, uat, _ = _two("production")
    uat_only = replace(routed, reach={"uat": routed.reach["uat"]})

    written = await uat_only.execute(SET_QUANTITY, token(SET_QUANTITY))
    previewed = await uat_only.preview(SET_QUANTITY, token(SET_QUANTITY))
    async with _client(uat_only) as c:
        read = await c.post("/v1/reads", json=_READ)

    assert (written.outcome, written.check, written.reason) == (
        "refused",
        "target",
        "target_unconfigured",
    )
    assert (previewed.check, previewed.reason) == ("target", "target_unconfigured")
    assert read.status_code == 503 and read.json()["detail"] == "target_unconfigured"
    assert uat.batches == []


async def test_a_rule_naming_no_target_the_gateway_reads_refuses_everything() -> None:
    routed, uat, production = _two(None)

    result = await routed.execute(SET_QUANTITY, token(SET_QUANTITY))
    async with _client(routed) as c:
        read = await c.post("/v1/reads", json=_READ)

    assert (result.check, result.reason) == ("target", "target_unreadable")
    assert read.status_code == 503
    assert uat.batches == [] and production.batches == []


async def test_a_switch_after_the_routing_refuses_at_the_pipeline() -> None:
    # Routed to UAT, then the tenant's rule names production before the
    # pipeline's own check: the pipeline refuses, whatever routed it.
    gw = gateway()
    gw.switches.target_ = "production"

    result = await gw.pipeline.execute(SET_QUANTITY, token(SET_QUANTITY))

    assert (result.outcome, result.check, result.reason) == (
        "refused",
        "target",
        "target_changed",
    )
    assert gw.bravo.batches == []


async def test_the_targets_route_says_which_is_current_and_which_are_configured() -> None:
    gw = gateway()
    async with _client(targets(gw)) as c:
        answer = (await c.get("/v1/targets")).json()

    assert answer == {"current": "uat", "configured": {"uat": True, "production": False}}
