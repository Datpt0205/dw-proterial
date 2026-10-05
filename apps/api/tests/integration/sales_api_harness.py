"""The Sales API suite's shared pieces: the app as the composition root builds
it, and a client per persona.

A module of its own rather than `conftest.py`, so test files import it by a
name no other suite uses.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_api.bootstrap import ApiContainer
from dw_api.bootstrap.wiring import build_sales
from dw_api.health import HealthService
from dw_api.main import create_app
from dw_api.settings import ApiSettings
from dw_kernel.ports import SystemClock, Uuid7Generator
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.adapters.persistence.directory import SqlWorkspaceDirectory
from dw_platform.adapters.persistence.idempotency_store import SqlIdempotencyStore
from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup
from dw_platform.adapters.persistence.notifications import SqlNotificationRepository
from dw_platform.adapters.persistence.scope_holders import SqlScopeHolders
from dw_platform.adapters.persistence.uow import SqlPlatformUnitOfWorkFactory
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.entitlement import DEFAULT_PLANS, PlanEntitlementService
from dw_platform.application.idempotency import HttpIdempotency
from dw_platform.application.identity import DbAccessContextFactory
from dw_platform.application.notifications import NotificationService
from dw_platform.testing.seed_env import sid

SECRET = "sales-api-integration-secret-0123456789"
REPO = Path(__file__).resolve().parents[4]
MOCK_DATA = REPO / "packages/python/dw_sales/src/dw_sales/adapters/mock/data"

ALPHA = "tenant-alpha"
BETA = "tenant-beta"

AN = "dev|an.nguyen"  # PIC đơn hàng, export control
DIEU = "dev|dieu.hoang"  # PIC báo giá, other customers' prices, approver_boost
GIANG = "dev|giang.do"  # Trưởng bộ phận
KHOA = "dev|khoa.lam"  # duyệt thay
HA = "dev|ha.vu"  # viewer
TAM = "dev|tam.ngo"  # tenant IT
BINH = "dev|binh.tran"  # purchasing, no sales scope
BAO = "dev|bao.pham"  # tenant-beta PIC


def user_id(subject: str) -> uuid.UUID:
    return sid("user", subject)


class MemoryArtifacts:
    """`ArtifactBytesPort` over a dict, by the key the server derived."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        self.objects[key] = data
        return key

    async def get_object(self, key: str) -> bytes:
        return self.objects[key]


@dataclass
class Persona:
    client: httpx.AsyncClient
    subject: str
    tenant: str = ALPHA
    calls: list[httpx.Response] = field(default_factory=list)

    @property
    def id(self) -> uuid.UUID:
        return user_id(self.subject)

    def headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        token = DevTokenVerifier(SECRET).issue(self.subject)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(sid("tenant", self.tenant)),
            "X-Workspace-Id": str(sid("workspace", f"{self.tenant}:main")),
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def get(self, path: str, **params: Any) -> httpx.Response:
        response = await self.client.get(
            f"/api/v1/sales{path}", params=params or None, headers=self.headers()
        )
        self.calls.append(response)
        return response

    async def post(self, path: str, body: Any = None, *, key: str | None = None) -> httpx.Response:
        response = await self.client.post(
            f"/api/v1/sales{path}",
            content=json.dumps(body if body is not None else {}, default=str),
            headers={
                **self.headers(key or str(uuid.uuid4())),
                "Content-Type": "application/json",
            },
        )
        self.calls.append(response)
        return response

    async def platform(self, path: str) -> httpx.Response:
        response = await self.client.get(f"/api/v1{path}", headers=self.headers())
        self.calls.append(response)
        return response


@dataclass
class Api:
    client: httpx.AsyncClient
    artifacts: MemoryArtifacts
    sessions: async_sessionmaker[AsyncSession]
    app: FastAPI

    def as_(self, subject: str, tenant: str = ALPHA) -> Persona:
        return Persona(self.client, subject, tenant)


@asynccontextmanager
async def build_app(app_url: str) -> AsyncIterator[Api]:
    """The API with the Sales mount the seam builds, over the app role."""
    engine = create_async_engine(app_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings = ApiSettings(profile="test", dev_secret=SECRET, database_url=app_url)
    clock, ids, authz = SystemClock(), Uuid7Generator(), ScopeAuthorizationService()
    artifacts = MemoryArtifacts()
    container = ApiContainer(
        settings=settings,
        engine=engine,
        health_service=HealthService(probes={}),
        token_verifier=DevTokenVerifier(SECRET),
        access_context_factory=DbAccessContextFactory(SqlMembershipLookup(sessions)),
        identity_bootstrap=None,
        uow_factory=SqlPlatformUnitOfWorkFactory(sessions),
        authorization=authz,
        entitlement=PlanEntitlementService(DEFAULT_PLANS),
    )
    container.idempotency = HttpIdempotency(SqlIdempotencyStore(sessions), clock)
    container.workspace_directory = SqlWorkspaceDirectory(sessions)
    container.notifications = NotificationService(SqlNotificationRepository(sessions))
    container.sales = build_sales(
        settings,
        session_factory=sessions,
        clock=clock,
        ids=ids,
        authorization=authz,
        directory=container.workspace_directory,
        holders=SqlScopeHolders(sessions),
        notifications=SqlNotificationRepository(sessions),
        artifact_bytes=artifacts,  # type: ignore[arg-type]
        release_manifest_ref="sha256:" + "0" * 64,
    )
    app = create_app(container)
    try:
        async with (
            LifespanManager(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            yield Api(client, artifacts, sessions, app)
    finally:
        await engine.dispose()


# ------------------------------------------------------------ known prices --


def known_price_strings() -> frozenset[str]:
    """Every price the mock data holds, as the text an API would print it:
    quotation prices, PO unit prices and line amounts, LME figures, and the
    price the quote tests decide. Short or decimal-free figures are left out,
    so a quantity or a lead time never reads as a leak."""
    found: set[str] = set()

    def add(value: object) -> None:
        text = str(value)
        if "." in text and len(text) >= 5:
            found.add(text)
            found.add(str(Decimal(text).normalize()))

    for row in json.loads((MOCK_DATA / "quotations.json").read_text(encoding="utf-8")):
        add(row["unit_price"])
    for row in json.loads((MOCK_DATA / "purchase_orders.json").read_text(encoding="utf-8")):
        for line in row.get("lines", []):
            for name in ("unit_price", "amount"):
                if name in line:
                    add(line[name])
    for row in json.loads((MOCK_DATA / "lme.json").read_text(encoding="utf-8")):
        found.add(str(row["usd_per_tonne"]))
    found.add(DECIDED_PRICE)
    return frozenset(s for s in found if len(s) >= 5)


DECIDED_PRICE = "0.6890"
