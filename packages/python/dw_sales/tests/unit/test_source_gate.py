"""What a person must have been served before prepare or cross-check (spec
decision 12): the order's source, and every page or sheet holding a value read
from a flagged region or typed by Sales."""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.application.case_store import SourceRegion
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.application.source import required_regions
from dw_sales.domain.orders import Actor, CorrectedBySales, OrderCase

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
POLICIES = Path(__file__).resolve().parents[5] / "configs" / "policies"
AN = Actor(user_id=uuid.UUID(int=0xA1))
AT = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
_IDS = itertools.count(1)


class _NoCases:
    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Sequence[OrderCase]:
        return ()


async def _case(message_id: str) -> OrderCase:
    inbox = MockInbox.load(SCOPE)
    intake = OrderIntake(
        catalog=MockSalesCatalog.load(SCOPE),
        inbox=inbox,
        reader=mock_po_readers(),
        rules=PlatformOrderRules(load_order_rules(POLICIES / "sales_order_rules@1.0.0.yaml")),
        cases=_NoCases(),
        new_case_id=lambda: uuid.UUID(int=next(_IDS)),
    )
    message = await inbox.get_message(SCOPE, message_id)
    assert message is not None
    outcome = await intake.process(SCOPE, message)
    assert outcome.case is not None
    return outcome.case.start_review()


def _sheet(case: OrderCase, line_no: int) -> str | None:
    return case.line(line_no).po_line.anchors.quantity.sheet


async def test_a_clean_order_needs_only_its_own_source() -> None:
    case = await _case("M01")
    anchor = case.header.anchors.po_no

    assert required_regions(case) == {SourceRegion(anchor.attachment_id, None, anchor.sheet)}


async def test_a_pdf_order_is_needed_by_page() -> None:
    case = await _case("M03")

    (region,) = required_regions(case)

    assert (region.page, region.sheet) == (1, None)


async def test_each_sheet_holding_a_flagged_value_is_needed() -> None:
    case = await _case("M27")

    regions = required_regions(case)

    # Line 2's row is hidden on the first sheet; lines 4-6 sit on a hidden one.
    assert {r.sheet for r in regions} >= {_sheet(case, 2), _sheet(case, 5)}
    assert len({r.sheet for r in regions}) >= 2


async def test_the_sheet_of_a_typed_value_is_needed() -> None:
    case = await _case("M21")  # line_total_mismatch, on the total
    total = case.document.total
    assert total is not None
    key = next(f.key for f in case.findings if f.code.value == "line_total_mismatch")

    typed = case.dispose(
        key,
        CorrectedBySales(value="1000", source="bản in", by=AN.user_id, at=AT),
        AN,
    )

    assert SourceRegion(total.anchor.attachment_id, None, total.anchor.sheet) in required_regions(
        typed
    )
