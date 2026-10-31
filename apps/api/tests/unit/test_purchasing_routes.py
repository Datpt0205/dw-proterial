"""`/api/v1/purchasing/*` over the real app and scope check, the store and
the model in memory (`dw_purchasing.testing.world`).

What the routes own: every one needs a verified caller, a scope is refused
before anything is read or written, the tenant comes from the context and a
body naming one is refused, and an unconfigured source answers 503.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from test_support_endpoint import SECRET, FakeLookup, FakeRepo, NoScopes

from dw_api.bootstrap import ApiContainer
from dw_api.health import CheckState, HealthService
from dw_api.main import create_app
from dw_api.settings import ApiSettings
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.entitlement import DEFAULT_PLANS, PlanEntitlementService
from dw_platform.application.identity import DbAccessContextFactory
from dw_platform.application.support_access import SupportGrantService, SupportScopeCatalog
from dw_purchasing.application.access import Gate
from dw_purchasing.application.services import PurchasingServices
from dw_purchasing.presentation.routes import PurchasingMount
from dw_purchasing.testing.world import ALPHA, EVERY_SCOPE, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
ANSWERS = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)["answers"]
FORM: dict[str, Any] = {
    "pr_no": "PR-2611-020",
    "department": "Kho",
    "requester": "Trần Văn Kho",
    "budget_code": "CC-WH-01",
    "currency": "VND",
    "lines": [{"line_no": 1, "description": "Pallet nhựa", "quantity": "20", "unit": "cái"}],
}


def _world() -> World:
    world = open_world(REPO, ANSWERS)
    # The platform's own scope check, as the app runs it.
    world.service = dataclasses.replace(world.service, gate=Gate(ScopeAuthorizationService()))
    return world


def _container(scopes: frozenset[str], mount: PurchasingMount | None) -> ApiContainer:
    async def ok() -> CheckState:
        return "ok"

    catalog = SupportScopeCatalog()
    catalog.freeze()
    return ApiContainer(
        settings=ApiSettings(profile="test", dev_secret=SECRET),
        engine=None,
        health_service=HealthService(probes={"database": ok}),
        token_verifier=DevTokenVerifier(SECRET),
        access_context_factory=DbAccessContextFactory(FakeLookup(scopes, frozenset())),
        identity_bootstrap=None,
        uow_factory=None,
        authorization=ScopeAuthorizationService(),
        entitlement=PlanEntitlementService(DEFAULT_PLANS),
        support_catalog=catalog,
        support_grants=SupportGrantService(
            repo=FakeRepo(),
            member_scopes=NoScopes(),
            catalog=catalog,
            clock=SystemClock(),
            ids=Uuid4Generator(),
        ),
        purchasing=mount,
    )


async def _call(
    container: ApiContainer,
    method: str,
    path: str,
    body: Any = None,
    *,
    signed_in: bool = True,
    tenant: tuple[uuid.UUID, uuid.UUID] = ALPHA,
) -> httpx.Response:
    headers = {"X-Tenant-Id": str(tenant[0]), "X-Workspace-Id": str(tenant[1])}
    if signed_in:
        token = DevTokenVerifier(SECRET).issue("dev|buyer", email="buyer@example.test")
        headers["Authorization"] = f"Bearer {token}"
    app = create_app(container)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(
                method, f"/api/v1/purchasing{path}", json=body, headers=headers
            )


def _mounted(world: World) -> PurchasingMount:
    return PurchasingMount(services=PurchasingServices(requests=world.service))


async def test_a_buyer_submits_a_form_reads_it_back_and_has_a_mail_read() -> None:
    world = _world()
    container = _container(EVERY_SCOPE, _mounted(world))

    created = await _call(container, "POST", "/requests", FORM)
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]
    listed = await _call(container, "GET", "/requests")
    assert [c["case_id"] for c in listed.json()["items"]] == [case_id]
    detail = await _call(container, "GET", f"/requests/{case_id}")
    assert detail.json()["rules_ref"] == "purchasing_rules@1.0.0"

    read = await _call(container, "POST", "/mail/P01/read")
    assert read.status_code == 200 and read.json()["disposition"] == "opened"
    mail = await _call(container, "GET", "/mail")
    assert [m["message_id"] for m in mail.json()][:2] == ["P01", "P02"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/requests", None),
        ("GET", f"/requests/{uuid.uuid4()}", None),
        ("POST", "/requests", FORM),
        ("GET", "/mail", None),
        ("POST", "/mail/P01/read", None),
    ],
)
async def test_every_route_refuses_a_caller_without_its_scope_and_touches_nothing(
    method: str, path: str, body: Any
) -> None:
    world = _world()
    container = _container(frozenset({"sales.case.read"}), _mounted(world))

    response = await _call(container, method, path, body)
    assert response.status_code == 403, response.text
    unsigned = await _call(container, method, path, body, signed_in=False)
    assert unsigned.status_code == 401
    assert world.store.scopes == {} and world.model.calls == []


async def test_a_body_naming_a_tenant_is_refused() -> None:
    world = _world()
    container = _container(EVERY_SCOPE, _mounted(world))
    response = await _call(container, "POST", "/requests", {**FORM, "tenant_id": str(ALPHA[0])})
    assert response.status_code == 422
    assert world.store.scopes == {}


async def test_an_incomplete_form_is_refused_naming_what_the_rules_require() -> None:
    world = _world()
    container = _container(EVERY_SCOPE, _mounted(world))
    response = await _call(container, "POST", "/requests", {**FORM, "budget_code": None})
    assert response.status_code == 422
    assert response.json()["details"]["refusals"] == "missing:budget_code"


async def test_another_tenant_finds_neither_the_case_nor_the_mail() -> None:
    world = _world()
    container = _container(EVERY_SCOPE, _mounted(world))
    case_id = (await _call(container, "POST", "/requests", FORM)).json()["case_id"]
    other = (uuid.UUID(int=0xB1), uuid.UUID(int=0xB2))

    assert (await _call(container, "GET", f"/requests/{case_id}", tenant=other)).status_code == 404
    assert (await _call(container, "POST", "/mail/P01/read", tenant=other)).status_code == 404
    assert (await _call(container, "GET", "/requests", tenant=other)).json()["items"] == []


async def test_without_a_data_source_a_caller_is_told_so_and_a_stranger_learns_nothing() -> None:
    container = _container(EVERY_SCOPE, PurchasingMount(services=None))
    assert (await _call(container, "GET", "/requests")).status_code == 503
    assert (await _call(container, "GET", "/requests", signed_in=False)).status_code == 401


def test_every_route_checks_its_scope_before_its_body_or_idempotency_key() -> None:
    """The service checks again, so a missing route guard answers 403 all the
    same; what the guard adds is refusing before the `Idempotency-Key` is
    claimed, which only its presence on the route shows."""
    from fastapi.routing import APIRoute

    from dw_purchasing.presentation.routes import build_router

    router = build_router(None, access_context=lambda: None, idempotency=lambda: None)
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    assert len(routes) == 5
    assert all(route.dependencies for route in routes), [
        route.path for route in routes if not route.dependencies
    ]
