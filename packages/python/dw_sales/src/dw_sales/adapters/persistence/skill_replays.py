"""Replays of proposed skill versions in PostgreSQL (ticket 40, migration
e1b1e0cadb66).

`sales.skill_replays` holds one row per replayed version, beside its
`platform.rule_versions` row, narrowed by tenant only as that row is.
`dw_app` may SELECT and INSERT, never UPDATE or DELETE: a replay is a fact
about one version, and leaves with it (`ON DELETE CASCADE`) or with the
tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.adapters.persistence.uow import AuditFactory
from dw_sales.application.ports import SalesScope
from dw_sales.application.skill_replay import SkillReplay

_TS = sa.TIMESTAMP(timezone=True)

# Mirrors the migration; constraints, policies and grants are the migration's.
skill_replays = sa.Table(
    "skill_replays",
    tables.metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("version_id", UUID(as_uuid=True), nullable=False),
    sa.Column("replayed_at", _TS, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("outcome", sa.Text, nullable=False),
    sa.Column("messages", sa.Integer, nullable=False),
    sa.Column("right_with", sa.Integer, nullable=False),
    sa.Column("right_without", sa.Integer, nullable=False),
    sa.Column("unanswered", sa.Integer, nullable=False),
    sa.Column("security_failed", JSONB, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
)
_R = skill_replays


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


def _replay(row: RowMapping) -> SkillReplay:
    return SkillReplay(
        version_id=row["version_id"],
        replayed_at=row["replayed_at"],
        source=row["source"],
        outcome=row["outcome"],
        messages=row["messages"],
        right_with=row["right_with"],
        right_without=row["right_without"],
        unanswered=row["unanswered"],
        security_failed=tuple(row["security_failed"]),
    )


@dataclass(frozen=True)
class SqlSkillReplays:
    """Implements `SkillReplayStorePort`: one short statement per call, in
    the tenant's own session; a stored replay's audit row in its
    transaction."""

    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    async def stored(
        self, scope: SalesScope, version_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, SkillReplay]:
        if not version_ids:
            return {}
        query = sa.select(_R).where(_R.c.version_id.in_(list(version_ids)))
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            rows = (await session.execute(query)).mappings()
            return {row["version_id"]: _replay(row) for row in rows}

    async def store(self, scope: SalesScope, replay: SkillReplay, audit: AuditEvent) -> bool:
        statement = (
            insert(_R)
            .values(
                id=uuid.uuid4(),
                **scope_values(scope),
                version_id=replay.version_id,
                replayed_at=replay.replayed_at,
                source=replay.source,
                outcome=replay.outcome,
                messages=replay.messages,
                right_with=replay.right_with,
                right_without=replay.right_without,
                unanswered=replay.unanswered,
                security_failed=list(replay.security_failed),
            )
            .on_conflict_do_nothing(index_elements=["version_id"])
            .returning(_R.c.id)
        )
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            stored = (await session.execute(statement)).scalar_one_or_none()
            if stored is not None:
                await self.audit(session).append(audit)
        return stored is not None
