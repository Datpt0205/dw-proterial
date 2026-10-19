"""What crosses the boundary to the reader sandbox, both ways (ticket 25).

One owner for the wire: the client (`reader_client`), the operations that
answer it (`readers.operations`) and the sandbox service (`apps/reader`) all
read these models, so a field added on one side cannot be dropped silently by
another.

- **`ReaderRequest`**: one operation (`ReaderOp`), the attachment it reads
  (its description and its bytes, base64), and the arguments the operation
  takes (`ReaderArgs`). An attachment's description is checked against its
  bytes on the way in (`AttachmentContent`): size and sha256 travel with them.
- **`ReaderReply`**: the operation's result as JSON, validated on arrival
  against the type its operation returns (`RESULTS`), or why there is none.
  A failure names a kind and a code, never a byte of the file:
    - ``timed_out``: the wall clock ran out and the reading process was killed;
    - ``crashed``: the reading process died, or raised (its type name only);
    - ``refused``: the file is over a limit the reader holds, or not of the
      kind the operation reads;
    - ``quote_file_unreadable``: a request or Design reply with a value that
      cannot be read (`QuoteFileUnreadableError`), with its place.

Everything here is data, and the sandbox's answer is no more trusted than the
file it read: a value in a reply is what the file says, checked by code
downstream exactly as an in-process read was.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from dw_sales.application.order_ports import QuoteForm
from dw_sales.application.source import SheetGrid
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.layouts import LayoutMapping, LayoutSource
from dw_sales.domain.master_data import ImportedTable
from dw_sales.domain.messages import Attachment, AttachmentContent
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.orders import PoDocument, PrintedBuyer, Unreadable
from dw_sales.domain.quotes import DesignReplyDocument, RfqDocument
from dw_sales.domain.rfq_reading import TextPart

_WIRE = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ReaderOp(StrEnum):
    """Every operation the reader answers. Each reads one attachment, or
    (``po.layouts``) none."""

    PO_BUYER = "po.buyer"
    PO_READ = "po.read"
    PO_READ_WITH = "po.read_with"
    PO_LABEL_SOURCE = "po.label_source"
    PO_LAYOUTS = "po.layouts"
    QUOTE_FORM = "quote.form"
    QUOTE_RFQ = "quote.rfq"
    QUOTE_DESIGN_REPLY = "quote.design_reply"
    TEXT_PARTS = "text.parts"
    SOURCE_PDF_PAGE = "source.pdf_page"
    SOURCE_SHEET_NAMES = "source.sheet_names"
    SOURCE_SHEET_GRID = "source.sheet_grid"
    # A master-data file as rows of cells (ticket 41).
    TABLE_ROWS = "table.rows"


class ReaderArgs(BaseModel):
    """What an operation takes besides the file. Each operation reads the
    fields it names and refuses the call without them (`required`)."""

    model_config = _WIRE

    caps: IntakeCaps | None = None
    customer_code: str | None = Field(default=None, max_length=64)
    mapping: LayoutMapping | None = None
    layout_ref: str | None = Field(default=None, max_length=200)
    page: int | None = Field(default=None, ge=1)
    sheet: str | None = Field(default=None, max_length=200)

    def required[T](self, value: T | None, name: str) -> T:
        if value is None:
            raise ValueError(f"the operation needs {name}")
        return value


class ReaderRequest(BaseModel):
    """One operation on one file. ``attachment`` describes ``content_b64``
    where the caller holds the description; a source view sends the bytes
    alone."""

    model_config = _WIRE

    operation: ReaderOp
    attachment: Attachment | None = None
    content_b64: str | None = None
    args: ReaderArgs = Field(default_factory=ReaderArgs)

    @classmethod
    def of(
        cls,
        operation: ReaderOp,
        *,
        content: AttachmentContent | None = None,
        data: bytes | None = None,
        args: ReaderArgs | None = None,
    ) -> ReaderRequest:
        raw = content.data if content is not None else data
        return cls(
            operation=operation,
            attachment=None if content is None else content.attachment,
            content_b64=None if raw is None else base64.b64encode(raw).decode("ascii"),
            args=args or ReaderArgs(),
        )

    def data(self) -> bytes:
        """The file's bytes. Refused (ValueError) when none were sent."""
        if self.content_b64 is None:
            raise ValueError("the operation reads a file and none was sent")
        try:
            return base64.b64decode(self.content_b64, validate=True)
        except (binascii.Error, ValueError) as refused:
            raise ValueError("the file's bytes are not base64") from refused

    def content(self) -> AttachmentContent:
        """The attachment with its bytes, which must be the ones described."""
        if self.attachment is None:
            raise ValueError("the operation reads an attachment and none was described")
        return AttachmentContent(attachment=self.attachment, data=self.data())


Failure = Literal["timed_out", "crashed", "refused", "quote_file_unreadable"]


class ReaderReply(BaseModel):
    """An operation's result, or why there is none (module docstring)."""

    model_config = _WIRE

    result: JsonValue = None
    failure: Failure | None = None
    # A code or a sentence code wrote: never text read from the file.
    detail: str | None = Field(default=None, max_length=500)
    # Where an unreadable request or Design reply has the value it could not read.
    at: SourceAnchor | None = None

    @classmethod
    def answered(cls, operation: ReaderOp, value: object) -> ReaderReply:
        return cls(result=RESULTS[operation].dump_python(value, mode="json"))

    @classmethod
    def failed(
        cls, failure: Failure, detail: str, *, at: SourceAnchor | None = None
    ) -> ReaderReply:
        return cls(failure=failure, detail=detail[:500], at=at)

    def value(self, operation: ReaderOp) -> Any:
        """The result as its operation's type (`RESULTS`)."""
        return RESULTS[operation].validate_python(self.result)


class PdfPage(BaseModel):
    """One page copied out as a one-page PDF, and how many the file has."""

    model_config = _WIRE

    pdf_b64: str
    pages: int = Field(ge=1)


# What each operation returns: the one table both sides validate against.
RESULTS: Final[Mapping[ReaderOp, TypeAdapter[Any]]] = MappingProxyType(
    {
        ReaderOp.PO_BUYER: TypeAdapter(PrintedBuyer | None),
        ReaderOp.PO_READ: TypeAdapter(PoDocument | Unreadable),
        ReaderOp.PO_READ_WITH: TypeAdapter(PoDocument | Unreadable),
        ReaderOp.PO_LABEL_SOURCE: TypeAdapter(LayoutSource | None),
        # The customers the platform's own layouts read, by kind of file.
        ReaderOp.PO_LAYOUTS: TypeAdapter(dict[Literal["pdf", "xlsx"], list[str]]),
        ReaderOp.QUOTE_FORM: TypeAdapter(QuoteForm | None),
        ReaderOp.QUOTE_RFQ: TypeAdapter(RfqDocument | None),
        ReaderOp.QUOTE_DESIGN_REPLY: TypeAdapter(DesignReplyDocument | None),
        ReaderOp.TEXT_PARTS: TypeAdapter(list[TextPart]),
        ReaderOp.SOURCE_PDF_PAGE: TypeAdapter(PdfPage | None),
        ReaderOp.SOURCE_SHEET_NAMES: TypeAdapter(list[str]),
        ReaderOp.SOURCE_SHEET_GRID: TypeAdapter(SheetGrid | None),
        ReaderOp.TABLE_ROWS: TypeAdapter(ImportedTable),
    }
)
