"""DW1's demo start state, the same on every run: no Sales case, an unread
mailbox, DW1 running, and the personas seeded.

What it removes, in the tenants the personas belong to (and nowhere else):
every order and quote case with its revisions, lines and findings, the case
events, the message log, the sources served, the artifact records and the
pause switch; and DW1's runs, their checkpoints and the `sales.` approvals
they paused on with their decisions, so the approvals inbox starts empty and
a rehearsal does not spend the next one's daily runs. It writes nothing to
the audit log, which is append-only: the trail of earlier rehearsals stays,
as it would in a real tenant.

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
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from dw_agent_runtime.adapters.runtime_tables import (
    run_checkpoint_writes,
    run_checkpoints,
    worker_runs,
)
from dw_platform.adapters.persistence.tables import approval_decisions, approval_requests
from dw_platform.testing.seed_env import sid
from dw_sales.adapters.persistence import tables
from dw_sales.application.runs import APPROVAL_PREFIX
from dw_sales.application.support import DW1_WORKER_ID
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
            removed |= await _clear_dw1_runs(conn, tenants)
    finally:
        await engine.dispose()
    return removed


async def _clear_dw1_runs(conn: AsyncConnection, tenants: list[object]) -> dict[str, int]:
    """DW1's runs in the demo tenants, their checkpoints, and the Sales
    approvals they paused on with their decisions; nothing else's."""
    runs = sa.select(worker_runs.c.thread_id).where(
        worker_runs.c.tenant_id.in_(tenants), worker_runs.c.worker_id == DW1_WORKER_ID
    )
    sales_approvals = sa.select(approval_requests.c.id).where(
        approval_requests.c.tenant_id.in_(tenants),
        approval_requests.c.approval_type.startswith(APPROVAL_PREFIX, autoescape=True),
    )
    removed: dict[str, int] = {}
    for name, statement in (
        (
            "run_checkpoint_writes",
            sa.delete(run_checkpoint_writes).where(run_checkpoint_writes.c.thread_id.in_(runs)),
        ),
        (
            "run_checkpoints",
            sa.delete(run_checkpoints).where(run_checkpoints.c.thread_id.in_(runs)),
        ),
        (
            "approval_decisions",
            sa.delete(approval_decisions).where(
                approval_decisions.c.request_id.in_(sales_approvals)
            ),
        ),
        (
            "approval_requests",
            sa.delete(approval_requests).where(approval_requests.c.id.in_(sales_approvals)),
        ),
        (
            "worker_runs",
            sa.delete(worker_runs).where(
                worker_runs.c.tenant_id.in_(tenants), worker_runs.c.worker_id == DW1_WORKER_ID
            ),
        ),
    ):
        removed[name] = (await conn.execute(statement)).rowcount
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
