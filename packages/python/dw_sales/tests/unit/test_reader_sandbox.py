"""Every file is read through the reader's wire (ticket 25): what the client
asks, what the operations answer, and what a failure becomes.

A file the reader could not read is that file's outcome (a PO `Unreadable`, a
form not found, no text); a reader that does not answer is an outage that
records nothing (`ReaderUnavailableError`). The in-process transport crosses
the same wire as the sandbox, so these tests exercise what the sandbox is sent.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from dw_kernel.errors import DomainError
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR
from dw_sales.adapters.order_rules import load_order_rules
from dw_sales.adapters.reader_client import (
    ClientDesignReplyReader,
    ClientPoReaders,
    ClientQuoteForms,
    ClientRfqReader,
    ClientSourceView,
    ClientTexts,
    HttpReaderTransport,
    ReaderUnavailableError,
)
from dw_sales.adapters.reader_wire import RESULTS, ReaderArgs, ReaderOp, ReaderReply, ReaderRequest
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.adapters.readers.operations import OPERATIONS, InProcessReaderTransport, handle
from dw_sales.application.quote_ports import QuoteFileUnreadableError
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.messages import Attachment, AttachmentContent
from dw_sales.domain.orders import PoDocument, Unreadable

pytestmark = pytest.mark.unit

CAPS = load_order_rules(
    Path(__file__).resolve().parents[5] / "configs" / "policies" / "sales_order_rules@1.5.0.yaml"
).intake
M01 = "M01_VLX-PO-2609-0118.xlsx"
M03 = "M03_BRN-PO-2609-031.pdf"
M09 = "M09_QRL-RFQ-2609-03.xlsx"
M18 = "M18_YCBG-2609-028-reply.xlsx"


def _content(name: str, data: bytes | None = None) -> AttachmentContent:
    raw = (ATTACHMENTS_DIR / name).read_bytes() if data is None else data
    attachment = Attachment(
        attachment_id="A1",
        name=name,
        media_type="application/octet-stream",
        size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    return AttachmentContent(attachment=attachment, data=raw)


class _Replying:
    """A transport that answers every request with one reply, and counts."""

    def __init__(self, reply: ReaderReply) -> None:
        self.reply = reply
        self.asked: list[ReaderRequest] = []

    async def call(self, request: ReaderRequest) -> ReaderReply:
        self.asked.append(request)
        return self.reply


class _Down:
    async def call(self, request: ReaderRequest) -> ReaderReply:
        raise ReaderUnavailableError("connection refused")


# ------------------------------------------------------------------ the wire --


def test_every_operation_has_one_answer_and_one_result_type() -> None:
    assert set(OPERATIONS) == set(ReaderOp) == set(RESULTS)


async def test_a_po_read_through_the_wire_is_the_po_the_readers_read() -> None:
    content = _content(M01)

    through = await ClientPoReaders(InProcessReaderTransport()).read(content, "VLX", CAPS)
    direct = await mock_po_readers().read(content, "VLX", CAPS)

    assert isinstance(through, PoDocument)
    assert through == direct


async def test_a_text_pdf_and_its_source_view_cross_the_wire() -> None:
    content = _content(M03)
    view = ClientSourceView(InProcessReaderTransport(), CAPS)

    read = await ClientPoReaders(InProcessReaderTransport()).read(content, "BRN", CAPS)
    page = await view.pdf_page(content.data, 1)

    assert isinstance(read, PoDocument)
    assert page is not None and page[0].startswith(b"%PDF-") and page[1] >= 1
    assert await view.pdf_page(content.data, 99) is None


async def test_quotation_forms_cross_the_wire() -> None:
    transport = InProcessReaderTransport()

    assert await ClientQuoteForms(transport).form(_content(M09)) == "quote_request"
    assert await ClientQuoteForms(transport).form(_content(M18)) == "design_reply"
    assert await ClientRfqReader(transport).read(_content(M09)) is not None
    assert await ClientDesignReplyReader(transport).read(_content(M18)) is not None
    assert await ClientRfqReader(transport).read(_content(M01)) is None


async def test_bytes_that_are_not_the_ones_described_are_refused() -> None:
    content = _content(M01)
    request = ReaderRequest.of(ReaderOp.PO_READ, content=content).model_copy(
        update={"content_b64": base64.b64encode(b"other bytes").decode("ascii")}
    )

    reply = await handle(request)

    assert reply.failure == "refused"
    assert reply.result is None


async def test_an_operation_missing_its_arguments_is_refused_not_crashed() -> None:
    reply = await handle(ReaderRequest.of(ReaderOp.PO_READ, content=_content(M01)))

    assert reply.failure == "refused"
    assert reply.detail == "the operation needs customer_code"


async def test_a_read_past_the_transport_clock_is_timed_out() -> None:
    request = ReaderRequest.of(ReaderOp.PO_READ, content=_content(M01)).model_copy(
        update={"args": ReaderArgs(caps=CAPS, customer_code="VLX")}
    )

    reply = await InProcessReaderTransport(read_seconds=0.0).call(request)

    assert reply.failure == "timed_out"
    assert reply.detail == "reading took longer than 0 s"


# --------------------------------------------- a file's failure is its outcome --


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        ("timed_out", "reading took longer than 120 s"),
        ("crashed", "the reader failed on this file"),
        ("refused", "the file is over the size the reader takes"),
    ],
)
async def test_a_po_the_reader_gave_up_on_is_unreadable_with_why(failure: str, reason: str) -> None:
    detail = None if failure == "crashed" else reason
    transport = _Replying(ReaderReply.model_validate({"failure": failure, "detail": detail}))

    read = await ClientPoReaders(transport).read(_content(M01), "VLX", CAPS)
    buyer = await ClientPoReaders(transport).buyer(_content(M01), CAPS)
    source = await ClientPoReaders(transport).label_source(_content(M01), CAPS)

    assert read == Unreadable(reason=reason)
    assert buyer is None and source is None


async def test_the_other_readers_find_nothing_in_a_file_they_gave_up_on() -> None:
    transport = _Replying(ReaderReply.failed("crashed", "ValueError"))

    assert await ClientQuoteForms(transport).form(_content(M09)) is None
    assert await ClientRfqReader(transport).read(_content(M09)) is None
    assert await ClientDesignReplyReader(transport).read(_content(M18)) is None
    assert await ClientTexts(transport).text_parts(_content(M09), CAPS) == ()
    with pytest.raises(DomainError):
        await ClientSourceView(transport, CAPS).sheet_names(_content(M01).data)


async def test_an_unreadable_quotation_value_is_raised_with_its_place() -> None:
    at = SourceAnchor(attachment_id="A1", attachment_sha256="0" * 64, cell_ref="RFQ!C7")
    transport = _Replying(ReaderReply.failed("quote_file_unreadable", "quantity", at=at))

    with pytest.raises(QuoteFileUnreadableError) as refused:
        await ClientRfqReader(transport).read(_content(M09))

    assert refused.value.at == at


async def test_a_reader_that_does_not_answer_is_an_outage_never_an_unreadable_file() -> None:
    readers = ClientPoReaders(_Down())

    with pytest.raises(ReaderUnavailableError):
        await readers.read(_content(M01), "VLX", CAPS)
    with pytest.raises(ReaderUnavailableError):
        await ClientRfqReader(_Down()).read(_content(M09))
    with pytest.raises(ReaderUnavailableError):
        await readers.has_layout("VLX", "xlsx")


async def test_the_platform_layouts_are_asked_once() -> None:
    transport = _Replying(ReaderReply.answered(ReaderOp.PO_LAYOUTS, {"xlsx": ["VLX"], "pdf": []}))
    readers = ClientPoReaders(transport)

    assert await readers.has_layout("VLX", "xlsx")
    assert not await readers.has_layout("VLX", "pdf")
    assert not await readers.has_layout("BRN", "xlsx")
    assert len(transport.asked) == 1


async def test_a_failed_layouts_answer_is_an_outage() -> None:
    readers = ClientPoReaders(_Replying(ReaderReply.failed("crashed", "ImportError")))

    with pytest.raises(ReaderUnavailableError):
        await readers.has_layout("VLX", "xlsx")


# ------------------------------------------------------------------ over HTTP --


def _http(handler: httpx.MockTransport) -> HttpReaderTransport:
    return HttpReaderTransport(base_url="http://reader.test", http=handler)


async def test_the_http_transport_posts_the_request_and_reads_the_reply() -> None:
    seen: list[dict[str, object]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        reply = ReaderReply.answered(ReaderOp.PO_LAYOUTS, {"xlsx": [], "pdf": []})
        return httpx.Response(200, content=reply.model_dump_json())

    reply = await _http(httpx.MockTransport(answer)).call(ReaderRequest.of(ReaderOp.PO_LAYOUTS))

    assert reply.failure is None and reply.result == {"xlsx": [], "pdf": []}
    assert seen[0]["operation"] == "po.layouts"


async def test_a_file_too_large_for_the_reader_is_refused_not_an_outage() -> None:
    transport = _http(httpx.MockTransport(lambda _: httpx.Response(413)))

    reply = await transport.call(ReaderRequest.of(ReaderOp.PO_LAYOUTS))

    assert reply.failure == "refused"


@pytest.mark.parametrize(
    "response",
    [httpx.Response(503), httpx.Response(500), httpx.Response(200, content=b"not a reply")],
    ids=["unavailable", "error", "nonsense"],
)
async def test_a_reader_answering_anything_but_a_reply_is_an_outage(
    response: httpx.Response,
) -> None:
    transport = _http(httpx.MockTransport(lambda _: response))

    with pytest.raises(ReaderUnavailableError):
        await transport.call(ReaderRequest.of(ReaderOp.PO_LAYOUTS))


async def test_an_unreachable_reader_is_an_outage() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ReaderUnavailableError):
        await _http(httpx.MockTransport(refuse)).call(ReaderRequest.of(ReaderOp.PO_LAYOUTS))


# ---------------------------------------------- the answer is not trusted --


async def test_a_po_naming_another_file_than_the_one_sent_is_refused() -> None:
    """A reading process a hostile file took over answers for itself: its PO
    must still be of the file it was sent."""
    real = await mock_po_readers().read(_content(M01), "VLX", CAPS)
    assert isinstance(real, PoDocument)
    other = _content(M01, (ATTACHMENTS_DIR / M01).read_bytes() + b" ")
    transport = _Replying(ReaderReply.answered(ReaderOp.PO_READ, real))

    read = await ClientPoReaders(transport).read(other, "VLX", CAPS)

    assert read == Unreadable(reason="the reader's answer names another file than the one sent")


async def test_a_buyer_anchored_in_another_file_is_not_a_buyer() -> None:
    m13 = "M13_NRV-PO-26-0471.xlsx"
    real = await mock_po_readers().buyer(_content(m13), CAPS)
    assert real is not None
    transport = _Replying(ReaderReply.answered(ReaderOp.PO_BUYER, real))
    other = _content(m13, (ATTACHMENTS_DIR / m13).read_bytes() + b" ")

    assert await ClientPoReaders(transport).buyer(other, CAPS) is None
    assert await ClientPoReaders(transport).buyer(_content(m13), CAPS) == real
