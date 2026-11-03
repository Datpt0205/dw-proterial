"""DW2 reads an `.eml` file, a workbook and an attachment's text through the
reader sandbox's client that exists (Sales'), adapted at the composition root
(ADR 0013 decision 2, the interim): the answer is DW2's own type, a refusal
keeps its reason, and a reader that does not answer still raises."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from dw_kernel.errors import DomainError, InfrastructureError
from dw_platform.domain.messages import (
    Attachment,
    AttachmentContent,
    EmailAddress,
    InboundMessage,
)
from dw_purchasing.application.mail_drop import MailFile, MailRefused
from dw_purchasing.domain.attachments import MAX_PAGE_CHARS, MAX_PAGES, AttachmentReading
from dw_sales.adapters.reader_wire import DocumentText
from dw_sales.application import mail_drop as sales
from dw_sales.domain.rfq_reading import TextPart
from dw_worker.purchasing_reader import (
    PurchasingDocumentReader,
    PurchasingMailReader,
    PurchasingWorkbookReader,
)

pytestmark = pytest.mark.unit


class SalesReader:
    def __init__(self, answer: sales.MailFile | sales.MailRefused | None) -> None:
        self.answer = answer

    async def read_mail(self, data: bytes) -> sales.MailFile | sales.MailRefused:
        if self.answer is None:
            raise InfrastructureError("the reader gave no answer")
        return self.answer


def _message(data: bytes) -> InboundMessage:
    return InboundMessage(
        message_id="eml-" + hashlib.sha256(data).hexdigest(),
        sender=EmailAddress(address="an@buyer.example"),
        subject="PR",
        received_at=datetime(2026, 11, 2, tzinfo=UTC),
        body_text="",
    )


async def test_a_read_mail_is_dw2_s_own_type_with_every_attachment() -> None:
    message = _message(b"x")
    read = await PurchasingMailReader(
        SalesReader(sales.MailFile(message=message, contents={"a1": b"bytes"}))
    ).read_mail(b"x")
    assert read == MailFile(message=message, contents={"a1": b"bytes"})


async def test_a_refusal_keeps_its_reason() -> None:
    read = await PurchasingMailReader(SalesReader(sales.MailRefused("not a mail"))).read_mail(b"x")
    assert read == MailRefused("not a mail")


async def test_a_reader_that_does_not_answer_still_raises() -> None:
    with pytest.raises(InfrastructureError):
        await PurchasingMailReader(SalesReader(None)).read_mail(b"x")


# ---------------------------------------------------------------- workbook --


def _reader() -> PurchasingWorkbookReader:
    from pathlib import Path

    from dw_sales.adapters.policy_files import load_sales_policies
    from dw_sales.adapters.reader_client import ClientSourceView, ClientTableReader
    from dw_sales.adapters.readers.operations import InProcessReaderTransport

    configs = Path(__file__).resolve().parents[4] / "configs"
    caps = load_sales_policies(configs / "policies", configs / "copy").order_rules.intake
    transport = InProcessReaderTransport()
    return PurchasingWorkbookReader(
        ClientSourceView(transport, caps), ClientTableReader(transport, caps)
    )


def _filled_template(**rows: list[list[object]]) -> bytes:
    import io

    from openpyxl import load_workbook

    from dw_purchasing.adapters.master_template import XlsxMasterTemplate

    book = load_workbook(io.BytesIO(XlsxMasterTemplate().workbook()))
    for sheet, values in rows.items():
        for row in values:
            book[sheet].append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


async def test_the_template_filled_in_reads_back_as_dw2s_lists_through_the_sandbox() -> None:
    from dw_purchasing.domain.master_lists import SHEETS, parse_workbook

    data = _filled_template(**{"Vật tư": [["GT-01", "Găng tay", "đôi"]]})

    sheets = await _reader().sheets(data, [s.sheet for s in SHEETS])

    # Every list's sheet is read, and the guide is not.
    assert set(sheets) == {s.sheet for s in SHEETS}
    parsed = parse_workbook(sheets)
    assert parsed.failure is None
    assert parsed.lists["items"] == [{"code": "GT-01", "description": "Găng tay", "unit": "đôi"}]
    assert parsed.lists["budgets"] == []


async def test_a_file_that_is_no_workbook_is_refused_with_a_reason() -> None:
    from dw_purchasing.application.master_data import WorkbookUnreadableError

    with pytest.raises(WorkbookUnreadableError):
        await _reader().sheets(b"PK\x03\x04 not really a zip", ["Vật tư"])


async def test_a_sheet_longer_than_the_reader_reads_is_refused_never_cut_short() -> None:
    from dw_purchasing.application.master_data import WorkbookUnreadableError
    from dw_sales.domain.master_data import ImportedTable, TableRow

    class Names:
        async def sheet_names(self, data: bytes) -> list[str]:
            return ["Hướng dẫn", "vat tu"]

    class Tables:
        async def read(
            self, data: bytes, file_name: str, sheet: str | None = None
        ) -> ImportedTable:
            assert sheet == "vat tu"
            return ImportedTable(sheet=sheet, rows=[TableRow(row=1, cells=["a"])], truncated=True)

    with pytest.raises(WorkbookUnreadableError, match="quá nhiều dòng"):
        await PurchasingWorkbookReader(Names(), Tables()).sheets(b"x", ["Vật tư"])


# ---------------------------------------------------------------- document --


def _attached(data: bytes = b"%PDF-1.7 scan") -> AttachmentContent:
    return AttachmentContent(
        attachment=Attachment(
            attachment_id="a1",
            name="scan.pdf",
            media_type="application/pdf",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        data=data,
    )


def _part(text: str, page: int | None) -> TextPart:
    return TextPart(
        part_id=f"a1#p{page}", text=text, attachment_id="a1", sha256="0" * 64, page=page
    )


class SalesDocuments:
    def __init__(self, answer: DocumentText | Exception | None) -> None:
        self.answer = answer

    async def read(self, content: AttachmentContent) -> DocumentText | None:
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


async def _text(answer: DocumentText | Exception | None) -> AttachmentReading:
    return await PurchasingDocumentReader(SalesDocuments(answer)).read_text(_attached())


async def test_a_document_s_pages_keep_which_were_read_by_ocr() -> None:
    read = await _text(
        DocumentText(kind="pdf", parts=[_part("PR-1", 1), _part("Dòng 1", 2)], ocr_pages=[2])
    )
    assert [(p.text, p.ocr) for p in read.pages] == [("PR-1", False), ("Dòng 1", True)]
    assert read.scanned


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (DocumentText(kind="other", parts=[]), "not_a_document"),
        (DocumentText(kind="pdf", parts=[]), "unreadable"),
        (None, "unreadable"),
        (DocumentText(kind="pdf", parts=[_part("x" * (MAX_PAGE_CHARS + 1), 1)]), "unreadable"),
        (
            DocumentText(kind="pdf", parts=[_part("x", n) for n in range(1, MAX_PAGES + 2)]),
            "unreadable",
        ),
        (DomainError("the reader's answer does not fit this version"), "unreadable"),
    ],
)
async def test_a_document_dw2_cannot_keep_whole_is_not_read_with_why(
    answer: DocumentText | Exception | None, reason: str
) -> None:
    """Never a page cut short or a page left out: a form read in part leaves
    out lines nobody knows are missing."""
    assert (await _text(answer)).not_read == reason


async def test_a_reader_that_does_not_answer_the_document_still_raises() -> None:
    with pytest.raises(InfrastructureError):
        await _text(InfrastructureError("the reader gave no answer"))
