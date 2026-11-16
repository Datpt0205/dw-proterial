"""`sales.customer_notations` (migration 99ae8f7eb765, ticket 37) against a
real database, as `dw_app`: a customer's notation kept in one process is read
in the next, with its audit row in the same transaction, replaced only where
it changes, under tenant AND workspace RLS, and every fixed set checked."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sales_harness import World, seed_world
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.ids import UserId
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.adapters.persistence.tenant_session import TenantScope, bind_tenant
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.persistence.customer_notations import SqlCustomerNotations
from dw_sales.application.ports import SalesScope
from dw_sales.domain.customer_notation import NotationEntry

pytestmark = pytest.mark.integration

WHO = uuid.UUID(int=0xA1)
AT = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)
CASE = uuid.UUID(int=7)


@pytest.fixture
async def world(migrator: AsyncEngine) -> World:
    return await seed_world(migrator)


def _ledger(sessions: async_sessionmaker[AsyncSession]) -> SqlCustomerNotations:
    return SqlCustomerNotations(sessions, SqlAuditRepository)


def _learned(value: str = ",", field: str = "quantity") -> NotationEntry:
    return NotationEntry(
        customer_code="VLX",
        kind="decimal_mark",
        value=value,
        source="confirmed",
        case_kind="quote",
        case_id=CASE,
        field=field,
        written="1.200 m",
        confirmed="1200",
        by=WHO,
        at=AT,
    )


def _event(scope: SalesScope, action: str = "sales.customer_notation.learned") -> AuditEvent:
    return AuditEvent(
        id=uuid.uuid4(),
        tenant_id=scope.tenant_id,
        workspace_id=scope.workspace_id,
        actor_id=UserId(WHO),
        action=action,
        resource_type="sales_customer",
        resource_id="VLX",
        occurred_at=AT,
        details={"kind": "decimal_mark"},
    )


async def _audited(migrator: AsyncEngine, scope: SalesScope) -> list[str]:
    async with migrator.connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT action FROM platform.audit_events"
                " WHERE tenant_id = :t AND resource_type = 'sales_customer' ORDER BY occurred_at"
            ),
            {"t": scope.tenant_id.value},
        )
        return [row.action for row in rows]


async def test_a_notation_kept_is_read_in_the_next_process_with_its_audit_row(
    world: World, app_sessions: async_sessionmaker[AsyncSession], migrator: AsyncEngine
) -> None:
    api, worker = _ledger(app_sessions), _ledger(app_sessions)

    assert await api.keep(world.alpha, _learned(), _event(world.alpha))
    # The same value again, from another confirmation: nothing written.
    assert not await api.keep(world.alpha, _learned(field="needed_by"), _event(world.alpha))

    (entry,) = await worker.entries(world.alpha, "VLX")
    assert entry == _learned()
    assert await _audited(migrator, world.alpha) == ["sales.customer_notation.learned"]
    # Another customer reads none of it; nor another workspace of the
    # tenant, nor another tenant.
    assert await worker.entries(world.alpha, "NRV") == []
    assert await worker.entries(world.alpha_other, "VLX") == []
    assert await worker.entries(world.beta, "VLX") == []


async def test_a_person_replaces_and_forgets_the_value(
    world: World, app_sessions: async_sessionmaker[AsyncSession], migrator: AsyncEngine
) -> None:
    ledger = _ledger(app_sessions)
    await ledger.keep(world.alpha, _learned(), _event(world.alpha))
    set_by_hand = NotationEntry(
        customer_code="VLX", kind="decimal_mark", value=".", source="set", by=WHO, at=AT
    )

    assert await ledger.keep(world.alpha, set_by_hand, _event(world.alpha, "sales.x.set"))
    assert await ledger.entries(world.alpha, "VLX") == [set_by_hand]
    # Another tenant's caller forgets nothing of it.
    assert not await ledger.forget(world.beta, "VLX", "decimal_mark", _event(world.beta))
    assert await ledger.forget(world.alpha, "VLX", "decimal_mark", _event(world.alpha, "sales.x.f"))
    assert await ledger.entries(world.alpha, "VLX") == []
    assert await _audited(migrator, world.alpha) == [
        "sales.customer_notation.learned",
        "sales.x.set",
        "sales.x.f",
    ]
    assert await _audited(migrator, world.beta) == []


@pytest.mark.parametrize(
    ("change", "constraint"),
    [
        ("value = 'USD'", "ck_customer_notations_value"),
        ("kind = 'thousands'", "ck_customer_notations_kind"),
        ("kind = 'dollar_sign', value = 'JPY'", "ck_customer_notations_value"),
        # Outside both sets, and so outside the evidence's two shapes too.
        ("source = 'guessed'", "ck_customer_notations_(source|evidence)"),
        ("source = 'set'", "ck_customer_notations_evidence"),
        ("written = NULL", "ck_customer_notations_evidence"),
        ("confirmed = NULL", "ck_customer_notations_evidence"),
        ("field = NULL", "ck_customer_notations_evidence"),
        ("case_kind = 'invoice'", "ck_customer_notations_case_kind"),
        ("customer_code = 'vlx'", "ck_customer_notations_customer_code"),
    ],
)
async def test_every_fixed_set_and_the_evidence_are_checked(
    world: World,
    app_sessions: async_sessionmaker[AsyncSession],
    change: str,
    constraint: str,
) -> None:
    await _ledger(app_sessions).keep(world.alpha, _learned(), _event(world.alpha))
    scope = TenantScope(
        tenant_id=world.alpha.tenant_id.value, workspace_id=world.alpha.workspace_id.value
    )
    async with app_sessions() as session, session.begin():
        await bind_tenant(session, scope)
        with pytest.raises(DBAPIError, match=constraint):
            await session.execute(sa.text(f"UPDATE sales.customer_notations SET {change}"))


async def test_a_row_for_another_tenant_cannot_be_written(
    world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    scope = TenantScope(
        tenant_id=world.alpha.tenant_id.value, workspace_id=world.alpha.workspace_id.value
    )
    async with app_sessions() as session, session.begin():
        await bind_tenant(session, scope)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                sa.text(
                    "INSERT INTO sales.customer_notations (tenant_id, workspace_id,"
                    " customer_code, kind, value, source, decided_by, decided_at)"
                    " VALUES (:t, :w, 'VLX', 'decimal_mark', ',', 'set', :by, now())"
                ),
                {
                    "t": world.beta.tenant_id.value,
                    "w": world.beta.workspace_id.value,
                    "by": WHO,
                },
            )
