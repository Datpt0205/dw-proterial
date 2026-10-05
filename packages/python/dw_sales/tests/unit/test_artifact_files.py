"""The file writer: text stays text, the same content writes the same bytes,
and a draft is an unsent message from the address it names."""

from __future__ import annotations

import email
import io
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from email import policy

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from dw_sales.adapters.artifact_files import ArtifactFiles
from dw_sales.application.artifact_content import (
    XLSX,
    EmailDraft,
    FileAttachment,
    Sheet,
    Workbook,
)
from dw_sales.domain.messages import EmailAddress

pytestmark = pytest.mark.unit

WRITER = ArtifactFiles()
AT = datetime(2026, 10, 2, 2, 0, tzinfo=UTC)
HOSTILE = (
    '=HYPERLINK("https://attacker.example/po","CVG-0003")',
    "+SUM(A1:A9)",
    "-2+3",
    "@cmd",
    "<b>not a tag</b> & more",
)


def _book(*rows: tuple[object, ...], language: str = "vi") -> Workbook:
    return Workbook(
        (
            Sheet(
                name="S",
                title="Tiêu đề",
                heading=(("Số", "Q-1"),),
                columns=("A", "B", "C"),
                rows=tuple(rows),  # type: ignore[arg-type]
                notes=("MOCK",),
            ),
        ),
        language,  # type: ignore[arg-type]
        AT,
    )


def test_every_string_is_a_text_cell_and_a_formula_start_gets_the_quote_prefix() -> None:
    data = WRITER.workbook(
        _book(*((text, Decimal("0.6890"), date(2026, 10, 2)) for text in HOSTILE))
    )

    sheet = load_workbook(io.BytesIO(data)).worksheets[0]
    cells = {c.value: c for row in sheet.iter_rows() for c in row if c.value in HOSTILE}
    assert set(cells) == set(HOSTILE)
    for text, cell in cells.items():
        assert cell.data_type == "s", text
        assert cell.quotePrefix is (str(text)[0] in "=+-@"), text
    assert b"<f>" not in zipfile.ZipFile(io.BytesIO(data)).read("xl/worksheets/sheet1.xml")


def test_a_decimal_keeps_its_places_and_a_date_is_a_date() -> None:
    data = WRITER.workbook(_book(("x", Decimal("0.6890"), date(2026, 10, 2))))

    sheet = load_workbook(io.BytesIO(data)).worksheets[0]
    price = next(c for row in sheet.iter_rows() for c in row if c.value == 0.689)
    assert price.number_format == "0.0000"


def test_the_same_content_writes_the_same_bytes() -> None:
    book = _book(("a", 1, None))

    assert WRITER.workbook(book) == WRITER.workbook(book)
    assert WRITER.pdf(book) == WRITER.pdf(book)
    entries = zipfile.ZipFile(io.BytesIO(WRITER.workbook(book))).infolist()
    assert {e.date_time for e in entries} == {(2026, 10, 2, 2, 0, 0)}


def test_the_pdf_prints_markup_as_characters_and_japanese_beside_vietnamese() -> None:
    data = WRITER.pdf(_book(("御見積書 Đỗ Minh Giang", HOSTILE[-1], None), language="ja"))

    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)
    assert "御見積書" in text and "Đỗ Minh Giang" in text
    assert "<b>not a tag</b> & more" in text


def test_a_draft_is_unsent_from_and_to_the_addresses_it_names() -> None:
    draft = EmailDraft(
        sender=EmailAddress(address="an.nguyen@alpha.local", display_name="Nguyễn Văn An"),
        reply_to=EmailAddress(address="sales@seller.example", display_name="Sales"),
        to=(EmailAddress(address="purchasing@velatrix.example"),),
        subject="Xác nhận đơn hàng VLX-PO-2609-0118",
        body="Kính gửi\n- Dòng 1",
        dated=AT,
        attachments=(FileAttachment("Q26-0301.xlsx", XLSX, b"PK..."),),
    )

    data = WRITER.email(draft)

    message = email.message_from_bytes(data, policy=policy.default)
    assert data == WRITER.email(draft)
    assert message["X-Unsent"] == "1"
    assert str(message["From"]) == "Nguyễn Văn An <an.nguyen@alpha.local>"
    assert str(message["Reply-To"]) == "Sales <sales@seller.example>"
    assert str(message["To"]) == "purchasing@velatrix.example"
    assert str(message["Subject"]) == draft.subject
    (attached,) = message.iter_attachments()
    assert (attached.get_filename(), attached.get_content()) == ("Q26-0301.xlsx", b"PK...")


def test_a_subject_cannot_carry_a_second_header() -> None:
    draft = EmailDraft(
        sender=EmailAddress(address="an.nguyen@alpha.local"),
        reply_to=EmailAddress(address="sales@seller.example"),
        to=(EmailAddress(address="a@b.example"),),
        subject="PO 1\r\nBcc: attacker@evil.example",
        body="x",
        dated=AT,
    )

    with pytest.raises(ValueError):
        WRITER.email(draft)
