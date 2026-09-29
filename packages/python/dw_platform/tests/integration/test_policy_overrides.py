"""Integration: `platform.policy_overrides` under RLS.

The write half of `TenantOverlay`'s own "a policy" artifact kind — see
migration `45dc1b5e0125`'s docstring. Round-trip, upsert-overwrites, RLS
isolation and the audit trail landing in the SAME transaction are what a
real database proves that a handler test with a fake repository cannot.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.policy_overrides import SqlPolicyOverrideRepository
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_platform.testing.seed_env import seed_test_env

pytestmark = pytest.mark.integration

# Seeded tenant-alpha/tenant-beta (uuid5, matches dw_platform.testing.seed_env)
# — a real row is required: policy_overrides.tenant_id has an FK to tenants.
ALPHA = uuid.UUID("d6b43d0e-c3c6-5dbc-bc08-150621bd9a5d")
ALPHA_WS = uuid.UUID("64764894-718d-5558-ba17-9a2949214063")
BETA = uuid.UUID("6634f09a-d1d7-54a6-aa23-f3f018f41f28")
BETA_WS = uuid.UUID("eda6af16-a0c4-55d3-be0b-163414390572")


@pytest.fixture
async def sessions(db_urls: DatabaseUrls) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    await seed_test_env(db_urls.migrator)
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


def _context(*, tenant: uuid.UUID = ALPHA, workspace: uuid.UUID = ALPHA_WS) -> AccessContext:
    return AccessContext(
        tenant_id=tenant,
        workspace_id=workspace,
        principal_id=uuid.uuid4(),
        roles=frozenset({"member"}),
        scopes=frozenset(),
        plan_id="professional",
    )


def _audit(context: AccessContext, *, action: str = "test.override_set") -> AuditEvent:
    return AuditEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action=action,
        resource_type="sla_policy",
        resource_id="example_sla",
        occurred_at=datetime.now(UTC),
    )


async def test_get_returns_none_when_no_override_exists(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlPolicyOverrideRepository(sessions)
    assert await repo.get(_context(), "example_sla") is None


async def test_put_then_get_round_trips(sessions: async_sessionmaker[AsyncSession]) -> None:
    repo = SqlPolicyOverrideRepository(sessions)
    context = _context()
    content = {
        "schema_version": "1.0",
        "policy_id": "example_sla",
        "sla": {"deposit": {"duration": "7d"}},
    }

    await repo.put(context, "example_sla", content, audit=_audit(context))
    fetched = await repo.get(context, "example_sla")

    assert fetched == content


async def test_a_second_put_overwrites_rather_than_duplicates(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlPolicyOverrideRepository(sessions)
    context = _context()
    await repo.put(context, "example_sla", {"version": 1}, audit=_audit(context))
    await repo.put(context, "example_sla", {"version": 2}, audit=_audit(context))

    fetched = await repo.get(context, "example_sla")
    assert fetched == {"version": 2}

    async with sessions() as session, session.begin():
        # RLS applies here too (no app.tenant_id, no visible rows at all) —
        # bind the same tenant this test owns before counting.
        await session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(context.tenant_id)}
        )
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM platform.policy_overrides"
                    " WHERE tenant_id = :t AND policy_id = 'example_sla'"
                ),
                {"t": str(context.tenant_id)},
            )
        ).scalar_one()
    assert count == 1


async def test_different_policy_ids_do_not_collide(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlPolicyOverrideRepository(sessions)
    context = _context()
    await repo.put(context, "example_sla", {"which": "sla"}, audit=_audit(context))
    await repo.put(context, "retention", {"which": "retention"}, audit=_audit(context))

    assert await repo.get(context, "example_sla") == {"which": "sla"}
    assert await repo.get(context, "retention") == {"which": "retention"}


async def test_another_tenant_neither_sees_nor_overwrites_the_override(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlPolicyOverrideRepository(sessions)
    alpha_context = _context(tenant=ALPHA, workspace=ALPHA_WS)
    beta_context = _context(tenant=BETA, workspace=BETA_WS)
    await repo.put(alpha_context, "example_sla", {"tenant": "alpha"}, audit=_audit(alpha_context))

    seen_by_beta = await repo.get(beta_context, "example_sla")
    assert seen_by_beta is None

    # Beta "overwriting" actually creates ITS OWN row — never touches Alpha's.
    await repo.put(beta_context, "example_sla", {"tenant": "beta"}, audit=_audit(beta_context))
    alpha_again = await repo.get(alpha_context, "example_sla")
    beta_again = await repo.get(beta_context, "example_sla")
    assert alpha_again == {"tenant": "alpha"}
    assert beta_again == {"tenant": "beta"}


async def test_rls_hides_the_row_even_from_a_query_with_no_tenant_filter(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The repository's own queries never name `tenant_id` at all (see
    `policy_overrides.py`'s docstring) — this test does not go through it,
    on purpose. It proves the database itself refuses the row under
    `app.tenant_id=BETA`, independent of anything the repository does or
    does not filter by."""
    # A policy_id used nowhere else in this file: the test database is
    # session-scoped and shared across every test function here (nothing
    # truncates between them), so a shared id like "example_sla" would
    # pick up another test's own legitimately-visible row for BETA and this
    # check would prove nothing.
    policy_id = "rls_hides_no_filter_check"
    repo = SqlPolicyOverrideRepository(sessions)
    context = _context(tenant=ALPHA, workspace=ALPHA_WS)
    await repo.put(context, policy_id, {"tenant": "alpha"}, audit=_audit(context))

    async with sessions() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(BETA)}
        )
        rows = (
            await session.execute(
                text("SELECT id FROM platform.policy_overrides WHERE policy_id = :p"),
                {"p": policy_id},
            )
        ).all()

    assert rows == []


async def test_the_audit_event_lands_in_the_same_transaction_as_the_write(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlPolicyOverrideRepository(sessions)
    context = _context()
    audit = _audit(context, action="test.override_lands_with_write")

    await repo.put(context, "example_sla", {"tenant": "alpha"}, audit=audit)

    async with sessions() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(context.tenant_id)}
        )
        row = (
            await session.execute(
                sa.select(tables.audit_events.c.action, tables.audit_events.c.resource_id).where(
                    tables.audit_events.c.id == audit.id
                )
            )
        ).first()

    assert row is not None
    assert row.action == "test.override_lands_with_write"
    assert row.resource_id == "example_sla"
