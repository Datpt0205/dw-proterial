"""The sign-in account routes over the real service, the outside faked honestly.

What the routes own: 503 with its reason when the deployment has no
`dw-accounts` client, `Cache-Control: no-store` on a body carrying a
temporary password, and a replayed `Idempotency-Key` that neither acts twice
nor ever answers (or stores) the password again. The rules are the service's
(`dw_platform/tests/unit/test_member_accounts.py`) and Keycloak's behaviour is
integration-tested (`test_keycloak_accounts.py`).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from types import TracebackType

import httpx
import pytest
from asgi_lifespan import LifespanManager
from test_idempotency_dependency import MemoryStore

from dw_api.bootstrap import ApiContainer
from dw_api.health import CheckState, HealthService
from dw_api.main import create_app
from dw_api.settings import ApiSettings
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.entitlement import DEFAULT_PLANS, PlanEntitlementService
from dw_platform.application.idempotency import HttpIdempotency
from dw_platform.application.identity import DbAccessContextFactory, MembershipAccess
from dw_platform.application.member_accounts import MemberAccountsService
from dw_platform.application.membership_admin import UserRef
from dw_platform.application.tenant_members import (
    MembershipChange,
    MemberWorkspace,
    Roles,
    TenantMember,
    TenantMembersService,
)
from dw_platform.domain.audit import AuditEvent
from dw_platform.testing.login_accounts import MemoryLoginAccounts

pytestmark = pytest.mark.unit

SECRET = "unit-test-secret-0123456789abcdef"
TENANT, WS = uuid.uuid4(), uuid.uuid4()
ADMIN, LAN = uuid.uuid4(), uuid.uuid4()
CATALOG = {
    "sales_pic": frozenset({"sales.case.read"}),
    "org_admin": frozenset({"platform.members.read", "platform.members.write"}),
}


class Lookup:
    async def find_access(
        self, subject: str, issuer: str, tenant_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> MembershipAccess | None:
        return MembershipAccess(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            principal_id=ADMIN,
            roles=frozenset({"org_admin"}),
            scopes=CATALOG["org_admin"],
            groups=frozenset(),
            clearance="internal",
            plan_id="professional",
            feature_flags=frozenset(),
        )


class Repo:
    def __init__(self) -> None:
        self.members = [
            TenantMember(
                user_id=LAN,
                display_name="Lan",
                email="lan@example.test",
                status="active",
                memberships=(MemberWorkspace(WS, "Sales", ("sales_pic",)),),
            )
        ]
        self.invited: list[str] = []

    async def role_catalog(self) -> dict[str, frozenset[str]]:
        return dict(CATALOG)

    async def list_members(self, context: AccessContext) -> list[TenantMember]:
        return list(self.members)

    async def replace_memberships(
        self,
        context: AccessContext,
        *,
        user_id: uuid.UUID,
        plan: Callable[[Roles], Roles],
        audit: Callable[[MembershipChange], AuditEvent],
    ) -> list[MembershipChange]:
        raise NotImplementedError("not exercised by the account routes")

    async def invite(
        self,
        context: AccessContext,
        *,
        display_name: str,
        email: str,
        memberships: Roles,
        audit: Callable[[uuid.UUID, uuid.UUID, frozenset[str]], AuditEvent],
    ) -> UserRef:
        self.invited.append(email)
        return UserRef(user_id=uuid.uuid4(), email=email, display_name=display_name)


class Uow:
    def __init__(self) -> None:
        self.committed: list[AuditEvent] = []
        self.pending: list[AuditEvent] = []
        self.audit = self

    def __call__(self, context: AccessContext) -> Uow:
        return self

    async def append(self, event: AuditEvent) -> None:
        self.pending.append(event)

    async def __aenter__(self) -> Uow:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.pending.clear()

    async def commit(self) -> None:
        self.committed += self.pending
        self.pending.clear()


class World:
    def __init__(self, *, configured: bool = True) -> None:
        self.repo, self.accounts, self.uow = Repo(), MemoryLoginAccounts(), Uow()
        self.store = MemoryStore()
        authz = ScopeAuthorizationService()
        members = TenantMembersService(self.repo, authz, SystemClock(), Uuid4Generator())

        async def ok() -> CheckState:
            return "ok"

        self.container = ApiContainer(
            settings=ApiSettings(profile="test", dev_secret=SECRET),
            engine=None,
            health_service=HealthService(probes={"database": ok}),
            token_verifier=DevTokenVerifier(SECRET),
            access_context_factory=DbAccessContextFactory(Lookup()),
            identity_bootstrap=None,
            uow_factory=None,
            authorization=authz,
            entitlement=PlanEntitlementService(DEFAULT_PLANS),
            idempotency=HttpIdempotency(self.store, SystemClock()),
            tenant_members=members,
            member_accounts=MemberAccountsService(
                members=members,
                accounts=self.accounts,
                uow=self.uow,  # type: ignore[arg-type]  # the audit slice of the unit of work
                authz=authz,
                clock=SystemClock(),
                ids=Uuid4Generator(),
            )
            if configured
            else None,
        )

    async def send(
        self, method: str, path: str, body: object = None, key: str | None = None
    ) -> httpx.Response:
        token = DevTokenVerifier(SECRET).issue("dev|admin", email="admin@example.test")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(TENANT),
            "X-Workspace-Id": str(WS),
        }
        if key:
            headers["Idempotency-Key"] = key
        app = create_app(self.container)
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(
                    method, f"/api/v1/admin/accounts{path}", json=body, headers=headers
                )


CREATE = {
    "display_name": "Vũ Minh",
    "email": "minh.vu@example.test",
    "memberships": [{"workspace_id": str(WS), "role_keys": ["sales_pic"]}],
}


async def test_without_the_client_every_route_answers_503_with_its_reason() -> None:
    world = World(configured=False)
    for method, path, body in (
        ("GET", "", None),
        ("POST", "", CREATE),
        ("POST", f"/{LAN}/password-reset", None),
        ("PUT", f"/{LAN}/enabled", {"enabled": False}),
    ):
        response = await world.send(method, path, body)
        assert response.status_code == 503, (method, path, response.text)
        assert response.json()["details"]["reason_code"] == "login_accounts_not_configured"


async def test_creating_answers_the_password_once_and_never_caches_it() -> None:
    world = World()
    first = await world.send("POST", "", CREATE, key="create-1")
    assert first.status_code == 201, first.text
    assert first.headers["Cache-Control"] == "no-store"
    password = first.json()["temporary_password"]
    assert world.accounts.held["minh.vu@example.test"].password == password

    again = await world.send("POST", "", CREATE, key="create-1")
    assert again.status_code == 201
    assert again.json()["temporary_password"] is None
    assert again.json()["user_id"] == first.json()["user_id"]
    assert world.repo.invited == ["minh.vu@example.test"]
    stored = [row.response.body for row in world.store.rows.values() if row.response]
    assert stored and password not in json.dumps(stored)


async def test_a_replayed_reset_does_not_reset_again() -> None:
    world = World()
    await world.accounts.create(
        tenant_id=TENANT, email="lan@example.test", display_name="Lan", temporary_password="old"
    )
    first = await world.send("POST", f"/{LAN}/password-reset", key="reset-1")
    assert first.status_code == 200, first.text
    assert first.headers["Cache-Control"] == "no-store"
    password = first.json()["temporary_password"]
    again = await world.send("POST", f"/{LAN}/password-reset", key="reset-1")
    assert again.json()["temporary_password"] is None
    assert world.accounts.held["lan@example.test"].password == password
    assert len(world.uow.committed) == 1


async def test_locking_answers_204_and_the_list_shows_it() -> None:
    world = World()
    await world.accounts.create(
        tenant_id=TENANT, email="lan@example.test", display_name="Lan", temporary_password="pw"
    )
    locked = await world.send("PUT", f"/{LAN}/enabled", {"enabled": False})
    assert locked.status_code == 204, locked.text
    listed = await world.send("GET", "")
    assert listed.json() == [{"email": "lan@example.test", "enabled": False}]


async def test_an_unknown_body_field_is_refused() -> None:
    world = World()
    response = await world.send("PUT", f"/{LAN}/enabled", {"enabled": False, "tenant_id": "x"})
    assert response.status_code == 422
    assert world.accounts.calls == 0
