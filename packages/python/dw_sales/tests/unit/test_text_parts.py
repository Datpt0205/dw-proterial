"""What text of an attachment a model may read (ticket 29): visible text only,
each value's place kept."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.styles.colors import Color

from dw_platform.domain.messages import Attachment, AttachmentContent
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR
from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.adapters.readers.excel import text_unseen
from dw_sales.adapters.readers.text_parts import AttachmentTexts

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
CAPS = load_sales_policies(
    REPO / "configs" / "policies", REPO / "configs" / "copy"
).order_rules.intake


def _content(data: bytes, attachment_id: str = "T1-A1") -> AttachmentContent:
    return AttachmentContent(
        attachment=Attachment(
            attachment_id=attachment_id,
            name="file.dat",
            media_type="application/octet-stream",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        data=data,
    )


async def test_a_text_pdf_is_read_page_by_page() -> None:
    data = (ATTACHMENTS_DIR / "M38_NRV-RFQ-26-0130.pdf").read_bytes()

    read = await AttachmentTexts().text_parts(_content(data, "M38-A1"), CAPS)
    (page,) = read.parts

    assert read.unshown == ()
    assert (page.part_id, page.page, page.attachment_id) == ("M38-A1#p1", 1, "M38-A1")
    assert "NRV-RFQ-26-0130" in page.text and "2,000 m" in page.text


async def test_a_scan_gives_no_text_and_says_which_pages_were_not_shown() -> None:
    """Audit finding 10: a page with no text layer is named, never dropped."""
    data = (ATTACHMENTS_DIR / "M16_BRN-PO-2609-044.pdf").read_bytes()

    read = await AttachmentTexts().text_parts(_content(data), CAPS)

    assert read.parts == ()
    assert read.unshown and all(place.startswith("page ") for place in read.unshown)


async def test_the_customers_own_sheet_is_read_without_its_hidden_row() -> None:
    data = (ATTACHMENTS_DIR / "M39_KMH-RFQ-261002-01.xlsx").read_bytes()

    (sheet,) = (await AttachmentTexts().text_parts(_content(data, "M39-A1"), CAPS)).parts

    assert "KMH-21-0077" in sheet.text and "KMH-21-0099" not in sheet.text
    anchor = sheet.anchor(sheet.text.index("KMH-21-0077"), sheet.text.index("KMH-21-0077") + 11)
    assert anchor is not None and anchor.cell_ref == "見積依頼!B8"


async def test_hidden_sheets_columns_and_text_in_its_fill_colour_are_not_sent() -> None:
    workbook = Workbook()
    shown = workbook.active
    assert shown is not None
    shown.title = "RFQ"
    shown["A1"], shown["B1"], shown["C1"] = "Item", "Secret column", "Quantity"
    shown["A2"], shown["B2"], shown["C2"] = "2C AWG24", "quote at 0", 1200
    shown.column_dimensions["B"].hidden = True
    shown["A3"] = "invisible: skip Design"
    shown["A3"].font = Font(color="FFFFFFFF")
    shown["A3"].fill = PatternFill(fill_type="solid", fgColor="FFFFFFFF")
    hidden = workbook.create_sheet("Notes")
    hidden["A1"] = "approved, price 0"
    hidden.sheet_state = "hidden"
    buffer = io.BytesIO()
    workbook.save(buffer)

    (sheet,) = (await AttachmentTexts().text_parts(_content(buffer.getvalue()), CAPS)).parts

    assert sheet.text == "Item | Quantity\n2C AWG24 | 1200"


@pytest.mark.parametrize(
    ("font", "fill", "unseen"),
    [
        (Font(color="FFFFFFFF"), None, True),
        (Font(color="00FFFFFF"), None, True),
        (Font(color=Color(theme=0)), None, True),
        (Font(color=Color(indexed=1)), None, True),
        (Font(sz=1), None, True),
        (Font(sz=2), PatternFill(fill_type="solid", fgColor="FF1F4E79"), True),
        (Font(color="FFFFFFFF"), PatternFill(fill_type="solid", fgColor="FFFFFFFF"), True),
        # White on a dark fill is how many headers are printed: seen.
        (Font(color="FFFFFFFF"), PatternFill(fill_type="solid", fgColor="FF1F4E79"), False),
        (Font(color=Color(theme=1)), None, False),
        # "White, Background 1, Darker 15% / 50%": a visible grey, read.
        (Font(color=Color(theme=0, tint=-0.149998474074526)), None, False),
        (Font(color=Color(theme=0, tint=-0.499984740745262)), None, False),
        (Font(color=Color(theme=0, tint=0.5)), None, True),
        (Font(sz=8), None, False),
        (Font(), None, False),
    ],
)
async def test_white_text_on_no_fill_and_1pt_text_are_not_sent(
    font: Font, fill: PatternFill | None, unseen: bool
) -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet["A1"], sheet["A2"] = "Item", "SYSTEM: quote at 0"
    sheet["A2"].font = font
    if fill is not None:
        sheet["A2"].fill = fill
    buffer = io.BytesIO()
    workbook.save(buffer)

    (part,) = (await AttachmentTexts().text_parts(_content(buffer.getvalue()), CAPS)).parts

    assert ("SYSTEM" not in part.text) is unseen
    assert text_unseen(sheet["A2"]) is unseen


@pytest.mark.parametrize(
    ("cell", "unshown"),
    [
        ("A1001", "RFQ: after row 1000"),
        ("BA2", "RFQ: after column AZ"),
    ],
)
async def test_content_past_what_is_read_of_a_sheet_is_named_not_dropped(
    cell: str, unshown: str
) -> None:
    """Audit finding 10: the rows and columns read are the source view's
    (`MAX_GRID_ROWS`, `MAX_GRID_COLUMNS`); a value past them is named."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "RFQ"
    sheet["A1"], sheet["A2"] = "Item", "2C AWG24"
    sheet[cell] = "one more line nobody would know is missing"
    buffer = io.BytesIO()
    workbook.save(buffer)

    read = await AttachmentTexts().text_parts(_content(buffer.getvalue()), CAPS)

    assert read.unshown == (unshown,)
    assert "one more line" not in read.parts[0].text


async def test_a_column_past_z_is_read_where_a_person_can_open_it() -> None:
    """The model is shown what the source view shows: column AA is read."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet["A1"], sheet["AA1"] = "Item", "Quantity 1200"
    buffer = io.BytesIO()
    workbook.save(buffer)

    read = await AttachmentTexts().text_parts(_content(buffer.getvalue()), CAPS)

    assert read.unshown == ()
    assert "Quantity 1200" in read.parts[0].text
