"""Who reaches which Sales route, signed in as each persona (ticket 11).

The negative half of the actor table: the purchasing manager and tenant IT
hold no `sales.*` scope and get 403 on every route; leadership reaches the
overview and nothing else; another tenant's PIC sees an empty mailbox and no
customers, and another tenant's case is not found, never forbidden.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.routing import APIRoute
from sales_api_harness import AN, BAO, BETA, BINH, HA, TAM, Api, Persona
from sales_flow import order_of

from dw_sales.presentation.routes import build_router

pytestmark = pytest.mark.integration

_PARAMS = {
    "case_id": str(uuid.uuid4()),
    "artifact_id": str(uuid.uuid4()),
    "attachment_id": "M01-A1",
    "finding_key": "price_mismatch:2",
    "line_no": "1",
    "message_id": "M01",
}


def _sales_routes() -> list[tuple[str, str]]:
    """Every (method, path) the Sales router declares, its parameters filled."""
    router = build_router(None, access_context=lambda: None, idempotency=lambda: None)
    routes = []
    for route in router.routes:
        assert isinstance(route, APIRoute)
        path = route.path.removeprefix("/api/v1/sales").format(**_PARAMS)
        routes.extend((method, path) for method in sorted(route.methods))
    return routes


async def _call(persona: Persona, method: str, path: str) -> int:
    if method == "GET":
        return (await persona.get(path, sheet="PO")).status_code
    return (await persona.post(path, {"case_version": 1})).status_code


@pytest.mark.parametrize("subject", [BINH, TAM])
async def test_a_member_without_sales_scopes_is_refused_on_every_sales_route(
    api: Api, subject: str
) -> None:
    persona = api.as_(subject)
    routes = _sales_routes()
    assert len(routes) >= 40  # the inventory was read, not an empty app

    answers = {route: await _call(persona, *route) for route in routes}

    assert {route for route, status in answers.items() if status != 403} == set()


async def test_leadership_reaches_the_overview_and_nothing_else(api: Api) -> None:
    ha = api.as_(HA)

    answers = {route: await _call(ha, *route) for route in _sales_routes()}

    assert answers.pop(("GET", "/overview")) == 200
    assert {route for route, status in answers.items() if status != 403} == set()


async def test_another_tenants_pic_sees_an_empty_mailbox_and_none_of_alphas_cases(
    api: Api,
) -> None:
    an, bao = api.as_(AN), api.as_(BAO, BETA)
    case = await order_of(an, "M01")

    assert (await bao.get("/inbox")).json() == []
    assert (await bao.get("/master-data/customers")).json()["items"] == []
    assert (await bao.get("/master-data/quotations")).json()["items"] == []
    assert (await bao.get("/orders")).json() == []
    assert (await bao.get(f"/orders/{case['case_id']}")).status_code == 404
    written = await bao.post(
        f"/orders/{case['case_id']}/prepare", {"case_version": case["case_version"]}
    )
    assert written.status_code == 404
    # Alpha's message is not a message in Beta's mailbox.
    assert (await bao.post("/inbox/M02/process")).status_code == 404


async def test_the_viewer_gets_403_on_case_detail(api: Api) -> None:
    case = await order_of(api.as_(AN), "M01")

    detail = await api.as_(HA).get(f"/orders/{case['case_id']}")

    assert detail.status_code == 403


async def test_an_anonymous_caller_is_refused_and_learns_nothing_else(api: Api) -> None:
    response = await api.client.get("/api/v1/sales/overview")

    # The platform's refusal of a missing token (401), before anything Sales runs.
    assert response.status_code == 401
    assert response.json()["message"] == "missing bearer token"
