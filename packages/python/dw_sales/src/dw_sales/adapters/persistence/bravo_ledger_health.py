"""How many of the gateway's Bravo writes wait for a person (ticket 84).

One number across every tenant, from `bravo.writes_needing_a_person()`
(migration fc8d358317fe): ledger rows `in_doubt`, `reconcile_failed`, or
still `claimed` 15 minutes on. The function is SECURITY DEFINER and answers a
count only, so this reads it without binding a tenant: no id, tenant or
content of any write leaves the database through it.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_COUNT = sa.text("SELECT bravo.writes_needing_a_person()")


class SqlBravoLedgerHealth:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def needing_a_person(self) -> int:
        async with self._sessions() as session:
            return int(await session.scalar(_COUNT) or 0)
