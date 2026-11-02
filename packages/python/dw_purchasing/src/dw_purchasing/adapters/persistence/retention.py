"""DW2's rows past their term, deleted per workspace through SECURITY DEFINER
functions (migration 191b591d4ef1 replaced the one-term
`purchasing.prune_expired`; 32c1f04b76d6 added the mailbox):
`purchasing.retention_scopes()` lists the workspaces holding DW2 rows, ids
only, `purchasing.prune_expired_in` deletes one workspace's cases and mail
outcomes before the cutoffs that tenant's rules give, and
`purchasing.prune_mailbox_in` its stored mail
(`dw_purchasing.application.retention`). `dw_app` holds no DELETE on
`mail_outcomes` or the mailbox, and reads no other tenant's rows."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_purchasing.application.retention import Pruned

_SCOPES: Final = sa.text("SELECT tenant_id, workspace_id FROM purchasing.retention_scopes()")
_PRUNE: Final = sa.text(
    "SELECT cases, outcomes FROM purchasing.prune_expired_in("
    ":tenant_id, :workspace_id, :cases_before, :outcomes_before)"
)
_PRUNE_MAILBOX: Final = sa.text(
    "SELECT purchasing.prune_mailbox_in(:tenant_id, :workspace_id, :mail_before)"
)


@dataclass(frozen=True)
class SqlRetentionStore:
    """Implements `RetentionStorePort`."""

    session_factory: async_sessionmaker[AsyncSession]

    async def scopes(self) -> Sequence[tuple[uuid.UUID, uuid.UUID]]:
        async with self.session_factory() as session, session.begin():
            rows = (await session.execute(_SCOPES)).all()
        return [(row.tenant_id, row.workspace_id) for row in rows]

    async def prune(
        self,
        scope: tuple[uuid.UUID, uuid.UUID],
        *,
        cases_before: datetime | None,
        outcomes_before: datetime | None,
        mail_before: datetime | None,
    ) -> Pruned:
        """A None cutoff deletes nothing of its table (the function's NULL)."""
        params = {
            "tenant_id": scope[0],
            "workspace_id": scope[1],
            "cases_before": cases_before,
            "outcomes_before": outcomes_before,
        }
        async with self.session_factory() as session, session.begin():
            row = (await session.execute(_PRUNE, params)).one()
            mail = await session.scalar(
                _PRUNE_MAILBOX,
                {"tenant_id": scope[0], "workspace_id": scope[1], "mail_before": mail_before},
            )
        return Pruned(cases=row.cases, outcomes=row.outcomes, mail=mail or 0)
