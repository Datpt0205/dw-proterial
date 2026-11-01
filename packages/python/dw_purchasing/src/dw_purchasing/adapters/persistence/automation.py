"""Which workspaces DW2's lane visits (`purchasing.automation_scopes_due`,
migration 6971b41fcdf6): the one read across tenants, ids only, through a
SECURITY DEFINER function, so the application role reads no tenant's rows
it is not bound to."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_DUE = sa.text("SELECT tenant_id, workspace_id FROM purchasing.automation_scopes_due()")


@dataclass(frozen=True)
class SqlAutomationScopes:
    """Implements `AutomationScopesPort`."""

    session_factory: async_sessionmaker[AsyncSession]

    async def due(self) -> Sequence[tuple[uuid.UUID, uuid.UUID]]:
        async with self.session_factory() as session, session.begin():
            rows = (await session.execute(_DUE)).all()
        return [(row.tenant_id, row.workspace_id) for row in rows]
