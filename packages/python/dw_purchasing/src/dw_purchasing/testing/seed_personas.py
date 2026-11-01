"""DW2's demo people, local and test only: the Purchasing keys a few of the
platform seed's fictional members hold, so a person can sign in on
/dev-login as each DW2 role, and DW2's own account in the demo workspace.

The Sales seed keeps every key that is not a Sales one, and this one every
key that is not a Purchasing one, so the two run in either order. Re-running
sets each persona's Purchasing keys to exactly these.

    uv run python -m dw_purchasing.testing.seed_personas
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from dw_platform.adapters.persistence import tables
from dw_platform.testing.seed_env import sid
from dw_purchasing.testing.seed_accounts import seed_dw2_account

PURCHASING_KEY_PREFIX = "purchasing_"


@dataclass(frozen=True)
class Persona:
    subject: str
    tenant_slug: str
    roles: tuple[str, ...] = ()
    permission_sets: tuple[str, ...] = ()

    def keys_on(
        self, role_keys: Iterable[str], permission_set_keys: Iterable[str]
    ) -> tuple[list[str], list[str]]:
        """A membership's keys once this persona is applied: every other key
        untouched, its Purchasing keys exactly these."""
        return _with(role_keys, self.roles), _with(permission_set_keys, self.permission_sets)


def _with(keys: Iterable[str], purchasing: tuple[str, ...]) -> list[str]:
    return [k for k in keys if not k.startswith(PURCHASING_KEY_PREFIX)] + list(purchasing)


# The people are fictional, as the platform seed's are.
PERSONAS: tuple[Persona, ...] = (
    # The purchasing manager: approves the first two tiers, decides a rule
    # version someone else proposed.
    Persona("dev|binh.tran", "tenant-alpha", ("purchasing_head",)),
    # A buyer: reads the mailbox, sends requests on, asks for quotes, drafts
    # the orders.
    Persona("dev|khoa.lam", "tenant-alpha", ("purchasing_buyer",)),
    # A member of another department who writes their own request.
    Persona("dev|an.nguyen", "tenant-alpha", ("purchasing_requester",)),
    # The tenant's IT: configures DW2, never approves its own change.
    Persona("dev|tam.ngo", "tenant-alpha", ("purchasing_configurer",)),
    # The director: decides the last tier and nothing else of DW2's.
    Persona("dev|giang.do", "tenant-alpha", (), ("purchasing_director_approver",)),
    # Another tenant's buyer, for the cross-tenant checks.
    Persona("dev|dung.vo", "tenant-beta", ("purchasing_buyer",)),
)

# DW2's account where the demo's mock mailbox is bound.
DW2_DEMO_TENANTS: tuple[str, ...] = ("tenant-alpha",)


async def seed_purchasing_personas(
    database_url: str, personas: Sequence[Persona] = PERSONAS
) -> int:
    """Each persona's Purchasing keys on their membership in the tenant's main
    workspace, and DW2's account there; how many memberships changed."""
    m = tables.memberships
    engine = create_async_engine(database_url, poolclass=NullPool)
    written = 0
    try:
        async with engine.begin() as conn:
            for persona in personas:
                user_id = (
                    sa.select(tables.users.c.id)
                    .where(tables.users.c.subject == persona.subject)
                    .scalar_subquery()
                )
                row = (
                    await conn.execute(
                        sa.select(m.c.id, m.c.role_keys, m.c.permission_set_keys)
                        .where(
                            m.c.workspace_id == sid("workspace", f"{persona.tenant_slug}:main"),
                            m.c.user_id == user_id,
                        )
                        .with_for_update()
                    )
                ).one_or_none()
                if row is None:
                    raise LookupError(
                        f"{persona.subject} has no membership in {persona.tenant_slug}:"
                        " run the platform seed first"
                    )
                roles, sets = persona.keys_on(row.role_keys, row.permission_set_keys)
                if (roles, sets) != (list(row.role_keys), list(row.permission_set_keys)):
                    await conn.execute(
                        sa.update(m)
                        .where(m.c.id == row.id)
                        .values(role_keys=roles, permission_set_keys=sets)
                    )
                    written += 1
            await seed_dw2_account(
                conn,
                [(sid("tenant", t), sid("workspace", f"{t}:main")) for t in DW2_DEMO_TENANTS],
            )
    finally:
        await engine.dispose()
    return written


def main() -> None:
    # Dev subjects with demo authority have no place in a deployed database.
    if os.environ.get("DW_API_PROFILE", "local") not in {"local", "test"}:
        sys.exit("refusing: demo personas are for the local and test profiles only")
    database_url = os.environ.get("DW_DATABASE_URL")
    if not database_url:
        sys.exit("DW_DATABASE_URL is not set (source .env): the migrator's URL")
    written = asyncio.run(seed_purchasing_personas(database_url))
    print(f"{written} Purchasing persona membership(s) written; DW2's account in the demo")


if __name__ == "__main__":
    main()
