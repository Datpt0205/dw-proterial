"""The ``external_identities`` (provider ``zalo``) write, owned in one place.

Both the API webhook and the worker's poll loop link a user to their Zalo chat
id through this repo, so the "one Zalo per user, one user per Zalo" rule and the
row shape live here once rather than in each caller. The identity plane has no
RLS (see :mod:`identity_provisioning`), so no tenant GUC is set — the write runs
as whatever role the caller's session_factory is bound to (``dw_provisioner`` on
the API, ``dw_app`` on the worker; both are granted the identity plane).

Structurally implements ``dw_connectors.adapters.zalo_link.ZaloLinkStore``; the
Protocol is not imported so the platform keeps no dependency on connectors.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence import tables

_ZALO = "zalo"


@dataclass(frozen=True)
class SqlZaloLink:
    session_factory: async_sessionmaker[AsyncSession]

    async def zalo_id_for(self, user_id: UUID) -> str | None:
        """The user's linked Zalo chat id, or None if they never connected."""
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    sa.select(tables.external_identities.c.subject)
                    .where(
                        tables.external_identities.c.provider == _ZALO,
                        tables.external_identities.c.user_id == user_id,
                    )
                    .limit(1)
                )
            ).first()
        return row[0] if row else None

    async def link(self, user_id: UUID, zalo_id: str) -> None:
        async with self.session_factory() as session, session.begin():
            # One Zalo per user and one user per Zalo: clear both sides first so
            # re-linking (a user who switched Zalo, or a Zalo moved to another
            # user) never trips the (issuer, subject) unique constraint.
            await session.execute(
                sa.delete(tables.external_identities).where(
                    tables.external_identities.c.provider == _ZALO,
                    sa.or_(
                        tables.external_identities.c.user_id == user_id,
                        tables.external_identities.c.subject == zalo_id,
                    ),
                )
            )
            await session.execute(
                sa.insert(tables.external_identities).values(
                    id=uuid4(),
                    user_id=user_id,
                    issuer=_ZALO,
                    subject=zalo_id,
                    provider=_ZALO,
                )
            )

    async def unlink_by_zalo(self, zalo_id: str) -> None:
        async with self.session_factory() as session, session.begin():
            await session.execute(
                sa.delete(tables.external_identities).where(
                    tables.external_identities.c.provider == _ZALO,
                    tables.external_identities.c.subject == zalo_id,
                )
            )

    async def unlink_by_user(self, user_id: UUID) -> None:
        async with self.session_factory() as session, session.begin():
            await session.execute(
                sa.delete(tables.external_identities).where(
                    tables.external_identities.c.provider == _ZALO,
                    tables.external_identities.c.user_id == user_id,
                )
            )
