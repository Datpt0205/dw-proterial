"""Open a database session with the RLS tenant context already bound.

Every tenant-scoped adapter needs the same three steps in the same order:
acquire a session, open a transaction, bind the `app.*` GUCs. Hand-rolling that
sequence is what produced four connection leaks, because acquiring the pooled
session before entering a cleanup guard loses it when `begin()` or the bind
raises. Here the guard is entered first, so there is no window in which a
connection is held by nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.application.access_context import AccessContext

_BIND_SCOPE = text(
    "SELECT set_config('app.tenant_id', :tenant_id, true),"
    "       set_config('app.workspace_id', :workspace_id, true),"
    "       set_config('app.user_id', :user_id, true)"
)


@dataclass(frozen=True)
class TenantScope:
    """The identifiers an RLS policy may read, and nothing else."""

    tenant_id: uuid.UUID
    workspace_id: uuid.UUID | None = None
    principal_id: uuid.UUID | None = None

    @classmethod
    def from_access_context(cls, context: AccessContext) -> TenantScope:
        return cls(
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            principal_id=context.principal_id,
        )


async def bind_tenant(session: AsyncSession, scope: TenantScope) -> None:
    """Bind the scope for the session's open transaction only.

    An absent identifier is bound as the empty string rather than skipped: every
    policy reads its GUC through ``NULLIF(..., '')``, so a scope that does not
    name a workspace denies a workspace-keyed policy instead of inheriting
    whatever the previous caller on this connection had set.
    """
    # Consume result to force execution; SELECT set_config(...) is lazy otherwise.
    (
        await session.execute(
            _BIND_SCOPE,
            {
                "tenant_id": str(scope.tenant_id),
                "workspace_id": str(scope.workspace_id) if scope.workspace_id else "",
                "user_id": str(scope.principal_id) if scope.principal_id else "",
            },
        )
    ).first()


@asynccontextmanager
async def tenant_session(
    session_factory: async_sessionmaker[AsyncSession], scope: TenantScope
) -> AsyncIterator[AsyncSession]:
    """Yield a session inside a transaction bound to ``scope``.

    Commits on a clean exit and rolls back on an exception, both by way of
    ``session.begin()``.
    """
    async with session_factory() as session, session.begin():
        await bind_tenant(session, scope)
        yield session
