"""SQL implementation of `PolicyOverridePort`.

The write half of what `dw_kernel.overlay.TenantOverlay`'s own docstring
already names as a covered artifact kind ("a policy") but never had storage
built for — see migration `45dc1b5e0125`'s own docstring for the full
reasoning. `content` is raw JSON on purpose: this repository validates
nothing about its shape, since it has no opinion on what a given
`policy_id` needs — that is the owning bounded context's job.

Queries here name no `tenant_id` filter of their own, same convention every
other tenant-scoped repository in this platform follows: RLS is the one
enforcement mechanism for a Postgres-backed store here.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent


@dataclass(frozen=True)
class SqlPolicyOverrideRepository:
    """Implements `PolicyOverridePort`."""

    session_factory: async_sessionmaker[AsyncSession]

    async def get(self, context: AccessContext, policy_id: str) -> dict[str, object] | None:
        scope = TenantScope.from_access_context(context)
        async with tenant_session(self.session_factory, scope) as session:
            row = (
                await session.execute(
                    sa.select(tables.policy_overrides.c.content).where(
                        tables.policy_overrides.c.policy_id == policy_id
                    )
                )
            ).first()
            return cast(dict[str, object], row.content) if row else None

    async def put(
        self,
        context: AccessContext,
        policy_id: str,
        content: Mapping[str, object],
        *,
        audit: AuditEvent,
    ) -> None:
        scope = TenantScope.from_access_context(context)
        async with tenant_session(self.session_factory, scope) as session:
            await session.execute(
                pg_insert(tables.policy_overrides)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=context.tenant_id,
                    policy_id=policy_id,
                    content=dict(content),
                )
                .on_conflict_do_update(
                    constraint="uq_policy_overrides_tenant_id_policy_id",
                    set_={"content": dict(content)},
                )
            )
            await SqlAuditRepository(session).append(audit)
