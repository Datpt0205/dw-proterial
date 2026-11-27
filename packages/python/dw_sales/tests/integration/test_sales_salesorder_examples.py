"""Worked examples in PostgreSQL, as the application role (ticket 38).

A pair is requested through the service, learned by the worker's step from
the id its outbox event carries, read back with its replay, and its files are
gone; "Gửi duyệt" marks it sent. Each negative is checked against rows that
are really there (read back as the migrator), so a zero is isolation and not
an empty table.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.errors import NotFoundError
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
    SqlOutboxRepository,
)
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.testing.scanners import NoMalware
from dw_sales.adapters.persistence.catalog import SqlCatalogUnitOfWorkFactory
from dw_sales.adapters.reader_client import ClientPoReaders, ClientSourceView
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.access import Gate
from dw_sales.application.ports import SalesScope
from dw_sales.application.salesorder_learning import (
    EXAMPLE_REQUESTED,
    SalesOrderExamples,
    SalesOrderExampleView,
    SalesOrderLearning,
)
from dw_sales.evals.graders import GIANG
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.rule_drafts import _PlatformRules, _policies
from dw_sales.evals.salesorder_rules import (
    Catalog,
    MappedPoReading,
    Proposals,
    converts,
    customers,
    file_cells,
    items,
    load_cases,
    pair,
    po_bytes,
    po_mapping,
    salesorder_bytes,
)
from dw_sales.evals.world import Directory

pytestmark = pytest.mark.integration

_REPO = Path(__file__).resolve().parents[5]
_CASES = load_cases(_REPO)
_PAIR = pair(_CASES, "SR02")


@pytest.fixture
def uow(app_sessions: async_sessionmaker[AsyncSession]) -> SqlCatalogUnitOfWorkFactory:
    return SqlCatalogUnitOfWorkFactory(
        app_sessions,
        audit=SqlAuditRepository,
        approvals=SqlApprovalRepository,
        outbox=SqlOutboxRepository,
    )


def _catalog(world: World) -> Catalog:
    master = _CASES["master"]
    return Catalog(customers(master), items(master), converts(master), tenant=world.alpha)


def _service(
    uow: SqlCatalogUnitOfWorkFactory, world: World, proposals: Proposals | None = None
) -> SalesOrderExamples:
    return SalesOrderExamples(
        uow,
        Gate(ScopeAuthorizationService()),
        SystemClock(),
        Uuid4Generator(),
        _catalog(world),
        _PlatformRules(_policies(_REPO).current()),
        proposals or Proposals(),
    )


def _learning(uow: SqlCatalogUnitOfWorkFactory, world: World) -> SalesOrderLearning:
    transport = InProcessReaderTransport()
    return SalesOrderLearning(
        uow=uow,
        po_reading=MappedPoReading(ClientPoReaders(transport), {"KHB": po_mapping(_PAIR)}),
        sheets=ClientSourceView(transport),
        scanner=NoMalware(),
        catalog=_catalog(world),
        rules=_PlatformRules(_policies(_REPO).current()),
        access=Directory((GIANG,)),
        model=Recorded(raw=_PAIR["gold"]),
        clock=SystemClock(),
        ids=Uuid4Generator(),
        worker_id="sales-dw1",
        worker_version="1.0.0",
    )


async def _count(migrator: AsyncEngine, sql: str, **params: object) -> int:
    async with migrator.connect() as conn:
        found = await conn.scalar(sa.text(sql), params)
    return int(found or 0)


async def _requested(uow: SqlCatalogUnitOfWorkFactory, world: World) -> SalesOrderExampleView:
    layout = _policies(_REPO).upload
    return await _service(uow, world).request(
        GIANG.context(world.alpha),
        "KHB",
        date.fromisoformat(_PAIR["received_on"]),
        ("po.xlsx", po_bytes(_PAIR)),
        ("SalesOrder.xlsx", salesorder_bytes(layout, file_cells(_PAIR))),
    )


async def _learned(
    uow: SqlCatalogUnitOfWorkFactory, world: World, migrator: AsyncEngine
) -> SalesOrderExampleView:
    """A pair requested in alpha and learned from its outbox event."""
    requested = await _requested(uow, world)
    async with migrator.connect() as conn:
        payload = await conn.scalar(
            sa.text(
                "SELECT payload FROM platform.outbox_events"
                " WHERE event_type = :type AND aggregate_id = :id"
            ),
            {"type": EXAMPLE_REQUESTED, "id": requested.example_id},
        )
    assert payload == {"example_id": str(requested.example_id)}
    learned = await _learning(uow, world).learn(world.alpha, uuid.UUID(payload["example_id"]))
    assert learned == "example replayed"
    return await _service(uow, world).get(GIANG.context(world.alpha), requested.example_id)


async def test_a_pair_is_learned_from_its_event_its_replay_kept_and_its_files_dropped(
    world: World, uow: SqlCatalogUnitOfWorkFactory, migrator: AsyncEngine
) -> None:
    view = await _learned(uow, world, migrator)
    assert view.status == "replayed" and view.submittable
    assert view.replay is not None and view.replay.matches
    assert view.rules is not None and len(view.rules.columns) == 5
    left = await _count(
        migrator,
        "SELECT count(*) FROM sales.salesorder_example_files WHERE example_id = :id",
        id=view.example_id,
    )
    assert left == 0
    actions = await _count(
        migrator,
        "SELECT count(*) FROM platform.audit_events WHERE resource_id = :id AND action IN"
        " ('sales.salesorder_example.requested', 'sales.salesorder_example.replayed')",
        id=str(view.example_id),
    )
    assert actions == 2
    listed = await _service(uow, world).for_customer(GIANG.context(world.alpha), "KHB")
    assert [v.example_id for v in listed] == [view.example_id]


async def test_a_sent_example_names_its_version_and_outlives_the_prune(
    world: World, uow: SqlCatalogUnitOfWorkFactory, migrator: AsyncEngine
) -> None:
    view = await _learned(uow, world, migrator)
    proposals = Proposals()
    sent = await _service(uow, world, proposals).submit(
        GIANG.context(world.alpha), view.example_id, "9.0.1"
    )
    shown = await _service(uow, world).for_version(GIANG.context(world.alpha), sent.version_id)
    assert (shown.example_id, shown.status, shown.version_id) == (
        view.example_id,
        "submitted",
        sent.version_id,
    )
    # A request a month later drops what was never sent, never a sent one.
    async with uow(world.alpha) as work:
        assert await work.examples.prune(view.requested_at + timedelta(days=60)) == 0
        await work.commit()
    assert (await _service(uow, world).get(GIANG.context(world.alpha), view.example_id)).status == (
        "submitted"
    )


async def test_an_outsider_reads_no_example(
    world: World,
    uow: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
) -> None:
    # A queued one keeps its files: both tables hold rows of alpha's.
    queued = await _requested(uow, world)
    held = await _count(
        migrator,
        "SELECT count(*) FROM sales.salesorder_example_files WHERE example_id = :id",
        id=queued.example_id,
    )
    assert held == 2, "the owner's rows are there: the zeros below are isolation"
    for outsider in (world.beta, world.alpha_other):
        with pytest.raises(NotFoundError):
            await _service(uow, world).get(GIANG.context(outsider), queued.example_id)
        # Asked of the policy alone: no WHERE names the scope here.
        async with tenant_session(
            app_sessions, TenantScope(outsider.tenant_id.value, outsider.workspace_id.value)
        ) as session:
            seen = [
                (await session.execute(sa.text(f"SELECT count(*) FROM sales.{table}"))).scalar()
                for table in ("salesorder_examples", "salesorder_example_files")
            ]
        assert seen == [0, 0], outsider


async def test_an_outsider_cannot_write_into_the_owners_scope(
    world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    owner, outsider = world.alpha, world.beta
    with pytest.raises(DBAPIError, match="row-level security"):
        async with tenant_session(
            app_sessions, TenantScope(outsider.tenant_id.value, outsider.workspace_id.value)
        ) as session:
            await session.execute(
                sa.text(
                    "INSERT INTO sales.salesorder_examples (id, tenant_id, workspace_id,"
                    " customer_code, status, requested_by, requested_at, received_on,"
                    " po_file_name, po_sha256, po_size, salesorder_file_name,"
                    " salesorder_sha256, salesorder_size)"
                    " VALUES (gen_random_uuid(), :t, :w, 'KHB', 'queued', gen_random_uuid(),"
                    " now(), current_date, 'p.xlsx', repeat('0', 64), 1, 's.xlsx',"
                    " repeat('0', 64), 1)"
                ),
                {"t": owner.tenant_id.value, "w": owner.workspace_id.value},
            )


async def test_the_database_refuses_what_an_example_cannot_be(
    world: World, uow: SqlCatalogUnitOfWorkFactory, migrator: AsyncEngine
) -> None:
    view = await _learned(uow, world, migrator)
    for change, constraint in (
        ("status = 'drafted', rules = NULL", "ck_salesorder_examples_status"),
        # Rules belong to a replayed or sent example only.
        ("status = 'refused'", "ck_salesorder_examples_rules"),
        # Sent names its version, and only sent does.
        ("status = 'submitted'", "ck_salesorder_examples_submitted"),
        ("version_id = gen_random_uuid()", "ck_salesorder_examples_submitted"),
        ("error = 'x'", "ck_salesorder_examples_error"),
        ("customer_code = 'kh b'", "ck_salesorder_examples_customer_code"),
        ("po_sha256 = 'x'", "ck_salesorder_examples_files"),
    ):
        async with migrator.connect() as conn:
            with pytest.raises(sa.exc.IntegrityError, match=constraint):
                await conn.execute(
                    sa.text(f"UPDATE sales.salesorder_examples SET {change} WHERE id = :id"),
                    {"id": view.example_id},
                )


async def test_an_example_file_is_never_rewritten(
    world: World,
    uow: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    queued = await _requested(uow, world)
    scope: SalesScope = world.alpha
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_session(
            app_sessions, TenantScope(scope.tenant_id.value, scope.workspace_id.value)
        ) as session:
            await session.execute(
                sa.text(
                    "UPDATE sales.salesorder_example_files SET content = 'x' WHERE example_id = :id"
                ),
                {"id": queued.example_id},
            )
