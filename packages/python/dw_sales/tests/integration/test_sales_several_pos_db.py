"""Tickets 19 and 22 against real Postgres: one message on several order
cases, and a message processed twice opening no second set.

The mock mailbox's M01, M02 and M03 are three POs; here they are three POs
of one mail ("P3"), stored as the intake leaves them: three cases whose
revision names the one message, and one disposition naming the first and
listing the others (`sales.message_cases`). The database, not only the
intake, refuses a second set (`sales.messages`' key, in the transaction
that stores the cases) and a second revision of one PO from one message
(`uq_order_revisions_tenant_id_workspace_id_message_id_po_no`).
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sales_harness import DW1, T0, OrderRun, World
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_kernel.errors import ConflictError
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import CaseEvent, CaseOrigin
from dw_sales.domain.dispositions import CaseKind, DispositionKind, MessageDisposition
from dw_sales.domain.orders import OrderCase

pytestmark = pytest.mark.integration

ORIGIN = CaseOrigin(None, "release@1.0.0")


def _of_one_mail(run: OrderRun, source: str, message_id: str, po_no: str) -> OrderCase:
    """The case ``source`` opened, as a fresh case of PO ``po_no`` opened by
    ``message_id``: an invented PO number, so no stored case holds it."""
    case = run.outcomes[source].case
    assert case is not None, source
    document = case.document
    header = document.header.model_copy(update={"po_no": po_no})
    return case.model_copy(
        update={
            "case_id": uuid.uuid4(),
            "message_id": message_id,
            "document": document.model_copy(update={"header": header}),
        }
    )


def _opened(message_id: str, cases: list[OrderCase]) -> MessageDisposition:
    return MessageDisposition(
        message_id=message_id,
        kind=DispositionKind.CASE_CREATED,
        case_kind=CaseKind.ORDER,
        case_id=cases[0].case_id,
        customer_code=cases[0].customer_code,
        more_cases=tuple(c.case_id for c in cases[1:]),
    )


async def _store(
    uow: SqlSalesUnitOfWorkFactory, run: OrderRun, cases: list[OrderCase], message_id: str
) -> MessageDisposition:
    disposition = _opened(message_id, cases)
    async with uow(run.scope) as work:
        for case in cases:
            await work.orders.add(
                case, ORIGIN, CaseEvent(action="order.checked", actor=DW1, occurred_at=T0)
            )
        await work.messages.record(disposition, T0)
        await work.commit()
    return disposition


def _three(run: OrderRun, message_id: str) -> list[OrderCase]:
    return [_of_one_mail(run, m, message_id, f"{message_id}-{m}") for m in ("M01", "M02", "M03")]


async def test_one_message_on_three_cases_reads_back_and_the_log_finds_all_three(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    cases = _three(order_run, "P3-READ")
    disposition = await _store(uow, order_run, cases, "P3-READ")

    async with uow(order_run.scope) as work:
        assert await work.messages.get("P3-READ") == disposition
        logged = await work.messages.logged("P3-READ")
        listed = [
            m for m in await work.messages.list_all() if m.disposition.message_id == "P3-READ"
        ]
        found = await work.messages.cases_of(["P3-READ"])
    assert logged is not None and logged.disposition.more_cases == disposition.more_cases
    assert [m.disposition for m in listed] == [disposition]
    # Ticket 24 reads a thread's cases through this: every case of the mail.
    assert sorted((f.case_kind, f.case_id) for f in found) == sorted(
        (CaseKind.ORDER, c.case_id) for c in cases
    )
    # Another workspace and another tenant find none of them.
    for other in (world.alpha_other, world.beta):
        async with uow(other) as work:
            assert await work.messages.cases_of(["P3-READ"]) == []
            assert await work.messages.get("P3-READ") is None


async def test_processing_the_mail_again_opens_no_second_set(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    """Acceptance 2, in the database: a second processing's cases are
    written in the transaction the message's key refuses, so none stays."""
    await _store(uow, order_run, _three(order_run, "P3-TWICE"), "P3-TWICE")
    again = _three(order_run, "P3-TWICE-B")

    with pytest.raises(ConflictError):
        async with uow(order_run.scope) as work:
            for case in again:
                case = case.model_copy(update={"message_id": "P3-TWICE"})
                await work.orders.add(
                    case, ORIGIN, CaseEvent(action="order.checked", actor=DW1, occurred_at=T0)
                )
            await work.messages.record(_opened("P3-TWICE", again), T0)
            await work.commit()

    async with uow(order_run.scope) as work:
        for case in again:
            assert await work.orders.get(case.case_id) is None


async def test_a_message_is_one_revision_per_po_number(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory
) -> None:
    """Two POs of one mail are two revisions; the same PO twice is refused,
    by the revisions' own key (the second is a duplicate case, which the
    cases' key lets through)."""
    first = _of_one_mail(order_run, "M01", "P2-SAME", "P2-SAME-A")
    other = _of_one_mail(order_run, "M02", "P2-SAME", "P2-SAME-B")
    same_po = _of_one_mail(order_run, "M01", "P2-SAME", "P2-SAME-A").model_copy(
        update={"duplicate_of_so": "SO-INVENTED-1"}
    )
    async with uow(order_run.scope) as work:
        for case in (first, other):
            await work.orders.add(
                case, ORIGIN, CaseEvent(action="order.checked", actor=DW1, occurred_at=T0)
            )
        await work.commit()

    with pytest.raises(ConflictError) as refused:
        async with uow(order_run.scope) as work:
            await work.orders.add(
                same_po, ORIGIN, CaseEvent(action="order.checked", actor=DW1, occurred_at=T0)
            )
            await work.commit()
    assert refused.value.details["constraint"] == (
        "uq_order_revisions_tenant_id_workspace_id_message_id_po_no"
    )


async def test_a_link_names_a_real_case_of_its_own_message_and_is_never_rewritten(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, migrator: AsyncEngine
) -> None:
    """The links are a fact about how a message was processed: no case that
    does not exist, and `dw_app` may neither update nor delete one."""
    cases = _three(order_run, "P3-LINKS")
    await _store(uow, order_run, cases, "P3-LINKS")
    ghost = _opened("P3-GHOST", cases[:1]).model_copy(update={"more_cases": (uuid.uuid4(),)})
    with pytest.raises(ConflictError):
        async with uow(order_run.scope) as work:
            await work.messages.record(ghost, T0)
            await work.commit()

    async with migrator.connect() as conn:
        held = {
            row.verb
            for row in await conn.execute(
                sa.text(
                    "SELECT v.verb"
                    " FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) AS v(verb)"
                    " WHERE has_table_privilege('dw_app', 'sales.message_cases', v.verb)"
                )
            )
        }
    assert held == {"SELECT", "INSERT"}
