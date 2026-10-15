"""DW1's demo personas: the Sales roles and permission sets on the platform
seed's memberships, per the spec's actor table (ticket 11).

Who owns which row: a user and their membership are platform rows, created by
``dw_platform.testing.seed_env`` with platform roles only. This module adds the
``sales_*`` keys to those memberships, because the platform seed must not name
a context. It writes no person and creates no person's membership: a persona
whose membership is missing fails loudly, since the platform seed was not run
first.

The one account it does create is not a person: DW1's own service account in
the demo tenant ("DW1 (tài khoản dịch vụ)", ticket 16), which the worker's
mailbox lane acts under (``seed_dw1_accounts``). It holds the role
``sales_dw1`` (``sales.inbox.process``) and nothing else, has no email, and is
not in the sign-in roster.

Each write passes the database's separation-of-duty trigger, so a persona that
broke a rule (tenant IT holding a price scope) cannot be seeded at all.

Re-running is a no-op: a membership already holding exactly its Sales keys is
not written. The platform seed sets a membership's roles outright, so the full
seed is the platform seed and then this one, in that order: run after this one,
the platform seed would take the Sales roles off again.

Run both against the dev database (local profile only):

    set -a; . ./.env; set +a
    uv run python -m dw_sales.testing.seed_personas
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from dw_platform.adapters.persistence import tables
from dw_platform.testing.seed_env import seed_test_env, sid
from dw_sales.application.inbox_lane import DW1_ROLE, DW1_SERVICE_ACCOUNT, dw1_subject

# The catalogue keys this context owns (CONTEXT.md, "Roles and permission
# sets"). A key with this prefix on a persona's membership is the seed's to set;
# every other key belongs to the platform and is kept as it is.
SALES_KEY_PREFIX = "sales_"


@dataclass(frozen=True)
class Persona:
    """A seeded subject and the Sales keys their membership holds."""

    subject: str
    tenant_slug: str
    roles: tuple[str, ...] = ()
    permission_sets: tuple[str, ...] = ()

    def keys_on(
        self, role_keys: Iterable[str], permission_set_keys: Iterable[str]
    ) -> tuple[list[str], list[str]]:
        """A membership's role and permission-set keys once this persona is
        applied: its platform keys untouched, its Sales keys exactly these."""
        return _with_sales(role_keys, self.roles), _with_sales(
            permission_set_keys, self.permission_sets
        )


def _with_sales(keys: Iterable[str], sales: tuple[str, ...]) -> list[str]:
    return [key for key in keys if not key.startswith(SALES_KEY_PREFIX)] + list(sales)


# The spec's actor table (`.claude/plans/sales/dw1-portal-demo/spec.md`). The
# people are fictional; none is a name from the customer's survey.
PERSONAS: tuple[Persona, ...] = (
    # PIC đơn hàng and the export-control PIC.
    Persona("dev|an.nguyen", "tenant-alpha", ("sales_pic",), ("sales_export_control",)),
    # PIC báo giá: sees other customers' prices, never approves. The platform
    # seed's `approver_boost` stays on her membership and carries no `sales.*`
    # scope, so she cannot approve a quotation, her own included.
    Persona("dev|dieu.hoang", "tenant-alpha", ("sales_pic",), ("sales_price_evidence",)),
    # Trưởng bộ phận: approves, never a quote he priced (the case refuses it).
    Persona("dev|giang.do", "tenant-alpha", ("sales_head",)),
    # The deputy approver: a PIC who may approve someone else's quote.
    Persona("dev|khoa.lam", "tenant-alpha", ("sales_pic",), ("sales_quote_approver",)),
    # Leadership: counts and times only.
    Persona("dev|ha.vu", "tenant-alpha", ("sales_viewer",)),
    # Listed with nothing, so a Sales key handed to them by hand is removed on
    # the next seed: tenant IT, the purchasing manager (the negative persona)
    # and the platform admin no walk-through uses.
    Persona("dev|tam.ngo", "tenant-alpha"),
    Persona("dev|binh.tran", "tenant-alpha"),
    Persona("dev|chi.le", "tenant-alpha"),
    # Another tenant's PIC, for the cross-tenant tests.
    Persona("dev|bao.pham", "tenant-beta", ("sales_pic",)),
)


async def seed_sales_personas(database_url: str, personas: Sequence[Persona] = PERSONAS) -> int:
    """Set each persona's Sales keys on their membership in the tenant's main
    workspace. Returns how many memberships were written; 0 on a re-run."""
    memberships = tables.memberships
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
                        sa.select(
                            memberships.c.id,
                            memberships.c.role_keys,
                            memberships.c.permission_set_keys,
                        )
                        .where(
                            memberships.c.workspace_id
                            == sid("workspace", f"{persona.tenant_slug}:main"),
                            memberships.c.user_id == user_id,
                        )
                        .with_for_update()
                    )
                ).one_or_none()
                if row is None:
                    raise LookupError(
                        f"{persona.subject} has no membership in {persona.tenant_slug}:"
                        " run the platform seed first"
                    )
                role_keys, permission_set_keys = persona.keys_on(
                    row.role_keys, row.permission_set_keys
                )
                if (role_keys, permission_set_keys) == (
                    list(row.role_keys),
                    list(row.permission_set_keys),
                ):
                    continue
                await conn.execute(
                    sa.update(memberships)
                    .where(memberships.c.id == row.id)
                    .values(role_keys=role_keys, permission_set_keys=permission_set_keys)
                )
                written += 1
    finally:
        await engine.dispose()
    return written


# The tenants whose mailbox the demo's mock is bound to: where DW1 has an
# account for its mailbox lane. tenant-beta's PIC has an empty mailbox and no
# lane, which is what the cross-tenant tests need of it.
DW1_ACCOUNT_TENANTS: tuple[str, ...] = ("tenant-alpha",)
DW1_ACCOUNT_NAME = DW1_SERVICE_ACCOUNT.display_name


async def seed_dw1_accounts(
    database_url: str, tenant_slugs: Sequence[str] = DW1_ACCOUNT_TENANTS
) -> None:
    """DW1's service account in each tenant's main workspace, holding the
    role ``sales_dw1`` and nothing else.

    Re-running resets the membership to exactly that, so a role or a
    permission set given to the account by hand is taken off again.
    """
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            for slug in tenant_slugs:
                tenant_id = sid("tenant", slug)
                subject = dw1_subject(tenant_id)
                user = pg_insert(tables.users).values(
                    id=sid("user", subject), subject=subject, display_name=DW1_ACCOUNT_NAME
                )
                await conn.execute(
                    user.on_conflict_do_update(
                        index_elements=["subject"],
                        set_={"display_name": user.excluded.display_name, "email": None},
                    )
                )
                user_id = (
                    await conn.execute(
                        sa.select(tables.users.c.id).where(tables.users.c.subject == subject)
                    )
                ).scalar_one()
                membership = pg_insert(tables.memberships).values(
                    id=sid("membership", f"{slug}:{subject}"),
                    tenant_id=tenant_id,
                    workspace_id=sid("workspace", f"{slug}:main"),
                    user_id=user_id,
                    role_keys=[DW1_ROLE],
                    permission_set_keys=[],
                )
                await conn.execute(
                    membership.on_conflict_do_update(
                        constraint="uq_memberships_scope_user",
                        set_={
                            "role_keys": membership.excluded.role_keys,
                            "permission_set_keys": membership.excluded.permission_set_keys,
                        },
                    )
                )
    finally:
        await engine.dispose()


async def seed_demo(database_url: str) -> None:
    await seed_test_env(database_url)
    written = await seed_sales_personas(database_url)
    await seed_dw1_accounts(database_url)
    # Imported here: it builds the Sales services, which this module's other
    # callers (the API's test conftest at import time) do not need.
    from dw_sales.testing.seed_rules import seed_demo_rules

    rules = await seed_demo_rules(database_url)
    print(
        f"platform seed done; {written} Sales persona membership(s) written;"
        f" DW1's service account in {', '.join(DW1_ACCOUNT_TENANTS)};"
        f" the demo tenant's own rules in force: {rules}"
    )


def main() -> None:
    # Dev subjects with demo authority have no place in a deployed database.
    if os.environ.get("DW_API_PROFILE", "local") not in {"local", "test"}:
        sys.exit("refusing: demo personas are for the local and test profiles only")
    database_url = os.environ.get("DW_DATABASE_URL")
    if not database_url:
        sys.exit("DW_DATABASE_URL is not set (source .env): the migrator's URL")
    asyncio.run(seed_demo(database_url))


if __name__ == "__main__":
    main()
