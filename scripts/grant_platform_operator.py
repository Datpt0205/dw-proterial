"""Add a signed-in user to the Platform Operator allowlist (ADR-002).

The first-operator bootstrap. The operator-management UI is itself
operator-gated, so the very first one has to be added directly, as the migrator
role (BYPASSRLS) — the same trust level as the seed.

The person must have signed in once first (SSO creates their identity); this
adds them to ``platform.platform_operators`` by email. Idempotent.

A Platform Operator can create/lock tenants and assign Org Admins, but — by the
grants on the provisioning role — reads no tenant's business data (ADR-001 §3).

    DW_DATABASE_URL=postgresql+asyncpg://dw_migrator:...@host/dw \
        uv run python scripts/grant_platform_operator.py --email datpt142@fpt.com
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine

from dw_platform.adapters.persistence import tables


async def _run(database_url: str, email: str, note: str | None) -> int:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            user = (
                await conn.execute(
                    sa.select(tables.users.c.id, tables.users.c.display_name).where(
                        sa.func.lower(tables.users.c.email) == email.strip().lower()
                    )
                )
            ).first()
            if user is None:
                print(
                    f"No user with email {email!r} has signed in yet. "
                    "Ask them to log in once, then re-run this.",
                    file=sys.stderr,
                )
                return 1

            await conn.execute(
                pg_insert(tables.platform_operators)
                .values(user_id=user.id, note=note, created_by=user.id)
                .on_conflict_do_nothing(index_elements=["user_id"])
            )
        print(f"{user.display_name} <{email}> is now a Platform Operator.")
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default="datpt142@fpt.com", help="the user's email")
    parser.add_argument("--note", default=None, help="optional note on why")
    args = parser.parse_args()

    database_url = os.environ.get("DW_DATABASE_URL")
    if not database_url:
        print("DW_DATABASE_URL is required (the migrator connection).", file=sys.stderr)
        return 1
    return asyncio.run(_run(database_url, args.email, args.note))


if __name__ == "__main__":
    raise SystemExit(main())
