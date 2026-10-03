"""The committed attachments are exactly what the generator makes from the fixtures."""

from __future__ import annotations

import io
import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from openpyxl import load_workbook
from pydantic import ValidationError
from pypdf import PdfReader

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, attachment_file_name
from dw_sales.adapters.mock.generate_attachments import (
    PurchaseOrderDocument,
    StatedAttributes,
    load_purchase_orders,
    render_attachments,
)
from dw_sales.application.ports import SalesScope

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
REGENERATE = "uv run python -m dw_sales.adapters.mock.generate_attachments"


@pytest.fixture(scope="module")
def rendered() -> dict[str, bytes]:
    return render_attachments()


def test_the_committed_attachments_are_what_the_generator_makes(rendered: dict[str, bytes]) -> None:
    committed = {path.name: path.read_bytes() for path in ATTACHMENTS_DIR.iterdir()}

    assert sorted(committed) == sorted(rendered), f"files differ from the fixtures: {REGENERATE}"
    stale = sorted(name for name, data in rendered.items() if committed[name] != data)
    assert not stale, f"{stale} are stale: {REGENERATE}"


def test_rendering_twice_gives_the_same_bytes(rendered: dict[str, bytes]) -> None:
    assert render_attachments() == rendered


async def test_every_attachment_in_the_inbox_has_a_document_and_no_document_is_orphaned(
    rendered: dict[str, bytes],
) -> None:
    inbox = MockInbox.load()
    carried = {
        attachment_file_name(message.message_id, attachment.name)
        for message in await inbox.list_messages(SCOPE)
        for attachment in message.attachments
    }

    assert carried == set(rendered)


def test_the_pdf_text_layer_carries_vietnamese_one_row_per_line() -> None:
    (po,) = [p for p in load_purchase_orders() if p.layout == "pdf"]
    reader = PdfReader(ATTACHMENTS_DIR / attachment_file_name(po.message_id, po.name))
    first, terms = (page.extract_text(extraction_mode="layout") for page in reader.pages)
    # Layout mode puts each printed row on one line, cells two or more spaces apart.
    rows = {
        cells[0]: cells[1:]
        for cells in (re.split(r"\s{2,}", line.strip()) for line in first.splitlines())
    }

    assert "ĐƠN ĐẶT HÀNG (PURCHASE ORDER)" in first
    assert "ĐIỀU KHOẢN CHUNG" in terms
    assert [rows[str(line.no)][0] for line in po.lines] == [
        line.customer_item_code for line in po.lines
    ]
    assert rows["2"] == [
        "BRN-C-0112",
        "MULTI-CORE CABLE 2C 0.75mm2 STRANDED BARE CU NO SHIELD GREY REEL 300M SPEC SP-5202",
        "3.000",
        "m",
        "14.500",
        "43.500.000",
        "30/11/2026",
    ]


def test_the_intra_group_po_prints_one_sheet_per_page(rendered: dict[str, bytes]) -> None:
    (po,) = [p for p in load_purchase_orders() if p.layout == "xlsx_sheet_per_page"]
    workbook = load_workbook(io.BytesIO(rendered[attachment_file_name(po.message_id, po.name)]))

    assert workbook.sheetnames == ["Page 1", "Page 2", "Page 3", "Page 4"]
    numbers = []
    for page, sheet in enumerate(workbook.worksheets, start=1):
        assert sheet["B4"].value == po.po_no
        assert sheet["E6"].value == f"{page} / 4"
        numbers += [
            row[0].value for row in sheet.iter_rows(min_row=10) if isinstance(row[0].value, int)
        ]
        totals = [
            cell for row in sheet.iter_rows(min_row=10) for cell in row if cell.value == "TOTAL"
        ]
        assert len(totals) == (1 if page == 4 else 0)
    assert numbers == list(range(1, 19))


def test_a_mapped_line_is_described_as_the_catalogue_describes_its_item(
    rendered: dict[str, bytes],
) -> None:
    (po,) = [p for p in load_purchase_orders() if p.message_id == "M01"]
    workbook = load_workbook(io.BytesIO(rendered[attachment_file_name(po.message_id, po.name)]))

    assert workbook["PO"]["C10"].value == (
        "HOOK-UP WIRE 1C AWG24 STRANDED TINNED CU NO SHIELD BLACK REEL 610M SPEC SP-1124"
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda po: po | {"lines_per_page": 5}, "sheet-per-page layout only"),
        (lambda po: po | {"layout": "xlsx_sheet_per_page"}, "sheet-per-page layout only"),
        (lambda po: po | {"terms": ["Payment in 60 days."]}, "printed by the PDF only"),
        (lambda po: po | {"buyer_address": "Lot 1, Demo Park"}, "printed by the PDF only"),
        (lambda po: po | {"lines": po["lines"][::-1]}, r"numbered 1\.\.n"),
    ],
    ids=["pages_on_one_sheet", "pages_unsized", "terms_in_excel", "address_in_excel", "order"],
)
def test_a_document_its_layout_cannot_print_is_refused(
    change: Callable[[dict[str, Any]], dict[str, Any]], message: str
) -> None:
    """Otherwise a fixture edit changes nothing in the file, or a README line
    number points at another line."""
    (po,) = [p for p in load_purchase_orders() if p.message_id == "M01"]

    with pytest.raises(ValidationError, match=message):
        PurchaseOrderDocument.model_validate(change(po.model_dump()))


def test_unstated_attributes_are_left_out_of_a_description() -> None:
    stated = StatedAttributes(
        family="multi_core_cable",
        cores=2,
        gauge="0.5mm2",
        stranding="stranded",
        conductor="tinned_copper",
        shield="foil",
        colour="black",
        spec_no="SP-5201",
    )

    assert (
        stated.describe()
        == "MULTI-CORE CABLE 2C 0.5mm2 STRANDED TINNED CU FOIL SHIELD BLACK SPEC SP-5201"
    )
