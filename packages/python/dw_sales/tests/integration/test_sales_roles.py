"""DW1's roles and permission sets in the platform catalogue (migration
68305ebe4a83, dw_sales ADR 0003)."""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.application.access import SUPPORT_SCOPES

pytestmark = pytest.mark.integration

# The platform's own rungs, and the two catalogue rows that are not a rung.
_GENERIC = ("member", "approver", "manager", "director", "executive", "org_admin")
_RULE = "sod_sales_price_vs_member_admin"


async def _scopes(engine: AsyncEngine, table: str) -> dict[str, set[str]]:
    async with engine.connect() as conn:
        rows = await conn.execute(sa.text(f"SELECT key, scopes FROM platform.{table}"))
        return {row.key: set(row.scopes) for row in rows}


async def test_no_sales_scope_sits_on_a_platform_role(migrator: AsyncEngine) -> None:
    """A purchasing manager must not approve a quotation, nor a member read
    every price: Sales authority is the context's own roles."""
    roles = await _scopes(migrator, "roles")
    permission_sets = await _scopes(migrator, "permission_sets")
    assert set(_GENERIC) <= set(roles)
    leaking = {
        key: sorted(scope for scope in roles[key] if scope.startswith("sales."))
        for key in (*_GENERIC, "platform_admin")
    }
    assert leaking == {key: [] for key in leaking}
    assert not [s for s in permission_sets["approver_boost"] if s.startswith("sales.")]


async def test_the_sales_roles_are_the_spec_actor_table(migrator: AsyncEngine) -> None:
    roles = await _scopes(migrator, "roles")
    permission_sets = await _scopes(migrator, "permission_sets")
    pic, head = roles["sales_pic"], roles["sales_head"]
    assert head - pic == {
        "sales.price.other_customers.read",
        "sales.quote.approve",
        "sales.worker.resume",
        # Raises an order's cross-check again for its Bravo recorder (58184771c541).
        "sales.order.resend_cross_check",
        # Gives a case to another member (934101cde272).
        "sales.case.assign",
        # Grants FPT support Sales' set, and decides support requests
        # (7c8ba908575f, ticket 22).
        "support.grant",
        # Decides a PO layout a PIC mapped (63242ec52c4b, ticket 30).
        "sales.layout.approve",
        # Approves or rejects a tenant's own rule version (57a241ea182b, ticket 19).
        "sales.rules.approve",
    }
    assert pic <= head
    # Both decide a Sales request (cross-check, quote approval), so both carry
    # the platform's decide right (ac31ff0f2087).
    assert "approvals.decide" in pic and "approvals.decide" in head
    assert "sales.quote.approve" not in pic and "sales.worker.resume" not in pic
    assert "sales.order.resend_cross_check" not in pic
    assert "sales.case.assign" not in pic
    assert "sales.layout.approve" not in pic
    # Both propose a version of a Sales rule; only the head decides one.
    assert "sales.rules.propose" in pic and "sales.rules.approve" not in pic
    assert roles["sales_viewer"] == {"sales.overview.read"}
    # DW1's service account (af154486381e): it processes the mailbox and
    # nothing else; it decides nothing, so not `approvals.decide` either.
    assert roles["sales_dw1"] == {"sales.inbox.process"}
    assert permission_sets["sales_price_evidence"] == {"sales.price.other_customers.read"}
    # `approvals.decide` too since ac31ff0f2087: the platform asks every
    # decider for it besides the request's stamp (docs/adr/0011).
    assert permission_sets["sales_quote_approver"] == {"sales.quote.approve", "approvals.decide"}
    assert permission_sets["sales_export_control"] == {"sales.compliance.ack"}
    async with migrator.connect() as conn:
        name = await conn.scalar(
            sa.text("SELECT name FROM platform.roles WHERE key = 'sales_head'")
        )
    assert name == "Trưởng bộ phận Sales"


async def test_only_the_sales_head_may_grant_support_access(migrator: AsyncEngine) -> None:
    """dw_sales ADR 0003 §5: the head grants Sales' support set. A granter
    must hold `support.grant` and every scope of the set (ADR 0024), and no
    other catalogue row carries `support.grant`, so nobody else can issue it."""
    roles = await _scopes(migrator, "roles")
    permission_sets = await _scopes(migrator, "permission_sets")
    assert {key for key, scopes in roles.items() if "support.grant" in scopes} == {"sales_head"}
    assert {key for key, scopes in permission_sets.items() if "support.grant" in scopes} == set()
    assert roles["sales_head"] >= SUPPORT_SCOPES


async def _grant(
    sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    world: World,
    roles: list[str],
    permission_sets: list[str],
) -> None:
    """A membership in alpha's workspace for a new fictional user, as dw_app."""
    user_id = uuid.uuid4()
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO platform.users (id, subject, display_name)"
                " VALUES (:u, :s, 'Ngô Tâm (giả lập)')"
            ),
            {"u": user_id, "s": f"dev|probe.{user_id.hex[:8]}"},
        )
    scope = TenantScope(world.alpha.tenant_id.value, world.alpha.workspace_id.value)
    async with tenant_session(sessions, scope) as session:
        await session.execute(
            sa.text(
                "INSERT INTO platform.memberships"
                " (id, tenant_id, workspace_id, user_id, role_keys, permission_set_keys)"
                " VALUES (gen_random_uuid(), :t, :w, :u,"
                " CAST(:roles AS jsonb), CAST(:sets AS jsonb))"
            ),
            {
                "t": scope.tenant_id,
                "w": scope.workspace_id,
                "u": user_id,
                "roles": json.dumps(roles),
                "sets": json.dumps(permission_sets),
            },
        )


@pytest.mark.parametrize(
    ("roles", "permission_sets"),
    [
        (["org_admin", "sales_pic"], []),  # dev|tam.ngo given sales_pic
        (["org_admin", "sales_head"], []),
    ],
)
async def test_it_cannot_also_hold_a_price_scope(
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    world: World,
    roles: list[str],
    permission_sets: list[str],
) -> None:
    with pytest.raises(IntegrityError) as refused:
        await _grant(app_sessions, migrator, world, roles, permission_sets)
    cause = getattr(refused.value.orig, "__cause__", None)
    assert getattr(cause, "constraint_name", None) == _RULE


@pytest.mark.parametrize(
    ("roles", "permission_sets"),
    [
        (["sales_pic"], ["sales_price_evidence", "sales_export_control"]),
        (["sales_pic"], ["sales_quote_approver"]),
        # The viewer sees counts and times, never a price.
        (["org_admin", "sales_viewer"], []),
    ],
)
async def test_the_spec_personas_combinations_are_allowed(
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    world: World,
    roles: list[str],
    permission_sets: list[str],
) -> None:
    await _grant(app_sessions, migrator, world, roles, permission_sets)


async def test_the_rule_is_not_waivable(migrator: AsyncEngine) -> None:
    async with migrator.connect() as conn:
        waivable = await conn.scalar(
            sa.text("SELECT waivable FROM platform.sod_rules WHERE key = :k"), {"k": _RULE}
        )
    assert waivable is False
