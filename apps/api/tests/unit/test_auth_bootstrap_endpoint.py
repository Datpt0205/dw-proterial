"""GET /api/v1/auth/bootstrap answers with what the identity bootstrap resolved.

The bootstrap itself is faked; the route's job is to carry every field of the
view to the screen, the role names and the effective scopes included. A field
dropped here is a screen that offers less than the API allows, or that names a
role from a copy of its own.
"""

import uuid

import httpx
import pytest
from asgi_lifespan import LifespanManager

from dw_api.bootstrap import ApiContainer
from dw_api.health import CheckState, HealthService
from dw_api.main import create_app
from dw_api.settings import ApiSettings
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.entitlement import DEFAULT_PLANS, PlanEntitlementService
from dw_platform.application.identity_bootstrap import BootstrapView, WorkspaceMembershipView

pytestmark = pytest.mark.unit

SECRET = "unit-test-secret-0123456789abcdef"
PRINCIPAL = uuid.uuid4()
TENANT = uuid.uuid4()
WORKSPACE = uuid.uuid4()


class FakeBootstrap:
    async def bootstrap(self, identity: object) -> BootstrapView:
        return BootstrapView(
            principal_id=PRINCIPAL,
            subject="dev|an",
            email="an@example.com",
            display_name="Nguyễn Văn An",
            memberships=(
                WorkspaceMembershipView(
                    tenant_id=TENANT,
                    tenant_slug="alpha",
                    tenant_name="FDX",
                    workspace_id=WORKSPACE,
                    workspace_slug="main",
                    workspace_name="Main workspace",
                    roles=("member", "sales_pic"),
                    scopes=("sales.case.read", "sales.compliance.ack"),
                    role_names={"member": "Member", "sales_pic": "Sales phụ trách (PIC)"},
                ),
            ),
        )


def make_container() -> ApiContainer:
    async def ok_probe() -> CheckState:
        return "ok"

    return ApiContainer(
        settings=ApiSettings(profile="test", dev_secret=SECRET),
        engine=None,
        health_service=HealthService(probes={"database": ok_probe}),
        token_verifier=DevTokenVerifier(SECRET),
        access_context_factory=None,
        identity_bootstrap=FakeBootstrap(),
        uow_factory=None,
        authorization=ScopeAuthorizationService(),
        entitlement=PlanEntitlementService(DEFAULT_PLANS),
    )


async def test_bootstrap_carries_role_names_and_effective_scopes() -> None:
    app = create_app(make_container())
    token = DevTokenVerifier(SECRET).issue("dev|an", email="an@example.com")
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/bootstrap", headers={"Authorization": f"Bearer {token}"}
            )

    assert response.status_code == 200
    (membership,) = response.json()["memberships"]
    assert membership["roles"] == ["member", "sales_pic"]
    assert membership["scopes"] == ["sales.case.read", "sales.compliance.ack"]
    assert membership["role_names"] == {
        "member": "Member",
        "sales_pic": "Sales phụ trách (PIC)",
    }
