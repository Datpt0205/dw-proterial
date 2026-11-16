"""Ticket 16 in PostgreSQL, as the application role.

- `ck_quote_cases_ycbg_no` holds a recorded number to Bravo's shape, by the
  same pattern the domain holds (asked of the database, failure-modes #4);
- a Bravo YCBG export is uploaded, read by the worker's step and its result
  recorded on the case waiting under the number, and the bytes are gone;
- another workspace or tenant sees neither the export nor the case, and a
  number its case holds matches nothing here.

Each negative is checked against rows that are really there (read back as
the migrator), so a zero is isolation and not an empty table.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import sqlalchemy as sa
from sales_harness import DW1, T0, QuoteRun, World
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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
from dw_sales.adapters.persistence.quotes import SqlQuoteCaseLookup
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.adapters.reader_client import ClientTableReader
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.access import Gate
from dw_sales.application.case_store import CaseEvent, CaseOrigin
from dw_sales.application.ports import SalesScope
from dw_sales.application.ycbg_exports import (
    YCBG_EXPORT_UPLOADED,
    DesignChecks,
    YcbgExportReading,
    YcbgExportService,
)
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.quotes import YCBG_NO_PATTERN, QuoteStatus
from dw_sales.evals.graders import DIEU
from dw_sales.evals.world import Directory
from dw_sales.testing.bravo_ycbg_export import ExportRow, ycbg_export_xlsx

pytestmark = pytest.mark.integration

_CAPS = IntakeCaps(
    max_attachment_bytes=10 * 1024 * 1024,
    max_unpacked_bytes=50 * 1024 * 1024,
    max_sheets=20,
    max_pages=200,
    max_cells=200_000,
)

M10_YCBG = "RFQ260930-030"
# M10's one line in the customer's words, as Sales enters it in Bravo.
_M10_WORDS = "MULTI-CORE CABLE 4C AWG22 STRANDED TINNED CU BRAID SHIELD GREY REEL 300M SPEC SP-5406"
SAMPLES = [
    "RFQ261110-002",
    "RFQ2611-2",
    "YCBG-2609-030",
    "rfq261110-002",
    "RFQ261110-0021",
    "RFQ261110-02",
    "RFQ261110-002\n",
    "XRFQ261110-002",
]


@asynccontextmanager
async def _bound(
    sessions: async_sessionmaker[AsyncSession], scope: SalesScope
) -> AsyncIterator[AsyncSession]:
    async with tenant_session(
        sessions, TenantScope(scope.tenant_id.value, scope.workspace_id.value)
    ) as session:
        yield session


async def _set_number(
    sessions: async_sessionmaker[AsyncSession], scope: SalesScope, case_id: object, number: str
) -> str | None:
    """The constraint writing ``number`` as the case's YCBG is refused on."""
    try:
        async with _bound(sessions, scope) as session:
            await session.execute(
                sa.text(
                    "UPDATE sales.quote_cases SET body = jsonb_set(body, '{ycbg,ycbg_no}',"
                    " to_jsonb(CAST(:number AS text))) WHERE id = :id"
                ),
                {"number": number, "id": case_id},
            )
    except IntegrityError as exc:
        return getattr(exc.orig.__cause__, "constraint_name", None)  # type: ignore[union-attr]
    return None


# ------------------------------------------------------- the column's CHECK --


async def test_the_database_matches_bravos_shape_exactly_as_the_domain_does(
    migrator: AsyncEngine,
) -> None:
    """PostgreSQL's regex engine, asked: the same verdict as Python's on every
    sample, and the constraint is the domain's pattern, validated."""
    async with migrator.connect() as conn:
        definition = await conn.scalar(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conname = 'ck_quote_cases_ycbg_no'"
            )
        )
        validated = await conn.scalar(
            sa.text(
                "SELECT convalidated FROM pg_constraint WHERE conname = 'ck_quote_cases_ycbg_no'"
            )
        )
        verdicts = {
            sample: await conn.scalar(
                sa.text("SELECT CAST(:s AS text) ~ CAST(:p AS text)"),
                {"s": sample, "p": YCBG_NO_PATTERN},
            )
            for sample in SAMPLES
        }

    assert YCBG_NO_PATTERN in str(definition)
    assert validated is True  # no row recorded before Bravo's shape here
    assert verdicts == {s: re.fullmatch(YCBG_NO_PATTERN, s) is not None for s in SAMPLES}
    assert verdicts["RFQ261110-002"] and not verdicts["RFQ2611-2"]


async def test_a_number_of_another_shape_is_refused_by_the_column(
    quote_run: QuoteRun, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    case_id = quote_run.steps[-1].case_id

    assert await _set_number(app_sessions, quote_run.scope, case_id, "RFQ2611-2") == (
        "ck_quote_cases_ycbg_no"
    )
    assert await _set_number(app_sessions, quote_run.scope, case_id, "YCBG-2609-030") == (
        "ck_quote_cases_ycbg_no"
    )
    assert await _set_number(app_sessions, quote_run.scope, case_id, "RFQ261110-002") is None


# ------------------------------------------------- the export, end to end --


@pytest.fixture
def exports(app_sessions: async_sessionmaker[AsyncSession]) -> SqlCatalogUnitOfWorkFactory:
    return SqlCatalogUnitOfWorkFactory(
        app_sessions,
        audit=SqlAuditRepository,
        approvals=SqlApprovalRepository,
        outbox=SqlOutboxRepository,
    )


def _service(
    exports: SqlCatalogUnitOfWorkFactory, uow: SqlSalesUnitOfWorkFactory
) -> YcbgExportService:
    return YcbgExportService(
        exports, uow, Gate(ScopeAuthorizationService()), SystemClock(), Uuid4Generator()
    )


def _reading(
    exports: SqlCatalogUnitOfWorkFactory,
    uow: SqlSalesUnitOfWorkFactory,
    sessions: async_sessionmaker[AsyncSession],
) -> YcbgExportReading:
    return YcbgExportReading(
        uow=exports,
        tables=ClientTableReader(InProcessReaderTransport(), _CAPS),
        scanner=NoMalware(),
        access=Directory((DIEU,)),
        checks=DesignChecks(uow, SqlQuoteCaseLookup(sessions), SystemClock(), Uuid4Generator()),
        clock=SystemClock(),
        ids=Uuid4Generator(),
    )


async def _waiting_m10(
    quote_run: QuoteRun, uow: SqlSalesUnitOfWorkFactory, scope: SalesScope
) -> uuid.UUID:
    """M10 as it stood when sent to Design, stored as a case of ``scope``."""
    sent = next(c for c in quote_run.steps if c.status is QuoteStatus.SENT_TO_DESIGN)
    case = sent.model_copy(update={"case_id": uuid.uuid4()})
    async with uow(scope) as work:
        await work.quotes.add(
            case,
            CaseOrigin(None, "release@1.0.0"),
            CaseEvent(action="quote.sent_to_design", actor=DW1, occurred_at=T0),
        )
        await work.commit()
    return case.case_id


async def test_an_export_is_read_onto_the_case_waiting_and_seen_by_no_one_else(
    quote_run: QuoteRun,
    uow: SqlSalesUnitOfWorkFactory,
    exports: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    world: World,
) -> None:
    # The run's M10 (in alpha) has moved past Design under the number; the
    # tenant's other workspace has one waiting under it.
    scope = world.alpha_other
    case_id = await _waiting_m10(quote_run, uow, scope)
    data = ycbg_export_xlsx(
        [
            ExportRow(M10_YCBG, None, "CLOSE", "QUOTE", None, "BP-26-0187", _M10_WORDS),
            ExportRow("RFQ260930-031", None, "CLOSE", "DECLINE", "không có vật liệu", None, "a"),
        ]
    )
    context = DIEU.context(scope)
    queued = await _service(exports, uow).upload(context, "ycbg.xlsx", data)

    done = await _reading(exports, uow, app_sessions).read(scope, queued.export_id)

    assert done == "export read"
    (read,) = await _service(exports, uow).latest(context)
    assert [(o.ycbg_no, o.outcome, o.case_id) for o in read.outcomes] == [
        (M10_YCBG, "recorded", case_id),
        ("RFQ260930-031", "no_case", None),
    ]
    async with uow(scope) as work:
        stored = await work.quotes.get(case_id)
    assert stored is not None and stored.case.design_check is not None
    assert stored.case.status is QuoteStatus.SENT_TO_DESIGN

    async with migrator.connect() as conn:
        files = await conn.scalar(
            sa.text("SELECT count(*) FROM sales.ycbg_export_files WHERE export_id = :id"),
            {"id": queued.export_id},
        )
        rows = await conn.scalar(
            sa.text("SELECT count(*) FROM sales.ycbg_exports WHERE id = :id"),
            {"id": queued.export_id},
        )
        events = await conn.scalar(
            sa.text(
                "SELECT count(*) FROM platform.outbox_events WHERE aggregate_id = :id"
                " AND event_type = :type"
            ),
            {"id": queued.export_id, "type": YCBG_EXPORT_UPLOADED},
        )
    assert (files, rows, events) == (0, 1, 1)

    # The tenant's other workspace, and another tenant: no export listed, and
    # the number finds only that workspace's own case, never this one.
    assert world.alpha == quote_run.scope
    lookup = SqlQuoteCaseLookup(app_sessions)
    for other in (world.alpha, world.beta):
        assert await _service(exports, uow).latest(DIEU.context(other)) == []
        async with _bound(app_sessions, other) as session:
            seen = await session.scalar(
                sa.text("SELECT count(*) FROM sales.ycbg_exports WHERE id = :id"),
                {"id": queued.export_id},
            )
        assert seen == 0
        found = await lookup.cases_for_ycbg(other, M10_YCBG)
        assert case_id not in {c.case_id for c in found}
        assert all(c.design_check is None for c in found)
    assert await lookup.cases_for_ycbg(world.beta, M10_YCBG) == []


async def test_a_connection_that_never_scoped_itself_reads_no_export(
    quote_run: QuoteRun,
    uow: SqlSalesUnitOfWorkFactory,
    exports: SqlCatalogUnitOfWorkFactory,
    sales_app_engine: AsyncEngine,
    migrator: AsyncEngine,
) -> None:
    data = ycbg_export_xlsx([ExportRow(M10_YCBG, None, "PENDING", description="a")])
    await _service(exports, uow).upload(DIEU.context(quote_run.scope), "ycbg.xlsx", data)

    async with migrator.connect() as conn:
        held = await conn.scalar(sa.text("SELECT count(*) FROM sales.ycbg_exports"))
    async with sales_app_engine.connect() as conn:
        seen = await conn.scalar(sa.text("SELECT count(*) FROM sales.ycbg_exports"))
        files = await conn.scalar(sa.text("SELECT count(*) FROM sales.ycbg_export_files"))

    assert held and held > 0
    assert (seen, files) == (0, 0)
