"""The knowledge upload refuses a classification off the clearance ladder.

`knowledge.ingest_jobs.classification` holds the ladder (CHECK, migration
0d8f03566652). Without the check (EnqueueIngestCommand's, which the route
builds before staging) an off-ladder value is staged in object storage and
then refused by the database as a 500; with it, the caller gets a validation
error and nothing is staged.

The job store is real but bound to no database: a value the route lets through
reaches staging and then fails at the first query, which is enough to tell
"refused before staging" from "let through".
"""

import uuid

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy.ext.asyncio import async_sessionmaker

from dw_api.bootstrap import ApiContainer
from dw_api.errors import status_for
from dw_api.health import CheckState, HealthService
from dw_api.main import create_app
from dw_api.settings import ApiSettings
from dw_kernel.errors import ErrorCode
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_knowledge.contracts import CLASSIFICATIONS
from dw_knowledge.ingest_jobs import IngestJobStore
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.application.authorization import (
    PLATFORM_ADMIN_ROLE,
    PLATFORM_ADMIN_SCOPE,
    ScopeAuthorizationService,
)
from dw_platform.application.entitlement import DEFAULT_PLANS, PlanEntitlementService
from dw_platform.application.identity import DbAccessContextFactory, MembershipAccess

pytestmark = pytest.mark.unit

SECRET = "unit-test-secret-0123456789abcdef"
TENANT = uuid.uuid4()
WORKSPACE = uuid.uuid4()


class FakeMembershipLookup:
    def __init__(
        self,
        roles: frozenset[str] = frozenset({"member"}),
        scopes: frozenset[str] = frozenset({"knowledge.write"}),
    ) -> None:
        self.roles = roles
        self.scopes = scopes

    async def find_access(
        self, subject: str, issuer: str, tenant_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> MembershipAccess | None:
        if tenant_id != TENANT or workspace_id != WORKSPACE:
            return None
        return MembershipAccess(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            principal_id=uuid.uuid4(),
            roles=self.roles,
            scopes=self.scopes,
            groups=frozenset(),
            clearance="internal",
            plan_id="professional",
            feature_flags=frozenset(),
        )


class FakeStorage:
    def __init__(self) -> None:
        self.staged: list[str] = []

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        self.staged.append(key)
        return key

    async def get_object(self, key: str) -> bytes:
        raise NotImplementedError("not exercised by the upload route")

    async def list_objects(self, prefix: str) -> list[str]:
        raise NotImplementedError("not exercised by the upload route")

    async def delete_object(self, key: str) -> None:
        raise NotImplementedError("not exercised by the upload route")


def _container(
    storage: FakeStorage, membership: FakeMembershipLookup | None = None
) -> ApiContainer:
    async def ok_probe() -> CheckState:
        return "ok"

    return ApiContainer(
        settings=ApiSettings(profile="test", dev_secret=SECRET),
        engine=None,
        health_service=HealthService(probes={"database": ok_probe}),
        token_verifier=DevTokenVerifier(SECRET),
        access_context_factory=DbAccessContextFactory(membership or FakeMembershipLookup()),
        identity_bootstrap=None,
        uow_factory=None,
        authorization=ScopeAuthorizationService(),
        entitlement=PlanEntitlementService(DEFAULT_PLANS),
        grant_membership=None,
        revoke_membership=None,
        ingest_job_store=IngestJobStore(
            session_factory=async_sessionmaker(),
            clock=SystemClock(),
            id_generator=Uuid4Generator(),
        ),
        object_storage=storage,
    )


async def _upload(
    storage: FakeStorage,
    classification: str,
    *,
    scope: str = "tenant",
    membership: FakeMembershipLookup | None = None,
) -> httpx.Response:
    token = DevTokenVerifier(SECRET).issue("dev|member", email="member@fpt.com")
    app = create_app(_container(storage, membership))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/api/v1/knowledge/documents",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": str(TENANT),
                    "X-Workspace-Id": str(WORKSPACE),
                },
                data={"title": "Biên bản", "classification": classification, "scope": scope},
                files={"file": ("bien-ban.txt", b"Noi dung.", "text/plain")},
            )


async def test_a_classification_off_the_ladder_is_refused_before_anything_is_staged() -> None:
    storage = FakeStorage()

    response = await _upload(storage, "public")

    assert response.status_code == status_for(ErrorCode.VALIDATION_FAILED)
    assert storage.staged == []


@pytest.mark.parametrize("classification", CLASSIFICATIONS)
async def test_every_rung_of_the_ladder_gets_past_the_check(classification: str) -> None:
    storage = FakeStorage()

    await _upload(storage, classification)

    assert len(storage.staged) == 1


# ------------------------------------------------- a global document (audit 18) --


async def test_a_member_without_the_platform_scope_cannot_publish_a_global_document() -> None:
    """Every tenant reads a global document: a tenant member who may write
    knowledge still may not seed one, and nothing is staged."""
    storage = FakeStorage()

    response = await _upload(storage, "internal", scope="global")

    assert response.status_code == status_for(ErrorCode.PERMISSION_DENIED)
    assert response.json()["details"]["action"] == PLATFORM_ADMIN_SCOPE
    assert storage.staged == []


@pytest.mark.parametrize(
    ("roles", "scopes"),
    [
        (frozenset({"member"}), frozenset({"knowledge.write", PLATFORM_ADMIN_SCOPE})),
        (frozenset({PLATFORM_ADMIN_ROLE}), frozenset({PLATFORM_ADMIN_SCOPE})),
    ],
    ids=["the-scope", "the-role"],
)
async def test_the_platform_scope_check_decides_who_publishes_globally(
    roles: frozenset[str], scopes: frozenset[str]
) -> None:
    """Decided by `authorization.require`, the platform's one answer to "may
    this caller", not by a role string the route keeps: the scope passes it
    without the role (and the role, which the check expands, still does)."""
    storage = FakeStorage()

    await _upload(
        storage, "internal", scope="global", membership=FakeMembershipLookup(roles, scopes)
    )

    assert len(storage.staged) == 1
