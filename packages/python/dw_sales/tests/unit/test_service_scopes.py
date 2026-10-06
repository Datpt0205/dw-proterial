"""Each Sales service checks the scope its step needs itself, before it reads
anything: the route checks first too, but the service is where the change
happens, and a caller that reaches it another way (a worker, a later route)
meets the same refusal (failure-modes #5).

The stores here refuse to be opened: a service that read before it checked
fails the test with that, not with the 403.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from dw_kernel.errors import PermissionDeniedError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_sales.application.access import Gate
from dw_sales.application.artifacts_service import ArtifactService
from dw_sales.application.decisions import CaseDecisions
from dw_sales.application.master_data_service import MasterDataService
from dw_sales.application.orders_service import OrderCommands, OrderQueries
from dw_sales.application.overview_service import OverviewService
from dw_sales.application.quotes_service import QuoteCommands, QuoteQueries
from dw_sales.application.runs import Dw1Runs
from dw_sales.application.source import SourceService
from dw_sales.application.worker_service import WorkerService
from dw_sales.domain.orders import CloseReason
from dw_sales.domain.quotes import DeclineReason

pytestmark = pytest.mark.unit

CASE = uuid.UUID(int=9)


class _Untouchable:
    """Fails loudly on any use: nothing may be read before the scope check."""

    def __call__(self, *args: object, **kwargs: object) -> Any:
        raise AssertionError("the store was opened before the scope was checked")

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"{name} was used before the scope was checked")


def _context(*scopes: str) -> AccessContext:
    return AccessContext(
        tenant_id=uuid.UUID(int=1),
        workspace_id=uuid.UUID(int=2),
        principal_id=uuid.UUID(int=3),
        roles=frozenset({"approver_boost", "member"}),
        # What `approver_boost` and a platform member hold: nothing of Sales.
        scopes=frozenset({"approvals.decide", "approvals.read", *scopes}),
        plan_id="professional",
    )


GATE = Gate(ScopeAuthorizationService())
STORE: Any = _Untouchable()
CLOCK = FixedClock(datetime(2026, 10, 2, tzinfo=UTC))
IDS = Uuid4Generator()

order_queries = OrderQueries(STORE, GATE, STORE)
order_commands = OrderCommands(STORE, GATE, CLOCK, IDS, STORE, STORE)
quote_queries = QuoteQueries(STORE, GATE, CLOCK, STORE, STORE)
quote_commands = QuoteCommands(STORE, GATE, CLOCK, IDS, STORE, STORE, STORE)
# The routes' way to start DW1, and the steps the run takes: both check.
dw1 = Dw1Runs(STORE, GATE, STORE, STORE, STORE)
steps = CaseDecisions(STORE, GATE, CLOCK, IDS, STORE, STORE)
RUN = uuid.UUID(int=10)
sources = SourceService(STORE, GATE, CLOCK, STORE, STORE)
artifacts = ArtifactService(STORE, GATE, STORE, CLOCK, IDS, STORE, STORE, STORE, STORE, STORE)
master = MasterDataService(GATE, STORE)
overview = OverviewService(STORE, GATE, CLOCK, STORE, STORE, STORE)
worker = WorkerService(STORE, GATE, CLOCK, IDS, STORE, STORE, STORE)

type Call = Callable[[AccessContext], Awaitable[object]]

CALLS: dict[str, tuple[str, Call]] = {
    "orders.summaries": ("sales.case.read", order_queries.summaries),
    "orders.get": ("sales.case.read", lambda c: order_queries.get(c, CASE)),
    "orders.prepare": (
        "sales.order.prepare",
        lambda c: order_commands.prepare(c, CASE, case_version=1),
    ),
    "orders.dispose": (
        "sales.order.prepare",
        lambda c: order_commands.dispose(
            c, CASE, "price_mismatch:2", case_version=1, disposition="ask_customer"
        ),
    ),
    "orders.mapping": (
        "sales.order.prepare",
        lambda c: order_commands.confirm_mapping(c, CASE, 1, case_version=1, prv_code="CB-2001"),
    ),
    "dw1.process": ("sales.inbox.process", lambda c: dw1.process(c, "M01")),
    "dw1.process_all": ("sales.inbox.process", dw1.process_all),
    "dw1.record_bravo_entry": (
        "sales.order.prepare",
        lambda c: dw1.record_bravo_entry(
            c, CASE, case_version=1, so_no="SO26-1001", entry_compared=True
        ),
    ),
    "dw1.submit_quote": (
        "sales.quote.prepare",
        lambda c: dw1.submit_quote(c, CASE, case_version=1, quote_no="Q26-0301"),
    ),
    "steps.record_bravo_entry": (
        "sales.order.prepare",
        lambda c: steps.record_bravo_entry(
            c, CASE, case_version=1, so_no="SO26-1001", entry_compared=True, run_id=RUN
        ),
    ),
    "steps.submit_quote": (
        "sales.quote.prepare",
        lambda c: steps.submit_quote(c, CASE, case_version=1, quote_no="Q26-0301", run_id=RUN),
    ),
    "orders.close": (
        "sales.order.prepare",
        lambda c: order_commands.close(
            c, CASE, case_version=1, reason=CloseReason.NOT_AN_ORDER, superseded_by=None
        ),
    ),
    "quotes.get": ("sales.case.read", lambda c: quote_queries.get(c, CASE)),
    "quotes.price": (
        "sales.quote.prepare",
        lambda c: quote_commands.price(
            c, CASE, case_version=1, lme_month=None, lines=[], management_guidance=None
        ),
    ),
    "quotes.decline": (
        "sales.quote.prepare",
        lambda c: quote_commands.decline(
            c, CASE, case_version=1, reason=DeclineReason.COMMERCIAL, note=None
        ),
    ),
    "sources.order": (
        "sales.case.read",
        lambda c: sources.order_source(c, CASE, "A1", page=None, sheet="PO"),
    ),
    "artifacts.order": ("sales.case.read", lambda c: artifacts.order_artifact(c, CASE, CASE)),
    "artifacts.order_list": ("sales.case.read", lambda c: artifacts.order_artifacts(c, CASE)),
    "artifacts.render_order": (
        "sales.case.read",
        lambda c: artifacts.render_order(c, CASE, kind="bravo_upload", case_version=1),
    ),
    "artifacts.render_quote": (
        "sales.case.read",
        lambda c: artifacts.render_quote(c, CASE, kind="send_draft", case_version=1),
    ),
    "master.quotations": ("sales.case.read", master.quotations),
    "overview": ("sales.overview.read", overview.overview),
    "worker.resume": ("sales.worker.resume", lambda c: worker.resume(c, "đã kiểm tra")),
}


@pytest.mark.parametrize("name", sorted(CALLS))
async def test_a_service_refuses_a_caller_without_its_scope_before_reading(name: str) -> None:
    scope, call = CALLS[name]

    with pytest.raises(PermissionDeniedError) as refused:
        await call(_context())

    assert refused.value.details["action"] == scope


async def test_the_source_of_a_case_needs_the_price_scope_besides_reading_it() -> None:
    _, serve = CALLS["sources.order"]

    with pytest.raises(PermissionDeniedError) as refused:
        await serve(_context("sales.case.read"))

    assert refused.value.details["action"] == "sales.price.read"


@pytest.mark.parametrize(
    ("render", "scope"),
    [
        (
            lambda c: artifacts.render_order(c, CASE, kind="bravo_upload", case_version=1),
            "sales.order.prepare",
        ),
        (
            lambda c: artifacts.render_quote(c, CASE, kind="ycbg_draft", case_version=1),
            "sales.quote.prepare",
        ),
    ],
)
async def test_rendering_an_artifact_needs_the_write_scope_besides_reading_the_case(
    render: Call, scope: str
) -> None:
    """A reader may download what is open to them; storing a new file is a
    write, and it takes the context's own write scope."""
    with pytest.raises(PermissionDeniedError) as refused:
        await render(_context("sales.case.read", "sales.price.read"))

    assert refused.value.details["action"] == scope
