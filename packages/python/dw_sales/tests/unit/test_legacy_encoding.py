"""Ticket 20: Vietnamese typed in a TCVN3 or VNI font is detected, never read as text.

The readers mark each value read from a cell or a PDF text run in such a font;
the document check raises a blocking PO-level `legacy_encoding` at the first
one; no attribute is matched on such a description; and the only way out is
the customer's PO sent again in Unicode, which arrives as a revision.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import itertools
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from pydantic import ValidationError
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, attachment_file_name
from dw_sales.adapters.mock.generate_attachments import FONT_PATH, load_purchase_orders
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.readers import ExcelPoReader, PdfPoReader, mock_po_readers
from dw_sales.adapters.readers.layouts import MOCK_EXCEL_LAYOUTS, MOCK_PDF_LAYOUTS
from dw_sales.adapters.rfq_excel import ExcelQuoteForms
from dw_sales.application.access import PriceView
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.application.views import order_case, order_finding
from dw_sales.domain.legacy_fonts import LegacyEncoding, legacy_encoding
from dw_sales.domain.messages import Attachment, AttachmentContent, InboundMessage
from dw_sales.domain.order_checks import IntakeCaps, check_document, map_line
from dw_sales.domain.orders import (
    Accepted,
    Actor,
    AskCustomer,
    CorrectedBySales,
    Finding,
    FindingCode,
    MappingStatus,
    OrderCase,
    OrderStatus,
    PoDocument,
    Severity,
    Unreadable,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[5]
RULES = load_order_rules(ROOT / "configs" / "policies" / "sales_order_rules@1.4.0.yaml")
CAPS = RULES.intake
EXCEL = ExcelPoReader(MOCK_EXCEL_LAYOUTS)
PDF = PdfPoReader(MOCK_PDF_LAYOUTS)
SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
AN = Actor(user_id=uuid.UUID(int=0xA1))
T0 = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
PRICES = PriceView(amounts=True, other_customers=False)

M01 = "M01_VLX-PO-2609-0118.xlsx"
M33 = "M33_VLX-PO-2610-0004.xlsx"
KEY = "legacy_encoding:-"


def _content(data: bytes, attachment_id: str = "A1") -> AttachmentContent:
    attachment = Attachment(
        attachment_id=attachment_id,
        name="po.xlsx",
        media_type="application/octet-stream",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    return AttachmentContent(attachment=attachment, data=data)


def _po(result: PoDocument | Unreadable) -> PoDocument:
    assert isinstance(result, PoDocument), result
    return result


def _excel(data: bytes) -> PoDocument:
    return _po(EXCEL.read(_content(data), "VLX", CAPS))


def _fixture(name: str) -> bytes:
    return (ATTACHMENTS_DIR / name).read_bytes()


def _edited(name: str, edit: Callable[[Workbook], object]) -> bytes:
    workbook = load_workbook(io.BytesIO(_fixture(name)))
    edit(workbook)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _where(document: PoDocument) -> tuple[str | None, LegacyEncoding] | None:
    first = document.first_legacy_text()
    return None if first is None else (first[0].cell_ref, first[1])


# -------------------------------------------------------------- the list --


@pytest.mark.parametrize(
    ("font", "encoding"),
    [
        (".VnTime", LegacyEncoding.TCVN3),
        (".VnTimeH", LegacyEncoding.TCVN3),
        (".VnArial", LegacyEncoding.TCVN3),
        (" .vnarial narrow", LegacyEncoding.TCVN3),
        ("VNI-Times", LegacyEncoding.VNI),
        ("VNI-Helve-Condense", LegacyEncoding.VNI),
        ("vni-aptima", LegacyEncoding.VNI),
        ("Times New Roman", None),
        ("Calibri", None),
        ("Arial Unicode MS", None),
        # Not a TCVN3 name: the dot is part of it.
        ("VnTime", None),
        ("", None),
        (None, None),
    ],
)
def test_a_font_name_says_which_legacy_encoding_it_types(
    font: str | None, encoding: LegacyEncoding | None
) -> None:
    assert legacy_encoding(font) == encoding


# ----------------------------------------------------------------- Excel --


def test_the_mock_po_typed_in_vntime_marks_the_cells_in_that_font_and_nothing_else() -> None:
    po = _excel(_fixture(M33))

    assert [(line.line_no, line.legacy_fields) for line in po.lines] == [
        (1, frozenset({"description"})),
        (2, frozenset({"description"})),
    ]
    assert not po.header.legacy and po.total is not None and not po.total.legacy
    # The first affected cell: line 1's description.
    assert _where(po) == ("PO!C10", LegacyEncoding.TCVN3)
    # Read as the cell holds it: the reader converts nothing (ADR 0010 decision 3).
    assert po.lines[0].description == "D©y ®iÖn 24AWG mµu ®en"


def _font(cell: str, name: str) -> Callable[[Workbook], None]:
    def edit(workbook: Workbook) -> None:
        workbook.worksheets[0][cell].font = Font(name=name)

    return edit


@pytest.mark.parametrize(
    ("cell", "font", "where"),
    [
        # The PO number, a header value.
        ("B4", ".VnArial", ("PO!B4", LegacyEncoding.TCVN3)),
        # A line's quantity: digits read the same, the cell is still in the font.
        ("D12", "VNI-Times", ("PO!D12", LegacyEncoding.VNI)),
        # The printed total.
        ("G14", "VNI-Helve", ("PO!G14", LegacyEncoding.VNI)),
        # The remarks: a cell no layout reads, so nothing read is affected.
        ("B7", ".VnTime", None),
    ],
)
def test_a_legacy_font_on_any_cell_the_reader_reads_is_detected_there(
    cell: str, font: str, where: tuple[str, LegacyEncoding] | None
) -> None:
    assert _where(_excel(_edited(M01, _font(cell, font)))) == where


def test_the_first_affected_cell_is_the_first_one_read_header_before_lines() -> None:
    def both(workbook: Workbook) -> None:
        _font("C10", ".VnTime")(workbook)
        _font("E5", "VNI-Times")(workbook)

    assert _where(_excel(_edited(M01, both))) == ("PO!E5", LegacyEncoding.VNI)


def test_no_mock_po_but_m33_holds_text_typed_in_a_legacy_font() -> None:
    """The existing fixtures raise no `legacy_encoding`."""
    affected = set()
    for po in load_purchase_orders():
        if po.layout == "pdf_image" or po.customer_code is None or po.form is not None:
            continue
        data = _content(
            (ATTACHMENTS_DIR / attachment_file_name(po.message_id, po.name)).read_bytes()
        )
        read: Callable[[AttachmentContent, str, IntakeCaps], PoDocument | Unreadable] = (
            PDF.read if po.layout == "pdf" else EXCEL.read
        )
        if _po(read(data, po.customer_code, CAPS)).first_legacy_text():
            affected.add(po.message_id)
    assert affected == {"M33"}


# ------------------------------------------------------------------- PDF --

# The mock Vietnamese layout (`test_po_readers.py` draws the same one): where
# each column is printed and whether it is right-aligned, its titles, one row.
_COLUMNS = (
    (55, True),
    (62, False),
    (140, False),
    (612, True),
    (618, False),
    (690, True),
    (770, True),
    (778, False),
)
_TITLES = (
    "STT",
    "Mã hàng KH",
    "Mô tả hàng hóa",
    "Số lượng",
    "ĐVT",
    "Đơn giá",
    "Thành tiền",
    "Ngày giao",
)
_ROW = (
    "1",
    "BRN-W-0007",
    "HOOK-UP WIRE 1C AWG24",
    "6.100",
    "m",
    "1.150",
    "7.015.000",
    "16/11/2026",
)


def _font_named(registered: str, face: str) -> str:
    """A TrueType font registered here, whose PDF base name is ``face``."""
    font = TTFont(registered, str(FONT_PATH))
    font.face.name = face.encode("ascii")
    pdfmetrics.registerFont(font)
    return registered


def _pdf(rows_font: str) -> bytes:
    """A one-page PO in the Vietnamese layout, the table rows drawn in ``rows_font``."""
    plain = _font_named("LegacyTestPlain", "DejaVuSans")
    buffer = io.BytesIO()
    width, height = landscape(A4)
    canvas = Canvas(buffer, pagesize=(width, height), invariant=1)
    y = height - 50
    canvas.setFont(plain, 9)
    for text in (
        "Số đơn hàng: BRN-PO-2610-001",
        "Lần sửa đổi: 0",
        "Ngày đặt hàng: 01/10/2026",
        "Đơn vị tiền tệ: VND",
    ):
        y -= 15
        canvas.drawString(40, y, text)
    for font, row in ((plain, _TITLES), (rows_font, _ROW)):
        y -= 14
        canvas.setFont(font, 7.5)
        for (x, right), value in zip(_COLUMNS, row, strict=True):
            (canvas.drawRightString if right else canvas.drawString)(x, y, value)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def test_a_pdf_run_drawn_in_a_vni_font_marks_the_values_it_drew() -> None:
    po = _po(PDF.read(_content(_pdf(_font_named("LegacyTestVni", "VNI-Times"))), "BRN", CAPS))

    (line,) = po.lines
    assert line.legacy_fields == set(type(line.anchors).model_fields)
    assert not po.header.legacy
    first = po.first_legacy_text()
    assert first is not None
    anchor, encoding = first
    # The first value of the row, on its page, boxed where it is printed.
    assert (anchor.page, anchor.quote, len(anchor.boxes), encoding) == (
        1,
        "1",
        1,
        LegacyEncoding.VNI,
    )


def test_a_pdf_value_drawn_apart_from_its_label_falls_back_to_its_page() -> None:
    """The PO number in VNI, its label in a Unicode font: two runs, so no run
    reads the whole ``label: value`` line, and the page's legacy run marks it
    (fail closed). The header lines drawn whole in one Unicode run are not."""
    plain = _font_named("LegacyTestPlain", "DejaVuSans")
    vni = _font_named("LegacyTestVniHeader", "VNI-Times")
    buffer = io.BytesIO()
    width, height = landscape(A4)
    canvas = Canvas(buffer, pagesize=(width, height), invariant=1)
    y = height - 65
    canvas.setFont(plain, 9)
    canvas.drawString(40, y, "Số đơn hàng:")
    canvas.setFont(vni, 9)
    canvas.drawString(110, y, "BRN-PO-2610-001")
    canvas.setFont(plain, 9)
    for text in ("Lần sửa đổi: 0", "Ngày đặt hàng: 01/10/2026", "Đơn vị tiền tệ: VND"):
        y -= 15
        canvas.drawString(40, y, text)
    for row in (_TITLES, _ROW):
        y -= 14
        canvas.setFont(plain, 7.5)
        for (x, right), value in zip(_COLUMNS, row, strict=True):
            (canvas.drawRightString if right else canvas.drawString)(x, y, value)
    canvas.showPage()
    canvas.save()

    po = _po(PDF.read(_content(buffer.getvalue()), "BRN", CAPS))

    assert po.header.po_no == "BRN-PO-2610-001"
    assert [(t.field, t.encoding) for t in po.header.legacy] == [("po_no", LegacyEncoding.VNI)]
    assert not po.lines[0].legacy


def test_a_pdf_in_a_unicode_font_has_no_legacy_text() -> None:
    po = _po(PDF.read(_content(_pdf(_font_named("LegacyTestUnicode", "DejaVuSans"))), "BRN", CAPS))

    assert po.first_legacy_text() is None


# ---------------------------------------------------------------- checks --


def test_the_document_check_raises_a_blocking_po_level_legacy_encoding() -> None:
    (finding,) = [
        f
        for f in check_document(_excel(_fixture(M33)), RULES)
        if f.code is FindingCode.LEGACY_ENCODING
    ]

    assert (finding.line_no, finding.severity, finding.blocking) == (None, Severity.ERROR, True)
    assert (finding.expected, finding.actual) == ("Unicode", "TCVN3")
    assert finding.rule_version == "sales_order_rules@1.4.0"
    assert not [
        f
        for f in check_document(_excel(_fixture(M01)), RULES)
        if f.code is FindingCode.LEGACY_ENCODING
    ]


async def test_no_attribute_is_matched_on_a_description_typed_in_a_legacy_font() -> None:
    """M33's line 2 states, in English words, an item exactly one catalogue
    item fits (`CB-2005`); typed in `.VnTime`, it is matched on nothing."""
    line = _excel(_fixture(M33)).lines[1]
    items = (await MockSalesCatalog.load(SCOPE).items(SCOPE)).data

    held = map_line(line, entry=None, items=items)
    unicode = map_line(line.model_copy(update={"legacy": ()}), entry=None, items=items)

    assert (held.mapping.status, held.mapping.candidates, held.item) == (
        MappingStatus.UNMAPPED,
        (),
        None,
    )
    assert (unicode.mapping.status, unicode.mapping.candidates) == (
        MappingStatus.CANDIDATE,
        ("CB-2005",),
    )


# ------------------------------------------------------------ the finding --


def _finding(**update: object) -> Finding:
    return Finding(
        code=FindingCode.LEGACY_ENCODING,
        severity=Severity.ERROR,
        rule_version=RULES.version,
        **update,
    )


def test_the_customer_is_asked_and_nothing_else_resolves_it() -> None:
    assert (
        _finding(disposition=AskCustomer(by=AN.user_id, at=T0)).disposition.kind == "ask_customer"
    )
    for refused in (
        Accepted(reason="đọc được", by=AN.user_id, at=T0),
        CorrectedBySales(value="Dây điện", source="đọc trên màn hình", by=AN.user_id, at=T0),
    ):
        with pytest.raises(ValidationError, match="cannot be"):
            _finding(disposition=refused)
    with pytest.raises(ValidationError, match="the PO as a whole"):
        _finding(line_no=1)


# --------------------------------------------------------------- the case --


class _Cases:
    """`OrderCaseLookupPort` over the cases this test kept."""

    def __init__(self) -> None:
        self.kept: list[OrderCase] = []

    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Sequence[OrderCase]:
        return [c for c in self.kept if (c.customer_code, c.header.po_no) == (customer_code, po_no)]


@dataclasses.dataclass
class _Resent:
    """The mock mailbox, plus M33 sent again by the customer in Unicode."""

    inbox: MockInbox
    message: InboundMessage
    content: AttachmentContent

    async def list_messages(self, scope: SalesScope) -> Sequence[InboundMessage]:
        return [*await self.inbox.list_messages(scope), self.message]

    async def get_message(self, scope: SalesScope, message_id: str) -> InboundMessage | None:
        if message_id == self.message.message_id:
            return self.message
        return await self.inbox.get_message(scope, message_id)

    async def read_attachment(
        self, scope: SalesScope, message_id: str, attachment_id: str
    ) -> AttachmentContent | None:
        if message_id == self.message.message_id:
            return self.content
        return await self.inbox.read_attachment(scope, message_id, attachment_id)


def _in_unicode(workbook: Workbook) -> None:
    sheet = workbook.worksheets[0]
    sheet["E4"] = 1  # Rev.1
    sheet["C10"] = "Dây điện 24AWG màu đen"
    for cell in ("C10", "C11"):
        sheet[cell].font = Font(name="Calibri")


async def _resent() -> _Resent:
    inbox = MockInbox.load(SCOPE)
    original = await inbox.get_message(SCOPE, "M33")
    assert original is not None
    content = _content(_edited(M33, _in_unicode), "M33R1-A1")
    message = original.model_copy(
        update={
            "message_id": "M33R1",
            "received_at": original.received_at + timedelta(days=1),
            "subject": "PO VLX-PO-2610-0004 Rev.1",
            "attachments": (
                content.attachment.model_copy(update={"name": "VLX-PO-2610-0004-Rev1.xlsx"}),
            ),
        }
    )
    named = content.model_copy(update={"attachment": message.attachments[0]})
    return _Resent(inbox, message, named)


def _intake(inbox: InboxPort, cases: _Cases) -> OrderIntake:
    ids = itertools.count(1)
    return OrderIntake(
        catalog=MockSalesCatalog.load(SCOPE),
        inbox=inbox,
        reader=mock_po_readers(),
        quote_forms=ExcelQuoteForms(),
        rules=PlatformOrderRules(RULES),
        cases=cases,
        new_case_id=lambda: uuid.UUID(int=next(ids)),
    )


async def _m33(cases: _Cases, inbox: InboxPort) -> OrderCase:
    message = await MockInbox.load(SCOPE).get_message(SCOPE, "M33")
    assert message is not None
    case = (await _intake(inbox, cases).process(SCOPE, message)).case
    assert case is not None
    return case.start_review()


async def test_a_po_typed_in_a_legacy_font_cannot_be_prepared_or_accepted() -> None:
    case = await _m33(_Cases(), MockInbox.load(SCOPE))

    assert case.finding(KEY).blocking
    with pytest.raises(ConflictError) as refused:
        case.prepare(AN, T0)
    assert KEY in cast(list[str], refused.value.details["open_findings"])
    with pytest.raises(ConflictError, match="cannot be accepted"):
        case.dispose(KEY, Accepted(reason="đọc được", by=AN.user_id, at=T0), AN)
    with pytest.raises(ConflictError, match="cannot be corrected_by_sales"):
        case.dispose(KEY, CorrectedBySales(value="x", source="y", by=AN.user_id, at=T0), AN)


async def test_the_screen_offers_only_asking_the_customer_and_opens_the_first_cell() -> None:
    case = await _m33(_Cases(), MockInbox.load(SCOPE))

    view = order_case(case, assigned_to=None, release_manifest_ref=None, prices=PRICES)
    assert view.legacy_text_anchor is not None
    assert view.legacy_text_anchor.cell_ref == "PO!C10"
    assert order_finding(case, case.finding(KEY), PRICES).allowed == ["ask_customer"]
    # A document read from Unicode text names no such place.
    m01 = await MockInbox.load(SCOPE).get_message(SCOPE, "M01")
    assert m01 is not None
    clean = (await _intake(MockInbox.load(SCOPE), _Cases()).process(SCOPE, m01)).case
    assert clean is not None
    no_view = order_case(clean, assigned_to=None, release_manifest_ref=None, prices=PRICES)
    assert no_view.legacy_text_anchor is None


def _line_1_hidden_and_alone_in_vntime(workbook: Workbook) -> None:
    sheet = workbook.worksheets[0]
    sheet.row_dimensions[10].hidden = True
    sheet["C11"].font = Font(name="Calibri")


async def test_typing_a_flagged_value_over_legacy_text_does_not_clear_the_finding() -> None:
    """Line 1's row is hidden too, so `value_uncertain` lets Sales type its
    description. The typed value is that finding's answer, not this one's:
    the PO is still the one the customer typed in `.VnTime`, and
    `legacy_encoding` is raised again on the recheck, still blocking, with the
    description still matched on nothing."""
    cases = _Cases()
    inbox = MockInbox.load(SCOPE)
    original = await inbox.get_message(SCOPE, "M33")
    assert original is not None
    content = _content(_edited(M33, _line_1_hidden_and_alone_in_vntime), "M33-A1")
    message = original.model_copy(update={"attachments": (content.attachment,)})
    intake = _intake(_Resent(inbox, message, content), cases)
    case = (await intake.process(SCOPE, message)).case
    assert case is not None
    case = case.start_review()
    assert {KEY, "value_uncertain:1"} <= {f.key for f in case.findings}
    assert case.line(2).po_line.legacy_fields == frozenset()

    corrected = await intake.correct_value(
        SCOPE, case, "value_uncertain:1", "description", "Dây điện 24AWG màu đen", AN, T0
    )

    assert corrected.line(1).effective.description == "Dây điện 24AWG màu đen"
    assert "description" in corrected.line(1).effective.legacy_fields
    assert corrected.finding(KEY).blocking
    assert corrected.finding(KEY).disposition.kind == "open"


async def test_the_po_sent_again_in_unicode_joins_the_case_and_is_read_afresh() -> None:
    """The re-upload: asked, the customer sends the PO again in Unicode, which
    arrives as a revision of the case; every check runs again on it."""
    cases = _Cases()
    resent = await _resent()
    case = await _m33(cases, resent)
    asked = case.dispose(KEY, AskCustomer(by=AN.user_id, at=T0), AN).request_correction()
    assert asked.status is OrderStatus.CORRECTION_REQUESTED
    cases.kept.append(asked)

    outcome = await _intake(resent, cases).process(SCOPE, resent.message)

    revised = outcome.case
    assert revised is not None and revised.case_id == asked.case_id
    assert revised.header.revision == 1
    assert FindingCode.LEGACY_ENCODING not in {f.code for f in revised.findings}
    # Now Unicode, line 2's description is matched by its attributes.
    assert revised.line(2).mapping.candidates == ("CB-2005",)
