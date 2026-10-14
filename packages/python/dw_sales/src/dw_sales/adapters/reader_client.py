"""DW1's readers as the application uses them: every file is read in the
reader sandbox (ticket 25, ADR 0010 decisions 2 and 6).

The application's reader ports (`PoDocumentReaderPort`, `LayoutReaderPort`,
`QuoteFormPort`, `RfqReaderPort`, `DesignReplyReaderPort`,
`AttachmentTextPort`, `SourceViewPort`) are satisfied here by asking a
`ReaderTransport` to run one operation (`reader_wire`) on one file:

- `HttpReaderTransport`: the reader sandbox (`apps/reader`), over its Unix
  socket in compose and in a deployment, or over the loopback gateway for a
  host-run local process. What every deployed process uses, and the only
  transport the API can reach (an import-linter contract keeps the parsers
  out of it);
- `readers.operations.InProcessReaderTransport`: the same operations in this
  process, for tests, evals and a host-run local worker.

**A file the reader could not read is that file's outcome, not an outage.** A
read that timed out, crashed or was refused comes back the way an unreadable
file always has: a PO is `Unreadable` with the reason (the message is routed
to Sales), a buyer, a form's cells or a quotation form is not found, a text
is empty, and a source view is refused (422). Nothing of the file's text is
logged: a failure is logged by its kind.

**A reader that does not answer is an outage**: `ReaderUnavailableError`
(503, "chưa đọc được tệp đính kèm, thử lại"), so nothing is recorded and the
processing is tried again, as when the malware scanner cannot answer.

Only `sniff` (and so `SourceViewPort.kind`) stays in the calling process:
magic numbers and a zip's table of contents (`dw_sales.adapters.formats`).
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal, Protocol

import httpx
from pydantic import ValidationError

from dw_kernel.errors import DomainError, InfrastructureError
from dw_sales.adapters.formats import refusal, sniff
from dw_sales.adapters.reader_wire import PdfPage, ReaderArgs, ReaderOp, ReaderReply, ReaderRequest
from dw_sales.application.order_ports import READ_AS, FileType, QuoteForm
from dw_sales.application.quote_ports import QuoteFileUnreadableError
from dw_sales.application.source import SheetGrid
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.layouts import LayoutMapping, LayoutSource
from dw_sales.domain.messages import AttachmentContent
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.orders import PoDocument, PrintedBuyer, Unreadable
from dw_sales.domain.quotes import DesignReplyDocument, RfqDocument
from dw_sales.domain.rfq_reading import TextPart

logger = logging.getLogger("dw_sales.reader")

# What a caller is told when the reader cannot answer; the button shows it.
READER_UNAVAILABLE: Final = "chưa đọc được tệp đính kèm, thử lại"

# Why a read the reader gave up on is unreadable, when it says no more.
_CRASHED: Final = "the reader failed on this file"
# Why a reading that names another file than the one sent is refused.
_ANOTHER_FILE: Final = "the reader's answer names another file than the one sent"


class ReaderUnavailableError(InfrastructureError):
    """The reader sandbox gave no answer: nothing is read, and a retry asks
    again (module docstring)."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            READER_UNAVAILABLE,
            details={"reason_code": "reader_unavailable", "reader": reason[:200]},
        )


class ReaderTransport(Protocol):
    """Runs one reader operation. Raises `ReaderUnavailableError` when no
    reply comes; a reply always comes for a file the reader could not read."""

    async def call(self, request: ReaderRequest) -> ReaderReply: ...


def _points_into(anchor: SourceAnchor, document: AttachmentContent) -> bool:
    """Whether ``anchor`` names the file that was sent."""
    return (anchor.attachment_id, anchor.attachment_sha256) == (
        document.attachment.attachment_id,
        document.attachment.sha256,
    )


def _failed(operation: ReaderOp, reply: ReaderReply) -> bool:
    """Whether the reply carries no result; logged by kind, never by detail."""
    if reply.failure is None:
        return False
    logger.warning("reader operation %s: %s", operation, reply.failure)
    return True


def _reason(reply: ReaderReply) -> str:
    """An unreadable PO's reason, from a failed reply."""
    if reply.failure == "crashed" or not reply.detail:
        return _CRASHED
    return reply.detail


async def _ask(
    transport: ReaderTransport,
    operation: ReaderOp,
    *,
    content: AttachmentContent | None = None,
    data: bytes | None = None,
    args: ReaderArgs | None = None,
) -> ReaderReply:
    return await transport.call(ReaderRequest.of(operation, content=content, data=data, args=args))


@dataclass
class ClientPoReaders:
    """`PoDocumentReaderPort` and `LayoutReaderPort` over the reader."""

    transport: ReaderTransport
    # The customers the platform's own layouts read, asked once: they are
    # code in the reader's image, so they cannot change under a process. Two
    # first calls at once both ask, and agree.
    _layouts: dict[str, list[str]] | None = field(default=None, repr=False)

    def sniff(self, data: bytes) -> FileType | None:
        return sniff(data)

    def refusal(self, name: str, data: bytes) -> str | None:
        """`FormatCheckPort`: the scanned mailbox's check of a file against
        its name, by its bytes, in this process (`formats.refusal`)."""
        return refusal(name, data)

    async def buyer(self, document: AttachmentContent, caps: IntakeCaps) -> PrintedBuyer | None:
        # A workbook prints its buyer where every PO does; a legacy one too,
        # once converted (ticket 27).
        if READ_AS.get(sniff(document.data) or "") != "xlsx":
            return None
        operation = ReaderOp.PO_BUYER
        reply = await _ask(self.transport, operation, content=document, args=ReaderArgs(caps=caps))
        found: PrintedBuyer | None = None if _failed(operation, reply) else reply.value(operation)
        if found is not None and not _points_into(found.anchor, document):
            logger.error("reader operation %s: the answer names another file", operation)
            return None
        return found

    async def read(
        self, document: AttachmentContent, customer_code: str, caps: IntakeCaps
    ) -> PoDocument | Unreadable:
        args = ReaderArgs(caps=caps, customer_code=customer_code)
        return await self._document(ReaderOp.PO_READ, document, args)

    async def read_with(
        self,
        document: AttachmentContent,
        mapping: LayoutMapping,
        caps: IntakeCaps,
        *,
        layout_ref: str,
    ) -> PoDocument | Unreadable:
        args = ReaderArgs(caps=caps, mapping=mapping, layout_ref=layout_ref)
        return await self._document(ReaderOp.PO_READ_WITH, document, args)

    async def label_source(
        self, document: AttachmentContent, caps: IntakeCaps
    ) -> LayoutSource | None:
        operation = ReaderOp.PO_LABEL_SOURCE
        reply = await _ask(self.transport, operation, content=document, args=ReaderArgs(caps=caps))
        source: LayoutSource | None = None if _failed(operation, reply) else reply.value(operation)
        return source

    async def has_layout(self, customer_code: str, file_type: FileType) -> bool:
        read_as = READ_AS.get(file_type)
        if read_as is None:
            return False
        return customer_code in (await self._platform_layouts()).get(read_as, ())

    async def _platform_layouts(self) -> dict[str, list[str]]:
        if self._layouts is None:
            operation = ReaderOp.PO_LAYOUTS
            reply = await _ask(self.transport, operation)
            if reply.failure is not None:
                # No file is read here: a failure is the reader's own.
                raise ReaderUnavailableError(f"{operation}: {reply.failure}")
            self._layouts = dict(reply.value(operation))
        return self._layouts

    async def _document(
        self, operation: ReaderOp, document: AttachmentContent, args: ReaderArgs
    ) -> PoDocument | Unreadable:
        reply = await _ask(self.transport, operation, content=document, args=args)
        if _failed(operation, reply):
            return Unreadable(reason=_reason(reply)[:500])
        read: PoDocument | Unreadable = reply.value(operation)
        if isinstance(read, PoDocument) and (read.attachment_id, read.attachment_sha256) != (
            document.attachment.attachment_id,
            document.attachment.sha256,
        ):
            # The answer is the sandbox's, no more trusted than the file it
            # read: a PO naming another file than the one sent is refused.
            logger.error("reader operation %s: the answer names another file", operation)
            return Unreadable(reason=_ANOTHER_FILE)
        return read


@dataclass(frozen=True)
class ClientQuoteForms:
    """`QuoteFormPort` over the reader."""

    transport: ReaderTransport

    async def form(self, content: AttachmentContent) -> QuoteForm | None:
        operation = ReaderOp.QUOTE_FORM
        reply = await _ask(self.transport, operation, content=content)
        found: QuoteForm | None = None if _failed(operation, reply) else reply.value(operation)
        return found


async def _quote_file[T](
    transport: ReaderTransport, operation: ReaderOp, content: AttachmentContent
) -> T | None:
    """A request or a Design reply: None when the reader does not recognise
    it or could not read it; `QuoteFileUnreadableError` where it is one with
    a value that cannot be read, as the in-process reader raised it."""
    reply = await _ask(transport, operation, content=content)
    if reply.failure == "quote_file_unreadable" and reply.at is not None:
        raise QuoteFileUnreadableError(reply.detail or "unreadable", at=reply.at)
    if _failed(operation, reply):
        return None
    document: T | None = reply.value(operation)
    return document


@dataclass(frozen=True)
class ClientRfqReader:
    """`RfqReaderPort` over the reader."""

    transport: ReaderTransport

    async def read(self, content: AttachmentContent) -> RfqDocument | None:
        return await _quote_file(self.transport, ReaderOp.QUOTE_RFQ, content)


@dataclass(frozen=True)
class ClientDesignReplyReader:
    """`DesignReplyReaderPort` over the reader."""

    transport: ReaderTransport

    async def read(self, content: AttachmentContent) -> DesignReplyDocument | None:
        return await _quote_file(self.transport, ReaderOp.QUOTE_DESIGN_REPLY, content)


@dataclass(frozen=True)
class ClientTexts:
    """`AttachmentTextPort` over the reader: no text for a file it could not
    read, so the request goes to a person."""

    transport: ReaderTransport

    async def text_parts(self, content: AttachmentContent, caps: IntakeCaps) -> Sequence[TextPart]:
        if content.attachment.size > caps.max_attachment_bytes:
            return ()
        operation = ReaderOp.TEXT_PARTS
        reply = await _ask(self.transport, operation, content=content, args=ReaderArgs(caps=caps))
        if _failed(operation, reply):
            return ()
        parts: list[TextPart] = reply.value(operation)
        return tuple(parts)


@dataclass(frozen=True)
class ClientSourceView:
    """`SourceViewPort` over the reader, bounded by the order rules' caps."""

    transport: ReaderTransport
    caps: IntakeCaps

    def kind(self, data: bytes) -> Literal["pdf", "xlsx"] | None:
        """What the file is shown as: a legacy one as its converted copy is
        (ticket 27), which the reader makes again to show it."""
        return READ_AS.get(sniff(data) or "")

    async def pdf_page(self, data: bytes, page: int) -> tuple[bytes, int] | None:
        opened: PdfPage | None = await self._open(
            ReaderOp.SOURCE_PDF_PAGE, data, ReaderArgs(caps=self.caps, page=page)
        )
        if opened is None:
            return None
        return base64.b64decode(opened.pdf_b64), opened.pages

    async def sheet_names(self, data: bytes) -> list[str]:
        names: list[str] = await self._open(
            ReaderOp.SOURCE_SHEET_NAMES, data, ReaderArgs(caps=self.caps)
        )
        return names

    async def sheet_grid(self, data: bytes, sheet: str) -> SheetGrid | None:
        grid: SheetGrid | None = await self._open(
            ReaderOp.SOURCE_SHEET_GRID, data, ReaderArgs(caps=self.caps, sheet=sheet)
        )
        return grid

    async def _open(self, operation: ReaderOp, data: bytes, args: ReaderArgs) -> Any:
        reply = await _ask(self.transport, operation, data=data, args=args)
        if _failed(operation, reply):
            raise DomainError(
                "tệp này không mở được để xem",
                details={"reason_code": "source_unreadable", "failure": reply.failure},
            )
        return reply.value(operation)


@dataclass(frozen=True)
class Dw1Readers:
    """Every reader port DW1's services take, over one transport."""

    po: ClientPoReaders
    forms: ClientQuoteForms
    rfq: ClientRfqReader
    design_reply: ClientDesignReplyReader
    texts: ClientTexts
    source: ClientSourceView


def client_readers(transport: ReaderTransport, caps: IntakeCaps) -> Dw1Readers:
    """DW1's readers over ``transport``; ``caps`` bound what a source view
    opens (the order rules' intake caps, as the source view always took)."""
    return Dw1Readers(
        po=ClientPoReaders(transport),
        forms=ClientQuoteForms(transport),
        rfq=ClientRfqReader(transport),
        design_reply=ClientDesignReplyReader(transport),
        texts=ClientTexts(transport),
        source=ClientSourceView(transport, caps),
    )


@dataclass(frozen=True)
class HttpReaderTransport:
    """The reader sandbox over HTTP: its Unix socket (``socket_path``) where
    this process mounts it, else ``base_url`` (the loopback gateway a host-run
    local process reaches it by). ``timeout_seconds`` is longer than the
    sandbox's own wall clock, which answers a slow file with `timed_out`.
    ``http`` replaces the connection itself (a test's)."""

    socket_path: str | None = None
    base_url: str = "http://127.0.0.1:8120"
    timeout_seconds: float = 180.0
    http: httpx.AsyncBaseTransport | None = field(default=None, repr=False)

    async def call(self, request: ReaderRequest) -> ReaderReply:
        connection = self.http or (
            httpx.AsyncHTTPTransport(uds=self.socket_path) if self.socket_path else None
        )
        # Over a socket the host name is never resolved; it names the service.
        base_url = "http://reader" if self.socket_path else self.base_url
        try:
            async with httpx.AsyncClient(
                transport=connection, base_url=base_url, timeout=self.timeout_seconds
            ) as client:
                response = await client.post(
                    "/v1/read",
                    content=request.model_dump_json(),
                    headers={"content-type": "application/json"},
                )
        except httpx.HTTPError as unreachable:
            raise ReaderUnavailableError(type(unreachable).__name__) from unreachable
        if response.status_code == httpx.codes.REQUEST_ENTITY_TOO_LARGE:
            return ReaderReply.failed("refused", "the file is over the size the reader takes")
        if response.status_code != httpx.codes.OK:
            raise ReaderUnavailableError(f"status {response.status_code}")
        try:
            return ReaderReply.model_validate_json(response.content)
        except ValidationError as nonsense:
            raise ReaderUnavailableError("the reader's answer is not a reply") from nonsense
