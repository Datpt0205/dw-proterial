"""Who in a workspace holds a scope: the members a sender should address.

A membership's scopes are read by `effective_scopes`, the same function that
builds the access context, so "who may act" and "who is told to act" cannot
disagree. A tenant that is not active has nobody to tell, as it has nobody
to let in.

`HolderMailboxes` answers a third from the first: whose mail a context's
lane reads from the one drop folder every DW shares (the folders named by
the addresses of those holding its scope), so whose mail is read and who is
told about it are one answer.

Both questions here — "who holds one of these scopes" (`holding`) and "does this
person hold this scope" (`holds`) — read memberships through one query,
`_members`, so the two answers cannot drift apart either. Neither takes an
`AccessContext`: a workflow node resuming after someone else's decision, or a
worker lane, has a tenant and a workspace from a verified source but no
signed-in caller.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.membership_lookup import effective_scopes
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session


async def _members(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> Sequence[sa.Row[Any]]:
    """The memberships of one workspace of an active tenant, by `user_id`.

    The one membership query of this module. RLS already bounds the rows to the
    bound tenant; the explicit tenant predicate says so again, and the tenant
    join refuses a tenant that is not `active` (an absent or unreadable status
    is not active either). With `user_id`, at most that one membership.
    """
    query = (
        sa.select(
            tables.memberships.c.user_id,
            tables.memberships.c.role_keys,
            tables.memberships.c.permission_set_keys,
        )
        .select_from(
            tables.memberships.join(
                tables.tenants, tables.tenants.c.id == tables.memberships.c.tenant_id
            )
        )
        .where(
            tables.memberships.c.tenant_id == tenant_id,
            tables.memberships.c.workspace_id == workspace_id,
            tables.tenants.c.status == "active",
        )
        .order_by(tables.memberships.c.user_id)
    )
    if user_id is not None:
        query = query.where(tables.memberships.c.user_id == user_id)
    return (await session.execute(query)).all()


async def _scopes_of(session: AsyncSession, member: sa.Row[Any]) -> frozenset[str]:
    return await effective_scopes(
        session, frozenset(member.role_keys), frozenset(member.permission_set_keys)
    )


@dataclass(frozen=True)
class SqlScopeHolders:
    session_factory: async_sessionmaker[AsyncSession]

    async def holding(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, scopes: frozenset[str]
    ) -> list[uuid.UUID]:
        """The members of `workspace_id` holding any of `scopes`, by user id.

        `tenant_id` and `workspace_id` must come from a source the caller has
        already verified — a row the database tagged with its tenant, a state
        stamped when the run started, an `AccessContext` — never from a request
        body. This function does not check where they came from.
        """
        if not scopes:
            return []
        scope = TenantScope(tenant_id=tenant_id, workspace_id=workspace_id)
        async with tenant_session(self.session_factory, scope) as session:
            holders: list[uuid.UUID] = []
            for member in await _members(session, tenant_id, workspace_id):
                if await _scopes_of(session, member) & scopes:
                    holders.append(member.user_id)
        return holders

    async def holds(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID, scope: str
    ) -> bool:
        """Whether `user_id`'s membership of `workspace_id` carries `scope`.

        False for no membership, a tenant that is not active, or an empty
        `scope` (fail closed). No role stands in for a scope here,
        `platform_admin` included: the question is what this membership holds,
        the same question `holding` answers.

        `tenant_id` and `workspace_id` must come from a source the caller has
        already verified (a stamped state, a tenant-tagged row), never from a
        request body; this function does not check where they came from.
        """
        if not scope:
            return False
        return scope in await self.scopes_of(tenant_id, workspace_id, user_id)

    async def scopes_of(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> frozenset[str]:
        """Every scope `user_id`'s membership of `workspace_id` carries; empty
        for no membership or a tenant that is not active. Implements
        `MemberScopesPort` (a support grant is in force only while its granter
        still holds what it stamped). Same provenance rule as `holds`."""
        bound = TenantScope(tenant_id=tenant_id, workspace_id=workspace_id)
        async with tenant_session(self.session_factory, bound) as session:
            members = await _members(session, tenant_id, workspace_id, user_id)
            if len(members) != 1:
                return frozenset()
            return await _scopes_of(session, members[0])

    async def addresses_holding(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, scopes: frozenset[str]
    ) -> frozenset[str]:
        """The sign-in addresses, lowercase, of the members `holding` names;
        a member without one is left out. Same provenance rule as `holding`."""
        members = await self.holding(tenant_id, workspace_id, scopes)
        if not members:
            return frozenset()
        async with self.session_factory() as session, session.begin():
            emails = await session.scalars(
                sa.select(tables.users.c.email).where(
                    tables.users.c.id.in_(members), tables.users.c.email.is_not(None)
                )
            )
            return frozenset(email.lower() for email in emails)


@dataclass(frozen=True)
class HolderMailboxes:
    """`FolderOwnersPort` for one context's lane in one workspace: the
    addresses of the members holding any of ``scopes``, asked each tick, so
    a scope granted or withdrawn changes whose mail is read at once."""

    holders: SqlScopeHolders
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    scopes: frozenset[str]

    async def addresses(self) -> frozenset[str]:
        return await self.holders.addresses_holding(self.tenant_id, self.workspace_id, self.scopes)
