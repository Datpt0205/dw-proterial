"""FPT support in Sales, as the composition root mounts it (ticket 22, G20).

dw_sales ADR 0003 §5 over the platform's support access (ADR 0024): the set
a customer may grant is the overview and the cases, never a price and never
a write; five reads take a support context and every other Sales route
refuses one before it reads anything. With a real grant, the reads, the
hidden amounts and the audit trail are `test_sales_api_support.py`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi.dependencies.models import Dependant
from fastapi.routing import RouteContext
from test_support_endpoint import SECRET
from test_support_routes import api_routes, mounted_app, template

from dw_api.bootstrap.wiring import SUPPORT_ALLOWED_ROUTES, register_sales_support
from dw_api.dependencies.auth import (
    SUPPORT_GRANT_HEADER,
    get_access_context,
    get_access_context_or_support,
)
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.application.support_access import SupportScopeCatalog
from dw_sales.application.access import (
    SUPPORT_SCOPE_SET_KEY,
    SUPPORT_SCOPES,
    SalesScopes,
)

pytestmark = pytest.mark.unit

# The five reads the ticket opens, written out: the constant at the
# composition root is checked against this, not against itself.
OPENED = {
    ("GET", "/api/v1/sales/overview"),
    ("GET", "/api/v1/sales/orders"),
    ("GET", "/api/v1/sales/orders/{case_id}"),
    ("GET", "/api/v1/sales/quotes"),
    ("GET", "/api/v1/sales/quotes/{case_id}"),
}

_PARAMS = {
    "case_id": str(uuid.uuid4()),
    "artifact_id": str(uuid.uuid4()),
    "attachment_id": "M01-A1",
    "finding_key": "price_mismatch:2",
    "line_no": "1",
    "message_id": "M01",
    # A tenant's own rule versions (ticket 19).
    "key": "sales_order_rules",
    "version_id": str(uuid.uuid4()),
}


def _calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    for sub in dependant.dependencies:
        if sub.call is not None:
            yield sub.call
        yield from _calls(sub)


def _sales_routes(app: Any) -> list[RouteContext]:
    routes = [r for r in api_routes(app.routes) if template(r).startswith("/api/v1/sales/")]
    assert len(routes) >= 40  # the inventory was read, not an empty app
    return routes


# ------------------------------------------------------------ the set --


def test_the_support_set_is_the_overview_and_the_cases_and_nothing_else() -> None:
    """ADR 0003 §5: never a price, never a write. Adding `sales.price.read`
    here would hand every amount to support; this is where that goes red."""
    assert {"sales.overview.read", "sales.case.read"} == SUPPORT_SCOPES
    prices = {SalesScopes.PRICE_READ.value, SalesScopes.PRICE_OTHER_CUSTOMERS_READ.value}
    assert not SUPPORT_SCOPES & prices
    assert all(scope.endswith(".read") for scope in SUPPORT_SCOPES)


def test_the_composition_root_registers_it_for_the_workspace() -> None:
    catalog = SupportScopeCatalog()
    register_sales_support(catalog)
    catalog.freeze()  # no resource type left that nobody names

    registered = catalog.get(SUPPORT_SCOPE_SET_KEY)

    assert registered is not None
    assert registered.scopes == SUPPORT_SCOPES
    assert registered.resource_types == {"workspace"}
    assert [s.key for s in catalog.sets()] == [SUPPORT_SCOPE_SET_KEY]


# ---------------------------------------------------------- the routes --


def test_the_composition_root_opens_exactly_the_five_reads() -> None:
    assert {r for r in SUPPORT_ALLOWED_ROUTES if r[1].startswith("/api/v1/sales/")} == OPENED


def test_every_other_sales_route_takes_the_member_only_context() -> None:
    """The five take the support-capable context; every other Sales route the
    one that refuses the support header outright."""
    for route in _sales_routes(mounted_app()):
        calls = set(_calls(route.dependant))
        opened = {(m, template(route)) for m in route.methods or ()} <= OPENED
        assert (get_access_context_or_support in calls) is opened, route.path
        assert (get_access_context in calls) is not opened, route.path


async def test_under_a_support_grant_every_other_sales_route_answers_403() -> None:
    """Every mutation, the source view, the evidence (master data, the
    screening) and the downloads: refused before the grant is even read, so a
    valid grant changes nothing (the same with a real one:
    `test_sales_api_support.py`)."""
    app = mounted_app()
    token = DevTokenVerifier(SECRET).issue("dev|staff", amr=["pwd", "otp"])
    headers = {"Authorization": f"Bearer {token}", SUPPORT_GRANT_HEADER: str(uuid.uuid4())}
    answered: dict[tuple[str, str], int] = {}
    async with (
        LifespanManager(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client,
    ):
        for route in _sales_routes(app):
            for method in route.methods or ():
                if (method, template(route)) in OPENED:
                    continue
                response = await client.request(
                    method,
                    route.path.format(**_PARAMS),
                    headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                    json={"case_version": 1},
                )
                reason = response.json().get("details", {}).get("reason_code")
                if response.status_code != 403 or reason != "support_context_not_allowed":
                    answered[method, route.path] = response.status_code
    assert answered == {}
