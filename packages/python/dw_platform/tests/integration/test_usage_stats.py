"""Integration: the F6 usage-stats read over the real ledger, under RLS.

The cross-tenant test is the one that matters: an Org Admin of one company
must never see another company's spend. The screen is tenant-level by design
(the ledger's RLS policy is tenant-only), so an admin in ANOTHER workspace of
the same tenant still sees the rows — asserted here on purpose, so a future
per-workspace narrowing is a deliberate change, not an accident.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_kernel.ports import SystemClock
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.usage_stats_repo import SqlUsageStatsRepository
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.usage_stats import USAGE_READ, UsageStatsService
from dw_platform.testing.seed_env import seed_test_env

pytestmark = pytest.mark.integration

ALPHA = uuid.UUID("d6b43d0e-c3c6-5dbc-bc08-150621bd9a5d")
ALPHA_WS = uuid.UUID("64764894-718d-5558-ba17-9a2949214063")

_NOW = datetime.now(tz=UTC)


@pytest.fixture
async def app_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    await seed_test_env(db_urls.migrator)
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def migrator_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.migrator, poolclass=NullPool)
    yield engine
    await engine.dispose()


def _admin(tenant: uuid.UUID = ALPHA, workspace: uuid.UUID = ALPHA_WS) -> AccessContext:
    return AccessContext(
        tenant_id=tenant,
        workspace_id=workspace,
        principal_id=uuid.uuid4(),
        roles=frozenset({"org_admin"}),
        scopes=frozenset({USAGE_READ}),
        plan_id="professional",
    )


def _service(engine: AsyncEngine) -> UsageStatsService:
    repo = SqlUsageStatsRepository(async_sessionmaker(engine, expire_on_commit=False))
    return UsageStatsService(repo=repo, authz=ScopeAuthorizationService(), clock=SystemClock())


async def _ledger_row(
    migrator: AsyncEngine,
    *,
    tenant: uuid.UUID,
    workspace: uuid.UUID,
    run_id: uuid.UUID,
    worker_id: str,
    cost: float | None,
    input_tokens: int = 1000,
    output_tokens: int = 100,
    at: datetime | None = None,
) -> None:
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO platform.model_usage_ledger "
                "(id, tenant_id, workspace_id, run_id, worker_id, task, provider, model,"
                " input_tokens, output_tokens, cost_usd, created_at) VALUES "
                "(:id, :tenant, :workspace, :run, :worker, 'agent_loop', 'mock', 'mock',"
                " :inp, :out, :cost, :at)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant": tenant,
                "workspace": workspace,
                "run": run_id,
                "worker": worker_id,
                "inp": input_tokens,
                "out": output_tokens,
                "cost": cost,
                "at": at or _NOW,
            },
        )


async def _tool_row(
    migrator: AsyncEngine, *, tenant: uuid.UUID, workspace: uuid.UUID, status: str
) -> None:
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO platform.tool_executions "
                "(id, tenant_id, workspace_id, tool_name, tool_version, status,"
                " input_hash, attempts, started_at) VALUES "
                "(:id, :tenant, :workspace, 'intel.search_web', '1.1.0', :status,"
                " 'h', 1, :at)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant": tenant,
                "workspace": workspace,
                "status": status,
                "at": _NOW,
            },
        )


async def _ensure_partition(migrator: AsyncEngine, at: datetime) -> None:
    """The monthly partition an out-of-window row lands in.

    Production has an operational job creating partitions ahead (0024); a
    fresh test database only carries the migration's initial months, so a
    row 40 days back needs its month made first — same DDL the job runs.
    """
    start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start + timedelta(days=32)).replace(day=1)
    name = f"model_usage_ledger_{start:%Y_%m}"
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(
                f"CREATE TABLE IF NOT EXISTS platform.{name} "
                "PARTITION OF platform.model_usage_ledger "
                f"FOR VALUES FROM ('{start:%Y-%m-%d}') TO ('{end:%Y-%m-%d}')"
            )
        )


async def _new_tenant(migrator: AsyncEngine, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    async with migrator.begin() as conn:
        await conn.execute(
            sa.insert(tables.tenants).values(id=tenant_id, slug=slug, name=slug.upper())
        )
        await conn.execute(
            sa.insert(tables.workspaces).values(
                id=workspace_id, tenant_id=tenant_id, slug="main", name="Main"
            )
        )
    return tenant_id, workspace_id


async def test_the_ledger_groups_by_usecase_and_stays_inside_the_tenant(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    run_a, run_b = uuid.uuid4(), uuid.uuid4()
    # Two calls of one run + one call of another run for one usecase — one of
    # them unpriced — and an old row outside the window that must not count.
    await _ledger_row(
        migrator_engine,
        tenant=ALPHA,
        workspace=ALPHA_WS,
        run_id=run_a,
        worker_id="sales_crm.stakeholder_digest",
        cost=0.001,
    )
    await _ledger_row(
        migrator_engine,
        tenant=ALPHA,
        workspace=ALPHA_WS,
        run_id=run_a,
        worker_id="sales_crm.stakeholder_digest",
        cost=None,
    )
    await _ledger_row(
        migrator_engine,
        tenant=ALPHA,
        workspace=ALPHA_WS,
        run_id=run_b,
        worker_id="sales_crm.stakeholder_digest",
        cost=0.002,
    )
    old_at = _NOW - timedelta(days=40)
    await _ensure_partition(migrator_engine, old_at)
    await _ledger_row(
        migrator_engine,
        tenant=ALPHA,
        workspace=ALPHA_WS,
        run_id=uuid.uuid4(),
        worker_id="sales_crm.stakeholder_digest",
        cost=9.99,
        at=old_at,
    )
    await _tool_row(migrator_engine, tenant=ALPHA, workspace=ALPHA_WS, status="succeeded")
    await _tool_row(migrator_engine, tenant=ALPHA, workspace=ALPHA_WS, status="failed")

    # Another company's spend, which the Alpha admin must never see.
    other_tenant, other_ws = await _new_tenant(migrator_engine, f"t-{uuid.uuid4().hex[:8]}")
    await _ledger_row(
        migrator_engine,
        tenant=other_tenant,
        workspace=other_ws,
        run_id=uuid.uuid4(),
        worker_id="sales_chat",
        cost=5.0,
    )

    view = await _service(app_engine).overview(_admin(), 30)
    digest = next(u for u in view.usecases if u.worker_id == "sales_crm.stakeholder_digest")
    assert digest.runs == 2 and digest.model_calls == 3
    assert digest.input_tokens == 3000 and digest.output_tokens == 300
    assert digest.cost_usd == pytest.approx(0.003)
    assert digest.unpriced_calls == 1
    # Cross-tenant denial: the other company's usecase never appears.
    assert all(u.worker_id != "sales_chat" for u in view.usecases)
    assert any(t.tool_name == "intel.search_web" and t.failed == 1 for t in view.tools)
    assert any(d.worker_id == "sales_crm.stakeholder_digest" and d.runs == 2 for d in view.daily)

    # The other admin sees their own row and none of Alpha's.
    other_view = await _service(app_engine).overview(_admin(other_tenant, other_ws), 30)
    assert [u.worker_id for u in other_view.usecases] == ["sales_chat"]

    # Tenant-level by design: a different workspace of the SAME tenant still
    # sees the tenant's usage (the ledger policy is tenant-only).
    sibling = await _service(app_engine).overview(_admin(ALPHA, uuid.uuid4()), 30)
    assert any(u.worker_id == "sales_crm.stakeholder_digest" for u in sibling.usecases)
