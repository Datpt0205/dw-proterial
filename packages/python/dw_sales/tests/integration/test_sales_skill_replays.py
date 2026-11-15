"""`sales.skill_replays` (migration e1b1e0cadb66, ticket 40) against a real
database, as `dw_app` wherever isolation is the question.

A replay is stored once per proposed skill version, beside its
`platform.rule_versions` row, read under the tenant's RLS only, never
changed or removed by the application, and held by its CHECKs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.application.rule_versions import RuleVersion
from dw_platform.domain.approval import ApprovalRequest
from dw_platform.domain.audit import AuditEvent, lane_audit_event
from dw_sales.adapters.persistence.skill_replays import SqlSkillReplays
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.application.skills import SKILLS_APPROVAL, SkillDocument, SkillReplay

pytestmark = pytest.mark.integration

_AT = datetime.now(UTC).replace(microsecond=0)


async def _opened(work: Any, scope: SalesScope) -> uuid.UUID:
    """The `sales.skills` approval a proposal waits on
    (`ck_rule_versions_proposed_has_approval`)."""
    approval_id = uuid.uuid4()
    await work.approvals.add(
        ApprovalRequest(
            id=approval_id,
            tenant_id=TenantId(scope.tenant_id.value),
            workspace_id=WorkspaceId(scope.workspace_id.value),
            approval_type=SKILLS_APPROVAL,
            requested_by=UserId(uuid.UUID(int=0x40A)),
            reason="ticket 40",
            payload={},
            required_scope="sales.rules.approve",
        )
    )
    return approval_id


async def _proposed(uow: SqlSalesUnitOfWorkFactory, scope: SalesScope) -> uuid.UUID:
    """A proposed version of the thread-intents skill in ``scope``'s tenant."""
    document = SkillDocument(
        policy_id="sales_skill_thread_intents",
        policy_version="1.1.0",
        description="Reading a thread message's intents.",
        instructions="Read it.",
    )
    version = RuleVersion(
        version_id=uuid.uuid4(),
        key=document.policy_id,
        version="1.1.0",
        document=document.model_dump(mode="json"),
        status="proposed",
        proposed_by=uuid.uuid4(),
        proposed_at=_AT,
        approval_id=None,
    )
    async with uow(scope) as work:
        version = version.model_copy(update={"approval_id": await _opened(work, scope)})
        await work.rule_versions.add(version)
        await work.commit()
    return version.version_id


def _audit(scope: SalesScope, version_id: uuid.UUID) -> AuditEvent:
    return lane_audit_event(
        lane="sales_skill_replay",
        event_id=uuid.uuid4(),
        tenant_id=scope.tenant_id,
        workspace_id=scope.workspace_id,
        action="sales.skills.replayed",
        resource_type="sales_skill_version",
        resource_id=str(version_id),
        occurred_at=_AT,
    )


def _replay(version_id: uuid.UUID, **changes: Any) -> SkillReplay:
    values: dict[str, Any] = {
        "version_id": version_id,
        "replayed_at": _AT,
        "source": "platform_examples",
        "outcome": "replayed",
        "messages": 60,
        "right_with": 52,
        "right_without": 48,
        "unanswered": 0,
        "security_failed": ("RP31",),
    }
    return SkillReplay.model_validate(values | changes)


async def test_a_replay_is_stored_once_and_read_back(
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    uow: SqlSalesUnitOfWorkFactory,
    world: World,
) -> None:
    version_id = await _proposed(uow, world.alpha)
    store = SqlSkillReplays(app_sessions, SqlAuditRepository)
    assert await store.stored(world.alpha, [version_id]) == {}
    assert await store.store(world.alpha, _replay(version_id), _audit(world.alpha, version_id))
    # A second workspace's lane got there second: nothing changes.
    assert not await store.store(
        world.alpha_other, _replay(version_id, right_with=1), _audit(world.alpha_other, version_id)
    )
    assert await store.stored(world.alpha, [version_id]) == {version_id: _replay(version_id)}
    # The stored one's audit row, in its transaction, and only that one.
    async with migrator.connect() as conn:
        audited = await conn.scalar(
            sa.text(
                "SELECT count(*) FROM platform.audit_events WHERE resource_id = :v"
                " AND action = 'sales.skills.replayed'"
            ),
            {"v": str(version_id)},
        )
    assert audited == 1
    # The tenant's: read from its other workspace too, as the version is.
    assert await store.stored(world.alpha_other, [version_id]) == {version_id: _replay(version_id)}


async def test_another_tenant_reads_none_and_an_unscoped_connection_nothing(
    app_sessions: async_sessionmaker[AsyncSession],
    sales_app_engine: AsyncEngine,
    uow: SqlSalesUnitOfWorkFactory,
    world: World,
) -> None:
    version_id = await _proposed(uow, world.alpha)
    store = SqlSkillReplays(app_sessions, SqlAuditRepository)
    await store.store(world.alpha, _replay(version_id), _audit(world.alpha, version_id))
    assert await store.stored(world.beta, [version_id]) == {}
    async with sales_app_engine.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM sales.skill_replays")) == 0


async def test_a_replay_written_for_another_tenant_is_refused_by_the_policy(
    app_sessions: async_sessionmaker[AsyncSession], uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    version_id = await _proposed(uow, world.beta)
    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_sessions() as session, session.begin():
            await session.execute(
                sa.text("SELECT set_config('app.tenant_id', :t, true)"),
                {"t": str(world.alpha.tenant_id.value)},
            )
            await session.execute(
                sa.text(
                    "INSERT INTO sales.skill_replays (id, tenant_id, workspace_id, version_id,"
                    " replayed_at, source, outcome, messages, right_with, right_without,"
                    " unanswered, security_failed) VALUES (:id, :t, :w, :v, now(),"
                    " 'platform_examples', 'replayed', 1, 1, 1, 0, '[]'::jsonb)"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": world.beta.tenant_id.value,
                    "w": world.beta.workspace_id.value,
                    "v": version_id,
                },
            )


async def test_the_application_never_changes_or_removes_a_replay(
    app_sessions: async_sessionmaker[AsyncSession], uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    version_id = await _proposed(uow, world.alpha)
    await SqlSkillReplays(app_sessions, SqlAuditRepository).store(
        world.alpha, _replay(version_id), _audit(world.alpha, version_id)
    )
    for statement in (
        "UPDATE sales.skill_replays SET right_with = 60",
        "DELETE FROM sales.skill_replays",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with app_sessions() as session, session.begin():
                await session.execute(
                    sa.text("SELECT set_config('app.tenant_id', :t, true)"),
                    {"t": str(world.alpha.tenant_id.value)},
                )
                await session.execute(sa.text(statement))


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("source", "'tenant_cases'"),
        ("outcome", "'maybe'"),
        ("right_with", "61"),
        ("right_without", "-1"),
        ("security_failed", "'{}'::jsonb"),
    ],
)
async def test_the_checks_hold_a_row_to_the_domains_shape(
    migrator: AsyncEngine,
    uow: SqlSalesUnitOfWorkFactory,
    world: World,
    column: str,
    value: str,
) -> None:
    version_id = await _proposed(uow, world.alpha)
    values = {
        "source": "'platform_examples'",
        "outcome": "'replayed'",
        "right_with": "1",
        "right_without": "1",
        "security_failed": "'[]'::jsonb",
    } | {column: value}
    with pytest.raises(IntegrityError):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.skill_replays (id, tenant_id, workspace_id, version_id,"
                    " replayed_at, source, outcome, messages, right_with, right_without,"
                    f" unanswered, security_failed) VALUES (:id, :t, :w, :v, now(),"
                    f" {values['source']}, {values['outcome']}, 60, {values['right_with']},"
                    f" {values['right_without']}, 0, {values['security_failed']})"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": world.alpha.tenant_id.value,
                    "w": world.alpha.workspace_id.value,
                    "v": version_id,
                },
            )


async def test_a_replay_leaves_with_its_version(
    migrator: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    uow: SqlSalesUnitOfWorkFactory,
    world: World,
) -> None:
    version_id = await _proposed(uow, world.alpha)
    await SqlSkillReplays(app_sessions, SqlAuditRepository).store(
        world.alpha, _replay(version_id), _audit(world.alpha, version_id)
    )
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text("DELETE FROM platform.rule_versions WHERE id = :v"), {"v": version_id}
        )
        left = await conn.scalar(
            sa.text("SELECT count(*) FROM sales.skill_replays WHERE version_id = :v"),
            {"v": version_id},
        )
    assert left == 0
