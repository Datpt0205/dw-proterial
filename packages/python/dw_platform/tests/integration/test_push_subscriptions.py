"""Integration: Web Push subscriptions (migration 4bcfa82060fc, Sales ticket
48), as `dw_app`.

A device is one person's, in one workspace: a push meant for someone reads
their devices and nobody else's, in this tenant or another. A row comes in
through `platform.save_push_subscription` alone, which reads who from the
bound session and refuses someone who is not a member; a device that signs
in as another person moves to them. Sales' reminder marks sit beside it:
one person's own, and a customer's term can only be marked done.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_platform.adapters.persistence.identity_provisioning import SqlIdentityBootstrap
from dw_platform.adapters.persistence.notifications import SqlNotificationRepository
from dw_platform.adapters.persistence.push_subscriptions import (
    SqlPushSubscriptionRetention,
    SqlPushSubscriptions,
)
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_platform.testing.seed_env import seed_test_env

pytestmark = pytest.mark.integration

ALPHA = uuid.UUID("d6b43d0e-c3c6-5dbc-bc08-150621bd9a5d")
ALPHA_WS = uuid.UUID("64764894-718d-5558-ba17-9a2949214063")
BETA = uuid.UUID("6634f09a-d1d7-54a6-aa23-f3f018f41f28")
BETA_WS = uuid.UUID("eda6af16-a0c4-55d3-be0b-163414390572")
P256DH = "B" + "A" * 86
AUTH = "A" * 22


@dataclass(frozen=True)
class _Identity:
    subject: str
    email: str | None
    issuer: str = "https://issuer.test/realms/dw"
    name: str | None = None
    auth_methods: frozenset[str] = frozenset()
    acr: str | None = None


@pytest.fixture
async def app_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    await seed_test_env(db_urls.migrator)
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def migrator_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.migrator, poolclass=NullPool)
    yield engine
    await engine.dispose()


async def _member(engine: AsyncEngine, tenant: uuid.UUID = ALPHA) -> AccessContext:
    workspace = ALPHA_WS if tenant == ALPHA else BETA_WS
    view = await SqlIdentityBootstrap(
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        default_tenant_id=tenant,
        default_workspace_id=workspace,
        auto_provision_default_membership=True,
    ).bootstrap(_Identity(subject=f"sub-{uuid.uuid4()}", email=f"{uuid.uuid4().hex[:8]}@p.test"))
    return AccessContext(
        tenant_id=tenant,
        workspace_id=workspace,
        principal_id=view.principal_id,
        roles=frozenset({"member"}),
        scopes=frozenset(),
        plan_id="professional",
    )


def _store(engine: AsyncEngine) -> SqlPushSubscriptions:
    return SqlPushSubscriptions(async_sessionmaker(engine, expire_on_commit=False))


def _endpoint() -> str:
    return f"https://web.push.apple.com/3/device/{uuid.uuid4().hex}"


async def _save(engine: AsyncEngine, who: AccessContext, endpoint: str) -> None:
    await _store(engine).save(who, endpoint=endpoint, p256dh=P256DH, auth=AUTH)


async def _endpoints(engine: AsyncEngine, who: AccessContext) -> list[str]:
    found = await _store(engine).of_member(who.tenant_id, who.workspace_id, who.principal_id)
    return [s.endpoint for s in found]


async def test_a_push_meant_for_one_person_reads_their_devices_alone(
    app_engine: AsyncEngine,
) -> None:
    """Acceptance 3 at the table: An's device; Bình's in the same workspace
    and Chi's in another tenant are never read for An."""
    an, binh = await _member(app_engine), await _member(app_engine)
    chi = await _member(app_engine, BETA)
    mine, theirs, elsewhere = _endpoint(), _endpoint(), _endpoint()
    await _save(app_engine, an, mine)
    await _save(app_engine, binh, theirs)
    await _save(app_engine, chi, elsewhere)
    assert await _endpoints(app_engine, an) == [mine]
    assert await _endpoints(app_engine, binh) == [theirs]
    # An's ids under another tenant's binding read nothing.
    other = await _store(app_engine).of_member(BETA, BETA_WS, an.principal_id)
    assert other == []
    # Bound as An, the table holds only An's row, whatever is asked.
    async with tenant_session(
        async_sessionmaker(app_engine), TenantScope.from_access_context(an)
    ) as session:
        seen = (
            await session.execute(sa.text("SELECT endpoint FROM platform.push_subscriptions"))
        ).scalars()
        assert list(seen) == [mine]


async def test_saving_again_renews_and_a_moved_device_follows_its_new_person(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    an, binh = await _member(app_engine), await _member(app_engine)
    endpoint = _endpoint()
    await _save(app_engine, an, endpoint)
    await _save(app_engine, an, endpoint)
    assert await _endpoints(app_engine, an) == [endpoint]
    # The same phone signs in as Bình: it is Bình's now, not both.
    await _save(app_engine, binh, endpoint)
    assert await _endpoints(app_engine, an) == []
    assert await _endpoints(app_engine, binh) == [endpoint]
    async with migrator_engine.connect() as conn:
        held = await conn.scalar(
            sa.text("SELECT count(*) FROM platform.push_subscriptions WHERE endpoint = :e"),
            {"e": endpoint},
        )
    assert held == 1


async def test_someone_outside_the_workspace_cannot_subscribe_there(
    app_engine: AsyncEngine,
) -> None:
    chi = await _member(app_engine, BETA)
    stranger = AccessContext(
        tenant_id=ALPHA,
        workspace_id=ALPHA_WS,
        principal_id=chi.principal_id,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="professional",
    )
    with pytest.raises(DBAPIError, match="member"):
        await _save(app_engine, stranger, _endpoint())


async def test_the_application_cannot_write_a_row_around_the_door(
    app_engine: AsyncEngine,
) -> None:
    an = await _member(app_engine)
    async with tenant_session(
        async_sessionmaker(app_engine), TenantScope.from_access_context(an)
    ) as session:
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(
                sa.text(
                    "INSERT INTO platform.push_subscriptions"
                    " (id, tenant_id, workspace_id, user_id, endpoint, p256dh, auth)"
                    " VALUES (gen_random_uuid(), :t, :w, :u, :e, :p, :a)"
                ),
                {
                    "t": an.tenant_id,
                    "w": an.workspace_id,
                    "u": an.principal_id,
                    "e": _endpoint(),
                    "p": P256DH,
                    "a": AUTH,
                },
            )


async def test_a_person_turns_their_own_off_and_a_gone_one_is_dropped(
    app_engine: AsyncEngine,
) -> None:
    an, binh = await _member(app_engine), await _member(app_engine)
    first, second = _endpoint(), _endpoint()
    await _save(app_engine, an, first)
    await _save(app_engine, an, second)
    store = _store(app_engine)
    # Bình cannot turn An's off.
    assert await store.remove(binh, first) is False
    assert await store.remove(an, first) is True
    (left,) = await store.of_member(an.tenant_id, an.workspace_id, an.principal_id)
    await store.drop(an.tenant_id, an.workspace_id, an.principal_id, left.id)
    assert await _endpoints(app_engine, an) == []


async def test_a_subscription_not_renewed_for_ninety_days_goes(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    an = await _member(app_engine)
    stale, fresh = _endpoint(), _endpoint()
    await _save(app_engine, an, stale)
    await _save(app_engine, an, fresh)
    async with migrator_engine.begin() as conn:
        await conn.execute(
            sa.text(
                "UPDATE platform.push_subscriptions SET updated_at = now() - interval '91 days'"
                " WHERE endpoint = :e"
            ),
            {"e": stale},
        )
    await SqlPushSubscriptionRetention(async_sessionmaker(app_engine)).prune()
    assert await _endpoints(app_engine, an) == [fresh]


# ------------------------------------------------- Sales' reminder marks --


async def _notice(engine: AsyncEngine, to: AccessContext) -> uuid.UUID:
    key = f"sales.followup:{to.workspace_id}:waiting_pc:remind:{uuid.uuid4()}:x"
    repo = SqlNotificationRepository(async_sessionmaker(engine, expire_on_commit=False))
    await repo.deliver(
        to, recipients=[to.principal_id], source_key=key, title="Nhắc", body="", link=None
    )
    (found,) = await repo.sourced(to, prefix=key, since=datetime(2000, 1, 1, tzinfo=UTC), limit=5)
    return found.id


async def _mark(
    engine: AsyncEngine, who: AccessContext, notification: uuid.UUID, followup: str, mark: str
) -> None:
    async with tenant_session(
        async_sessionmaker(engine), TenantScope.from_access_context(who)
    ) as session:
        await session.execute(
            sa.text(
                "INSERT INTO sales.reminder_marks (notification_id, user_id, tenant_id,"
                " workspace_id, followup, mark, until, marked_at)"
                " VALUES (:n, :u, :t, :w, :f, :m, CASE WHEN :m = 'snoozed'"
                " THEN now() + interval '1 hour' END, now())"
            ),
            {
                "n": notification,
                "u": who.principal_id,
                "t": who.tenant_id,
                "w": who.workspace_id,
                "f": followup,
                "m": mark,
            },
        )


async def test_a_customers_term_is_marked_done_or_not_at_all(app_engine: AsyncEngine) -> None:
    an = await _member(app_engine)
    for followup in ("quote_deadline", "implied_acceptance"):
        for mark in ("dismissed", "snoozed"):
            notification = await _notice(app_engine, an)
            with pytest.raises(DBAPIError, match="ck_reminder_marks_customer_term"):
                await _mark(app_engine, an, notification, followup, mark)
    await _mark(app_engine, an, await _notice(app_engine, an), "quote_deadline", "done")
    await _mark(app_engine, an, await _notice(app_engine, an), "waiting_pc", "dismissed")


async def test_one_persons_marks_are_theirs_alone(app_engine: AsyncEngine) -> None:
    an, binh = await _member(app_engine), await _member(app_engine)
    notification = await _notice(app_engine, an)
    # Bình cannot write a mark as An.
    impostor = AccessContext(
        tenant_id=binh.tenant_id,
        workspace_id=binh.workspace_id,
        principal_id=binh.principal_id,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="professional",
    )
    async with tenant_session(
        async_sessionmaker(app_engine), TenantScope.from_access_context(impostor)
    ) as session:
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                sa.text(
                    "INSERT INTO sales.reminder_marks (notification_id, user_id, tenant_id,"
                    " workspace_id, followup, mark, marked_at)"
                    " VALUES (:n, :u, :t, :w, 'waiting_pc', 'done', now())"
                ),
                {
                    "n": notification,
                    "u": an.principal_id,
                    "t": an.tenant_id,
                    "w": an.workspace_id,
                },
            )
    await _mark(app_engine, an, notification, "waiting_pc", "done")
    async with tenant_session(
        async_sessionmaker(app_engine), TenantScope.from_access_context(binh)
    ) as session:
        seen = await session.scalar(sa.text("SELECT count(*) FROM sales.reminder_marks"))
    assert seen == 0
