"""SA7: a support context reaches only the routes that opted in (ADR 0024).

Default deny is the real gate: a missing scope only stops a route that checks
one, and `GET /runs/{id}` checks none. So `RequireAccessContext` refuses the
support header outright, and the set of routes taking
`RequireAccessContextOrSupport` must equal `SUPPORT_ALLOWED_ROUTES`, read off
the app with every context mounted. A context opening a route adds it there
with its own negative test (Sales: `test_sales_support.py`).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Iterator
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from starlette.routing import BaseRoute
from test_support_endpoint import ENABLED, GRANTER, SECRET, TENANT, WORKSPACE, _container

from dw_api.bootstrap.wiring import SUPPORT_ALLOWED_ROUTES
from dw_api.dependencies.auth import (
    SUPPORT_GRANT_HEADER,
    RequireAccessContextOrSupport,
    get_access_context_or_support,
)
from dw_api.main import create_app
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_sales.presentation.routes import SalesMount

pytestmark = pytest.mark.unit


def _calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    for sub in dependant.dependencies:
        if sub.call is not None:
            yield sub.call
        yield from _calls(sub)


def api_routes(routes: Iterable[BaseRoute]) -> Iterator[RouteContext]:
    """Every API route, inside the included routers too, by FastAPI's own walk.

    FastAPI 0.141 keeps an included router as one `_IncludedRouter` entry in
    `app.routes`, so a walk of `app.routes` alone finds no included route at
    all (this test compared two empty sets until 2026-10-12).
    `iter_route_contexts` (as `test_platform_endpoint.py` walks the app) yields
    each route with the dependencies an `include_router(dependencies=...)`
    adds, which the route's own `dependant` does not carry (measured), so a
    route opted in at the include is seen too. ``.path`` is the URL; the
    template the dependency matches is `template`.
    """
    for route in iter_route_contexts(list(routes)):
        if isinstance(route.original_route, APIRoute):
            yield route


def template(route: RouteContext) -> str:
    """What `request.scope["route"].path` is at request time, which is what the
    dependency matches against `SUPPORT_ALLOWED_ROUTES`: a router's own prefix
    is in it (Sales' `/api/v1/sales`), an `include_router(prefix=...)` is not
    (measured)."""
    original = route.original_route
    assert isinstance(original, APIRoute)
    return original.path


def support_routes(app: FastAPI) -> set[tuple[str, str]]:
    """Every (method, template) whose dependency tree builds a support context."""
    found: set[tuple[str, str]] = set()
    for route in api_routes(app.routes):
        if get_access_context_or_support in set(_calls(route.dependant)):
            found |= {(method, template(route)) for method in route.methods or ()}
    return found


def mounted_app() -> FastAPI:
    """The app with every context mounted, as the composition root mounts
    them (a context's services need not be wired for its routes to exist)."""
    container = _container(GRANTER, ENABLED)
    container.sales = SalesMount(services=None)
    return create_app(container)


def test_the_walker_sees_a_route_that_opts_in() -> None:
    # The guard below can fail: a route taking the dependency is found, on
    # the app itself, inside an included router, and opted in by the include
    # itself; each as the template the dependency matches at request time.
    app = FastAPI()
    router = APIRouter(prefix="/api/v1/ctx")
    included = APIRouter(prefix="/other")

    @app.get("/probe/{item_id}")
    async def probe(item_id: str, context: RequireAccessContextOrSupport) -> None: ...

    @router.get("/items/{item_id}")
    async def item(item_id: str, context: RequireAccessContextOrSupport) -> None: ...

    @included.get("/things")
    async def things() -> None: ...

    app.include_router(router)
    app.include_router(
        included, prefix="/api/v1", dependencies=[Depends(get_access_context_or_support)]
    )

    assert support_routes(app) == {
        ("GET", "/probe/{item_id}"),
        ("GET", "/api/v1/ctx/items/{item_id}"),
        ("GET", "/other/things"),
    }


def test_the_walker_reads_the_whole_mounted_app() -> None:
    paths = {template(route) for route in api_routes(mounted_app().routes)}
    assert len(paths) >= 80
    assert {"/support/grants", "/api/v1/sales/orders/{case_id}"} <= paths


def test_only_the_allowed_routes_take_a_support_context() -> None:
    assert support_routes(mounted_app()) == set(SUPPORT_ALLOWED_ROUTES)


@pytest.mark.parametrize(
    "path",
    [
        f"/runs/{uuid.uuid4()}",
        "/approvals",
        "/knowledge/documents",
        "/audit/events",
        "/admin/members",
        "/support/grants",
    ],
)
async def test_sa7_a_route_not_opened_to_support_refuses_the_header(path: str) -> None:
    token = DevTokenVerifier(SECRET).issue("dev|staff", amr=["pwd", "otp"])
    app = create_app(_container(GRANTER, ENABLED))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": str(TENANT),
                    "X-Workspace-Id": str(WORKSPACE),
                    SUPPORT_GRANT_HEADER: str(uuid.uuid4()),
                },
            )
    assert response.status_code == 403, path
    assert response.json()["details"]["reason_code"] == "support_context_not_allowed", path


async def test_the_dependency_itself_refuses_a_route_missing_from_the_list() -> None:
    # Belt and braces: a route that takes the dependency without being listed
    # still refuses support, before any grant is read.
    app = create_app(_container(GRANTER, ENABLED))

    @app.get("/api/v1/probe/{item_id}")
    async def probe(item_id: str, context: RequireAccessContextOrSupport) -> dict[str, str]:
        return {"tenant": str(context.tenant_id)}

    token = DevTokenVerifier(SECRET).issue("dev|staff", amr=["pwd", "otp"])
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/probe/1",
                headers={
                    "Authorization": f"Bearer {token}",
                    SUPPORT_GRANT_HEADER: str(uuid.uuid4()),
                },
            )
    assert response.status_code == 403
    assert response.json()["details"]["reason_code"] == "support_context_not_allowed"
