"""SQL side of customer-granted support access (ADR 0024), as `dw_app`.

RLS on `platform.support_grants` narrows to the bound tenant only, so every
read and every write by id here also names the caller's workspace: a grant of
another workspace is absent, the same answer as one that never existed. Each
write commits with its audit event or not at all. The status machine itself is
the database's (`platform.guard_support_grant()`); the `expected` statuses here
only make a lost race read as "moved meanwhile" instead of a database error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.adapters.persistence.separation_of_duties import refusal
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_platform.application.support_access import (
    AuditFor,
    GrantChange,
    GrantStatus,
    NewSupportGrant,
    SupportGrant,
    support_staff_not_member,
)

_G = tables.support_grants
_NOT_SUPPORT_STAFF = "ck_memberships_not_support_staff"


def support_staff_conflict(error: IntegrityError) -> ConflictError | None:
    """The membership guard's refusal (`ck_memberships_not_support_staff`) as
    the 409 every membership path gives; None for any other integrity error."""
    refused = refusal(error)
    if refused is None or refused[0] != _NOT_SUPPORT_STAFF:
        return None
    return support_staff_not_member()


def grant_from_row(row: Any) -> SupportGrant:
    return SupportGrant(
        id=row.id,
        code=row.code,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        resource_label=row.resource_label,
        scope_set_key=row.scope_set_key,
        scope_set_label=row.scope_set_label,
        scopes=frozenset(row.scopes),
        reason=row.reason,
        duration_hours=row.duration_hours,
        status=GrantStatus(row.status),
        requested_by=row.requested_by,
        requested_at=row.requested_at,
        granted_by=row.granted_by,
        granted_at=row.granted_at,
        rejected_by=row.rejected_by,
        rejected_at=row.rejected_at,
        reject_reason=row.reject_reason,
        staff_user_id=row.staff_user_id,
        assigned_by=row.assigned_by,
        activated_at=row.activated_at,
        expires_at=row.expires_at,
        revoked_by=row.revoked_by,
        revoked_at=row.revoked_at,
    )


@dataclass(frozen=True)
class SqlSupportGrantRepository:
    """Implements ``SupportGrantRepositoryPort``."""

    session_factory: async_sessionmaker[AsyncSession]

    async def workspace_name(self, context: AccessContext) -> str | None:
        async with tenant_session(self.session_factory, _scope(context)) as session:
            name: str | None = await session.scalar(
                sa.select(tables.workspaces.c.name).where(
                    tables.workspaces.c.id == context.workspace_id
                )
            )
        return name

    async def create(
        self, context: AccessContext, grant: NewSupportGrant, audit: AuditFor
    ) -> SupportGrant:
        async with tenant_session(self.session_factory, _scope(context)) as session:
            row = (
                await session.execute(
                    sa.insert(_G)
                    .values(
                        id=grant.id,
                        tenant_id=context.tenant_id,
                        workspace_id=context.workspace_id,
                        resource_type=grant.resource_type,
                        resource_id=grant.resource_id,
                        resource_label=grant.resource_label,
                        scope_set_key=grant.scope_set_key,
                        scope_set_label=grant.scope_set_label,
                        scopes=sorted(grant.scopes),
                        reason=grant.reason,
                        duration_hours=grant.duration_hours,
                        status=grant.status.value,
                        requested_by=grant.requested_by,
                        requested_at=grant.requested_at,
                        granted_by=grant.granted_by,
                        granted_at=grant.granted_at,
                    )
                    .returning(*_G.c)
                )
            ).one()
            created = grant_from_row(row)
            await SqlAuditRepository(session).append(audit(created))
        return created

    async def get(
        self, context: AccessContext, grant_id: UUID, *, requested_by: UUID | None = None
    ) -> SupportGrant | None:
        query = sa.select(_G).where(_G.c.id == grant_id, *_mine(context, requested_by))
        async with tenant_session(self.session_factory, _scope(context)) as session:
            row = (await session.execute(query)).first()
        return None if row is None else grant_from_row(row)

    async def list_grants(
        self, context: AccessContext, *, requested_by: UUID | None = None
    ) -> list[SupportGrant]:
        query = (
            sa.select(_G)
            .where(*_mine(context, requested_by))
            .order_by(_G.c.requested_at.desc(), _G.c.id.desc())
        )
        async with tenant_session(self.session_factory, _scope(context)) as session:
            rows = (await session.execute(query)).all()
        return [grant_from_row(row) for row in rows]

    async def change(
        self,
        context: AccessContext,
        grant_id: UUID,
        *,
        expected: frozenset[GrantStatus],
        change: GrantChange,
        audit: AuditFor,
    ) -> SupportGrant | None:
        values: dict[str, object] = {"status": change.status.value}
        for column in (
            "granted_by",
            "granted_at",
            "rejected_by",
            "rejected_at",
            "reject_reason",
            "revoked_by",
            "revoked_at",
        ):
            value = getattr(change, column)
            if value is not None:
                values[column] = value
        async with tenant_session(self.session_factory, _scope(context)) as session:
            row = (
                await session.execute(
                    sa.update(_G)
                    .where(
                        _G.c.id == grant_id,
                        *_mine(context, None),
                        _G.c.status.in_([s.value for s in expected]),
                    )
                    .values(**values)
                    .returning(*_G.c)
                )
            ).first()
            if row is None:
                return None
            changed = grant_from_row(row)
            await SqlAuditRepository(session).append(audit(changed))
        return changed


def _scope(context: AccessContext) -> TenantScope:
    return TenantScope.from_access_context(context)


def _mine(context: AccessContext, requested_by: UUID | None) -> list[sa.ColumnElement[bool]]:
    """The caller's tenant (RLS says it too) and workspace; a requester's own."""
    clauses = [_G.c.tenant_id == context.tenant_id, _G.c.workspace_id == context.workspace_id]
    if requested_by is not None:
        clauses.append(_G.c.requested_by == requested_by)
    return clauses
