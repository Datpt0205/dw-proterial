"""Ticket 03: a "Customer order information (Form 1)" export read back after
the paste, matched by customer and PO number to the case waiting on its Bravo
entry, compared with what was prepared, and kept for the case. Every file
here is synthetic, shaped as Bravo exports the screen (Box B02): a merged
title, Bravo's titles on row 2, a SUBTOTAL row under them."""

from __future__ import annotations

import io
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.reader_client import ClientPoReaders, ClientQuoteForms, ClientTableReader
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.bravo_sales_orders import (
    SalesOrderScreen,
    parse_sales_orders,
    prepared_rows,
    without_prices,
)
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.domain.bravo_exports import MissingColumnsError
from dw_sales.domain.orders import Actor, OrderCase
from dw_sales.evals.graders import AN as AN_CALLER
from dw_sales.testing.bravo_export_store import MemoryBravoExportStore
from dw_sales.testing.followups import platform_zone

pytestmark = pytest.mark.unit

SHA = "c" * 64
REPO = Path(__file__).resolve().parents[5]
SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
T0 = datetime(2026, 10, 2, 2, 0, tzinfo=UTC)
_ORDER_RULES = load_order_rules(REPO / "configs" / "policies" / "sales_order_rules@1.15.0.yaml")
_RULES = PlatformOrderRules(_ORDER_RULES)
# Bravo's own titles, as B02 prints them (not customer data), with columns
# DW1 does not read between them.
TITLES = [
    "RowId", "No.", "PO line", "PO Number", "Item code", "Quantity", "Delivery date",
    "Sale order No", "PO Request date", "Direct customer code", "Original Price", "CURRENCY",
]  # fmt: skip


def _so(rows: Sequence[Sequence[object]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "grdDetail"
    sheet.append(["Customer order information (Form 1) (MẪU GIẢ LẬP)"])
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(TITLES))
    sheet.append(TITLES)
    sheet.append([None, None, None, None, None, f"=SUBTOTAL(9,F4:F{3 + len(rows)})"])
    for row in rows:
        sheet.append(list(row))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _bravo_rows(
    case: OrderCase, *, customer: str | None = None, price_bump: int = 0
) -> list[list[object]]:
    """The case's paste-sheet rows as Bravo would hold them, the first row's
    price moved by ``price_bump`` ten-thousandths."""
    rows: list[list[object]] = []
    for index, row in enumerate(prepared_rows(case)):
        price = row.unit_price + (Decimal(price_bump) / 10000 if index == 0 else 0)
        rows.append([
            f"{index}SO", index + 1, row.line_no, row.po_no, row.prv_code, float(row.quantity),
            None, "SO2611-000161", row.requested_date.isoformat() if row.requested_date else None,
            customer or case.customer_code, float(price), "USD",
        ])  # fmt: skip
    return rows


class _Cases:
    """`OrderCaseLookupPort` over one case, found under its own customer and
    PO number only."""

    def __init__(self, case: OrderCase) -> None:
        self.case = case

    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> list[OrderCase]:
        same = (customer_code, po_no) == (self.case.customer_code, self.case.header.po_no)
        return [self.case] if same else []


class _NoCases:
    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> list[OrderCase]:
        return []


async def _case() -> OrderCase:
    """M01 as DW1 opens it, reviewed and prepared: waiting on its Bravo entry."""
    message = await MockInbox.load(SCOPE).get_message(SCOPE, "M01")
    assert message is not None
    intake = OrderIntake(
        catalog=MockSalesCatalog.load(SCOPE),
        inbox=MockInbox.load(SCOPE),
        reader=ClientPoReaders(InProcessReaderTransport()),
        quote_forms=ClientQuoteForms(InProcessReaderTransport()),
        zones=platform_zone(),
        rules=_RULES,
        cases=_NoCases(),
        new_case_id=uuid.uuid4,
    )
    outcome = await intake.process(SCOPE, message)
    assert outcome.case is not None
    return outcome.case.start_review().prepare(Actor(user_id=uuid.UUID(int=0xA1)), T0)


async def _take(case: OrderCase, data: bytes) -> tuple[list[object], MemoryBravoExportStore]:
    store = MemoryBravoExportStore()
    screen = SalesOrderScreen(_Cases(case), store, FixedClock(T0), Uuid4Generator())
    reader = ClientTableReader(InProcessReaderTransport(), _ORDER_RULES.intake)
    table = await reader.read(data, "so.xlsx")
    context = AN_CALLER.context().model_copy(
        update={"tenant_id": SCOPE.tenant_id.value, "workspace_id": SCOPE.workspace_id.value}
    )
    outcomes, rejected = await screen.take(context, table, file_sha256=SHA)
    assert rejected == ()
    return list(outcomes), store


async def test_an_entry_bravo_holds_as_prepared_is_equal_and_names_its_so() -> None:
    case = await _case()

    (outcome,), store = await _take(case, _so(_bravo_rows(case)))

    assert (outcome.outcome, outcome.case_id, outcome.differences) == ("equal", case.case_id, 0)  # type: ignore[attr-defined]
    async with store(SCOPE) as work:
        read_back = await work.read_backs.get(case.case_id)
    assert read_back is not None and read_back.so_no == "SO2611-000161"
    assert read_back.case_version == case.case_version and read_back.equal


async def test_one_wrong_price_is_one_difference_on_that_line_hidden_from_non_price_readers() -> (
    None
):
    """Acceptance 1."""
    case = await _case()

    (outcome,), store = await _take(case, _so(_bravo_rows(case, price_bump=1)))

    assert (outcome.outcome, outcome.differences) == ("differs", 1)  # type: ignore[attr-defined]
    async with store(SCOPE) as work:
        read_back = await work.read_backs.get(case.case_id)
    assert read_back is not None
    (difference,) = read_back.differences
    assert difference.field == "unit_price" and difference.expected is not None
    hidden = without_prices(read_back).differences[0]
    assert (hidden.field, hidden.line_no, hidden.expected, hidden.actual) == (
        "unit_price",
        difference.line_no,
        None,
        None,
    )


async def test_another_customers_so_under_the_same_po_number_is_never_matched() -> None:
    """Acceptance 2."""
    case = await _case()

    (outcome,), store = await _take(case, _so(_bravo_rows(case, customer="FG99999999")))

    assert (outcome.outcome, outcome.case_id) == ("no_case", None)  # type: ignore[attr-defined]
    async with store(SCOPE) as work:
        assert await work.read_backs.get(case.case_id) is None


async def test_an_export_without_bravos_columns_is_refused_naming_them() -> None:
    from dw_sales.domain.bravo_exports import ImportedTable, TableRow

    table = ImportedTable(
        sheet="grdDetail",
        rows=[TableRow(row=1, cells=["PO Number", "Item code"]), TableRow(row=2, cells=["X", "Y"])],
    )

    with pytest.raises(MissingColumnsError) as refused:
        parse_sales_orders(table)

    assert "Sale order No" in refused.value.headers


async def test_a_case_not_yet_prepared_for_bravo_is_not_read_back() -> None:
    """Only a case waiting on its Bravo entry, or entered, is compared."""
    case = await _case()
    in_review = case.model_copy(update={"status": case.status.__class__("in_review")})
    in_review = OrderCase.model_validate(
        in_review.model_dump() | {"prepared_by": None, "prepared_at": None}
    )

    (outcome,), _ = await _take(in_review, _so(_bravo_rows(case)))

    assert outcome.outcome == "no_case"  # type: ignore[attr-defined]


async def test_the_case_page_shows_a_price_difference_to_a_price_reader_only() -> None:
    """Where the read-back leaves for a page: a reader of cases only gets
    the line and the field of a price difference, never its values."""
    from dw_sales.application.bravo_sales_orders import BravoReadBack
    from dw_sales.domain.bravo_sales_orders import SoDifference
    from dw_sales.evals.graders import CALLERS, DIEU, READER
    from dw_sales.evals.world import ALPHA, SampleSet, open_world

    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    seen = await world.process_each(DIEU, ["M01"])
    case_id = seen["M01"][0].case_id
    assert case_id is not None
    case = world.order(case_id)
    service = world.services.read_backs
    async with service.uow(ALPHA) as work:
        await work.read_backs.put(
            BravoReadBack(
                case_id=case_id,
                case_version=case.case_version,
                po_no=case.header.po_no,
                so_no="SO2611-000161",
                differences=(
                    SoDifference(
                        po_no=case.header.po_no,
                        line_no=1,
                        field="unit_price",
                        expected="4.3285",
                        actual="4.3286",
                    ),
                ),
                rows_read=1,
                file_sha256=SHA,
                read_by=DIEU.user_id,
                read_at=T0,
            )
        )
        await work.commit()

    priced = await service.latest(DIEU.context(), case_id)
    blind = await service.latest(READER.context(), case_id)

    assert priced.read_back is not None and priced.read_back.differences[0].actual == "4.3286"
    assert blind.prices_hidden and blind.read_back is not None
    assert "4.3286" not in blind.model_dump_json() and "4.3285" not in blind.model_dump_json()
    assert not priced.stale
