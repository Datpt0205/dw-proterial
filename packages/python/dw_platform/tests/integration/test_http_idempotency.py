"""Integration: the HTTP idempotency store against real Postgres, as dw_app.

The unit tests prove the decision. This proves the storage the decision rests
on, against the role and the policies that will actually be in force:

* a replay returns the stored response;
* a key reused for a different request is refused;
* two tenants may spend the same key string without meeting;
* a reservation abandoned by a dead process can be taken over;
* the application role can use the table with no GRANT written for it — the
  baseline's ``ALTER DEFAULT PRIVILEGES`` carries, which is exactly the claim
  migration 0002 relies on by writing none.

Connecting as ``dw_app`` rather than the migrator is the point: the migrator
holds BYPASSRLS and would prove nothing about either privileges or isolation.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from dw_kernel.errors import ConflictError, IdempotencyConflictError
from dw_kernel.ports import SystemClock
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.idempotency_store import SqlIdempotencyStore
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_platform.application.idempotency import (
    STALE_RESERVATION,
    HttpIdempotency,
    RequestFingerprint,
    StoredResponse,
)

pytestmark = pytest.mark.integration

TENANT_ONE = uuid.UUID(int=0x1DE0)
WORKSPACE_ONE = uuid.UUID(int=0x1DE1)
TENANT_TWO = uuid.UUID(int=0x1DF0)
WORKSPACE_TWO = uuid.UUID(int=0x1DF1)

# Long enough that "now minus this" is unambiguously older than the stale
# cutoff, without the test having to know the cutoff's exact value.
BACKDATE = STALE_RESERVATION * 2


def context_for(tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> AccessContext:
    return AccessContext(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        principal_id=uuid.uuid4(),
        roles=frozenset({"org_admin"}),
        plan_id="professional",
    )


def fingerprint(
    *, body: bytes = b'{"approve":true}', workspace_id: uuid.UUID = WORKSPACE_ONE
) -> RequestFingerprint:
    return RequestFingerprint.of(
        method="POST",
        path="/api/v1/approvals/decisions",
        workspace_id=workspace_id,
        body=body,
    )


@pytest.fixture
async def app_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def sessions(app_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Tenant + workspace rows to hang the foreign key on, created as dw_app."""
    factory = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    for tenant_id, workspace_id, slug in (
        (TENANT_ONE, WORKSPACE_ONE, "idem-tenant-one"),
        (TENANT_TWO, WORKSPACE_TWO, "idem-tenant-two"),
    ):
        async with tenant_session(factory, TenantScope(tenant_id=tenant_id)) as session:
            await session.execute(
                sa.text(
                    "INSERT INTO platform.tenants (id, slug, name) VALUES (:id, :slug, :slug) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": str(tenant_id), "slug": slug},
            )
            await session.execute(
                sa.text(
                    "INSERT INTO platform.workspaces (id, tenant_id, slug, name) "
                    "VALUES (:id, :tenant, 'main', 'Main') ON CONFLICT (id) DO NOTHING"
                ),
                {"id": str(workspace_id), "tenant": str(tenant_id)},
            )
    return factory


@pytest.fixture
def idempotency(sessions: async_sessionmaker[AsyncSession]) -> HttpIdempotency:
    return HttpIdempotency(store=SqlIdempotencyStore(sessions), clock=SystemClock())


async def backdate(
    sessions: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, key: str
) -> None:
    """Age a reservation past the takeover cutoff, as a dead process would."""
    async with tenant_session(sessions, TenantScope(tenant_id=tenant_id)) as session:
        await session.execute(
            sa.update(tables.idempotency_keys)
            .where(
                tables.idempotency_keys.c.tenant_id == tenant_id,
                tables.idempotency_keys.c.idempotency_key == key,
            )
            .values(created_at=sa.func.now() - BACKDATE)
        )


async def test_a_replay_returns_the_stored_response(idempotency: HttpIdempotency) -> None:
    context = context_for(TENANT_ONE, WORKSPACE_ONE)
    key = "replay-me"
    body: dict[str, object] = {"id": "abc", "status": "approved"}

    assert await idempotency.claim(context, key=key, fingerprint=fingerprint()) is None
    await idempotency.complete(
        context, key=key, response=StoredResponse(status_code=200, body=body)
    )

    replayed = await idempotency.claim(context, key=key, fingerprint=fingerprint())
    assert replayed is not None
    assert replayed.status_code == 200
    assert replayed.body == body


async def test_the_same_key_on_a_different_request_is_refused(
    idempotency: HttpIdempotency,
) -> None:
    context = context_for(TENANT_ONE, WORKSPACE_ONE)
    key = "mismatched"

    await idempotency.claim(context, key=key, fingerprint=fingerprint(body=b'{"approve":true}'))

    with pytest.raises(IdempotencyConflictError):
        await idempotency.claim(
            context, key=key, fingerprint=fingerprint(body=b'{"approve":false}')
        )


async def test_a_second_request_while_the_first_is_in_flight_is_refused(
    idempotency: HttpIdempotency,
) -> None:
    """The reservation is committed before the handler runs, so it is visible."""
    context = context_for(TENANT_ONE, WORKSPACE_ONE)
    key = "in-flight"

    assert await idempotency.claim(context, key=key, fingerprint=fingerprint()) is None
    with pytest.raises(ConflictError) as excinfo:
        await idempotency.claim(context, key=key, fingerprint=fingerprint())
    assert not isinstance(excinfo.value, IdempotencyConflictError), "in flight, not a mismatch"


async def test_an_abandoned_reservation_can_be_taken_over(
    idempotency: HttpIdempotency, sessions: async_sessionmaker[AsyncSession]
) -> None:
    context = context_for(TENANT_ONE, WORKSPACE_ONE)
    key = "abandoned"

    await idempotency.claim(context, key=key, fingerprint=fingerprint())
    await backdate(sessions, TENANT_ONE, key)

    assert await idempotency.claim(context, key=key, fingerprint=fingerprint()) is None


async def test_releasing_lets_the_key_be_spent_again(idempotency: HttpIdempotency) -> None:
    context = context_for(TENANT_ONE, WORKSPACE_ONE)
    key = "released"

    await idempotency.claim(context, key=key, fingerprint=fingerprint())
    await idempotency.release(context, key=key)

    assert await idempotency.claim(context, key=key, fingerprint=fingerprint()) is None


async def test_two_tenants_may_spend_the_same_key_string(idempotency: HttpIdempotency) -> None:
    """The primary key is (tenant, key). Clients choose keys without coordinating."""
    key = "1"
    one = context_for(TENANT_ONE, WORKSPACE_ONE)
    two = context_for(TENANT_TWO, WORKSPACE_TWO)

    assert await idempotency.claim(one, key=key, fingerprint=fingerprint()) is None
    assert (
        await idempotency.claim(two, key=key, fingerprint=fingerprint(workspace_id=WORKSPACE_TWO))
        is None
    ), "tenant two's identical key must not collide with tenant one's"


async def test_one_tenant_cannot_see_another_tenants_keys(
    idempotency: HttpIdempotency, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """RLS, not the query, is what keeps the rows apart."""
    key = "isolated"
    await idempotency.claim(
        context_for(TENANT_ONE, WORKSPACE_ONE), key=key, fingerprint=fingerprint()
    )

    async with tenant_session(sessions, TenantScope(tenant_id=TENANT_TWO)) as session:
        rows = (
            await session.execute(
                sa.select(tables.idempotency_keys.c.tenant_id).where(
                    tables.idempotency_keys.c.idempotency_key == key
                )
            )
        ).all()
    assert rows == []
