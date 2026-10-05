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
from dw_sales.application.master_data_service import MasterDataService
from dw_sales.application.orders_service import OrderCommands, OrderQueries
from dw_sales.application.overview_service import OverviewService
from dw_sales.application.quotes_service import QuoteCommands, QuoteQueries
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

order_queries = OrderQueries(STORE, GATE)
order_commands = OrderCommands(STORE, GATE, CLOCK, IDS, STORE)
quote_queries = QuoteQueries(STORE, GATE, CLOCK, STORE)
quote_commands = QuoteCommands(STORE, GATE, CLOCK, IDS, STORE, STORE)
sources = SourceService(STORE, GATE, CLOCK, STORE, STORE)
artifacts = ArtifactService(STORE, GATE, STORE)
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
    "orders.cross_check": (
        "sales.order.cross_check",
        lambda c: order_commands.cross_check(
            c, CASE, case_version=1, decision="accept", reason=None
        ),
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
    "quotes.approval": (
        "sales.quote.approve",
        lambda c: quote_commands.approval(
            c,
            CASE,
            case_version=1,
            decision="approve",
            comment=None,
            document_sha256="a" * 64,
            reasons={},
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


async def test_the_platforms_approvals_decide_approves_no_sales_quote() -> None:
    """Diệu's `approver_boost` grants `approvals.decide`: it is not
    `sales.quote.approve`, and the service says which one it needed."""
    _, approve = CALLS["quotes.approval"]

    with pytest.raises(PermissionDeniedError) as refused:
        await approve(_context("sales.quote.prepare", "sales.case.read", "sales.price.read"))

    assert refused.value.details["action"] == "sales.quote.approve"


async def test_the_source_of_a_case_needs_the_price_scope_besides_reading_it() -> None:
    _, serve = CALLS["sources.order"]

    with pytest.raises(PermissionDeniedError) as refused:
        await serve(_context("sales.case.read"))

    assert refused.value.details["action"] == "sales.price.read"
