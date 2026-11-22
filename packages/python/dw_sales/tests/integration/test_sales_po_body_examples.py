"""A customer's decided mail-PO values read back as examples (ticket 43's
second step), on a real database as `dw_app`: the words are cut from the
revision's stored mail, only the newest decision on a value counts, a value
the mail never wrote is none, and another tenant or workspace reads nothing.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sales_harness import DW1, World
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_sales.adapters.persistence.po_body_examples import SqlPoBodyExamples
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import CaseEvent, CaseOrigin
from dw_sales.application.po_body_reading import PO_BODY_EXTRACTION
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.labelled_cases import LabelledCase
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.recorded import ByPrompt, Recorded
from dw_sales.evals.world import SampleWith, open_world

pytestmark = pytest.mark.integration

_AT = datetime.now(UTC).replace(microsecond=0)
_REPO = Path(__file__).resolve().parents[5]
_VI = json.loads((_REPO / "evals/fixtures/cases/sales_po_body.json").read_text(encoding="utf-8"))[
    "golden"
][0]
LINE_1 = "1. VX-W24-BK dây điện AWG24 đen: 6.100 m, đơn giá 0,0420, giao ngày 20/10/2026"


async def _body_case(uow: SqlSalesUnitOfWorkFactory, scope: SalesScope) -> OrderCase:
    """The case a PO written in a mail opens (AI item 4), as intake builds it
    on the sample world, stored through the repository as intake stores it."""
    intent = Recorded(raw={"language": "vi", "referenced_number_spans": [], "kind": "po"})
    model = ByPrompt(
        {
            "sales.message_intent": intent,
            PO_BODY_EXTRACTION.prompt_id: Recorded(raw=_VI["answer"]),
        }
    )
    spec = _VI["message"]
    with SampleWith([spec]) as sample:
        world = open_world(_REPO, sample, CALLERS, model=model)
        _, case = (await world.process_each(AN, [spec["message_id"]]))[spec["message_id"]]
    assert isinstance(case, OrderCase) and case.document.from_message
    async with uow(scope) as work:
        event = CaseEvent(action="order.checked", actor=DW1, occurred_at=_AT)
        await work.orders.add(case, CaseOrigin(None, "release@1.0.0"), event)
        await work.commit()
    return case


async def test_a_po_written_in_a_mail_is_stored_and_read_back(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    """AI item 4 on PostgreSQL: a PO with no file (its anchors point into the
    mail's text) is a case like any other, read back whole."""
    case = await _body_case(uow, world.alpha)

    async with uow(world.alpha) as work:
        stored = await work.orders.get(case.case_id)
    assert stored is not None
    assert stored.case.document == case.document


def _label(
    case: OrderCase,
    line_no: int | None,
    field: str,
    proposed: str,
    kept: str,
    *,
    at: datetime = _AT,
) -> LabelledCase:
    return LabelledCase(
        label_id=uuid.uuid4(),
        decided_at=at,
        step=ModelStep.PO_BODY_EXTRACTION,
        lane=CaseKind.ORDER,
        case_id=case.case_id,
        customer_code=case.customer_code,
        message_id=case.message_id,
        attachment_id=None,
        line_no=line_no,
        field=field,
        proposed=proposed,
        kept=kept,
        prompt="sales.po_body_extraction@1.2.0",
        model_profile="onprem",
        rules="sales_order_rules@1.15.0",
        decided_by=uuid.UUID(int=0xA1),
    )


async def test_decided_values_read_back_as_the_mails_words_in_their_own_scope_only(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
) -> None:
    case = await _body_case(uow, world.alpha)
    assert case.customer_code is not None
    labels = [
        _label(case, 1, "quantity", "6100", "6100", at=_AT - timedelta(hours=3)),
        # Corrected: its words were not the field.
        _label(case, 1, "unit_price", "0.042", "0.05", at=_AT - timedelta(hours=2)),
        # Never written (quantity x price, at the price): no example.
        _label(case, 1, "amount", "256.2", "256.2", at=_AT - timedelta(hours=1)),
        # Decided again later: only this one counts for the date.
        _label(case, 1, "requested_date", "2026-10-20", "2026-10-21", at=_AT - timedelta(hours=4)),
        _label(case, 1, "requested_date", "2026-10-20", "2026-10-20"),
    ]
    async with uow(world.alpha) as work:
        await work.labelled_cases.append(labels)
        await work.commit()
    examples = SqlPoBodyExamples(app_sessions)

    found = await examples.latest(world.alpha, case.customer_code, 6)

    assert [(e.field, e.line, e.words, e.right) for e in found] == [
        ("requested_date", LINE_1, "20/10/2026", True),
        ("unit_price", LINE_1, "0,0420", False),
        ("quantity", LINE_1, "6.100 m", True),
    ]
    assert await examples.latest(world.alpha, "SOMEONE-ELSE", 6) == []
    for scope in (world.beta, world.alpha_other):
        assert await examples.latest(scope, case.customer_code, 6) == []
