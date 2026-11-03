"""DW2 reads an `.eml` file through the reader sandbox's client that exists
(Sales'), adapted at the composition root (ADR 0013 decision 2, the interim):
the answer is DW2's own type, a refusal keeps its reason, and a reader that
does not answer still raises."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from dw_kernel.errors import InfrastructureError
from dw_platform.domain.messages import EmailAddress, InboundMessage
from dw_purchasing.application.mail_drop import MailFile, MailRefused
from dw_sales.application import mail_drop as sales
from dw_worker.purchasing_reader import PurchasingMailReader, PurchasingWorkbookReader

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
