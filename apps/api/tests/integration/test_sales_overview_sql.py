"""The overview's figures and the work list from SQL (Sales ticket 24).

The demo is walked through the API (every message processed, orders prepared,
entered, cross-checked and confirmed, a quotation priced, submitted and
approved), and then:

- the SQL reader's figures equal those of the Python computation the service
  made before ticket 24 (`PythonOverviewReader`), run over the same cases,
  messages and events read back from the database;
- for several work filters, walking the SQL work list two rows a page returns
  exactly the rows the Python one returns at once, in the same order;
- every persona's `/my-work`, walked a page at a time, is what one large page
  holds;
- on a workspace with history, each branch of the paged query reads its
  partial index in order in a generic plan (the predicate and the due-date
  expression are written as the index's are);
- another tenant, and another workspace of the same tenant, read nothing.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sales_api_harness import AN, DIEU, GIANG, KHOA, Api, user_id
from sales_flow import (
    approve,
    cross_checked,
    dates,
    decide,
    order_of,
    process,
    replied,
    submitted,
    typed_as_read,
    uploaded,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.pagination import CursorPosition, Page, PageQuery, PageRequest, page_request
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.adapters.persistence.tenant_session import TenantScope, bind_tenant
from dw_platform.testing.seed_env import sid
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import LoggedEvent
from dw_sales.application.overview_ports import (
    NO_DUE,
    OpenOrder,
    OverviewFigures,
    WorkEntry,
    WorkFilter,
)
from dw_sales.application.overview_service import figure_basis
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import SALES_PIC_POOL, CaseKind
from dw_sales.domain.orders import OrderStatus
from dw_sales.evals.overview_memory import PythonOverviewReader

pytestmark = pytest.mark.integration

# Named rather than the whole mailbox, so the walk does not move with every
# message a later ticket adds to it.
DEMO_MAIL = ("M03", "M04", "M06", "M07", "M11", "M15", "M16", "M17", "M31")

ALPHA = SalesScope(
    TenantId(sid("tenant", "tenant-alpha")), WorkspaceId(sid("workspace", "tenant-alpha:main"))
)


@pytest.fixture
async def demo(api: Api) -> AsyncIterator[Api]:
    """The demo walked: M01 confirmed, M27 entered in Bravo awaiting its
    cross-check, M10 approved, and the rest of `DEMO_MAIL` processed."""
    an, dieu, giang = api.as_(AN), api.as_(DIEU), api.as_(GIANG)
    await approve(giang, await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25")))
    m01, m27 = await order_of(an, "M01"), await order_of(an, "M27")
    # A PDF in review, a PO with findings, a revision, and mail routed to Sales.
    for message_id in DEMO_MAIL:
        await process(an, message_id)
    m01 = await cross_checked(dieu, await uploaded(an, m01))
    await decide(an, m01, "confirm", {"delivery_dates": dates(m01)})
    # Its uncertain values typed as read: a maker's corrections.
    await uploaded(an, await typed_as_read(an, m27))
    yield api


def _uow(api: Api) -> SqlSalesUnitOfWorkFactory:
    return SqlSalesUnitOfWorkFactory(
        api.sessions, audit=SqlAuditRepository, approvals=SqlApprovalRepository
    )


async def _python_reader(api: Api, scope: SalesScope) -> PythonOverviewReader:
    """The Python computation over what the database holds for ``scope``."""
    async with _uow(api)(scope) as work:
        orders = list(await work.orders.list_all())
        quotes = list(await work.quotes.list_all())
        messages = list(await work.messages.list_all())
    async with api.sessions() as session, session.begin():
        await bind_tenant(
            session,
            TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value),
        )
        rows = await session.execute(
            sa.text(
                "SELECT case_kind, case_id, case_version, action, from_status, to_status,"
                " actor_kind, occurred_at FROM sales.case_events"
                " ORDER BY occurred_at, case_version, id"
            )
        )
        events = [
            LoggedEvent(
                case_kind=CaseKind(r.case_kind),
                case_id=r.case_id,
                case_version=r.case_version,
                action=r.action,
                from_status=r.from_status,
                to_status=r.to_status,
                actor_kind=r.actor_kind,
                occurred_at=r.occurred_at,
            )
            for r in rows
        ]
    return PythonOverviewReader(orders=orders, quotes=quotes, messages=messages, events=events)


def _comparable(figures: OverviewFigures) -> dict[str, Any]:
    """The figures as plain, ordered data."""
    plain = asdict(figures)
    plain["decided_inbox_ids"] = sorted(figures.decided_inbox_ids)
    plain["statuses"] = {
        kind.value: dict(sorted(counts.items())) for kind, counts in figures.statuses.items()
    }
    plain["export"] = sorted((step, month, n) for (step, month), n in figures.export.items())
    plain["findings_by_code"] = dict(sorted(figures.findings_by_code.items()))
    return plain


def _differences(sql: Any, python: Any, at: str = "") -> list[str]:
    """Where two figures disagree. Seconds agree to the microsecond, not to
    the last bit: a sum in SQL is exact and a sum of Python floats is not."""
    if isinstance(sql, float) and isinstance(python, float):
        return [] if math.isclose(sql, python, rel_tol=1e-9, abs_tol=1e-6) else [at]
    if isinstance(sql, dict) and isinstance(python, dict):
        if sql.keys() != python.keys():
            return [f"{at}: keys {sorted(sql)} != {sorted(python)}"]
        return [d for k in sql for d in _differences(sql[k], python[k], f"{at}.{k}")]
    if isinstance(sql, list | tuple) and isinstance(python, list | tuple):
        if len(sql) != len(python):
            return [f"{at}: {sql} != {python}"]
        return [
            d
            for i, (a, b) in enumerate(zip(sql, python, strict=True))
            for d in _differences(a, b, f"{at}[{i}]")
        ]
    return [] if sql == python else [f"{at}: {sql!r} != {python!r}"]


async def test_the_sql_figures_are_the_python_figures(demo: Api) -> None:
    inbox = frozenset({"M01", "M02", "M03", "M10", "M99-not-processed"})
    basis = figure_basis(inbox)
    async with _uow(demo)(ALPHA) as work:
        sql = await work.overview.figures(basis)
    python = await (await _python_reader(demo, ALPHA)).figures(basis)

    assert _differences(_comparable(sql), _comparable(python)) == []
    # The comparison has something to compare: every kind of figure is there.
    assert sql.statuses[CaseKind.ORDER][OrderStatus.CONFIRMED.value] == 1
    assert sql.statuses[CaseKind.QUOTE]["approved"] == 1
    assert sql.decided_inbox_ids == {"M01", "M03", "M10"}
    assert sql.routed_to_sales >= 1
    assert all(sql.times[b].cases > 0 for b in ("dw", "sales", "approver"))
    assert sql.order_confirmation.cases == 1
    assert sql.lines_read > 0 and sql.lines_exact > 0 and sql.findings_by_code
    assert sql.orders_prepared_without_correction >= 1
    assert sql.a3_shadow >= 1 and sql.months and sql.export


def _filters() -> list[WorkFilter]:
    every_step = WorkFilter(
        principal_id=user_id(AN),
        order_statuses=frozenset(
            {
                OrderStatus.CHECKED,
                OrderStatus.IN_REVIEW,
                OrderStatus.PREPARED,
                OrderStatus.CROSS_CHECKED,
                OrderStatus.CHANGE_REVIEW,
            }
        ),
        quote_statuses=frozenset({"received", "ycbg_drafted", "approved", "sent"}),
        cross_checks=True,
        approvals=True,
        message_owners=frozenset({SALES_PIC_POOL}),
    )
    return [
        every_step,
        # Someone else's view: the assignee rule leaves An's cases out.
        replace(every_step, principal_id=user_id(DIEU)),
        # The approver who priced nothing, and no messages.
        replace(
            every_step,
            principal_id=user_id(KHOA),
            order_statuses=frozenset(),
            quote_statuses=frozenset(),
            cross_checks=False,
            message_owners=frozenset(),
        ),
        # Nothing at all.
        WorkFilter(
            principal_id=user_id(GIANG),
            order_statuses=frozenset(),
            quote_statuses=frozenset(),
            cross_checks=False,
            approvals=False,
            message_owners=frozenset(),
        ),
    ]


def _identity(entry: WorkEntry) -> tuple[str, str, str]:
    row = entry.row
    kind = type(row).__name__
    key = getattr(row, "case_id", None) or getattr(getattr(row, "case", None), "case_id", None)
    if key is None:
        key = row.disposition.message_id  # type: ignore[union-attr]
    return entry.position.group, kind, str(key)


async def _walk_sql(api: Api, wanted: WorkFilter, limit: int) -> list[WorkEntry]:
    query = PageQuery(key="test.work", filters={"principal": wanted.principal_id})
    cursor: str | None = None
    walked: list[WorkEntry] = []
    for _ in range(100):
        request = page_request(limit=limit, cursor=cursor, query=query)
        async with _uow(api)(ALPHA) as work:
            page: Page[WorkEntry] = await work.overview.work_page(wanted, request)
        walked.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            return walked
    raise AssertionError("the work list never ended")


async def test_the_sql_work_list_pages_through_what_python_lists(demo: Api) -> None:
    python = await _python_reader(demo, ALPHA)
    everything = PageRequest(limit=200, after=None, query=PageQuery(key="test.work"))
    for wanted in _filters():
        expected = (await python.work_page(wanted, everything)).items
        walked = await _walk_sql(demo, wanted, limit=2)
        # Messages sort by their row ids within one processing time, and the
        # Python store mints those differently; so compare as (due, row) runs
        # and check each list is in (due, received) order.
        assert sorted(map(_identity, walked)) == sorted(map(_identity, expected))
        keys = [(e.position.group, e.position.sort_value) for e in walked]
        assert keys == sorted(keys)
        assert len({_identity(e) for e in walked}) == len(walked), "a row came back twice"
    every = await _walk_sql(demo, _filters()[0], limit=2)
    assert {type(e.row).__name__ for e in every} >= {"OpenOrder", "LoggedMessage"}
    # An order with a short line is paged in its due date's group, read from
    # the column the repository wrote (M06: line 3, 2026-09-30); an order with
    # none is in the NO_DUE group with no date.
    inbox = (await demo.as_(AN).get("/inbox")).json()
    m06 = uuid.UUID(next(m["disposition"]["case_id"] for m in inbox if m["message_id"] == "M06"))
    orders = [
        (e.row.case_id, e.position.group, e.row.due)
        for wanted in _filters()
        for e in await _walk_sql(demo, wanted, limit=2)
        if isinstance(e.row, OpenOrder)
    ]
    assert {(group, due) for case_id, group, due in orders if case_id == m06} == {
        ("2026-09-30", date(2026, 9, 30))
    }, orders
    undated = [due for _, group, due in orders if group == NO_DUE]
    assert undated and all(due is None for due in undated), orders


async def test_my_work_walked_page_by_page_is_my_work_at_once(demo: Api) -> None:
    for subject in (AN, DIEU, GIANG, KHOA):
        persona = demo.as_(subject)
        whole = (await persona.get("/my-work", limit=200)).json()
        assert whole["next_cursor"] is None
        walked: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 1}
            if cursor:
                params["cursor"] = cursor
            response = await persona.get("/my-work", **params)
            assert response.status_code == 200, response.text
            page = response.json()
            walked.extend(page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert walked == whole["items"], subject
    # A cursor is the caller's: another person's is refused, not answered.
    an_page = (await demo.as_(AN).get("/my-work", limit=1)).json()
    if an_page["next_cursor"]:
        refused = await demo.as_(DIEU).get("/my-work", cursor=an_page["next_cursor"])
        assert refused.status_code == 422


async def test_another_tenant_or_workspace_reads_no_figure_and_no_work(
    demo: Api, migrator: AsyncEngine
) -> None:
    other_workspace = uuid.uuid4()
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO platform.workspaces (id, tenant_id, slug, name)"
                " VALUES (:w, :t, 'ke-toan-24', 'ke-toan-24')"
            ),
            {"w": other_workspace, "t": ALPHA.tenant_id.value},
        )
    beta = SalesScope(
        TenantId(sid("tenant", "tenant-beta")), WorkspaceId(sid("workspace", "tenant-beta:main"))
    )
    elsewhere = SalesScope(ALPHA.tenant_id, WorkspaceId(other_workspace))
    basis = figure_basis(frozenset({"M01"}))
    for scope in (beta, elsewhere):
        async with _uow(demo)(scope) as work:
            figures = await work.overview.figures(basis)
            page = await work.overview.work_page(
                _filters()[0], PageRequest(limit=200, after=None, query=PageQuery(key="t"))
            )
        assert page.items == ()
        assert figures.statuses == {CaseKind.ORDER: {}, CaseKind.QUOTE: {}}
        assert figures.decided_inbox_ids == frozenset()
        assert (figures.lines_read, figures.a3_shadow, figures.months) == (0, 0, ())
        assert all(spread.cases == 0 for spread in figures.times.values())


@pytest.fixture
async def history(api: Api, migrator: AsyncEngine) -> Api:
    """A workspace with history: 3,000 closed orders and 3,000 processed
    messages beside 100 open orders (a third of them due) and 100 messages
    routed to Sales, and one quotation, analysed. On a near-empty table a
    plan says nothing."""
    an = api.as_(AN)
    await process(an, "M10")
    at = datetime(2026, 10, 1, tzinfo=UTC)
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO sales.order_cases (id, tenant_id, workspace_id, customer_code,"
                " po_no, case_version, status, received_at, rules_version, catalog_as_of,"
                " cross_check_required, export_control_mode, changes, bravo_entry_compared,"
                " close_reason, closed_by, closed_at, release_manifest_ref, due)"
                " SELECT gen_random_uuid(), :t, :w, 'VLX', 'PO-H' || n, 2,"
                " CASE WHEN n <= 3000 THEN 'closed' ELSE 'in_review' END,"
                " CAST(:at AS timestamptz) - make_interval(mins => n),"
                " 'sales_order_rules@1.0.0', CAST(:at AS timestamptz), true, 'warn', '[]', false,"
                " CASE WHEN n <= 3000 THEN 'not_an_order' END,"
                " CASE WHEN n <= 3000 THEN CAST(:me AS uuid) END,"
                " CASE WHEN n <= 3000 THEN CAST(:at AS timestamptz) END, 'sha256:history',"
                " CASE WHEN n % 3 = 0 THEN to_char(DATE '2026-10-01' + n % 40, 'YYYY-MM-DD') END"
                " FROM generate_series(1, 3100) AS n"
            ),
            {
                "t": ALPHA.tenant_id.value,
                "w": ALPHA.workspace_id.value,
                "me": user_id(AN),
                "at": at,
            },
        )
        await conn.execute(
            sa.text(
                "INSERT INTO sales.messages (id, tenant_id, workspace_id, message_id,"
                " disposition, routing_reason, owner, processed_at)"
                " SELECT gen_random_uuid(), :t, :w, 'H' || n,"
                " CASE WHEN n <= 3000 THEN 'not_yet_processed' ELSE 'routed_to_sales' END,"
                " CASE WHEN n <= 3000 THEN NULL ELSE 'complaint' END,"
                " CASE WHEN n <= 3000 THEN NULL ELSE :pool END,"
                " CAST(:at AS timestamptz) - make_interval(mins => n)"
                " FROM generate_series(1, 3100) AS n"
            ),
            {
                "t": ALPHA.tenant_id.value,
                "w": ALPHA.workspace_id.value,
                "pool": SALES_PIC_POOL,
                "at": at,
            },
        )
    async with migrator.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        for table in ("order_cases", "quote_cases", "messages"):
            await conn.exec_driver_sql(f"ANALYZE sales.{table}")
    return api


async def test_each_branch_of_the_work_list_reads_its_partial_index_in_order(
    history: Api,
) -> None:
    """In a generic plan (sequential scans priced out, so a tiny quotation
    table does not decide it): each branch reads its partial index, whose
    predicate and due-date expression match what the statement writes, in
    the list's order, so the only sort is the merge of the three."""
    request = page_request(
        limit=20,
        cursor=None,
        query=PageQuery(key="test.work", filters={"principal": user_id(AN)}),
    )
    after = CursorPosition(
        sort_value=datetime(2026, 9, 30, 12, tzinfo=UTC), tiebreaker=uuid.uuid4(), group=NO_DUE
    )
    async with history.sessions() as session, session.begin():
        await bind_tenant(
            session,
            TenantScope(tenant_id=ALPHA.tenant_id.value, workspace_id=ALPHA.workspace_id.value),
        )
        plan = await _generic_plan(session, replace(request, after=after))
    for index in (
        "ix_order_cases_open_work",
        "ix_quote_cases_open_work",
        "ix_messages_routed_work",
    ):
        assert index in plan, plan
    assert plan.count("Sort Key") == 1, plan


async def _generic_plan(session: AsyncSession, request: PageRequest) -> str:
    """The plan of `work_page`'s keyset statement, prepared and forced generic."""
    captured: list[str] = []

    class _Capture:
        def __init__(self, inner: AsyncSession) -> None:
            self.inner = inner

        async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            if not captured:
                captured.append(statement)
            return await self.inner.execute(statement, *args, **kwargs)

    from dw_sales.adapters.persistence.overview import SqlOverviewReader

    await SqlOverviewReader(_Capture(session), ALPHA).work_page(_filters()[0], request)  # type: ignore[arg-type]
    connection = await session.connection()
    compiled = captured[0].compile(  # type: ignore[attr-defined]
        dialect=connection.dialect, compile_kwargs={"render_postcompile": True}
    )
    values = ", ".join(_literal(compiled.params[name]) for name in compiled.positiontup or ())
    await connection.exec_driver_sql("SET LOCAL plan_cache_mode = force_generic_plan")
    await connection.exec_driver_sql("SET LOCAL enable_seqscan = off")
    await connection.exec_driver_sql(f"PREPARE work_page AS {compiled}")
    rows = await connection.exec_driver_sql(f"EXPLAIN EXECUTE work_page({values})")
    return "\n".join(row[0] for row in rows)


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | tuple):
        return "ARRAY[" + ", ".join(_literal(v) for v in value) + "]::text[]" if value else "'{}'"
    if isinstance(value, int | float) and not isinstance(value, bool):
        return "NULL" if isinstance(value, float) and math.isnan(value) else str(value)
    return "'" + str(value).replace("'", "''") + "'"
