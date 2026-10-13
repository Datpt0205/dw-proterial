"""`PoDocumentReaderPort`: what a file is, by its bytes, and the reader for it.

The type is sniffed from the first bytes and the container's own table of
contents, never from the file name or the media type the sender declared: both
are the sender's claim. A file that is not what it claims is still read as
what it is, or refused for what it is.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from typing import Final

from dw_sales.adapters.readers.excel import ExcelPoReader
from dw_sales.adapters.readers.layouts import MOCK_EXCEL_LAYOUTS, MOCK_PDF_LAYOUTS
from dw_sales.adapters.readers.pdf import PdfPoReader
from dw_sales.adapters.readers.stored import excel_layout, pdf_layout
from dw_sales.application.order_ports import FileType
from dw_sales.domain.layouts import LayoutMapping, LayoutSource
from dw_sales.domain.messages import AttachmentContent
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.orders import PoDocument, PrintedBuyer, Unreadable

_PDF: Final = b"%PDF-"
_ZIP: Final = b"PK\x03\x04"
# An OLE compound file: a legacy .xls/.doc, or an encrypted OOXML workbook.
_OLE: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_IMAGES: Final = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*", b"GIF8")
_WORKBOOK: Final = "xl/workbook.xml"


def sniff(data: bytes) -> FileType | None:
    """What the bytes are, as far as a PO goes.

    ``pdf`` and ``xlsx`` are read. ``unsupported`` is a document DW1 does not
    read in this slice (a scan as an image, a legacy or encrypted Office file,
    an archive), which routes the message to Sales with the reason. None is
    anything else.
    """
    if data.startswith(_PDF):
        return "pdf"
    if data.startswith(_ZIP):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return "unsupported"
        return "xlsx" if _WORKBOOK in names else "unsupported"
    if data.startswith(_OLE) or data.startswith(_IMAGES):
        return "unsupported"
    return None


class PoDocumentReaders:
    """Implements `PoDocumentReaderPort` with an Excel and a text-PDF reader."""

    def __init__(self, excel: ExcelPoReader, pdf: PdfPoReader) -> None:
        self._excel = excel
        self._pdf = pdf

    def sniff(self, data: bytes) -> FileType | None:
        return sniff(data)

    async def buyer(self, document: AttachmentContent, caps: IntakeCaps) -> PrintedBuyer | None:
        if sniff(document.data) != "xlsx":
            return None
        return await asyncio.to_thread(self._excel.buyer, document, caps)

    async def read(
        self, document: AttachmentContent, customer_code: str, caps: IntakeCaps
    ) -> PoDocument | Unreadable:
        kind = sniff(document.data)
        # Parsing is CPU work on a file of the sender's choosing: off the event loop.
        if kind == "xlsx":
            return await asyncio.to_thread(self._excel.read, document, customer_code, caps)
        if kind == "pdf":
            return await asyncio.to_thread(self._pdf.read, document, customer_code, caps)
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
                return await asyncio.to_thread(
                    self._excel.read_with, document, layout, caps, layout_ref=layout_ref
                )
            if kind == "pdf" and mapping.kind == "pdf":
                pdf = pdf_layout(mapping)
                return await asyncio.to_thread(
                    self._pdf.read_with, document, pdf, caps, layout_ref=layout_ref
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
            cells = await asyncio.to_thread(self._excel.label_cells, document, caps)
            rows = await asyncio.to_thread(self._excel.form_rows, document, caps)
            if not cells:
                return None
            return LayoutSource(
                kind="excel", cells=tuple(cells[:2000]), rows=tuple(map(tuple, rows[:60]))
            )
        if kind == "pdf":
            cells = await asyncio.to_thread(self._pdf.label_cells, document, caps)
            rows = await asyncio.to_thread(self._pdf.form_rows, document, caps)
            if not cells:
                return None
            return LayoutSource(
                kind="pdf", cells=tuple(cells[:2000]), rows=tuple(map(tuple, rows[:60]))
            )
        return None


def mock_po_readers() -> PoDocumentReaders:
    """The readers for the fictional customers' layouts."""
    return PoDocumentReaders(ExcelPoReader(MOCK_EXCEL_LAYOUTS), PdfPoReader(MOCK_PDF_LAYOUTS))
