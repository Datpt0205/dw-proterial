"""DW1's demo start state, the same on every run: no Sales case, an unread
mailbox, DW1 running, and the personas seeded.

What it removes, in the tenants the personas belong to (and nowhere else):
every order and quote case with its revisions, lines and findings, the case
events, the message log, the sources served, the artifact records and the
pause switch. It writes nothing to the audit log, which is append-only: the
trail of earlier rehearsals stays, as it would in a real tenant.

Artifact bytes already in object storage are not deleted. Their records are
gone, so nothing serves them; tenant offboarding purges them by prefix.

Then it runs the full demo seed (`seed_personas`: the platform seed, then the
Sales keys), so a persona whose role was changed by hand is reset too.

Local and test profiles only, as the migrator (the one role that may delete
across these tables; the app role may not touch an append-only one):

    set -a; . ./.env; set +a
    uv run python -m dw_sales.testing.demo_reset

or `make demo-reset`, which also gives every persona a Keycloak login.
"""

from __future__ import annotations

import asyncio
import os
import sys

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from dw_platform.testing.seed_env import sid
from dw_sales.adapters.persistence import tables
from dw_sales.testing.seed_personas import PERSONAS, seed_demo

# Children first is not needed (every child cascades from its case), but the
# logs that name a case without a foreign key are listed explicitly.
_CLEARED = (
    tables.case_events,
    tables.source_served,
    tables.artifacts,
    tables.messages,
    tables.worker_state,
    tables.order_cases,
    tables.quote_cases,
)


def demo_tenants() -> list[object]:
    """The tenants the personas sign in to: the only ones a reset touches."""
    return sorted({sid("tenant", persona.tenant_slug) for persona in PERSONAS}, key=str)


async def clear_sales_cases(database_url: str) -> dict[str, int]:
    """Delete the demo tenants' Sales rows; how many went from each table."""
    tenants = demo_tenants()
    engine = create_async_engine(database_url, poolclass=NullPool)
    removed: dict[str, int] = {}
    try:
        async with engine.begin() as conn:
            for table in _CLEARED:
                result = await conn.execute(sa.delete(table).where(table.c.tenant_id.in_(tenants)))
                removed[table.name] = result.rowcount
    finally:
        await engine.dispose()
    return removed


async def _reset(database_url: str) -> None:
    removed = await clear_sales_cases(database_url)
    print("sales rows removed: " + ", ".join(f"{k}={v}" for k, v in removed.items()))
    await seed_demo(database_url)


def main() -> None:
    if os.environ.get("DW_API_PROFILE", "local") not in {"local", "test"}:
        sys.exit("refusing: the demo reset deletes Sales cases; local and test profiles only")
    database_url = os.environ.get("DW_DATABASE_URL")
    if not database_url:
        sys.exit("DW_DATABASE_URL is not set (source .env): the migrator's URL")
    asyncio.run(_reset(database_url))


if __name__ == "__main__":
    main()
