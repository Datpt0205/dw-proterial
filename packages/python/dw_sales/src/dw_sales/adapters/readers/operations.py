"""The reader operations: what reading one file means, by name (ticket 25).

`handle` takes a `ReaderRequest` and answers a `ReaderReply`, calling the
in-process readers this package holds (PO, quotation forms, attachment text,
source view). It runs in two places, and nowhere else:

- **in the reader sandbox** (`apps/reader`): one throwaway process per
  request, under the containment the sandbox owns (no network, ulimits, a wall
  clock that kills the process group, a capped answer). Where every deployed
  process reads a file;
- **in process**, through `InProcessReaderTransport`, for unit tests, evals
  and a host-run local worker (`DW_SALES_READER=in_process`, refused in a
  deployed profile). The request and the reply still cross the wire format,
  so what a test exercises is what the sandbox is sent.

**A legacy file is converted first** (ticket 27): an `.xls` PO to `.xlsx` and
a `.doc` to PDF by the tools' converter (`readers.legacy`), then read, mapped
or shown like one. Every anchor read from the copy names both hashes, the
customer's file's and the copy's, and the PO names the converter
(`Derivation`). A conversion that fails makes the file unreadable with the
reason, never a failed run. **A scanned PDF page is read by OCR** where the
tools have an engine (`readers.ocr`, flagged in `readers.pdf`).

The tools are the image's (`ReaderTools.installed`): LibreOffice and
Tesseract. In process, where neither is installed, a legacy file is
unreadable ("LibreOffice is not installed where this file was read") and a
scan is as unreadable as before; a test hands in its own.

The API never imports this module (an import-linter contract says so): it
reaches the readers through the sandbox only.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

from dw_sales.adapters.formats import sniff
from dw_sales.adapters.reader_client import Dw1Readers, client_readers
from dw_sales.adapters.reader_wire import (
    RESULTS,
    PdfPage,
    ReaderOp,
    ReaderReply,
    ReaderRequest,
)
from dw_sales.adapters.readers.documents import PoDocumentReaders
from dw_sales.adapters.readers.excel import ExcelPoReader
from dw_sales.adapters.readers.layouts import MOCK_EXCEL_LAYOUTS, MOCK_PDF_LAYOUTS
from dw_sales.adapters.readers.legacy import (
    ConversionError,
    ConverterPort,
    Legacy,
    LibreOfficeConverter,
)
from dw_sales.adapters.readers.ocr import PageOcrPort, TesseractOcr
from dw_sales.adapters.readers.pdf import PdfPoReader
from dw_sales.adapters.readers.text_parts import AttachmentTexts
from dw_sales.adapters.rfq_excel import ExcelDesignReplyReader, ExcelQuoteForms, ExcelRfqReader
from dw_sales.adapters.source_view import FileSourceView
from dw_sales.application.quote_ports import QuoteFileUnreadableError
from dw_sales.domain.messages import AttachmentContent
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.orders import Derivation, PoDocument, Unreadable

logger = logging.getLogger("dw_sales.reader")


@dataclass(frozen=True)
class ReaderTools:
    """The tools a reading process starts besides its own code (ticket 27)."""

    converter: ConverterPort = field(default_factory=LibreOfficeConverter)
    ocr: PageOcrPort | None = field(default_factory=TesseractOcr)

    @classmethod
    def installed(cls) -> ReaderTools:
        """LibreOffice and Tesseract, as the reader's image installs them."""
        return cls()

    def po_readers(self) -> PoDocumentReaders:
        """The readers for the fictional customers' layouts, a scan read by OCR."""
        return PoDocumentReaders(
            ExcelPoReader(MOCK_EXCEL_LAYOUTS), PdfPoReader(MOCK_PDF_LAYOUTS, ocr=self.ocr)
        )


@dataclass(frozen=True, slots=True)
class _Readable:
    """The file a reader opens: the attachment, or its converted copy, with
    how the copy was made and what it was made from."""

    content: AttachmentContent
    original_sha256: str
    derivation: Derivation | None

    def as_read(self, operation: ReaderOp, value: object) -> object:
        """``value`` read from the copy, as read from the attachment: every
        anchor names both hashes, and a PO the converter (module docstring)."""
        if self.derivation is None or value is None:
            return value
        adapter = RESULTS[operation]
        dumped = _named_both(
            adapter.dump_python(value, mode="json"),
            original=self.original_sha256,
            derived=str(self.derivation.derived_sha256),
        )
        if isinstance(value, PoDocument):
            dumped["derivation"] = self.derivation.model_dump(mode="json")
        return adapter.validate_python(dumped)


def _named_both(value: Any, *, original: str, derived: str) -> Any:
    """``value`` with every hash of the copy put back to the attachment's,
    and every anchor naming the copy's hash beside it."""
    if isinstance(value, list):
        return [_named_both(item, original=original, derived=derived) for item in value]
    if not isinstance(value, dict):
        return value
    named = {k: _named_both(v, original=original, derived=derived) for k, v in value.items()}
    if named.get("attachment_sha256") == derived:
        named["attachment_sha256"] = original
        if "derived_sha256" in named:  # an anchor
            named["derived_sha256"] = derived
    return named


def _legacy(data: bytes) -> Legacy | None:
    """The legacy kind of the file, which the reader converts first."""
    match sniff(data):
        case "xls":
            return "xls"
        case "doc":
            return "doc"
        case _:
            return None


def _readable(request: ReaderRequest, tools: ReaderTools) -> _Readable:
    """The attachment, or its copy when it is a legacy file. Raises
    `ConversionError` when the copy cannot be made."""
    content = request.content()
    kind = _legacy(content.data)
    if kind is None:
        return _Readable(content, content.attachment.sha256, None)
    converted = tools.converter.convert(content.data, kind)
    stem = content.attachment.name.rpartition(".")[0] or content.attachment.name
    copy = AttachmentContent(
        attachment=content.attachment.model_copy(
            update={
                "name": f"{stem}.{converted.kind}",
                "size": len(converted.data),
                "sha256": converted.sha256,
            }
        ),
        data=converted.data,
    )
    derivation = Derivation(
        method="converted", tool=converted.tool, derived_sha256=converted.sha256
    )
    return _Readable(copy, content.attachment.sha256, derivation)


def _readable_bytes(request: ReaderRequest, tools: ReaderTools) -> bytes:
    """A source view's bytes: a legacy file's copy, so it is shown as it was
    read. A copy that cannot be made is a refusal (ValueError)."""
    data = request.data()
    kind = _legacy(data)
    if kind is None:
        return data
    try:
        return tools.converter.convert(data, kind).data
    except ConversionError as failed:
        raise ValueError(f"the {kind} file could not be converted to be shown: {failed}") from None


_Operation = Callable[[ReaderRequest, ReaderTools], Awaitable[Any]]


async def _document(
    request: ReaderRequest,
    tools: ReaderTools,
    operation: ReaderOp,
    read: Callable[[PoDocumentReaders, AttachmentContent], Awaitable[PoDocument | Unreadable]],
) -> Any:
    try:
        readable = await asyncio.to_thread(_readable, request, tools)
    except ConversionError as failed:
        kind = sniff(request.content().data)
        return Unreadable(reason=f"the {kind} file could not be converted: {failed}"[:500])
    return readable.as_read(operation, await read(tools.po_readers(), readable.content))


async def _buyer(request: ReaderRequest, tools: ReaderTools) -> Any:
    caps = request.args.required(request.args.caps, "caps")
    try:
        readable = await asyncio.to_thread(_readable, request, tools)
    except ConversionError:
        return None
    found = await tools.po_readers().buyer(readable.content, caps)
    return readable.as_read(ReaderOp.PO_BUYER, found)


async def _read(request: ReaderRequest, tools: ReaderTools) -> Any:
    args = request.args
    customer, caps = args.required(args.customer_code, "customer_code"), _caps(request)
    return await _document(
        request, tools, ReaderOp.PO_READ, lambda po, content: po.read(content, customer, caps)
    )


async def _read_with(request: ReaderRequest, tools: ReaderTools) -> Any:
    args = request.args
    mapping, caps = args.required(args.mapping, "mapping"), _caps(request)
    ref = args.required(args.layout_ref, "layout_ref")
    return await _document(
        request,
        tools,
        ReaderOp.PO_READ_WITH,
        lambda po, content: po.read_with(content, mapping, caps, layout_ref=ref),
    )


async def _label_source(request: ReaderRequest, tools: ReaderTools) -> Any:
    caps = _caps(request)
    try:
        readable = await asyncio.to_thread(_readable, request, tools)
    except ConversionError:
        return None
    return await tools.po_readers().label_source(readable.content, caps)


async def _layouts(request: ReaderRequest, tools: ReaderTools) -> Any:
    # The same constants the PO readers are built from.
    return {"xlsx": sorted(MOCK_EXCEL_LAYOUTS), "pdf": sorted(MOCK_PDF_LAYOUTS)}


async def _form(request: ReaderRequest, tools: ReaderTools) -> Any:
    return await asyncio.to_thread(ExcelQuoteForms().form, request.content())


async def _rfq(request: ReaderRequest, tools: ReaderTools) -> Any:
    return await asyncio.to_thread(ExcelRfqReader().read, request.content())


async def _design_reply(request: ReaderRequest, tools: ReaderTools) -> Any:
    return await asyncio.to_thread(ExcelDesignReplyReader().read, request.content())


async def _text_parts(request: ReaderRequest, tools: ReaderTools) -> Any:
    return list(await AttachmentTexts().text_parts(request.content(), _caps(request)))


async def _pdf_page(request: ReaderRequest, tools: ReaderTools) -> Any:
    data = await asyncio.to_thread(_readable_bytes, request, tools)
    page = request.args.required(request.args.page, "page")
    opened = await FileSourceView(_caps(request)).pdf_page(data, page)
    if opened is None:
        return None
    pdf, pages = opened
    return PdfPage(pdf_b64=base64.b64encode(pdf).decode("ascii"), pages=pages)


async def _sheet_names(request: ReaderRequest, tools: ReaderTools) -> Any:
    data = await asyncio.to_thread(_readable_bytes, request, tools)
    return await FileSourceView(_caps(request)).sheet_names(data)


async def _sheet_grid(request: ReaderRequest, tools: ReaderTools) -> Any:
    data = await asyncio.to_thread(_readable_bytes, request, tools)
    sheet = request.args.required(request.args.sheet, "sheet")
    return await FileSourceView(_caps(request)).sheet_grid(data, sheet)


def _caps(request: ReaderRequest) -> IntakeCaps:
    return request.args.required(request.args.caps, "caps")


# Every operation the wire names, and what answers it: one table. A test holds
# its keys to `ReaderOp`'s, so an operation cannot be named and unanswered.
OPERATIONS: Final[Mapping[ReaderOp, _Operation]] = MappingProxyType(
    {
        ReaderOp.PO_BUYER: _buyer,
        ReaderOp.PO_READ: _read,
        ReaderOp.PO_READ_WITH: _read_with,
        ReaderOp.PO_LABEL_SOURCE: _label_source,
        ReaderOp.PO_LAYOUTS: _layouts,
        ReaderOp.QUOTE_FORM: _form,
        ReaderOp.QUOTE_RFQ: _rfq,
        ReaderOp.QUOTE_DESIGN_REPLY: _design_reply,
        ReaderOp.TEXT_PARTS: _text_parts,
        ReaderOp.SOURCE_PDF_PAGE: _pdf_page,
        ReaderOp.SOURCE_SHEET_NAMES: _sheet_names,
        ReaderOp.SOURCE_SHEET_GRID: _sheet_grid,
    }
)


async def handle(request: ReaderRequest, tools: ReaderTools | None = None) -> ReaderReply:
    """One operation's answer. A request or reply the readers refuse
    (ValueError: over a cap, the wrong kind of file, a missing argument) is a
    `refused` reply; an unreadable quotation file says where. Anything else
    raises: the caller counts it a crash, in the sandbox by the process's
    exit and in process by the transport."""
    try:
        value = await OPERATIONS[request.operation](request, tools or ReaderTools.installed())
    except QuoteFileUnreadableError as unreadable:
        problem = str(unreadable.details.get("problem", "unreadable"))
        return ReaderReply.failed("quote_file_unreadable", problem, at=unreadable.at)
    except ValueError as refused:
        return ReaderReply.failed("refused", str(refused))
    return ReaderReply.answered(request.operation, value)


@dataclass(frozen=True)
class InProcessReaderTransport:
    """`ReaderTransport` in this process: no containment, for tests, evals and
    a host-run local worker only (module docstring). The request and the reply
    are serialised and parsed again, as the sandbox's are, and the call runs
    under the same wall clock the sandbox gives a read (``read_seconds``),
    past which the reply is `timed_out`; the thread is not stopped. ``tools``
    are the installed ones unless a test hands in its own."""

    read_seconds: float = 30.0
    tools: ReaderTools | None = None

    async def call(self, request: ReaderRequest) -> ReaderReply:
        sent = ReaderRequest.model_validate_json(request.model_dump_json())
        try:
            reply = await asyncio.wait_for(handle(sent, self.tools), self.read_seconds)
        except TimeoutError:
            reply = ReaderReply.failed(
                "timed_out", f"reading took longer than {self.read_seconds:g} s"
            )
        except Exception as crashed:
            # The type only: an exception's text may quote the file.
            logger.warning("reader operation %s raised %s", sent.operation, type(crashed).__name__)
            reply = ReaderReply.failed("crashed", type(crashed).__name__)
        return ReaderReply.model_validate_json(reply.model_dump_json())


def in_process_readers(caps: IntakeCaps, tools: ReaderTools | None = None) -> Dw1Readers:
    """DW1's readers in this process (`InProcessReaderTransport`): what a
    test, an eval and a host-run local worker read files with."""
    return client_readers(InProcessReaderTransport(tools=tools), caps)
