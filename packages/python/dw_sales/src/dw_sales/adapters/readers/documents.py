"""The PO readers in process: an Excel and a text-PDF reader behind one door.

What a file is comes from `dw_sales.adapters.formats` (`sniff`, `refusal`),
re-exported here for the readers that import it from this module. Since
ticket 25 this runs only where reading is contained: in the reader sandbox
(`apps/reader`, through `dw_sales.adapters.readers.operations`), and in
process for tests, evals and a host-run local worker
(`InProcessReaderTransport`), never in the API.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

from dw_sales.adapters.formats import refusal, sniff
from dw_sales.adapters.readers.excel import ExcelPoReader
from dw_sales.adapters.readers.layouts import MOCK_EXCEL_LAYOUTS, MOCK_PDF_LAYOUTS
from dw_sales.adapters.readers.pdf import PdfPoReader
from dw_sales.adapters.readers.stored import excel_layout, pdf_layout
from dw_sales.application.order_ports import FileType
from dw_sales.domain.layouts import LayoutMapping, LayoutSource
from dw_sales.domain.messages import AttachmentContent
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.orders import PoDocument, PrintedBuyer, Unreadable

__all__ = ["PoDocumentReaders", "mock_po_readers", "refusal", "sniff"]

_T = TypeVar("_T")


class PoDocumentReaders:
    """An Excel and a text-PDF reader behind one door: what the reader
    operations (`readers.operations`) call for a PO. The application reaches
    it only through `PoDocumentReaderPort`, which the reader client satisfies
    (`dw_sales.adapters.reader_client`).

    **Every read has a wall clock** (ticket 25): parsing a file of the
    sender's choosing runs off the event loop, and one that takes longer than
    ``read_seconds`` comes back `Unreadable` ("reading took longer than ..."),
    so the message is routed with the reason and the run goes on. The thread
    itself cannot be stopped from here: in the reader sandbox the process
    reading it is killed by its parent (`apps/reader`), which is the clock
    that contains it; in process (tests, evals, a host-run local worker) it
    finishes on its own.
    """

    def __init__(
        self, excel: ExcelPoReader, pdf: PdfPoReader, *, read_seconds: float = 30.0
    ) -> None:
        self._excel = excel
        self._pdf = pdf
        self._seconds = read_seconds

    async def _within(self, call: Callable[[], _T]) -> _T | Unreadable:
        """``call`` off the event loop, or `Unreadable` once the clock runs out."""
        try:
            return await asyncio.wait_for(asyncio.to_thread(call), self._seconds)
        except TimeoutError:
            return Unreadable(reason=f"reading took longer than {self._seconds:g} s")

    def sniff(self, data: bytes) -> FileType | None:
        return sniff(data)

    def refusal(self, name: str, data: bytes) -> str | None:
        return refusal(name, data)

    async def buyer(self, document: AttachmentContent, caps: IntakeCaps) -> PrintedBuyer | None:
        if sniff(document.data) != "xlsx":
            return None
        found = await self._within(lambda: self._excel.buyer(document, caps))
        return None if isinstance(found, Unreadable) else found

    async def read(
        self, document: AttachmentContent, customer_code: str, caps: IntakeCaps
    ) -> PoDocument | Unreadable:
        kind = sniff(document.data)
        # Parsing is CPU work on a file of the sender's choosing: off the event loop.
        if kind == "xlsx":
            return await self._within(lambda: self._excel.read(document, customer_code, caps))
        if kind == "pdf":
            return await self._within(lambda: self._pdf.read(document, customer_code, caps))
        return Unreadable(reason="not a PO format read in this slice (text PDF or .xlsx)")

    def has_layout(self, customer_code: str, file_type: FileType) -> bool:
        """Whether the platform's layouts read this customer's file of this type."""
        if file_type == "xlsx":
            return self._excel.has_layout(customer_code)
        if file_type == "pdf":
            return self._pdf.has_layout(customer_code)
        return False

    async def read_with(
        self,
        document: AttachmentContent,
        mapping: LayoutMapping,
        caps: IntakeCaps,
        *,
        layout_ref: str,
    ) -> PoDocument | Unreadable:
        """``document`` read with a layout people mapped (ticket 30): the same
        reader as every other PO, given the tenant's labels."""
        kind = sniff(document.data)
        try:
            if kind == "xlsx" and mapping.kind == "excel":
                layout = excel_layout(mapping)
                return await self._within(
                    lambda: self._excel.read_with(document, layout, caps, layout_ref=layout_ref)
                )
            if kind == "pdf" and mapping.kind == "pdf":
                pdf = pdf_layout(mapping)
                return await self._within(
                    lambda: self._pdf.read_with(document, pdf, caps, layout_ref=layout_ref)
                )
        except ValueError as refused:
            return Unreadable(reason=f"the layout cannot be read with: {refused}"[:500])
        return Unreadable(reason="the file is not of the kind the layout maps")

    async def label_source(
        self, document: AttachmentContent, caps: IntakeCaps
    ) -> LayoutSource | None:
        """The text cells of the form a label may be (ticket 30), or None for
        a file that is no form a layout can map."""
        kind = sniff(document.data)
        if kind == "xlsx":
            read = await self._within(
                lambda: (
                    self._excel.label_cells(document, caps),
                    self._excel.form_rows(document, caps),
                )
            )
            if isinstance(read, Unreadable) or not read[0]:
                return None
            cells, rows = read
            return LayoutSource(
                kind="excel", cells=tuple(cells[:2000]), rows=tuple(map(tuple, rows[:60]))
            )
        if kind == "pdf":
            printed = await self._within(
                lambda: (
                    self._pdf.label_cells(document, caps),
                    self._pdf.form_rows(document, caps),
                )
            )
            if isinstance(printed, Unreadable) or not printed[0]:
                return None
            cells, rows = printed
            return LayoutSource(
                kind="pdf", cells=tuple(cells[:2000]), rows=tuple(map(tuple, rows[:60]))
            )
        return None


def mock_po_readers() -> PoDocumentReaders:
    """The readers for the fictional customers' layouts."""
    return PoDocumentReaders(ExcelPoReader(MOCK_EXCEL_LAYOUTS), PdfPoReader(MOCK_PDF_LAYOUTS))
