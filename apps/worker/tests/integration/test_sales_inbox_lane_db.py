"""DW1's mailbox lane as the worker wires it, against real Postgres (ticket 16).

`build_sales_inbox_lane` is the whole lane: DW1 built by the call the API
makes, a LangGraph runner of the worker's own over Postgres, and DW1's service
account resolved by the platform's membership lookup as `dw_app`. Nothing is
faked but object storage, which processing never touches. Each test has its
own tenant, the mock mailbox bound to it, and the account the demo seed gives.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from dw_agent_runtime.adapters.runtime_tables import worker_runs
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_observability.telemetry import NullTelemetry
from dw_platform.adapters.persistence import tables
from dw_platform.domain.audit import system_actor
from dw_platform.testing.seed_env import sid
from dw_sales.adapters.mock.fixtures import DATA_DIR
from dw_sales.adapters.persistence import tables as sales_tables
from dw_sales.application.inbox_lane import SALES_INBOX_LANE, InboxLane, dw1_subject
from dw_sales.application.ports import SalesScope
from dw_sales.testing.seed_personas import seed_dw1_accounts
from dw_worker.main import build_sales_inbox_lane
from dw_worker.settings import WorkerSettings

pytestmark = pytest.mark.integration

# The fictional mock mailbox, counted from its fixture: a number typed here
# went stale twice as messages were added (`dw_sales/adapters/mock/README.md`).
MAILBOX = len(json.loads((DATA_DIR / "inbox.json").read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Tenancy:
    slug: str
    tenant: uuid.UUID
    workspace: uuid.UUID


@pytest.fixture
async def migrator(worker_db: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(worker_db.migrator, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_sessions(
    worker_db: DatabaseUrls,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(worker_db.app, poolclass=NullPool)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _tenancy(migrator: AsyncEngine, *, plan: str = "professional") -> Tenancy:
    """A fresh tenant with ids the demo seed derives from its slug."""
    slug = f"t-{uuid.uuid4().hex[:12]}"
    tenancy = Tenancy(slug, sid("tenant", slug), sid("workspace", f"{slug}:main"))
    async with migrator.begin() as conn:
        await conn.execute(
            sa.insert(tables.tenants).values(id=tenancy.tenant, slug=slug, name="Công ty thử")
        )
        await conn.execute(
            sa.insert(tables.workspaces).values(
                id=tenancy.workspace, tenant_id=tenancy.tenant, slug="main", name="Main"
            )
        )
        await conn.execute(
            sa.insert(tables.entitlements).values(
                id=uuid.uuid4(), tenant_id=tenancy.tenant, plan_id=plan
            )
        )
    return tenancy


def _lane(
    worker_db: DatabaseUrls, sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> tuple[InboxLane, SalesScope]:
    settings = WorkerSettings(  # type: ignore[call-arg]
        profile="test",
        database_url=worker_db.app,
        s3_endpoint_url="http://127.0.0.1:1",
        s3_access_key="unused",
        s3_secret_key="unused",
        qdrant_url=None,
        model_provider="mock",
        sales_demo_tenant_id=str(tenancy.tenant),
        sales_demo_workspace_id=str(tenancy.workspace),
    )
    built = build_sales_inbox_lane(
        settings, sessions, clock=SystemClock(), ids=Uuid4Generator(), telemetry=NullTelemetry()
    )
    assert built is not None
    return built


async def _messages(migrator: AsyncEngine, tenancy: Tenancy) -> dict[str, str]:
    m = sales_tables.messages
    async with migrator.connect() as conn:
        rows = await conn.execute(
            sa.select(m.c.message_id, m.c.disposition).where(m.c.workspace_id == tenancy.workspace)
        )
        return {row.message_id: row.disposition for row in rows}


async def _runs(migrator: AsyncEngine, tenancy: Tenancy) -> list[Any]:
    r = worker_runs
    async with migrator.connect() as conn:
        return list(
            await conn.execute(
                sa.select(r.c.requested_by, r.c.actor_scopes, r.c.actor_roles).where(
                    r.c.tenant_id == tenancy.tenant
                )
            )
        )


async def _account(migrator: AsyncEngine, tenancy: Tenancy) -> uuid.UUID:
    async with migrator.connect() as conn:
        return (
            await conn.execute(
                sa.select(tables.users.c.id).where(
                    tables.users.c.subject == dw1_subject(tenancy.tenant)
                )
            )
        ).scalar_one()


async def test_dw1s_account_processes_the_whole_mailbox_once_and_the_lane_audits_as_itself(
    worker_db: DatabaseUrls,
    migrator: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    tenancy = await _tenancy(migrator)
    await seed_dw1_accounts(worker_db.migrator, [tenancy.slug])
    account = await _account(migrator, tenancy)
    lane, scope = _lane(worker_db, app_sessions, tenancy)

    tick = await lane.tick(scope)

    assert (len(tick.processed), tick.stopped) == (MAILBOX, None)
    assert set(await _messages(migrator, tenancy)) == set(tick.processed)
    runs = await _runs(migrator, tenancy)
    assert len(runs) == MAILBOX
    assert {(r.requested_by, tuple(r.actor_scopes), tuple(r.actor_roles)) for r in runs} == {
        (account, ("sales.inbox.process",), ())
    }
    async with migrator.connect() as conn:
        audit = list(
            await conn.execute(
                sa.select(
                    tables.audit_events.c.action,
                    tables.audit_events.c.actor_id,
                    tables.audit_events.c.details,
                ).where(tables.audit_events.c.tenant_id == tenancy.tenant)
            )
        )
    lane_rows = [row for row in audit if row.action == "sales.message.processed_by_lane"]
    assert len(lane_rows) == MAILBOX
    assert {row.actor_id for row in lane_rows} == {system_actor(SALES_INBOX_LANE).value}
    assert {row.details["actor"] for row in lane_rows} == {"system:sales_inbox"}
    # Every other row the processing wrote is the account's, never a person's.
    assert {row.actor_id for row in audit if row not in lane_rows} <= {account}

    again = await lane.tick(scope)

    assert again.processed == ()
    assert len(await _runs(migrator, tenancy)) == MAILBOX


async def test_over_the_plans_runs_the_rest_of_the_mailbox_waits(
    worker_db: DatabaseUrls,
    migrator: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """`basic` allows 20 runs a day: the lane gets 20 and no more."""
    tenancy = await _tenancy(migrator, plan="basic")
    await seed_dw1_accounts(worker_db.migrator, [tenancy.slug])
    lane, scope = _lane(worker_db, app_sessions, tenancy)

    tick = await lane.tick(scope)

    assert (len(tick.processed), tick.stopped) == (20, "quota")
    assert len(await _messages(migrator, tenancy)) == 20
    assert len(await _runs(migrator, tenancy)) == 20


async def test_a_paused_workspace_spends_no_run(
    worker_db: DatabaseUrls,
    migrator: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    tenancy = await _tenancy(migrator)
    await seed_dw1_accounts(worker_db.migrator, [tenancy.slug])
    async with migrator.begin() as conn:
        await conn.execute(
            sa.insert(sales_tables.worker_state).values(
                tenant_id=tenancy.tenant,
                workspace_id=tenancy.workspace,
                paused=True,
                changed_by=uuid.uuid4(),
                changed_at=sa.func.now(),
            )
        )
    lane, scope = _lane(worker_db, app_sessions, tenancy)

    tick = await lane.tick(scope)

    assert (tick.processed, tick.stopped) == ((), "paused")
    assert await _messages(migrator, tenancy) == {}
    assert await _runs(migrator, tenancy) == []


async def test_a_tenant_without_dw1s_account_gets_no_lane_work(
    worker_db: DatabaseUrls,
    migrator: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    tenancy = await _tenancy(migrator)
    lane, scope = _lane(worker_db, app_sessions, tenancy)

    tick = await lane.tick(scope)

    assert (tick.processed, tick.stopped) == ((), "no_account")
    assert await _runs(migrator, tenancy) == []
