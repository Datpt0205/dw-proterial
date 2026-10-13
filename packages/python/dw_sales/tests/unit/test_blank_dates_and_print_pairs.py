"""Ticket 34: a line printed with no requested date reads and asks for one,
and a workbook and its PDF print in one mail are one PO.

The readers' own cases are `test_po_readers.py`'s. Here: the finding and the
decisions it allows, the mock POs `M44` and `M45` through the real services
over the in-memory world, a customer's own form read through an approved
layout (ticket 30), the pairing rule on its own, and what a viewer who may not
see amounts is shown of a PDF's anchors.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from dw_kernel.errors import ConflictError, NotFoundError
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR
from dw_sales.adapters.mock.generate_attachments import (
    catalogue_of,
    load_purchase_orders,
    render_po,
)
from dw_sales.adapters.order_rules import load_order_rules
from dw_sales.adapters.readers import ExcelPoReader, PdfPoReader
from dw_sales.adapters.readers.layouts import MOCK_EXCEL_LAYOUTS, MOCK_PDF_LAYOUTS
from dw_sales.adapters.readers.stored import excel_layout, pdf_layout
from dw_sales.application.access import PriceView
from dw_sales.application.artifact_content import Value
from dw_sales.application.order_artifacts import upload_rows
from dw_sales.application.views import order_case
from dw_sales.domain.layouts import LayoutMapping
from dw_sales.domain.messages import Attachment, AttachmentContent
from dw_sales.domain.order_checks import received_date
from dw_sales.domain.orders import (
    AMOUNT_FIELDS,
    Accepted,
    Actor,
    AskCustomer,
    CorrectedBySales,
    Finding,
    FindingCode,
    FlaggedValue,
    OrderCase,
    OrderStatus,
    PoDocument,
    RegionFlag,
    Severity,
    Unreadable,
)
from dw_sales.domain.print_pairs import one_po
from dw_sales.evals.graders import AN, CALLERS, READER
from dw_sales.evals.world import SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
RULES = load_order_rules(REPO / "configs" / "policies" / "sales_order_rules@1.5.0.yaml")
T0 = datetime(2026, 10, 2, 19, 0, tzinfo=UTC)
ACTOR = Actor(user_id=AN.user_id)
MISSING = "requested_date_missing:2"


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _case(world: World, message_id: str) -> OrderCase:
    ((disposition, case),) = (await world.process_each(AN, [message_id])).values()
    assert isinstance(case, OrderCase), disposition
    return case


def _content(data: bytes, attachment_id: str, name: str) -> AttachmentContent:
    attachment = Attachment(
        attachment_id=attachment_id,
        name=name,
        media_type="application/octet-stream",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    return AttachmentContent(attachment=attachment, data=data)


# ------------------------------------------------------------- the finding --


def _missing(**update: object) -> Finding:
    values: dict[str, object] = {
        "code": FindingCode.REQUESTED_DATE_MISSING,
        "severity": Severity.ERROR,
        "line_no": 2,
        "rule_version": RULES.version,
    } | update
    return Finding.model_validate(values)


def test_a_missing_date_is_asked_for_or_accepted_never_typed_and_is_about_one_line() -> None:
    for decided in (
        AskCustomer(by=AN.user_id, at=T0),
        Accepted(reason="Khách báo ngày giao sau", by=AN.user_id, at=T0),
    ):
        assert _missing(disposition=decided).disposition.kind == decided.kind
    typed = CorrectedBySales(value="2026-12-01", source="điện thoại", by=AN.user_id, at=T0)
    with pytest.raises(ValidationError, match="cannot be"):
        _missing(disposition=typed)
    with pytest.raises(ValidationError, match="one line"):
        _missing(line_no=None)


def test_every_shipped_rules_version_blocks_on_a_missing_date() -> None:
    tenant = load_order_rules(
        REPO
        / "packages/python/dw_sales/src/dw_sales/adapters/mock/data/policies"
        / "sales_order_rules@1.5.1.yaml"
    )
    for rules in (RULES, tenant):
        assert rules.findings[FindingCode.REQUESTED_DATE_MISSING] is Severity.ERROR


# --------------------------------------------------- M44, a blank date --


async def test_m44_reads_line_2_with_no_date_and_is_not_prepared_until_sales_decides() -> None:
    world = _world()
    case = await _case(world, "M44")

    line = case.line(2)
    assert (line.po_line.requested_date, line.po_line.schedules) == (None, ())
    assert line.po_line.anchors.requested_date.cell_ref == "PO!H11"
    # DW1's proposal: the first day the lead time allows.
    assert line.basis.lead_time_days is not None
    first_day = received_date(case.received_at) + timedelta(days=line.basis.lead_time_days)
    assert line.suggested_delivery_date == first_day
    finding = case.finding(MISSING)
    assert (finding.blocking, finding.is_open, finding.expected) == (True, True, "a date")
    assert [f.key for f in case.findings] == [MISSING]

    with pytest.raises(ConflictError) as refused:
        case.prepare(ACTOR, T0)
    assert MISSING in refused.value.details["open_findings"]  # type: ignore[operator]
    accepted = case.dispose(
        MISSING, Accepted(reason="Khách báo ngày giao sau", by=AN.user_id, at=T0), ACTOR
    )
    assert accepted.prepare(ACTOR, T0).status is OrderStatus.PREPARED


async def test_m44s_upload_row_for_line_2_has_no_requested_date_and_the_suggestion() -> None:
    case = await _case(_world(), "M44")
    line = case.line(2)

    (row,) = upload_rows(case, line)

    expected: dict[str, Value] = {
        "requested_date": None,
        "suggested_delivery_date": line.suggested_delivery_date,
        "quantity": Decimal(3000),
    }
    assert {key: row[key] for key in expected} == expected  # type: ignore[index]


async def test_m44_asked_of_the_customer_goes_back_to_them() -> None:
    case = await _case(_world(), "M44")

    asked = case.dispose(MISSING, AskCustomer(by=AN.user_id, at=T0), ACTOR)

    assert asked.request_correction().status is OrderStatus.CORRECTION_REQUESTED


# ------------------------------------- a form read through an approved layout --

_M43 = next(po for po in load_purchase_orders() if po.message_id == "M43")


def _form_mapping(kind: str) -> LayoutMapping:
    """The approved mapping of M43's form, built from the form the fixture prints."""
    form = _M43.form
    assert form is not None
    labels: dict[str, str] = {f: label for label, f in (*form.header, *form.columns)}
    fields = (
        "po_no",
        "po_date",
        "currency",
        "line_no",
        "customer_item_code",
        "description",
        "quantity",
        "uom",
        "unit_price",
        "amount",
        "requested_date",
    )
    return LayoutMapping.model_validate(
        {
            "kind": kind,
            **{field: labels[field] for field in fields},
            "revision": None,
            "total_label": form.total,
            "thousands_separator": form.thousands,
            "decimal_separator": form.decimal,
            "date_format": form.date_format,
            "pdf_columns": tuple(t for t, _ in form.columns) if kind == "pdf" else None,
        }
    )


def _form_with_no_date(layout: str) -> bytes:
    """M43's form, line 2 printed with no date: the form prints a dash for
    an empty cell, and a "Buyer Note" column after the date."""
    lines = tuple(
        line.model_copy(update={"requested_date": None}) if line.no == 2 else line
        for line in _M43.lines
    )
    po = _M43.model_copy(update={"layout": layout, "lines": lines})
    return render_po(po, catalogue_of())


@pytest.mark.parametrize("kind", ["pdf", "excel"])
def test_a_blank_date_in_an_approved_form_reads_as_date_to_follow(kind: str) -> None:
    mapping = _form_mapping(kind)
    layout_ref = "po_layout:00000000-0000-0000-0000-000000000043@1"
    if kind == "pdf":
        content = _content(_form_with_no_date("pdf"), "F1", "form.pdf")
        read = PdfPoReader({}).read_with(
            content, pdf_layout(mapping), RULES.intake, layout_ref=layout_ref
        )
    else:
        content = _content(_form_with_no_date("xlsx"), "F1", "form.xlsx")
        read = ExcelPoReader({}).read_with(
            content, excel_layout(mapping), RULES.intake, layout_ref=layout_ref
        )

    assert isinstance(read, PoDocument), read
    assert [line.requested_date for line in read.lines] == [
        _M43.lines[0].requested_date,
        None,
        _M43.lines[2].requested_date,
    ]
    assert read.layout_ref == layout_ref


# ------------------------------------------------ M45, a workbook and its print --


async def test_m45s_workbook_and_print_are_one_case_with_the_differing_date_uncertain() -> None:
    world = _world()
    case = await _case(world, "M45")

    document = case.document
    assert (document.attachment_id, document.parser_version) == (
        "M45-A1",
        "excel_po_reader@1.5.0",
    )
    copy = document.print_copy
    assert copy is not None
    assert (copy.attachment_id, copy.parser_version) == ("M45-A2", "pdf_po_reader@1.5.0")
    ((difference),) = copy.differences
    assert (difference.line_no, difference.field) == (1, "requested_date")
    assert (difference.anchor.page, difference.anchor.quote) == (1, "23/11/2026")
    # The workbook is the record; the print's date is beside it, flagged.
    assert case.line(1).po_line.requested_date == date(2026, 11, 16)
    assert case.line(1).po_line.flags == (
        FlaggedValue(field="requested_date", flag=RegionFlag.PRINT_DIFFERS),
    )
    assert case.finding("value_uncertain:1").actual == "print_differs"
    assert {f.code for f in case.findings} == {
        FindingCode.MISSING_NOC_ESF,
        FindingCode.VALUE_UNCERTAIN,
    }


async def test_m45s_print_is_served_as_a_source_labelled_where_it_differs() -> None:
    world = _world()
    case = await _case(world, "M45")

    view = await world.services.sources.order_source(
        AN.context(), case.case_id, "M45-A2", page=1, sheet=None
    )

    assert (view.kind, view.attachment_id) == ("pdf", "M45-A2")
    assert [(a.field, a.line_no) for a in view.anchors] == [("requested_date", 1)]


async def test_a_case_serves_only_its_own_print() -> None:
    """The print is a source of M45's case alone: M44's case answers 404 for
    it, as for any attachment that is not its own."""
    world = _world()
    m44 = await _case(world, "M44")
    await _case(world, "M45")

    with pytest.raises(NotFoundError):
        await world.services.sources.order_source(
            AN.context(), m44.case_id, "M45-A2", page=1, sheet=None
        )


# -------------------------------------------------------- the pairing rule --


def _pair() -> tuple[PoDocument, PoDocument]:
    """M45's two files, read as the readers read them, with no pairing."""
    name = "BRN-PO-2610-018"
    workbook = ExcelPoReader(MOCK_EXCEL_LAYOUTS).read(
        _content((ATTACHMENTS_DIR / f"M45_{name}.xlsx").read_bytes(), "A1", f"{name}.xlsx"),
        "BRN",
        RULES.intake,
    )
    printed = PdfPoReader(MOCK_PDF_LAYOUTS).read(
        _content((ATTACHMENTS_DIR / f"M45_{name}.pdf").read_bytes(), "A2", f"{name}.pdf"),
        "BRN",
        RULES.intake,
    )
    assert not isinstance(workbook, Unreadable) and not isinstance(printed, Unreadable)
    return workbook, printed


def _print_with(printed: PoDocument, number: int, **values: object) -> PoDocument:
    lines = tuple(
        line.model_copy(update=values) if line.line_no == number else line for line in printed.lines
    )
    return printed.model_copy(update={"lines": lines})


def test_a_print_that_agrees_adds_no_flag_and_is_kept_as_a_source() -> None:
    workbook, printed = _pair()
    agreeing = _print_with(printed, 1, requested_date=workbook.lines[0].requested_date)

    paired = one_po(workbook, agreeing)

    assert paired is not None and paired.print_copy is not None
    assert paired.print_copy.differences == ()
    assert paired.model_copy(update={"print_copy": None}) == workbook


def test_text_set_differently_by_the_print_is_the_same_value() -> None:
    workbook, printed = _pair()
    agreeing = _print_with(
        printed,
        1,
        requested_date=workbook.lines[0].requested_date,
        description="  " + workbook.lines[0].description.upper().replace(" ", "   "),
    )

    paired = one_po(workbook, agreeing)

    assert paired is not None and paired.print_copy is not None
    assert paired.print_copy.differences == ()


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        ({"unit_price": Decimal(1200)}, [(1, "requested_date"), (1, "unit_price")]),
        ({"quantity": Decimal(6000)}, [(1, "quantity"), (1, "requested_date")]),
    ],
    ids=["price", "quantity"],
)
def test_each_value_the_print_shows_differently_is_flagged_on_its_line(
    edit: dict[str, object], expected: list[tuple[int, str]]
) -> None:
    workbook, printed = _pair()

    paired = one_po(workbook, _print_with(printed, 1, **edit))

    assert paired is not None and paired.print_copy is not None
    assert sorted((d.line_no or 0, d.field) for d in paired.print_copy.differences) == expected
    assert sorted(f.field for f in paired.lines[0].flags) == sorted(f for _, f in expected)
    assert paired.lines[1].flags == ()


def test_a_header_value_and_a_total_the_print_shows_differently_are_flagged_on_the_po() -> None:
    workbook, printed = _pair()
    assert workbook.total is not None and printed.total is not None
    other = printed.model_copy(
        update={
            "header": printed.header.model_copy(update={"currency": "USD"}),
            "total": printed.total.model_copy(update={"amount": Decimal(1)}),
        }
    )

    paired = one_po(workbook, other)

    assert paired is not None
    assert [f.field for f in paired.header.flags] == ["currency"]
    assert paired.total is not None and [f.field for f in paired.total.flags] == ["amount"]


@pytest.mark.parametrize(
    "other",
    ["po_no", "revision", "lines", "line numbers"],
)
def test_two_documents_that_are_not_the_same_po_are_not_paired(other: str) -> None:
    workbook, printed = _pair()
    if other == "lines":
        changed = printed.model_copy(update={"lines": printed.lines[:1]})
    elif other == "line numbers":
        changed = _print_with(printed, 2, line_no=3)
    else:
        value = {"po_no": "BRN-PO-2610-019", "revision": 1}[other]
        changed = printed.model_copy(
            update={"header": printed.header.model_copy(update={other: value})}
        )

    assert one_po(workbook, changed) is None


# --------------------------------------- a viewer who may not see amounts --


async def test_no_price_reaches_a_viewer_without_amounts_through_a_pdf_anchor() -> None:
    """A PDF anchor quotes the printed words: M03's unit price anchor quotes
    ``1.150``. A reader without amounts gets no anchor for a price, and no
    print difference on one."""
    world = _world()
    m03 = await _case(world, "M03")
    m45 = await _case(world, "M45")

    seen_by_an = await world.services.orders.get(AN.context(), m03.case_id)
    seen = await world.services.orders.get(READER.context(), m03.case_id)

    assert seen_by_an.lines[0].anchors["unit_price"].quote == "1.150"
    for line in seen.lines:
        assert AMOUNT_FIELDS.isdisjoint(line.anchors)
        assert "quantity" in line.anchors
    assert seen.total_anchor is None and seen_by_an.total_anchor is not None
    m45_seen = await world.services.orders.get(READER.context(), m45.case_id)
    assert m45_seen.print_copy is not None
    assert [d.field for d in m45_seen.print_copy.differences] == ["requested_date"]


async def test_a_price_the_print_shows_differently_reaches_only_a_viewer_of_amounts() -> None:
    """The print's anchor for a price quotes the printed price: a viewer
    without amounts gets no difference on one, a viewer with them does."""
    case = await _case(_world(), "M45")
    copy = case.document.print_copy
    assert copy is not None
    (dated,) = copy.differences
    priced = copy.model_copy(
        update={"differences": (dated, dated.model_copy(update={"field": "unit_price"}))}
    )
    shown = case.model_copy(
        update={"document": case.document.model_copy(update={"print_copy": priced})}
    )

    def fields(prices: PriceView) -> list[str]:
        view = order_case(shown, assigned_to=None, release_manifest_ref=None, prices=prices)
        assert view.print_copy is not None
        return [d.field for d in view.print_copy.differences]

    assert fields(PriceView(amounts=False, other_customers=False)) == ["requested_date"]
    assert fields(PriceView(amounts=True, other_customers=False)) == [
        "requested_date",
        "unit_price",
    ]
