"""DW2's `MailFileReaderPort`, `WorkbookReaderPort` and `DocumentTextPort`
over the reader sandbox's client that exists.

ADR 0013 decision 2 makes the reader's mail operation the platform's; until
that split, the client is Sales' (`dw_sales.adapters.reader_client`), and
DW2 may not import Sales. So the composition root, which may import both,
adapts one to the other here: the same bytes read by the same sandbox, the
answer turned into DW2's own types. Removed when the split lands.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from dw_kernel.errors import DomainError, InfrastructureError
from dw_platform.domain.messages import AttachmentContent
from dw_purchasing.application.mail_drop import MailFile, MailRefused
from dw_purchasing.application.master_data import WorkbookUnreadableError
from dw_purchasing.domain.attachments import (
    MAX_PAGE_CHARS,
    MAX_PAGES,
    AttachmentPage,
    AttachmentReading,
)
from dw_purchasing.domain.master_lists import CellValue, SheetRows, fold
from dw_sales.adapters.reader_wire import DocumentText
from dw_sales.application import mail_drop as sales
from dw_sales.domain.master_data import ImportedTable


class _SalesMailReader(Protocol):
    async def read_mail(self, data: bytes) -> sales.MailFile | sales.MailRefused: ...


@dataclass(frozen=True)
class PurchasingMailReader:
    """Implements DW2's `MailFileReaderPort`. A reader that does not answer
    raises as it did (`InfrastructureError`)."""

    reader: _SalesMailReader

    async def read_mail(self, data: bytes) -> MailFile | MailRefused:
        read = await self.reader.read_mail(data)
        if isinstance(read, sales.MailRefused):
            return MailRefused(read.reason)
        return MailFile(message=read.message, contents=read.contents)


class _SalesSheetNames(Protocol):
    async def sheet_names(self, data: bytes) -> list[str]: ...


class _SalesTables(Protocol):
    async def read(
        self, data: bytes, file_name: str, sheet: str | None = None
    ) -> ImportedTable: ...


@dataclass(frozen=True)
class PurchasingWorkbookReader:
    """Implements DW2's `WorkbookReaderPort` over the same client: the
    workbook's sheet names first, then each sheet DW2 wants (case and accents
    aside) as rows. A sheet longer than the reader reads is refused whole,
    never cut short; a reader that does not answer raises as it did."""

    names: _SalesSheetNames
    tables: _SalesTables

    async def sheets(self, data: bytes, wanted: Sequence[str]) -> SheetRows:
        folded = {fold(name) for name in wanted}
        try:
            present = [n for n in await self.names.sheet_names(data) if fold(n) in folded]
            read: dict[str, list[tuple[int, Sequence[CellValue]]]] = {}
            for name in present:
                table = await self.tables.read(data, "workbook.xlsx", sheet=name)
                if table.truncated:
                    raise WorkbookUnreadableError(
                        f"trang {name} có quá nhiều dòng: chỉ giữ dòng cần dùng"
                        " (ví dụ giá mua gần nhất của mỗi vật tư với mỗi nhà cung cấp)"
                    )
                read[name] = [(row.row, list(row.cells)) for row in table.rows]
        except InfrastructureError:
            raise
        except DomainError as refused:
            if isinstance(refused, WorkbookUnreadableError):
                raise
            raise WorkbookUnreadableError(str(refused)) from None
        return read


class _SalesDocumentText(Protocol):
    async def read(self, content: AttachmentContent) -> DocumentText | None: ...


@dataclass(frozen=True)
class PurchasingDocumentReader:
    """Implements DW2's `DocumentTextPort` over the same client: each page or
    sheet with its text, and whether OCR read it. A file that is no document
    is `not_a_document`; one with no text, over the caps, given up on, or
    whose text DW2 would have to cut (a page past `MAX_PAGE_CHARS`, more
    than `MAX_PAGES`) is `unreadable`, never kept in part. An answer of
    another reader version is `unreadable` too: asking again gets the same.
    A reader that does not answer raises as it did."""

    reader: _SalesDocumentText

    async def read_text(self, content: AttachmentContent) -> AttachmentReading:
        try:
            read = await self.reader.read(content)
        except InfrastructureError:
            raise
        except DomainError:
            return AttachmentReading.refused("unreadable")
        if read is not None and read.kind == "other":
            return AttachmentReading.refused("not_a_document")
        if (
            read is None
            or not read.parts
            or len(read.parts) > MAX_PAGES
            or any(len(part.text) > MAX_PAGE_CHARS for part in read.parts)
        ):
            return AttachmentReading.refused("unreadable")
        ocr = set(read.ocr_pages)
        return AttachmentReading(
            pages=tuple(
                AttachmentPage(text=part.text, ocr=part.page is not None and part.page in ocr)
                for part in read.parts
            )
        )
