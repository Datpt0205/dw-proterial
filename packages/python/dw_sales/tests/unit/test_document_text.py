"""The reader's ``text.document`` operation (DW2's PR forms and scanned
requests, ADR 0013 decision 2's interim): a document's text for a model to
read, each page or sheet with any, a page with no text layer read by OCR and
said to be, a legacy file converted first, and anything that is no document
said to be no document. Run through the wire the sandbox is sent, in
process, with the tools' stand-ins (`dw_sales.testing.reading_tools`)."""

from __future__ import annotations

import asyncio
import hashlib
import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from dw_platform.domain.messages import Attachment, AttachmentContent
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR
from dw_sales.adapters.order_rules import load_order_rules
from dw_sales.adapters.reader_client import ClientDocumentText
from dw_sales.adapters.reader_wire import DocumentText
from dw_sales.adapters.readers.operations import InProcessReaderTransport, ReaderTools
from dw_sales.testing.reading_tools import SCAN, ScriptedConverter, TruthOcr, compound_file

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
CAPS = load_order_rules(REPO / "configs/policies/sales_order_rules@1.6.0.yaml").intake


def _content(data: bytes) -> AttachmentContent:
    return AttachmentContent(
        attachment=Attachment(
            attachment_id="A1",
            name="pr.bin",
            media_type="application/octet-stream",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        data=data,
    )


def _form() -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "PR"
    sheet.append(["Số PR", "PR-2611-013"])
    sheet.append([1, "GT-C5", "Găng tay chống cắt", 30, "đôi"])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _read(data: bytes, tools: ReaderTools) -> DocumentText | None:
    client = ClientDocumentText(InProcessReaderTransport(tools=tools), CAPS)
    return asyncio.run(client.read(_content(data)))


def _tools(ocr: TruthOcr | None = None, made: bytes | None = None) -> ReaderTools:
    return ReaderTools(converter=ScriptedConverter(made), ocr=ocr)


def test_an_excel_form_is_read_as_its_visible_cells_with_no_page_by_ocr() -> None:
    ocr = TruthOcr()
    read = _read(_form(), _tools(ocr))
    assert read is not None and read.kind == "xlsx" and read.ocr_pages == []
    (part,) = read.parts
    assert part.text == "Số PR | PR-2611-013\n1 | GT-C5 | Găng tay chống cắt | 30 | đôi"
    assert ocr.pages == []


def test_a_scanned_page_is_read_by_ocr_and_said_to_be() -> None:
    data = SCAN.read_bytes()
    read = _read(data, _tools(TruthOcr()))
    assert read is not None and read.kind == "pdf"
    assert read.ocr_pages == [part.page for part in read.parts] and read.ocr_pages
    assert "BRN-PO-2610-027" in read.parts[0].text
    assert all(part.sha256 == hashlib.sha256(data).hexdigest() for part in read.parts)


def test_a_scan_where_no_ocr_is_installed_has_no_text() -> None:
    read = _read(SCAN.read_bytes(), _tools(None))
    assert read is not None and read.parts == [] and read.ocr_pages == []


def test_a_text_pdf_is_read_from_its_text_layer_not_by_ocr() -> None:
    ocr = TruthOcr()
    read = _read((ATTACHMENTS_DIR / "M03_BRN-PO-2609-031.pdf").read_bytes(), _tools(ocr))
    assert read is not None and read.parts and read.ocr_pages == [] and ocr.pages == []


def test_a_legacy_workbook_is_read_from_its_converted_copy_named_as_the_original() -> None:
    legacy = compound_file("Workbook")
    read = _read(legacy, _tools(made=_form()))
    assert read is not None and read.kind == "xls"
    assert "PR-2611-013" in read.parts[0].text
    assert read.parts[0].sha256 == hashlib.sha256(legacy).hexdigest()


def test_a_conversion_that_fails_gives_no_text_not_a_failed_read() -> None:
    read = _read(compound_file("Workbook"), ReaderTools(converter=ScriptedConverter(error="x")))
    assert read is not None and read.kind == "xls" and read.parts == []


@pytest.mark.parametrize("data", [b"\x89PNG\r\n\x1a\n not a form", b"PK\x03\x04 no workbook"])
def test_no_document_is_said_to_be_none(data: bytes) -> None:
    read = _read(data, _tools(TruthOcr()))
    assert read is not None and read.kind == "other" and read.parts == []


def test_a_file_over_the_caps_is_not_sent() -> None:
    class Never:
        async def call(self, request: object) -> object:
            raise AssertionError("sent")

    client = ClientDocumentText(Never(), CAPS.model_copy(update={"max_attachment_bytes": 4}))  # type: ignore[arg-type]
    assert asyncio.run(client.read(_content(_form()))) is None
