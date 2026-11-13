"""Ticket 18: "Tải PO lên" for a file Sales downloaded, and a portal's export.

The export's bytes (`formats.sniff`); the export read with the customer's
layout, firm rows only and forecast rows counted (`readers.export`); and the
whole of DW1 over the in-memory world: a person uploads an export for a
customer they choose, it is stored once as one message whose sender is them
and whose customer the server stamped, and processing it opens the case from
the firm rows. Refused without the scope, for a customer not in the tenant's
master data, and over the caps; and a mail never passes for an upload.

Every export here is made by this file, in the shape customer 2's portal
exports (UTF-16 with its mark, tab-separated, fifteen columns, two-digit
years, forecast and firm rows mixed, one PO number per row), with the sample
set's fictional customer Corvane's codes.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_platform.domain.messages import Attachment, AttachmentContent
from dw_sales.adapters.formats import refusal, sniff
from dw_sales.adapters.readers.export import export_source, read_export
from dw_sales.application.po_uploads import (
    MAX_UPLOAD_FILES,
    PO_UPLOADED,
    UploadedFile,
    upload_id,
)
from dw_sales.domain.layouts import (
    NO_FIRM_ROW,
    ExportMapping,
    LayoutSample,
    PoLayout,
    check_titles,
)
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.orders import OrderCase, PoDocument, RegionFlag, Unreadable
from dw_sales.evals.graders import AN, CALLERS, GIANG, KHOA, OUTSIDER, READER
from dw_sales.evals.world import ALPHA, BETA, NOW, SampleSet, SampleWith, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
CUSTOMER = "CVG"
REF = f"po_layout:{uuid.UUID(int=18)}@1"
TITLES = (
    "Part No.",
    "Description",
    "Order Qty",
    "Unit",
    "Backlog",
    "Del'y Date",
    "PO No.",
    "PO Type",
    "Issue Date",
    "Site",
    "Supplier",
    "ORG",
    "Packing Capacity",
    "Delivery To",
    "Note",
)
CAPS = IntakeCaps(
    max_attachment_bytes=10_000_000,
    max_unpacked_bytes=50_000_000,
    max_sheets=20,
    max_pages=50,
    max_cells=200_000,
)
MAPPING = ExportMapping(
    kind="csv",
    po_no="PO No.",
    po_date="Issue Date",
    customer_item_code="Part No.",
    description="Description",
    quantity="Order Qty",
    uom="Unit",
    requested_date="Del'y Date",
    order_type="PO Type",
    firm_values=("Firm Order",),
    currency="USD",
    date_format="%y-%m-%d",
)


def _row(code: str, qty: str, day: str, po_no: str, kind: str, note: str = "") -> list[str]:
    return [code, "Magnet roll", qty, "PC", "", day, po_no, kind, "26-11-05", "S1", "V1", "O1"]


def export(rows: list[list[str]], *, titles: tuple[str, ...] = TITLES) -> bytes:
    """UTF-16 with its mark, tab-separated, LF line ends: Excel's "Unicode
    text", as the portal exports it. Short rows are padded to the titles."""
    lines = ["\t".join(titles)]
    lines += ["\t".join([*row, *[""] * (len(titles) - len(row))]) for row in rows]
    return b"\xff\xfe" + ("\n".join(lines) + "\n").encode("utf-16-le")


FIRM = [
    _row("CVG-0001", "120", "26-11-17", "CVG-PO-2611-0001", "Firm Order"),
    _row("CVG-0003", "1,500", "26-11-18", "CVG-PO-2611-0002", "Firm Order"),
]
FORECAST = [
    _row("CVG-0001", "300", "26-12-01", "CVG-PO-2612-0101", "Forecast"),
    _row("CVG-0003", "300", "26-12-08", "CVG-PO-2612-0102", "Forecast"),
    _row("CVG-0004", "50", "26-12-15", "CVG-PO-2612-0103", "Forecast"),
]
# Forecast rows first and between, as the portal mixes them.
EXPORT = export([FORECAST[0], FIRM[0], FORECAST[1], FIRM[1], FORECAST[2]])


def _content(data: bytes, attachment_id: str = "A1") -> AttachmentContent:
    return AttachmentContent(
        attachment=Attachment(
            attachment_id=attachment_id,
            name="ORD_20261111_133453.csv",
            media_type="application/octet-stream",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        data=data,
    )


# -------------------------------------------------------------- the bytes --


def test_utf16_text_with_a_tab_on_its_first_line_is_an_export_whatever_its_name() -> None:
    assert sniff(EXPORT) == "csv"
    assert sniff(b"\xfe\xff" + "a\tb\n".encode("utf-16-be")) == "csv"
    # Not an export: UTF-16 with no tab, UTF-8 text, a mark alone.
    assert sniff(b"\xff\xfe" + "Dear Sales,\n".encode("utf-16-le")) is None
    assert sniff(b"PO No.\tPart No.\n") is None
    assert sniff(b"\xff\xfe") is None
    # Its name claims nothing a check holds it to.
    assert refusal("ORD.csv", EXPORT) is None
    assert refusal("ORD.xlsx", EXPORT) == "named .xlsx but its bytes are not one"


# ------------------------------------------------------------- the reader --


def test_only_firm_rows_are_lines_and_forecast_rows_are_counted() -> None:
    read = read_export(_content(EXPORT), MAPPING, CAPS, layout_ref=REF)

    assert isinstance(read, PoDocument)
    assert read.forecast_rows == 3
    assert [line.customer_item_code for line in read.lines] == ["CVG-0001", "CVG-0003"]
    assert [line.line_no for line in read.lines] == [1, 2]
    assert [line.quantity for line in read.lines] == [Decimal(120), Decimal(1500)]
    assert [line.requested_date for line in read.lines] == [date(2026, 11, 17), date(2026, 11, 18)]
    # Each line keeps its own PO number, where the file prints it.
    owned = [line.line_po for line in read.lines]
    assert [(p.po_no, p.anchor.cell_ref) for p in owned if p] == [
        ("CVG-PO-2611-0001", "CSV!G3"),
        ("CVG-PO-2611-0002", "CSV!G5"),
    ]
    # The PO's number is the first firm line's, its date that row's issue date.
    header = read.header
    assert (header.po_no, header.revision, header.po_date) == (
        "CVG-PO-2611-0001",
        0,
        date(2026, 11, 5),
    )
    assert read.rows_printed == 2 and read.regions == ("CSV",) and read.total is None


def test_what_the_export_does_not_print_is_flagged_for_sales() -> None:
    read = read_export(_content(EXPORT), MAPPING, CAPS, layout_ref=REF)

    assert isinstance(read, PoDocument)
    assert read.header.currency == "USD"  # as the layout states it
    not_printed = RegionFlag.NOT_PRINTED
    assert {f.field for f in read.header.flags if f.flag is not_printed} == {"currency"}
    for line in read.lines:
        assert (line.unit_price, line.amount) == (Decimal(0), Decimal(0))
        assert {f.field for f in line.flags if f.flag is not_printed} == {"unit_price", "amount"}
        # Held beside the quantity it stands with.
        assert line.anchors.unit_price == line.anchors.quantity


def test_a_cell_is_text_and_never_a_formula() -> None:
    row = _row("CVG-0001", "120", "26-11-17", "CVG-PO-2611-0001", "Firm Order")
    row[1] = '=HYPERLINK("http://x.example","1")+cmd|\'/c calc\'!A0'
    read = read_export(_content(export([row])), MAPPING, CAPS, layout_ref=REF)

    assert isinstance(read, PoDocument)
    assert read.lines[0].description == row[1]


def test_a_firm_row_that_does_not_read_refuses_the_export_naming_where() -> None:
    bad = _row("CVG-0003", "many", "26-11-18", "CVG-PO-2611-0002", "Firm Order")
    read = read_export(_content(export([FIRM[0], bad])), MAPPING, CAPS, layout_ref=REF)

    assert isinstance(read, Unreadable)
    assert read.reason == "row 3: quantity is not a number in the layout's notation"
    assert read.anchor is not None and read.anchor.cell_ref == "CSV!C3"
    # A forecast row is never read, so one that would not read refuses nothing.
    forecast = _row("CVG-0003", "many", "someday", "CVG-PO-2612-0102", "Forecast")
    assert isinstance(
        read_export(_content(export([FIRM[0], forecast])), MAPPING, CAPS, layout_ref=REF),
        PoDocument,
    )


def test_an_export_of_forecasts_only_is_no_po() -> None:
    read = read_export(_content(export(FORECAST)), MAPPING, CAPS, layout_ref=REF)

    assert isinstance(read, Unreadable)
    assert read.reason == f"{NO_FIRM_ROW} (3 rows marked otherwise, never ordered)"


def test_the_layout_names_each_title_once_and_its_firm_values_once() -> None:
    with pytest.raises(ValidationError):
        ExportMapping.model_validate({**MAPPING.model_dump(), "uom": "Order Qty"})
    with pytest.raises(ValidationError):
        ExportMapping.model_validate(
            {**MAPPING.model_dump(), "firm_values": ("Firm Order", "firm  order")}
        )
    source = export_source(_content(EXPORT), CAPS)
    assert source is not None and source.kind == "csv"
    assert check_titles(MAPPING, source) == []
    missing = MAPPING.model_copy(update={"order_type": "Order Type"})
    assert [str(p) for p in check_titles(missing, source)] == ["label_not_found:order_type"]


# -------------------------------------------------------------- the world --


@pytest.fixture
def world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, OUTSIDER))


def _approved_layout(world: World) -> PoLayout:
    """Customer 2's export layout as a PIC mapped it and the head approved it:
    the tenant's data, stored in the world."""
    proposed = PoLayout(
        layout_id=uuid.uuid4(),
        customer_code=CUSTOMER,
        version=1,
        mapping=MAPPING,
        sample=LayoutSample(message_id="upload-x", attachment_id="A1", attachment_sha256="0" * 64),
        proposed_by=GIANG.user_id,
        proposed_at=NOW,
        approval_id=uuid.uuid4(),
    )
    layout = proposed.approve(KHOA.user_id, NOW)
    world.store.state(ALPHA).layouts[layout.layout_id] = layout
    return layout


async def test_an_upload_opens_the_case_from_firm_lines_only_and_shows_the_forecasts(
    world: World,
) -> None:
    """Acceptance 1."""
    layout = _approved_layout(world)

    view = await world.services.uploads.upload(
        AN.context(), CUSTOMER, [UploadedFile("ORD_20261111_133453.csv", EXPORT)]
    )

    assert (view.customer_code, view.already_stored) == (CUSTOMER, False)
    assert view.job is not None and view.job.status == "queued"
    # One message, whose sender is the uploader, stamped with the customer.
    message = await world.inbox.get_message(ALPHA, view.message_id)
    assert message is not None and message.sender.address == AN.email
    assert [a.name for a in message.attachments] == ["ORD_20261111_133453.csv"]
    assert await world.uploads.upload_of(ALPHA, view.message_id) is not None
    (uploaded,) = [e for e in world.audit(ALPHA) if e.action == PO_UPLOADED]
    assert (uploaded.actor_id.value, uploaded.resource_id) == (AN.user_id, view.message_id)
    assert uploaded.details == {"customer_code": CUSTOMER, "files": 1}

    assert await world.drain() == 1

    logged = world.store.state(ALPHA).messages[view.message_id]
    assert (logged.disposition.kind, logged.disposition.customer_code) == (
        "case_created",
        CUSTOMER,
    )
    case_id = logged.disposition.case_id
    assert case_id is not None
    case = world.order(case_id)
    assert isinstance(case, OrderCase)
    assert [line.effective.customer_item_code for line in case.lines] == ["CVG-0001", "CVG-0003"]
    assert case.document.layout_ref == layout.ref
    assert case.coverage().forecast_rows == 3
    view_of_case = await world.services.orders.get(AN.context(), case_id)
    assert view_of_case.coverage.forecast_rows == 3
    assert [line.po_no for line in view_of_case.lines] == [
        "CVG-PO-2611-0001",
        "CVG-PO-2611-0002",
    ]
    # The source is the export, shown as a sheet a person opens.
    await world.open_sources(AN, case_id)


async def test_the_same_file_uploaded_twice_is_stored_once(world: World) -> None:
    """Acceptance 3."""
    _approved_layout(world)
    files = [UploadedFile("ORD_20261111_133453.csv", EXPORT)]

    first = await world.services.uploads.upload(AN.context(), CUSTOMER, files)
    again = await world.services.uploads.upload(
        GIANG.context(), CUSTOMER, [UploadedFile("renamed.csv", EXPORT)]
    )

    assert again.message_id == first.message_id == upload_id(files)
    assert (again.already_stored, again.job) == (True, None)
    assert len(await world.uploads.list_messages(ALPHA)) == 1
    assert len([e for e in world.audit(ALPHA) if e.action == PO_UPLOADED]) == 1
    assert len(world.store.state(ALPHA).jobs) == 1


async def test_a_person_without_the_right_to_process_the_mailbox_cannot_upload(
    world: World,
) -> None:
    """Acceptance 2, at the service (the route's own guard is in
    `apps/api/tests/unit/test_sales_upload_routes.py`)."""
    with pytest.raises(PermissionDeniedError):
        await world.services.uploads.upload(
            READER.context(), CUSTOMER, [UploadedFile("a.csv", EXPORT)]
        )
    assert await world.uploads.list_messages(ALPHA) == []


async def test_a_customer_outside_the_tenants_master_data_is_refused(world: World) -> None:
    with pytest.raises(NotFoundError):
        await world.services.uploads.upload(AN.context(), "ZZZ", [UploadedFile("a.csv", EXPORT)])
    # Another tenant's PIC naming this tenant's customer finds none.
    with pytest.raises(NotFoundError):
        await world.services.uploads.upload(
            OUTSIDER.context(BETA), CUSTOMER, [UploadedFile("a.csv", EXPORT)]
        )
    assert await world.uploads.list_messages(ALPHA) == []
    assert await world.uploads.list_messages(BETA) == []


async def test_an_upload_is_held_to_the_caps_mail_is_held_to(world: World) -> None:
    caps = world.policies.order_rules.intake
    too_big = b"x" * (caps.max_attachment_bytes + 1)
    refusals = [
        [UploadedFile("a.csv", too_big)],
        [UploadedFile(f"{n}.csv", f"{n}".encode()) for n in range(MAX_UPLOAD_FILES + 1)],
        [UploadedFile("../a.csv", EXPORT)],
        [],
    ]
    for files in refusals:
        with pytest.raises(DomainError):
            await world.services.uploads.upload(AN.context(), CUSTOMER, files)
    assert await world.uploads.list_messages(ALPHA) == []


async def test_an_upload_waits_while_dw1_is_paused(world: World) -> None:
    await world.services.worker.pause(GIANG.context(), "bảo trì")
    with pytest.raises(ConflictError):
        await world.services.uploads.upload(AN.context(), CUSTOMER, [UploadedFile("a.csv", EXPORT)])
    assert await world.uploads.list_messages(ALPHA) == []


async def test_an_upload_no_layout_reads_goes_to_sales_as_a_po(world: World) -> None:
    """No layout of the customer's export yet: it is a PO a person said it
    is, so it goes the way a PO no layout reads goes, for Sales to map; no
    keyword table or model classifies it."""
    view = await world.services.uploads.upload(
        AN.context(), CUSTOMER, [UploadedFile("ORD.csv", EXPORT)]
    )
    await world.drain()

    disposition = world.store.state(ALPHA).messages[view.message_id].disposition
    assert (disposition.kind, disposition.reason, disposition.customer_code) == (
        "routed_to_sales",
        "attachment_unreadable",
        CUSTOMER,
    )
    # The layout screen maps it as the customer's form, not the sender's.
    source = await world.services.layouts.source(GIANG.context(), view.message_id, "A1")
    assert (source.kind, source.customer_code) == ("csv", CUSTOMER)


async def test_a_mail_never_passes_for_an_upload(tmp_path: Path) -> None:
    """The same export mailed from the PIC's own address, its subject
    claiming an upload and naming the customer: a mail's customer is its
    sender's, and the PIC's address is no customer's, so no case opens for
    Corvane. Only the server's stamp beside a stored upload makes one."""
    export_file = tmp_path / "ORD.csv"
    export_file.write_bytes(EXPORT)
    mail = {
        "message_id": "M-FORGED",
        "sender": AN.email,
        "subject": f"Tải PO lên: ORD.csv (khách {CUSTOMER})",
        "received_at": "2026-11-12T02:00:00+00:00",
        "body": f"uploaded_for: {CUSTOMER}; uploaded_by: {AN.user_id}",
        "authentication": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
        "attachments": [
            {
                "attachment_id": "M-FORGED-A1",
                "name": "ORD.csv",
                "media_type": "text/csv",
                "file": export_file,
            }
        ],
    }
    with SampleWith([mail]) as sample:
        world = open_world(REPO, sample, CALLERS)
        _approved_layout(world)
        processed = await world.process_each(AN, ["M-FORGED"])

    disposition, case = processed["M-FORGED"]
    assert case is None
    assert (disposition.kind, disposition.customer_code) == ("routed_to_sales", None)
    assert await world.uploads.upload_of(ALPHA, "M-FORGED") is None
