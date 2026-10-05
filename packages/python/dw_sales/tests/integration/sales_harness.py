"""The sales integration suite's shared pieces: seeded tenants and the 02/03
golden runs, persisted through the store step by step.

A module of its own rather than `conftest.py`, so test files can import it by
a name no other suite uses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
import yaml
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.persistence.orders import SqlOrderCaseLookup
from dw_sales.adapters.persistence.quotes import SqlQuoteCaseLookup
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.adapters.rfq_excel import ExcelDesignReplyReader, ExcelRfqReader
from dw_sales.application.case_store import CaseEvent, CaseOrigin, EventActor
from dw_sales.application.order_intake import IntakeOutcome, OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.application.quotation import QuotationService, QuoteRules, ReplyAttached
from dw_sales.domain.catalog import LmeBand, LmeMonth
from dw_sales.domain.orders import OrderCase
from dw_sales.domain.pricing import SalesPricing
from dw_sales.domain.quotes import (
    LinePrice,
    PricingDecision,
    QuoteActor,
    QuoteCapability,
    QuoteCase,
)

TEST_DB = "dw_test_sales"


@dataclass(frozen=True)
class World:
    """Two tenants; the first with two workspaces."""

    alpha: SalesScope
    alpha_other: SalesScope
    beta: SalesScope


def _scope(tenant: uuid.UUID, workspace: uuid.UUID) -> SalesScope:
    return SalesScope(TenantId(tenant), WorkspaceId(workspace))


async def seed_world(migrator: AsyncEngine) -> World:
    """Two fresh tenants, the first with two workspaces, written as the migrator."""
    alpha, beta = uuid.uuid4(), uuid.uuid4()
    rows = (
        (alpha, uuid.uuid4(), "ban-hang"),
        (alpha, uuid.uuid4(), "ke-toan"),
        (beta, uuid.uuid4(), "ban-hang"),
    )
    async with migrator.begin() as conn:
        for tenant in (alpha, beta):
            await conn.execute(
                sa.text("INSERT INTO platform.tenants (id, slug, name) VALUES (:t, :s, :s)"),
                {"t": tenant, "s": f"t-{tenant.hex[:12]}"},
            )
        for tenant, workspace, slug in rows:
            await conn.execute(
                sa.text(
                    "INSERT INTO platform.workspaces (id, tenant_id, slug, name)"
                    " VALUES (:w, :t, :s, :s)"
                ),
                {"w": workspace, "t": tenant, "s": slug},
            )
    (a1, a2, b) = (_scope(t, w) for t, w, _ in rows)
    return World(alpha=a1, alpha_other=a2, beta=b)


# ------------------------------------------------------------- golden runs --

_REPO = Path(__file__).resolve().parents[5]
_POLICIES = _REPO / "configs" / "policies"
DW1 = EventActor(
    kind="worker", actor_id="svc|sales-dw1", worker_id="sales-dw1", worker_version="1.0.0"
)
T0 = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


@dataclass(frozen=True)
class OrderRun:
    """The mock mailbox processed once, oldest first, every case persisted."""

    scope: SalesScope
    outcomes: dict[str, IntakeOutcome]

    def latest(self) -> dict[uuid.UUID, OrderCase]:
        """Each case as the last outcome that touched it left it."""
        cases: dict[uuid.UUID, OrderCase] = {}
        for outcome in self.outcomes.values():
            if outcome.case is not None:
                cases[outcome.case.case_id] = outcome.case
        return cases


async def persist_outcome(
    uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, outcome: IntakeOutcome, at: datetime
) -> None:
    async with uow(scope) as work:
        case = outcome.case
        if case is not None:
            stored = await work.orders.get(case.case_id)
            if stored is None:
                event = CaseEvent(action="order.checked", actor=DW1, occurred_at=at)
                await work.orders.add(case, CaseOrigin(None, "release@1.0.0"), event)
            else:
                event = CaseEvent(action="order.revised", actor=DW1, occurred_at=at)
                await work.orders.save(case, expected_version=stored.case.case_version, event=event)
        if outcome.disposition is not None:
            await work.messages.record(outcome.disposition, at)
        await work.commit()


async def run_mailbox(
    uow: SqlSalesUnitOfWorkFactory,
    sessions: async_sessionmaker[AsyncSession],
    scope: SalesScope,
    only: frozenset[str] | None = None,
) -> OrderRun:
    """The mock mailbox (or ``only`` those messages), oldest first, each
    outcome persisted before the next message is processed."""
    inbox = MockInbox.load(scope)
    intake = OrderIntake(
        catalog=MockSalesCatalog.load(scope),
        inbox=inbox,
        reader=mock_po_readers(),
        rules=PlatformOrderRules(load_order_rules(_POLICIES / "sales_order_rules@1.0.0.yaml")),
        # Duplicates and revisions are recognised against the cases as stored.
        cases=SqlOrderCaseLookup(sessions),
        new_case_id=uuid.uuid4,
    )
    outcomes: dict[str, IntakeOutcome] = {}
    for step, message in enumerate(await inbox.list_messages(scope)):
        if only is not None and message.message_id not in only:
            continue
        outcome = await intake.process(scope, message)
        await persist_outcome(uow, scope, outcome, T0 + timedelta(minutes=step))
        outcomes[message.message_id] = outcome
    return OrderRun(scope, outcomes)


PRICER = uuid.UUID(int=0x101)  # the quotation PIC (fictional)
HEAD = uuid.UUID(int=0x102)
DECIDED = Decimal("0.6890")


def user(actor: uuid.UUID | str) -> EventActor:
    return EventActor(kind="user", actor_id=str(actor))


@dataclass(frozen=True)
class QuoteRun:
    """M10 from request to master list, each step persisted as it happened."""

    scope: SalesScope
    steps: list[QuoteCase]


def _policy(name: str) -> dict[str, object]:
    raw = yaml.safe_load((_POLICIES / name).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


async def run_m10(
    uow: SqlSalesUnitOfWorkFactory,
    sessions: async_sessionmaker[AsyncSession],
    scope: SalesScope,
) -> QuoteRun:
    catalog = MockSalesCatalog.load(scope)
    service = QuotationService(
        catalog=catalog,
        inbox=MockInbox.load(scope),
        rfq_reader=ExcelRfqReader(),
        reply_reader=ExcelDesignReplyReader(),
        cases=SqlQuoteCaseLookup(sessions),
        ledger=catalog,
        rules=QuoteRules.model_validate(_policy("sales_quote_rules@1.1.0.yaml")),
        pricing=SalesPricing.model_validate(_policy("sales_pricing@1.0.0.yaml")),
    )
    steps: list[QuoteCase] = []
    clock = iter(T0 + timedelta(minutes=minute) for minute in range(100))

    async def keep(case: QuoteCase, action: str, actor: EventActor) -> QuoteCase:
        event = CaseEvent(action=action, actor=actor, occurred_at=next(clock))
        async with uow(scope) as work:
            if steps:
                await work.quotes.save(case, expected_version=steps[-1].case_version, event=event)
            else:
                await work.quotes.add(case, CaseOrigin(None, "release@1.0.0"), event)
            await work.commit()
        steps.append(case)
        return case

    at = T0
    case = await keep(
        await service.open_case(scope, "M10", uuid.uuid4()),
        "quote.received",
        DW1,
    )
    case = await keep(case.draft_ycbg(), "quote.ycbg_drafted", DW1)
    case = await keep(
        case.record_ycbg("YCBG-2609-030", by=PRICER, at=at), "quote.ycbg_recorded", user(PRICER)
    )
    case = await keep(case.send_to_design(), "quote.sent_to_design", user(PRICER))
    outcome = await service.take_design_reply(scope, "M25")
    assert isinstance(outcome, ReplyAttached)
    case = await keep(outcome.case, "quote.design_replied", DW1)
    decision = PricingDecision(
        decided_by=PRICER,
        decided_at=at,
        lme=LmeMonth(month="2026-09", usd_per_tonne=Decimal(10870)),
        lines=(
            LinePrice(
                line_no=1,
                unit_price=DECIDED,
                moq=Decimal(3000),
                lead_time_days=45,
                copper_basis=LmeBand(
                    low_usd_per_tonne=Decimal(10500), high_usd_per_tonne=Decimal(11000)
                ),
            ),
        ),
    )
    case = await keep(
        await service.decide_price(scope, case, decision, by=PRICER), "quote.priced", user(PRICER)
    )
    case = await keep(
        await service.submit(
            scope, case, quote_no="Q26-0301", issued_on=date(2026, 10, 2), by=PRICER, at=at
        ),
        "quote.submitted",
        user(PRICER),
    )
    assert case.submission is not None
    case = await keep(
        case.approve(
            QuoteActor(user_id=HEAD, capabilities=frozenset({QuoteCapability.APPROVE})),
            at=at,
            document_sha256=case.submission.document_sha256,
        ),
        "quote.approved",
        user(HEAD),
    )
    case = await keep(case.mark_sent(by=PRICER, at=at), "quote.sent", user(PRICER))
    await keep(
        await service.record_master_list(scope, case, by=PRICER, at=at),
        "quote.master_list_recorded",
        user(PRICER),
    )
    return QuoteRun(scope, steps)
