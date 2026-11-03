"""DW2's `MailFileReaderPort` and `WorkbookReaderPort` over the reader
sandbox's client that exists.

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
from dw_purchasing.application.mail_drop import MailFile, MailRefused
from dw_purchasing.application.master_data import WorkbookUnreadableError
from dw_purchasing.domain.master_lists import CellValue, SheetRows, fold
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
