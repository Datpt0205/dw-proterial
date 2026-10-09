"""The Sales mount as the composition root builds it, without a database.

- Every `/api/v1/sales/*` route depends on the verified access context, and
  every mutation checks its scope before it claims an `Idempotency-Key`.
- The mocks are wired only outside a deployed profile, or for the demo tenant
  a deployment names; otherwise every Sales route answers that no data source
  is configured (G31).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from dw_api.bootstrap import ApiContainer
from dw_api.bootstrap.wiring import build_sales
from dw_api.dependencies.auth import get_access_context
from dw_api.dependencies.idempotency import get_idempotent_operation
from dw_api.health import HealthService
from dw_api.main import create_app
from dw_api.settings import ApiSettings
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.entitlement import DEFAULT_PLANS, PlanEntitlementService
from dw_platform.application.identity import DbAccessContextFactory, MembershipAccess
from dw_sales.presentation.routes import NOT_CONFIGURED, SalesMount, build_router

pytestmark = pytest.mark.unit

SECRET = "unit-test-secret-0123456789abcdef"
TENANT, WORKSPACE = uuid.uuid4(), uuid.uuid4()


def _calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    for sub in dependant.dependencies:
        if sub.call is not None:
            yield sub.call
        yield from _calls(sub)


def _routes() -> list[APIRoute]:
    router = build_router(
        None, access_context=get_access_context, idempotency=get_idempotent_operation
    )
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    assert len(routes) >= 40
    return routes


@pytest.mark.parametrize("route", _routes(), ids=lambda r: f"{sorted(r.methods)[0]} {r.path}")
def test_every_sales_route_depends_on_the_verified_access_context(route: APIRoute) -> None:
    assert route.path.startswith("/api/v1/sales/")
    assert get_access_context in set(_calls(route.dependant))


@pytest.mark.parametrize(
    "route",
    [r for r in _routes() if "POST" in r.methods],
    ids=lambda r: r.path,
)
def test_every_mutation_checks_its_scope_before_it_claims_the_key(route: APIRoute) -> None:
    top = [sub.call for sub in route.dependant.dependencies]
    assert get_idempotent_operation in top, "every mutation honours Idempotency-Key"
    guard = next(i for i, call in enumerate(top) if getattr(call, "__name__", "") == "guard")
    assert guard < top.index(get_idempotent_operation)


def test_every_case_mutation_names_the_version_it_was_decided_on() -> None:
    case_routes = [r for r in _routes() if "POST" in r.methods and "{case_id}" in r.path]
    assert case_routes
    for route in case_routes:
        (body,) = route.dependant.body_params
        assert "case_version" in body.field_info.annotation.model_fields  # type: ignore[union-attr]


def test_no_sales_route_decides_what_a_checker_decides() -> None:
    """The quotation approval and the cross-check are decided on the platform
    approval DW1's run pauses on (ticket 10, dw_sales ADR 0004): the routes
    that decided them on the case are gone, and none has taken their place."""
    paths = {route.path for route in _routes()}
    assert "/api/v1/sales/quotes/{case_id}/approval" not in paths
    assert "/api/v1/sales/orders/{case_id}/cross-check" not in paths
    assert not [p for p in paths if p.endswith(("/approval", "/approve", "/cross-check"))]


# ------------------------------------------------------------- the gating --


def test_a_deployed_profile_wires_no_mock_unless_it_names_the_demo_tenant() -> None:
    assert ApiSettings(profile="uat").sales_demo_scope() is None
    named = ApiSettings(
        profile="production",
        sales_demo_tenant_id=str(TENANT),
        sales_demo_workspace_id=str(WORKSPACE),
    )
    assert named.sales_demo_scope() == (TENANT, WORKSPACE)
    local = ApiSettings(profile="local")
    assert local.sales_demo_scope() == (
        uuid.UUID(local.default_tenant_id),
        uuid.UUID(local.default_workspace_id),
    )
    with pytest.raises(RuntimeError, match="SALES_DEMO_WORKSPACE_ID"):
        ApiSettings(profile="uat", sales_demo_tenant_id=str(TENANT)).sales_demo_scope()
    # Half a demo scope fails at startup, not on the first Sales request.
    with pytest.raises(RuntimeError, match="SALES_DEMO_WORKSPACE_ID"):
        ApiSettings(profile="local", sales_demo_tenant_id=str(TENANT)).validate_for_profile()


def test_build_sales_in_a_deployed_profile_without_the_demo_tenant_mounts_nothing() -> None:
    unused: Any = object()
    mount = build_sales(
        ApiSettings(profile="production"),
        session_factory=unused,
        clock=unused,
        ids=unused,
        authorization=ScopeAuthorizationService(),
        directory=unused,
        holders=unused,
        notifications=unused,
        artifact_bytes=unused,
        release_manifest_ref=None,
        runtime=unused,
    )
    assert mount == SalesMount(services=None)


class _Lookup:
    async def find_access(
        self, subject: str, issuer: str, tenant_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> MembershipAccess | None:
        return MembershipAccess(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            principal_id=uuid.uuid4(),
            roles=frozenset({"sales_pic"}),
            scopes=frozenset({"sales.overview.read", "sales.case.read"}),
            groups=frozenset(),
            clearance="internal",
            plan_id="professional",
            feature_flags=frozenset(),
        )


async def test_an_unconfigured_source_answers_every_sales_route_with_503() -> None:
    container = ApiContainer(
        settings=ApiSettings(profile="test", dev_secret=SECRET),
        engine=None,
        health_service=HealthService(probes={}),
        token_verifier=DevTokenVerifier(SECRET),
        access_context_factory=DbAccessContextFactory(_Lookup()),
        identity_bootstrap=None,
        uow_factory=None,
        authorization=ScopeAuthorizationService(),
        entitlement=PlanEntitlementService(DEFAULT_PLANS),
    )
    container.sales = SalesMount(services=None)
    app = create_app(container)
    token = DevTokenVerifier(SECRET).issue("dev|an.nguyen")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(TENANT),
        "X-Workspace-Id": str(WORKSPACE),
    }
    async with (
        LifespanManager(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client,
    ):
        overview = await client.get("/api/v1/sales/overview", headers=headers)
        process = await client.post("/api/v1/sales/inbox/process-all", headers=headers)
        anonymous = await client.get("/api/v1/sales/overview")

    assert overview.status_code == process.status_code == 503
    assert overview.json()["message"] == NOT_CONFIGURED
    # Who is asking is settled first: a caller with no token learns nothing
    # but that it must sign in (401, the platform's missing-bearer answer).
    assert anonymous.status_code == 401
