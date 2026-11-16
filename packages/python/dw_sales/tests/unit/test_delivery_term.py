"""A PO's delivery term against the customer's (dw_sales ticket 02, acceptance 2).

The upload file writes the customer's term (`sales_bravo_upload`, a
`customer` column); a PO printing another one raises `delivery_term_mismatch`
for Sales to decide, never a silent fix either way. The term is read where a
person mapped its label on the customer's layout, kept as printed, and
compared in a closed set, Incoterms 2020, so "DAP Hanoi" is the customer's
"DAP". A PO that states no term, or a customer whose record holds none, has
nothing to compare.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from openpyxl import load_workbook
from pydantic import ValidationError
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.messages import Attachment, AttachmentContent, MailAuthentication
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR
from dw_sales.adapters.mock.generate_attachments import FONT_PATH
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.reader_client import ClientPoReaders, ClientQuoteForms
from dw_sales.adapters.readers import ExcelLayout, ExcelPoReader, PdfPoReader
from dw_sales.adapters.readers.layouts import ONE_SHEET, VIETNAMESE_PDF
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.adapters.readers.stored import excel_layout
from dw_sales.application.access import PriceView
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.application.views import order_case
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import Customer
from dw_sales.domain.layouts import LayoutMapping, flagged_as_new
from dw_sales.domain.order_checks import (
    IntakeCaps,
    check_customer,
    incoterm,
    same_delivery_term,
)
from dw_sales.domain.orders import (
    Actor,
    FindingCode,
    FlaggedValue,
    LinePo,
    OrderCase,
    PoDocument,
    PoHeader,
    PoHeaderAnchors,
    RegionFlag,
    Severity,
    Unreadable,
)
from dw_sales.domain.po_groups import per_po
from dw_sales.testing.followups import platform_zone

from .test_po_readers import _PDF_COLUMNS, _ROW, _TITLES

pytestmark = pytest.mark.unit

POLICIES = Path(__file__).resolve().parents[5] / "configs" / "policies"
RULES = load_order_rules(POLICIES / "sales_order_rules@1.15.0.yaml")
SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
SHA = "c" * 64
M01 = (ATTACHMENTS_DIR / "M01_VLX-PO-2609-0118.xlsx").read_bytes()
AN = Actor(user_id=uuid.UUID(int=0xA1))
T0 = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


# ------------------------------------------------------------- the comparison --


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("DAP", "DAP"),
        ("dap hanoi", "DAP"),
        ("FCA Haiphong, Incoterms 2020", "FCA"),
        ("C.I.P", None),  # no rule as a word of its own
        ("FCA or FOB", None),  # two rules: which one is not said
        ("DAPHNE warehouse", None),
        ("Door to door", None),
    ],
)
def test_a_term_names_one_incoterms_rule_as_a_word_or_none(text: str, rule: str | None) -> None:
    assert incoterm(text) == rule


@pytest.mark.parametrize(
    ("stated", "held", "same"),
    [
        ("DAP Hanoi", "DAP", True),
        ("Incoterms 2020: FCA Haiphong port", "FCA", True),
        ("FCA Haiphong", "DAP", False),
        ("FCA or DAP", "DAP", False),
        # A term outside Incoterms, as Bravo spells the customer's: the same words only.
        ("Door  to door", "door to door", True),
        ("Door to door", "DAP", False),
        ("DAP", "Door to door", False),
    ],
)
def test_a_stated_term_is_the_customers_only_when_it_names_the_same_one(
    stated: str, held: str, same: bool
) -> None:
    assert same_delivery_term(stated, held) is same


def _customer(term: str | None) -> Customer:
    return Customer.model_validate(
        {
            "code": "NRV",
            "name": "Norvanta Automotive Components Vietnam Co., Ltd.",
            "email_domains": ["norvanta.example"],
            "contacts": [{"address": "po-desk@norvanta.example"}],
            "language": "en",
            "intra_group": False,
            "compliance": {
                "noc_confirmed": True,
                "esf_fiscal_year": 2026,
                "denial_list_checked_on": "2026-09-01",
            },
            "status": "official",
            "confirmation_channel": "email",
            "sales_pic": None,
            "delivery_term": term,
        }
    )


def _checked(stated: str | None, held: str | None) -> list[tuple[str, str | None, str | None]]:
    found = check_customer(
        _customer(held),
        attributed_by_document=False,
        authentication=MailAuthentication(spf="pass", dkim="pass", dmarc="pass"),
        po_date=date(2026, 9, 24),
        received_on=date(2026, 9, 25),
        delivery_term=stated,
        rules=RULES,
    )
    return [(f.code.value, f.expected, f.actual) for f in found]


def test_a_po_stating_another_term_than_the_customers_raises_a_finding() -> None:
    (finding,) = check_customer(
        _customer("DAP"),
        attributed_by_document=False,
        authentication=MailAuthentication(spf="pass", dkim="pass", dmarc="pass"),
        po_date=date(2026, 9, 24),
        received_on=date(2026, 9, 25),
        delivery_term="FCA Haiphong",
        rules=RULES,
    )

    assert (finding.code, finding.line_no, finding.expected, finding.actual) == (
        FindingCode.DELIVERY_TERM_MISMATCH,
        None,
        "DAP",
        "FCA Haiphong",
    )
    # Wrong with the order as printed: shown as blocking, and Sales decides.
    assert finding.severity is Severity.ERROR
    assert finding.is_open and finding.rule_version == "sales_order_rules@1.15.0"


def test_the_customers_term_with_its_place_raises_nothing() -> None:
    assert _checked("DAP Hanoi", "DAP") == []


def test_nothing_to_compare_is_not_a_mismatch() -> None:
    assert _checked(None, "DAP") == []
    assert _checked("FCA Haiphong", None) == []


def test_a_term_that_names_no_single_rule_waits_for_a_person() -> None:
    assert _checked("FCA or DAP", "DAP") == [("delivery_term_mismatch", "DAP", "FCA or DAP")]


# ----------------------------------------------------------------- the PO read --


def _content(data: bytes) -> AttachmentContent:
    attachment = Attachment(
        attachment_id="A1",
        name="po.xlsx",
        media_type="application/octet-stream",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    return AttachmentContent(attachment=attachment, data=data)


def _with_term(term: str | None, label: str = "Incoterms") -> bytes:
    """M01 with the term printed beside its label at D6/E6 (E6 blank for None)."""
    workbook = load_workbook(io.BytesIO(M01))
    sheet = workbook["PO"]
    sheet["D6"] = label
    sheet["E6"] = term
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _caps() -> IntakeCaps:
    return RULES.intake


_TERMED = ExcelLayout(
    header_labels=MappingProxyType({**ONE_SHEET.header_labels, "delivery_term": "Incoterms"}),
    column_labels=ONE_SHEET.column_labels,
)


def _read(data: bytes, layout: ExcelLayout = _TERMED) -> PoDocument | Unreadable:
    return ExcelPoReader({"VLX": layout}).read(_content(data), "VLX", _caps())


def test_a_mapped_term_is_read_as_printed_at_its_cell() -> None:
    po = _read(_with_term("  FCA   Haiphong "))

    assert isinstance(po, PoDocument), po
    assert po.header.delivery_term == "FCA Haiphong"
    assert po.header.anchors.delivery_term is not None
    assert po.header.anchors.delivery_term.cell_ref == "PO!E6"


def test_a_blank_term_is_a_po_stating_none() -> None:
    po = _read(_with_term(None))

    assert isinstance(po, PoDocument), po
    assert (po.header.delivery_term, po.header.anchors.delivery_term) == (None, None)
    assert dict(po.header.anchors.stated()).keys() == {"po_no", "revision", "po_date", "currency"}


def test_a_layout_mapping_no_term_reads_none() -> None:
    po = _read(_with_term("FCA"), ONE_SHEET)

    assert isinstance(po, PoDocument), po
    assert po.header.delivery_term is None


def test_a_mapped_label_the_po_no_longer_prints_refuses_it() -> None:
    """As a mapped revision label does: the form changed, a person looks."""
    refused = _read(M01)

    assert isinstance(refused, Unreadable)
    assert "delivery term" in refused.reason


def _pdf(term_line: str) -> bytes:
    """A one-page PO in the mock Vietnamese layout printing ``term_line``
    under its header."""
    pdfmetrics.registerFont(TTFont("TermTest", str(FONT_PATH)))
    buffer = io.BytesIO()
    width, height = landscape(A4)
    canvas = Canvas(buffer, pagesize=(width, height), invariant=1)
    y = height - 50
    canvas.setFont("TermTest", 9)
    for text in (
        "Số đơn hàng: BRN-PO-2610-001",
        "Lần sửa đổi: 0",
        "Ngày đặt hàng: 01/10/2026",
        "Đơn vị tiền tệ: VND",
        term_line,
    ):
        y -= 15
        canvas.drawString(40, y, text)
    for row in (_TITLES, _ROW):
        y -= 14
        canvas.setFont("TermTest", 7.5)
        for (x, right), value in zip(_PDF_COLUMNS, row, strict=True):
            (canvas.drawRightString if right else canvas.drawString)(x, y, value)
    y -= 14
    canvas.drawString(612, y, "Tổng cộng: 7.015.000")
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


_TERMED_PDF = dataclasses.replace(
    VIETNAMESE_PDF,
    header_labels=MappingProxyType(
        {**VIETNAMESE_PDF.header_labels, "delivery_term": "Điều kiện giao hàng"}
    ),
)


@pytest.mark.parametrize(("printed", "read"), [("DAP Hà Nội", "DAP Hà Nội"), ("", None)])
def test_a_pdf_prints_its_term_on_a_labelled_line(printed: str, read: str | None) -> None:
    po = PdfPoReader({"BRN": _TERMED_PDF}).read(
        _content(_pdf(f"Điều kiện giao hàng: {printed}")), "BRN", _caps()
    )

    assert isinstance(po, PoDocument), po
    assert po.header.delivery_term == read
    assert (po.header.anchors.delivery_term is None) is (read is None)


def test_a_person_maps_the_term_on_the_layout_and_the_reader_takes_it() -> None:
    labels: dict[str, Any] = {
        "po_no": "PO No.",
        "po_date": "PO Date",
        "currency": "Currency",
        "line_no": "No.",
        "customer_item_code": "Customer Part No.",
        "description": "Description",
        "quantity": "Quantity",
        "uom": "UoM",
        "unit_price": "Unit Price",
        "amount": "Amount",
        "requested_date": "Requested Date",
        "total_label": "TOTAL",
    }
    mapping = LayoutMapping(kind="excel", delivery_term="Incoterms", **labels)

    assert mapping.labels()["delivery_term"] == "Incoterms"
    assert excel_layout(mapping).header_labels["delivery_term"] == "Incoterms"
    assert "delivery_term" not in LayoutMapping(kind="excel", **labels).header_labels()


def test_a_new_layouts_term_is_flagged_with_its_other_values_only_where_read() -> None:
    stated = _read(_with_term("FCA Haiphong"))
    blank = _read(_with_term(None))
    assert isinstance(stated, PoDocument) and isinstance(blank, PoDocument)

    assert "delivery_term" in flagged_as_new(stated).header.flagged
    assert "delivery_term" not in flagged_as_new(blank).header.flagged


def test_a_term_is_read_with_its_place_or_not_at_all() -> None:
    anchor = SourceAnchor(attachment_id="A1", attachment_sha256=SHA, cell_ref="PO!E6")
    anchors = PoHeaderAnchors(po_no=anchor, revision=anchor, po_date=anchor, currency=anchor)
    header: dict[str, Any] = {
        "po_no": "VLX-1",
        "revision": 0,
        "po_date": date(2026, 9, 19),
        "currency": "USD",
    }

    with pytest.raises(ValidationError, match="delivery term"):
        PoHeader(**header, anchors=anchors, delivery_term="DAP")
    with pytest.raises(ValidationError, match="delivery term"):
        PoHeader(**header, anchors=anchors.model_copy(update={"delivery_term": anchor}))


def test_each_po_of_a_file_keeps_the_term_its_header_prints() -> None:
    """A portal file naming two PO numbers is read as two POs (ticket 19)."""
    po = _read(_with_term("FCA Haiphong"))
    assert isinstance(po, PoDocument)
    first = po.lines[0]
    other = po.lines[1].model_copy(
        update={"line_po": LinePo(po_no="VLX-OTHER", anchor=first.anchors.line_no)}
    )
    split = po.model_copy(update={"lines": (first, other, *po.lines[2:])})

    parts = per_po(PoDocument.model_validate(split.model_dump()))

    assert len(parts) == 2
    for part in parts:
        assert part.header.delivery_term == "FCA Haiphong"
        assert part.header.anchors.delivery_term == po.header.anchors.delivery_term


# -------------------------------------------------------------- through intake --


class _StatingTerm(ClientPoReaders):
    """The platform's reader, each PO it reads printing ``term`` beside its
    currency (as a layout mapping the term reads it), flagged ``flags``."""

    def __init__(self, term: str, *flags: RegionFlag) -> None:
        super().__init__(InProcessReaderTransport())
        self.term = term
        self.flags = flags

    async def read(
        self, document: AttachmentContent, customer_code: str, caps: IntakeCaps
    ) -> PoDocument | Unreadable:
        read = await super().read(document, customer_code, caps)
        if not isinstance(read, PoDocument):
            return read
        header = read.header.model_dump()
        header["delivery_term"] = self.term
        header["anchors"]["delivery_term"] = header["anchors"]["currency"]
        header["flags"] = [
            *header["flags"],
            *(FlaggedValue(field="delivery_term", flag=flag) for flag in self.flags),
        ]
        return PoDocument.model_validate({**read.model_dump(), "header": header})


class _NoCases:
    async def cases_for_po(self, scope: SalesScope, customer_code: str, po_no: str) -> list[Any]:
        return []


async def _catalog(term: str) -> MockSalesCatalog:
    """The mock catalogue, Velatrix's record holding ``term``."""
    loaded = MockSalesCatalog.load(SCOPE)
    customers = [
        c.model_copy(update={"delivery_term": term}) if c.code == "VLX" else c
        for c in (await loaded.customers(SCOPE)).data
    ]
    return MockSalesCatalog(
        scope=SCOPE,
        as_of=(await loaded.customers(SCOPE)).as_of,
        customers=customers,
        items=(await loaded.items(SCOPE)).data,
        convert_list=(await loaded.convert_list(SCOPE)).data,
        quotations=(await loaded.quotations(SCOPE)).data,
        lme=(await loaded.lme_months(SCOPE)).data,
        bravo_orders=(await loaded.orders_since(SCOPE, date(2000, 1, 1))).data,
        open_ycbg=(await loaded.open_ycbg(SCOPE)).data,
    )


async def _intake(customer_term: str, reader: ClientPoReaders) -> OrderIntake:
    return OrderIntake(
        catalog=await _catalog(customer_term),
        inbox=MockInbox.load(SCOPE),
        reader=reader,
        quote_forms=ClientQuoteForms(InProcessReaderTransport()),
        zones=platform_zone(),
        rules=PlatformOrderRules(RULES),
        cases=_NoCases(),
        new_case_id=uuid.uuid4,
    )


async def _m01(intake: OrderIntake) -> OrderCase:
    message = await MockInbox.load(SCOPE).get_message(SCOPE, "M01")
    assert message is not None
    outcome = await intake.process(SCOPE, message)
    assert outcome.case is not None, outcome
    return outcome.case


def _terms(case: OrderCase) -> list[tuple[str | None, str | None, bool]]:
    return [
        (f.expected, f.actual, f.is_open)
        for f in case.findings
        if f.code is FindingCode.DELIVERY_TERM_MISMATCH
    ]


async def test_intake_raises_the_mismatch_on_the_case_sales_reviews() -> None:
    case = await _m01(await _intake("DAP", _StatingTerm("FCA Haiphong")))

    assert _terms(case) == [("DAP", "FCA Haiphong", True)]
    # Nothing is fixed silently: the case keeps the PO's term as printed, and
    # Sales sees it beside its anchor on the case.
    assert case.header.delivery_term == "FCA Haiphong"
    view = order_case(
        case,
        assigned_to=None,
        release_manifest_ref=None,
        prices=PriceView(amounts=False, other_customers=False),
    )
    assert view.delivery_term == "FCA Haiphong"
    assert view.header_anchors["delivery_term"] == case.header.anchors.delivery_term


async def test_intake_raises_nothing_for_the_customers_own_term() -> None:
    case = await _m01(await _intake("DAP", _StatingTerm("DAP Velatrix warehouse")))

    assert _terms(case) == []


async def test_a_term_sales_corrects_is_compared_again() -> None:
    """A new layout's term is `value_uncertain`; the value Sales types is
    the one the customer check reads when it runs again."""
    intake = await _intake("DAP", _StatingTerm("FCA Haiphong", RegionFlag.NEW_LAYOUT))
    case = (await _m01(intake)).start_review()
    assert _terms(case) == [("DAP", "FCA Haiphong", True)]
    key = next(
        f.key for f in case.findings if f.code is FindingCode.VALUE_UNCERTAIN and f.line_no is None
    )

    corrected = await intake.correct_value(SCOPE, case, key, "delivery_term", "DAP Hanoi", AN, T0)

    assert _terms(corrected) == []
    again = await intake.correct_value(SCOPE, case, key, "delivery_term", "CIP Hanoi", AN, T0)
    assert _terms(again) == [("DAP", "CIP Hanoi", True)]
