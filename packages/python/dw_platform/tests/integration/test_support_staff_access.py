# ruff: noqa: F811  (`provisioner_engine` is a fixture imported from test_provisioning)
"""Integration: the staff side of support access (ADR 0024, ticket 02).

SA12: the two `SECURITY DEFINER` functions return only the caller's grants,
the person being the transaction's `app.principal_id`, never a parameter, and
`PUBLIC` may not run them. SA4/SA10 end to end: a staff member's context from
a real grant, and its `support.access` row on the customer's trail.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from support_world import SupportWorld, build_world, context_of, grant_service, provisioning
from test_provisioning import provisioner_engine  # noqa: F401  (a fixture, used by name)

from dw_kernel.errors import NotFoundError, PermissionDeniedError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.pagination import PageQuery, PageRequest
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.persistence.scope_holders import SqlScopeHolders
from dw_platform.adapters.persistence.support_grants import SqlStaffGrants
from dw_platform.adapters.persistence.uow import SqlPlatformUnitOfWorkFactory
from dw_platform.application.support_access import (
    RequestSupportGrant,
    SupportAccessContextFactory,
)
from dw_platform.domain.audit import (
    SUPPORT_GRANT_DETAIL,
    AuditActorKind,
    AuditEvent,
    lane_audit_event,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
OTP = frozenset({"pwd", "otp"})


@pytest.fixture
async def migrator(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.migrator, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def world(migrator: AsyncEngine) -> SupportWorld:
    return await build_world(migrator)


async def _active_grant(
    w: SupportWorld, app_engine: AsyncEngine, provisioner_engine: AsyncEngine
) -> uuid.UUID:
    """A grant the granter of ws1 asked for and the operator assigned to
    `staff`: its trail already holds `support.grant.requested` and
    `support.grant.assigned`."""
    clock = FixedClock(NOW)
    granter = await context_of(app_engine, w, "granter", w.tenant_a, w.ws1)
    view = await grant_service(app_engine, clock).request(
        granter,
        RequestSupportGrant(
            scope_set_key="probe.read",
            resource_type="workspace",
            resource_id=None,
            reason="the parser misread page 3",
            duration_hours=72,
        ),
    )
    ops = provisioning(provisioner_engine, clock)
    await ops.add_support_staff(w.operator, email=w.email("staff"), note=None)
    await ops.add_support_staff(w.operator, email=w.email("other_staff"), note=None)
    await ops.assign_support_request(
        w.operator, grant_id=view.grant.id, staff_user_id=w.users["staff"]
    )
    return view.grant.id


def _staff(app_engine: AsyncEngine) -> SqlStaffGrants:
    return SqlStaffGrants(async_sessionmaker(app_engine, expire_on_commit=False))


async def test_sa12_a_grant_is_readable_only_by_its_staff_member(
    world: SupportWorld, app_engine: AsyncEngine, provisioner_engine: AsyncEngine
) -> None:
    grant_id = await _active_grant(world, app_engine, provisioner_engine)
    staff = _staff(app_engine)

    mine = await staff.grant_for_staff(world.users["staff"], grant_id)
    assert mine is not None and mine.id == grant_id
    assert [r.grant.id for r in await staff.grants_for_staff(world.users["staff"])] == [grant_id]

    # Another staff member, and nobody at all, read nothing.
    assert await staff.grant_for_staff(world.users["other_staff"], grant_id) is None
    assert await staff.grants_for_staff(world.users["other_staff"]) == []
    async with app_engine.connect() as conn:
        assert (
            await conn.execute(sa.text("SELECT * FROM platform.support_grants_for_staff()"))
        ).all() == []
        # Without a tenant bound, RLS shows the table itself as empty too.
        assert await conn.scalar(sa.text("SELECT count(*) FROM platform.support_grants")) == 0


async def test_sa12_the_functions_are_security_definer_and_not_public(
    migrator: AsyncEngine,
) -> None:
    async with migrator.connect() as conn:
        rows = (
            await conn.execute(
                sa.text(
                    "SELECT p.proname, p.prosecdef,"
                    "       has_function_privilege('public', p.oid, 'EXECUTE') AS public_exec,"
                    "       has_function_privilege('dw_app', p.oid, 'EXECUTE') AS app_exec"
                    " FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
                    " WHERE n.nspname = 'platform'"
                    "   AND p.proname IN ('support_grant_for_staff', 'support_grants_for_staff')"
                )
            )
        ).all()
    assert {r.proname for r in rows} == {"support_grant_for_staff", "support_grants_for_staff"}
    for row in rows:
        assert row.prosecdef, row.proname
        assert not row.public_exec, row.proname
        assert row.app_exec, row.proname


async def test_the_grant_filter_index_reads_the_key_the_writers_write(
    migrator: AsyncEngine,
) -> None:
    """`?support_grant_id=`'s index names its `details` key in migration text;
    the writers and the filter name it through `SUPPORT_GRANT_DETAIL`. Renaming
    one side would leave the filter walking the whole trail with every other
    test green, so the catalog is asked, partitions included (failure-modes #0,
    #2)."""
    async with migrator.connect() as conn:
        partitions = set(
            (
                await conn.execute(
                    sa.text(
                        "SELECT c.relname FROM pg_inherits i"
                        " JOIN pg_class c ON c.oid = i.inhrelid"
                        " WHERE i.inhparent = 'platform.audit_events'::regclass"
                    )
                )
            ).scalars()
        )
        indexed = set(
            (
                await conn.execute(
                    sa.text(
                        "SELECT tablename FROM pg_indexes WHERE schemaname = 'platform'"
                        " AND indexdef LIKE :expr"
                    ),
                    {"expr": f"%(details ->> '{SUPPORT_GRANT_DETAIL}'::text)%"},
                )
            ).scalars()
        )
    assert "audit_events_default" in partitions
    assert indexed == partitions | {"audit_events"}


async def test_sa4_sa10_a_staff_context_and_its_trail(
    world: SupportWorld,
    app_engine: AsyncEngine,
    provisioner_engine: AsyncEngine,
    migrator: AsyncEngine,
) -> None:
    grant_id = await _active_grant(world, app_engine, provisioner_engine)
    staff = _staff(app_engine)
    factory = SupportAccessContextFactory(
        grants=staff,
        member_scopes=SqlScopeHolders(async_sessionmaker(app_engine, expire_on_commit=False)),
        clock=FixedClock(NOW),
        ids=Uuid4Generator(),
    )
    context = await factory.build(
        principal_id=world.users["staff"], auth_methods=OTP, grant_id=grant_id
    )
    assert context.roles == frozenset()
    assert context.tenant_id == world.tenant_a and context.workspace_id == world.ws1
    assert context.scopes == frozenset({"x.read"})

    # Not support staff, and staff without a second factor, get nothing.
    with pytest.raises(PermissionDeniedError):
        await factory.build(
            principal_id=world.users["not_staff"], auth_methods=OTP, grant_id=grant_id
        )
    with pytest.raises(PermissionDeniedError):
        await factory.build(
            principal_id=world.users["staff"], auth_methods=frozenset({"pwd"}), grant_id=grant_id
        )
    # Another staff member: the grant does not exist for them.
    with pytest.raises(NotFoundError):
        await factory.build(
            principal_id=world.users["other_staff"], auth_methods=OTP, grant_id=grant_id
        )

    for n in range(3):
        await staff.record_access(
            factory.access_event(
                context, method="GET", route="/api/v1/probe/{id}", path_ids={"id": str(n)}
            )
        )
    async with migrator.connect() as conn:
        count = await conn.scalar(
            sa.text(
                "SELECT count(*) FROM platform.audit_events"
                " WHERE tenant_id = :t AND action = 'support.access'"
                "   AND details->>'support_grant_id' = :g AND actor_id = :a"
            ),
            {"t": world.tenant_a, "g": str(grant_id), "a": world.users["staff"]},
        )
    assert count == 3


async def test_sa10_the_customer_reads_a_grants_trail_and_who_acted_under_it(
    world: SupportWorld,
    app_engine: AsyncEngine,
    provisioner_engine: AsyncEngine,
) -> None:
    """`GET /audit/events`'s store: filtered by grant, each actor's name, and
    `support` only for the staff member the grant was assigned to."""
    grant_id = await _active_grant(world, app_engine, provisioner_engine)
    staff = _staff(app_engine)
    factory = SupportAccessContextFactory(
        grants=staff,
        member_scopes=SqlScopeHolders(async_sessionmaker(app_engine, expire_on_commit=False)),
        clock=FixedClock(NOW),
        ids=Uuid4Generator(),
    )
    context = await factory.build(
        principal_id=world.users["staff"], auth_methods=OTP, grant_id=grant_id
    )
    for n in range(3):
        await staff.record_access(
            factory.access_event(
                context, method="GET", route="/probe/{id}", path_ids={"id": str(n)}
            )
        )

    def event(actor: uuid.UUID, grant: str | None) -> AuditEvent:
        return AuditEvent(
            id=uuid.uuid4(),
            tenant_id=TenantId(world.tenant_a),
            workspace_id=WorkspaceId(world.ws1),
            actor_id=UserId(actor),
            action="probe.touched",
            resource_type="probe",
            resource_id="p",
            occurred_at=NOW,
            details={} if grant is None else {SUPPORT_GRANT_DETAIL: grant},
        )

    other_grant = str(uuid.uuid4())
    async with SqlPlatformUnitOfWorkFactory(async_sessionmaker(app_engine, expire_on_commit=False))(
        context
    ) as uow:
        # The staff member naming a grant that is not theirs is not support;
        # a grant id that is no id fails nothing; a lane has no name.
        await uow.audit.append(event(world.users["staff"], other_grant))
        await uow.audit.append(event(world.users["granter"], "not-a-uuid"))
        await uow.audit.append(
            lane_audit_event(
                lane="probe_lane",
                event_id=uuid.uuid4(),
                tenant_id=TenantId(world.tenant_a),
                workspace_id=WorkspaceId(world.ws1),
                action="probe.swept",
                resource_type="probe",
                resource_id="p",
                occurred_at=NOW,
            )
        )
        await uow.commit()

    granter = await context_of(app_engine, world, "granter", world.tenant_a, world.ws1)
    page = PageRequest(limit=50, after=None, query=PageQuery(key="test.support_trail"))
    sessions = async_sessionmaker(app_engine, expire_on_commit=False)
    async with SqlPlatformUnitOfWorkFactory(sessions)(granter) as uow:
        of_grant = await uow.audit.list_page(
            page, workspace_id=world.ws1, support_grant_id=grant_id
        )
        whole = await uow.audit.list_page(page, workspace_id=world.ws1)
    # ws2 of the same tenant reads none of it, filtered or not.
    async with SqlPlatformUnitOfWorkFactory(sessions)(granter) as uow:
        assert (
            await uow.audit.list_page(page, workspace_id=world.ws2, support_grant_id=grant_id)
        ).items == ()
    # Tenant B naming tenant A's grant and workspace reads nothing: RLS, not the filter.
    b_granter = await context_of(app_engine, world, "b_granter", world.tenant_b, world.ws_b)
    async with SqlPlatformUnitOfWorkFactory(sessions)(b_granter) as uow:
        assert (
            await uow.audit.list_page(page, workspace_id=world.ws1, support_grant_id=grant_id)
        ).items == ()

    rows = sorted(
        (e.event.action, e.actor_display_name, e.actor_kind.value) for e in of_grant.items
    )
    assert rows == [
        ("support.access", "staff", AuditActorKind.SUPPORT.value),
        ("support.access", "staff", AuditActorKind.SUPPORT.value),
        ("support.access", "staff", AuditActorKind.SUPPORT.value),
        ("support.grant.assigned", "operator", AuditActorKind.USER.value),
        ("support.grant.requested", "granter", AuditActorKind.USER.value),
    ]
    assert all(e.event.details[SUPPORT_GRANT_DETAIL] == str(grant_id) for e in of_grant.items)

    rest = sorted(
        (str(e.event.details.get(SUPPORT_GRANT_DETAIL)), e.actor_display_name, e.actor_kind.value)
        for e in whole.items
        if e.event.action in {"probe.touched", "probe.swept"}
    )
    assert rest == sorted(
        [
            (other_grant, "staff", AuditActorKind.USER.value),
            ("not-a-uuid", "granter", AuditActorKind.USER.value),
            ("None", None, AuditActorKind.USER.value),
        ]
    )
    assert len(whole.items) == len(of_grant.items) + 3
