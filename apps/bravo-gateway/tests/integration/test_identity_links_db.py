# ruff: noqa: E501 - SQL kept on the lines a reader runs it from
"""Person links and the admin's queue on a migrated PostgreSQL (ticket 64):
one live link per person and per code held by the database, a retired link
freeing its code, and no link of one tenant seen or taken by another.
Requires `make infra-up`."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from pg_test_db import (
    TENANT_A,
    TENANT_B,
    WORKSPACE_A,
    database_urls,
    recreate_database,
    run_alembic,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.persistence.identity_links import SqlIdentityLinks
from dw_sales.application.identity_links import Link

pytestmark = pytest.mark.integration

TEST_DB = "dw_test_identity_links"
NOW = datetime(2026, 11, 21, 3, tzinfo=UTC)


@pytest.fixture(scope="module")
def urls() -> object:
    urls = database_urls(TEST_DB)
    asyncio.run(recreate_database(urls.admin, TEST_DB))
    result = run_alembic(["upgrade", "head"], urls.migrator)
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")

    async def seed() -> None:
        engine = create_async_engine(urls.migrator)
        async with engine.begin() as conn:
            for tenant in (TENANT_A, TENANT_B):
                await conn.execute(
                    sa.text("INSERT INTO platform.tenants (id, slug, name) VALUES (:id, :s, :s)"),
                    {"id": tenant, "s": f"t{tenant.int:x}"},
                )
            await conn.execute(
                sa.text(
                    "INSERT INTO platform.workspaces (id, tenant_id, slug, name) VALUES (:id, :t, 'main', 'Main')"
                ),
                {"id": WORKSPACE_A, "t": TENANT_A},
            )
        await engine.dispose()

    asyncio.run(seed())
    return urls


@pytest.fixture
async def store(urls: object) -> AsyncIterator[SqlIdentityLinks]:
    engine = create_async_engine(urls.app)  # type: ignore[attr-defined]
    yield SqlIdentityLinks(async_sessionmaker(engine, expire_on_commit=False), SqlAuditRepository)
    await engine.dispose()


def _audit(subject: uuid.UUID, tenant: uuid.UUID = TENANT_A) -> AuditEvent:
    return AuditEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(tenant),
        workspace_id=WorkspaceId(WORKSPACE_A),
        actor_id=UserId(uuid.uuid4()),
        action="sales.identity.linked",
        resource_type="person_link",
        resource_id=str(subject),
        occurred_at=NOW,
    )


async def test_one_live_link_per_code_and_a_retired_link_frees_it(store: SqlIdentityLinks) -> None:
    old, new, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    code = f"NV{uuid.uuid4().hex[:6]}"
    await store.save(
        TENANT_A,
        Link(old, code, "employee_id"),
        linked_by=None,
        retire=None,
        at=NOW,
        audit=_audit(old),
    )

    with pytest.raises(ConflictError):
        await store.save(
            TENANT_A,
            Link(other, code, "email"),
            linked_by=None,
            retire=None,
            at=NOW,
            audit=_audit(other),
        )

    await store.queue(TENANT_A, new, "relink_while_old_live", code, NOW)
    await store.queue(TENANT_A, new, "relink_while_old_live", code, NOW)  # one open item
    await store.save(
        TENANT_A,
        Link(new, code, "employee_id"),
        linked_by=None,
        retire=old,
        at=NOW,
        audit=_audit(new),
    )

    live = {link.subject: link.employee_code for link in await store.links(TENANT_A)}
    assert live.get(new) == code and old not in live
    assert all(item[0] != new for item in await store.open_items(TENANT_A))


async def test_another_tenant_neither_sees_nor_takes_a_link(store: SqlIdentityLinks) -> None:
    person = uuid.uuid4()
    code = f"NV{uuid.uuid4().hex[:6]}"
    await store.save(
        TENANT_A,
        Link(person, code, "admin"),
        linked_by=uuid.uuid4(),
        retire=None,
        at=NOW,
        audit=_audit(person),
    )

    assert all(link.subject != person for link in await store.links(TENANT_B))
    # Tenant B may link its own person to the same code: codes are per tenant,
    # and B's link changes nothing of A's.
    intruder = uuid.uuid4()
    await store.save(
        TENANT_B,
        Link(intruder, code, "admin"),
        linked_by=uuid.uuid4(),
        retire=person,
        at=NOW,
        audit=_audit(intruder, TENANT_B),
    )
    assert {link.subject for link in await store.links(TENANT_A) if link.employee_code == code} == {
        person
    }
