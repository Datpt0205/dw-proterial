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
from dw_sales.application.order_ports import FileType
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


def mock_po_readers() -> PoDocumentReaders:
    """The readers for the fictional customers' layouts."""
    return PoDocumentReaders(ExcelPoReader(MOCK_EXCEL_LAYOUTS), PdfPoReader(MOCK_PDF_LAYOUTS))
