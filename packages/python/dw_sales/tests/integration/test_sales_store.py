"""The sales store against real Postgres, driven by the 02/03 golden runs.

The whole mock mailbox goes through `OrderIntake` with `SqlOrderCaseLookup` as
its case port, so a duplicate or a revision is recognised against the cases
as stored, not as a test kept them. Every case read back must equal the case
the domain produced, through the domain's own constructor.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from sales_harness import DW1, T0, OrderRun, QuoteRun, user
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_kernel.errors import ConflictError
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import (
    ArtifactRecord,
    CaseEvent,
    ServedSource,
    SourceRegion,
    WorkerState,
)
from dw_sales.domain.dispositions import CaseKind, DispositionKind
from dw_sales.domain.orders import Accepted, Actor, OrderStatus

pytestmark = pytest.mark.integration

AN_ID = uuid.UUID(int=0xA1)
DIEU_ID = uuid.UUID(int=0xD1)

# Prices the golden runs handle (M04's PO and quotation, M10's decision and
# the other customers' quotations M10's evidence shows). None may reach an
# event (spec decision 8, ticket 04 G27).
PRICE_STRINGS = ("0.658", "0.6980", "0.698", "0.6890", "0.689", "0.7120", "0.7050")
# Those the case tables hold: M04's PO price, its quotation price, M10's decision.
STORED_PRICES = ("0.658", "0.6980", "0.6890")


async def test_every_case_of_the_mailbox_reads_back_as_the_domain_left_it(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    latest = order_run.latest()
    assert len(latest) >= 10, "the golden run opened too few cases to prove anything"
    async with uow(order_run.scope) as work:
        for case_id, case in latest.items():
            stored = await work.orders.get(case_id)
            assert stored is not None, case_id
            assert stored.case == case, case.message_id
            assert stored.origin.release_manifest_ref == "release@1.0.0"


async def test_a_revision_supersedes_inside_the_same_case_and_keeps_the_original(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    revised = order_run.outcomes["M07"]
    assert revised.disposition is not None
    assert revised.disposition.kind is DispositionKind.ATTACHED_TO_CASE
    assert revised.case is not None
    async with uow(order_run.scope) as work:
        stored = await work.orders.get(revised.case.case_id)
    assert stored is not None
    assert [old.message_id for old in stored.case.superseded] == ["M04"]
    assert stored.case.message_id == "M07"
    assert stored.case.case_id == order_run.outcomes["M04"].case.case_id  # type: ignore[union-attr]


async def test_every_message_disposition_reads_back(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    async with uow(order_run.scope) as work:
        for message_id, outcome in order_run.outcomes.items():
            if outcome.disposition is None:
                continue  # handed to the quotation flow
            assert await work.messages.get(message_id) == outcome.disposition, message_id


async def test_each_quote_step_reads_back_and_events_name_the_moves(
    quote_run: QuoteRun, uow: SqlSalesUnitOfWorkFactory, migrator: AsyncEngine
) -> None:
    final = quote_run.steps[-1]
    async with uow(quote_run.scope) as work:
        stored = await work.quotes.get(final.case_id)
    assert stored is not None
    assert stored.case == final
    async with migrator.connect() as conn:
        moves = (
            await conn.execute(
                sa.text(
                    "SELECT case_version, from_status, to_status, actor_kind FROM sales.case_events"
                    " WHERE case_id = :c ORDER BY occurred_at"
                ),
                {"c": final.case_id},
            )
        ).all()
    assert [m.to_status for m in moves] == [step.status.value for step in quote_run.steps]
    assert [m.case_version for m in moves] == [step.case_version for step in quote_run.steps]
    assert moves[0].from_status is None
    assert [m.from_status for m in moves[1:]] == [m.to_status for m in moves[:-1]]
    assert {m.actor_kind for m in moves} == {"worker", "user"}


async def test_no_event_of_the_golden_runs_carries_a_price(
    order_run: OrderRun, quote_run: QuoteRun, migrator: AsyncEngine
) -> None:
    async with migrator.connect() as conn:
        events = (
            await conn.execute(
                sa.text("SELECT * FROM sales.case_events WHERE tenant_id = :t"),
                {"t": order_run.scope.tenant_id.value},
            )
        ).all()
        # The amounts really are in the case tables, so the scan below is not
        # passing for want of anything to find.
        stored = await conn.scalar(
            sa.text(
                "SELECT string_agg(t, ' ') FROM ("
                " SELECT po_line::text AS t FROM sales.order_lines WHERE tenant_id = :t"
                " UNION ALL SELECT expected FROM sales.order_findings WHERE tenant_id = :t"
                " UNION ALL SELECT body::text FROM sales.quote_cases WHERE tenant_id = :t) s"
            ),
            {"t": order_run.scope.tenant_id.value},
        )
    for price in STORED_PRICES:
        assert price in str(stored), price
    assert len(events) >= len(quote_run.steps) + 10
    text = " | ".join(repr(tuple(row)) for row in events)
    for price in PRICE_STRINGS:
        assert price not in text, price


async def test_a_decision_on_a_stale_version_is_refused(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    case = order_run.outcomes["M01"].case
    assert case is not None
    reviewing = case.start_review()
    event = CaseEvent(action="order.review_started", actor=DW1, occurred_at=T0)
    async with uow(order_run.scope) as work:
        await work.orders.save(reviewing, expected_version=case.case_version, event=event)
        await work.commit()
    # A second decision made on the version both callers read.
    async with uow(order_run.scope) as work:
        with pytest.raises(ConflictError, match="changed since it was read"):
            await work.orders.save(reviewing, expected_version=case.case_version, event=event)


async def test_a_disposition_reads_back_with_who_and_when(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    case = order_run.outcomes["M02"].case
    assert case is not None
    an = Actor(user_id=AN_ID)
    (finding,) = case.findings
    reviewing = case.start_review()
    decided = reviewing.dispose(
        finding.key, Accepted(reason="Khách đã đồng ý mức LME", by=an.user_id, at=T0), an
    )
    async with uow(order_run.scope) as work:
        for before, after, action in (
            (case, reviewing, "order.review_started"),
            (reviewing, decided, "order.finding_disposed"),
        ):
            event = CaseEvent(
                action=action, actor=user(an.user_id), occurred_at=T0, finding_key=finding.key
            )
            await work.orders.save(after, expected_version=before.case_version, event=event)
        await work.commit()
    async with uow(order_run.scope) as work:
        stored = await work.orders.get(case.case_id)
    assert stored is not None and stored.case == decided
    assert stored.case.status is OrderStatus.IN_REVIEW


async def test_records_the_flows_keep_besides_cases(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    case = order_run.outcomes["M01"].case
    assert case is not None
    served = ServedSource(
        principal_id=DIEU_ID,
        case_kind=CaseKind.ORDER,
        case_id=case.case_id,
        case_version=case.case_version,
        attachment_id=case.attachment_id,
        attachment_sha256=case.document.attachment_sha256,
        sheet="PO",
        served_at=T0,
    )
    artifact = ArtifactRecord(
        artifact_id=uuid.uuid4(),
        case_kind=CaseKind.ORDER,
        case_id=case.case_id,
        case_version=case.case_version,
        kind="bravo_upload",
        template_ref="sales_bravo_upload@1.0.0",
        sha256="a" * 64,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=4096,
        created_by=AN_ID,
        created_at=T0,
    )
    paused = WorkerState(paused=True, changed_by=AN_ID, changed_at=T0)
    async with uow(order_run.scope) as work:
        assert await work.worker.state() == WorkerState(paused=False)
        await work.served.record(served)
        await work.served.record(served.model_copy(update={"served_at": T0 + timedelta(1)}))
        await work.artifacts.add(artifact)
        await work.worker.set(paused)
        await work.commit()
    async with uow(order_run.scope) as work:
        regions = await work.served.served(DIEU_ID, CaseKind.ORDER, case.case_id, case.case_version)
        assert regions == {SourceRegion(case.attachment_id, None, "PO")}
        assert not await work.served.served(AN_ID, CaseKind.ORDER, case.case_id, case.case_version)
        assert await work.artifacts.get(artifact.artifact_id) == artifact
        assert await work.worker.state() == paused


async def test_leaving_without_commit_keeps_nothing(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    async with uow(order_run.scope) as work:
        await work.worker.set(WorkerState(paused=True, changed_by=AN_ID, changed_at=T0))
    async with uow(order_run.scope) as work:
        assert await work.worker.state() == WorkerState(paused=False)
