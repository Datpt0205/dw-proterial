"""Read-only questions about the approval inbox that a bounded context asks
without owning the table.

A context that raises approvals (`<context>.<action>`) sometimes needs to
know which of ITS approvals are still undecided — a daily summary counts
them, say. It declares a narrow Protocol for that, and this
class satisfies it at the composition root, so no context reads
`platform.approval_requests` itself.

Queries name no `tenant_id` filter of their own: RLS is the one enforcement
mechanism for a Postgres-backed store here, same as every repository in this
package.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.repositories import _approval_from_row
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.approval import ApprovalRequest, ApprovalStatus


@dataclass(frozen=True)
class SqlPendingApprovalQuery:
    session_factory: async_sessionmaker[AsyncSession]

    async def list_pending_by_type_prefix(
        self, context: AccessContext, *, prefix: str, limit: int
    ) -> tuple[int, list[ApprovalRequest]]:
        """How many pending approvals have an `approval_type` starting with
        `prefix`, and the newest `limit` of them. The prefix is matched
        literally — `autoescape` keeps the `_` in `leave_request.` from being
        LIKE's any-one-character wildcard."""
        approvals = tables.approval_requests
        matches = sa.and_(
            approvals.c.status == ApprovalStatus.PENDING.value,
            approvals.c.approval_type.startswith(prefix, autoescape=True),
        )
        scope = TenantScope.from_access_context(context)
        async with tenant_session(self.session_factory, scope) as session:
            total = (
                await session.execute(
                    sa.select(sa.func.count()).select_from(approvals).where(matches)
                )
            ).scalar_one()
            rows = await session.execute(
                sa.select(approvals)
                .where(matches)
                .order_by(approvals.c.created_at.desc(), approvals.c.id.desc())
                .limit(limit)
            )
            return total, [_approval_from_row(row) for row in rows]
