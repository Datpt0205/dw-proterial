"""Who reaches which Sales route, signed in as each persona (ticket 11).

The negative half of the actor table: the purchasing manager holds no
`sales.*` scope and gets 403 on every route; tenant IT reaches the rules
routes and nothing else (`sales_rules_editor`, 2026-10-21); leadership reaches
the overview and nothing else; another tenant's PIC sees an empty mailbox and
no customers, and another tenant's case is not found, never forbidden.
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
    # A tenant's own rule versions (ticket 19): a key holding no price, so
    # tenant IT's answer on it is the rules scope's, not the price scope's.
    "key": "sales_bravo_upload",
    "version_id": str(uuid.uuid4()),
    # Master data imports (ticket 41).
    "catalog_list": "customers",
    "snapshot_id": str(uuid.uuid4()),
    # A rule version drafted from a company's template ("Tạo từ tệp mẫu").
    "draft_id": str(uuid.uuid4()),
    # A Q12 screening row's question to the customer (AI item 11).
    "customer_code": "NRV",
    "prv_code": "CB-2006",
    # A status-assistant session (dw_sales ADR 0007).
    "session_id": str(uuid.uuid4()),
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
    if method == "PUT":
        return (await persona.put(path, {"case_version": 1, "assignee": None})).status_code
    return (await persona.post(path, {"case_version": 1})).status_code


async def test_a_member_without_sales_scopes_is_refused_on_every_sales_route(api: Api) -> None:
    persona = api.as_(BINH)
    routes = _sales_routes()
    assert len(routes) >= 40  # the inventory was read, not an empty app

    answers = {route: await _call(persona, *route) for route in routes}

    assert {route for route, status in answers.items() if status != 403} == set()


async def test_tenant_it_reaches_the_rules_routes_and_nothing_else(api: Api) -> None:
    """`sales_rules_editor` is `sales.rules.propose` alone: no case, no
    overview, no master data, no price. The process page reads the same
    scope (2026-10-22). The proposal here carries no document,
    so it is refused as invalid (422) and writes nothing. Drafting a version
    from the company's template ("Tạo từ tệp mẫu") or from words (ADR 0006)
    is the same scope, so IT, who configures the rules, reaches those routes
    too; the walk's draft id is random, so the read answers 404."""
    answers = {route: await _call(api.as_(TAM), *route) for route in _sales_routes()}

    def named(route: tuple[str, str]) -> tuple[str, str]:
        method, path = route
        if path.startswith("/rules/drafts/"):
            return method, "/rules/drafts/{draft_id}"
        return route

    assert {named(route) for route, status in answers.items() if status != 403} == {
        ("GET", "/rules"),
        ("GET", "/rules/process"),
        ("GET", "/rules/sales_bravo_upload/schema"),
        ("GET", "/rules/sales_bravo_upload/platform"),
        ("POST", "/rules/sales_bravo_upload/versions"),
        ("POST", "/rules/sales_bravo_upload/drafts"),
        ("POST", "/rules/sales_bravo_upload/drafts/words"),
        ("GET", "/rules/drafts/{draft_id}"),
    }


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


async def test_another_tenants_pic_cannot_correct_a_value_on_alphas_order(api: Api) -> None:
    """Ticket 15: the per-field correction reads the case in the caller's own
    workspace only; Beta's PIC learns nothing and Alpha's order is unchanged."""
    an, bao = api.as_(AN), api.as_(BAO, BETA)
    case = await order_of(an, "M27")

    written = await bao.post(
        f"/orders/{case['case_id']}/findings/value_uncertain:2/corrections",
        {"case_version": case["case_version"], "field": "quantity", "value": "1"},
    )

    assert written.status_code == 404
    after = (await an.get(f"/orders/{case['case_id']}")).json()
    assert after["case_version"] == case["case_version"]
    assert all(not line["corrections"] for line in after["lines"])
