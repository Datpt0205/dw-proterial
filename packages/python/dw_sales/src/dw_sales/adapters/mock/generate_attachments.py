"""Regenerate the mock email attachments from the fixtures in `data/`.

    uv run python -m dw_sales.adapters.mock.generate_attachments

The files stand in for what customers' own systems print, so the layouts and
the wording of item descriptions are theirs (documented in `README.md`), not
this context's. Purchase orders come from `data/purchase_orders.json` and
requests for quotation from `data/quote_requests.json`. A line that states no
attributes is described the way the catalogue describes the item its code maps
to, so a description never disagrees with the item it stands for.

Byte-for-byte deterministic: fixed document dates, fixed zip entry times and
no compression anywhere. A regeneration changes nothing unless a fixture did,
and a unit test proves the committed files are exactly what this produces.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Literal, Self

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.writer.excel import ExcelWriter
from openpyxl.xml import LXML
from pydantic import BaseModel, ConfigDict, Field, model_validator
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from dw_sales.adapters.mock.fixtures import (
    ATTACHMENTS_DIR,
    DATA_DIR,
    MOCK_ROOT,
    attachment_file_name,
    read_records,
)
from dw_sales.domain.catalog import (
    Colour,
    Conductor,
    ConvertEntry,
    Currency,
    Customer,
    Item,
    ItemFamily,
    Packaging,
    Shield,
    Stranding,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# The fictional seller every mock document is addressed to.
SELLER_NAME = "Demo Wire & Cable Vietnam Co., Ltd."

# DejaVu Sans cut down to Latin and Vietnamese; licence and provenance in
# `fonts/`. Embedded (subset) into every PDF, so the text layer carries real
# Vietnamese characters rather than whatever a viewer substitutes.
FONT_PATH = MOCK_ROOT / "fonts" / "DejaVuSans-LatinVi.ttf"
_FONT = "DejaVuSans-LatinVi"

_FAMILY_WORDS: dict[ItemFamily, str] = {
    "hook_up_wire": "HOOK-UP WIRE",
    "multi_core_cable": "MULTI-CORE CABLE",
}
_CONDUCTOR_WORDS: dict[Conductor, str] = {"bare_copper": "BARE CU", "tinned_copper": "TINNED CU"}
_SHIELD_WORDS: dict[Shield, str] = {
    "none": "NO SHIELD",
    "foil": "FOIL SHIELD",
    "braid": "BRAID SHIELD",
}
_TITLE_SUFFIX = {"vi": " / ĐƠN ĐẶT HÀNG", "en": "", "ja": " / 注文書"}
_RFQ_TITLE_SUFFIX = {"vi": " / YÊU CẦU BÁO GIÁ", "en": "", "ja": " / 見積依頼書"}
_PO_SHEET = {"vi": "PO", "en": "PO", "ja": "注文書"}
_RFQ_SHEET = {"vi": "RFQ", "en": "RFQ", "ja": "見積依頼"}
_PRICE_FORMAT: dict[Currency, str] = {"USD": "0.0000", "JPY": "0.00", "VND": "#,##0"}
_AMOUNT_FORMAT: dict[Currency, str] = {"USD": "#,##0.00", "JPY": "#,##0", "VND": "#,##0"}
_AMOUNT_STEP: dict[Currency, Decimal] = {
    "USD": Decimal("0.01"),
    "JPY": Decimal(1),
    "VND": Decimal(1),
}
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

# What these documents put in a cell: a subset of what openpyxl accepts.
_CellValue = str | int | Decimal | date | None


class StatedAttributes(BaseModel):
    """What a customer's description states about an item. Unset = not stated."""

    model_config = _FROZEN

    family: ItemFamily | None = None
    cores: int | None = Field(default=None, ge=1)
    gauge: str | None = None
    stranding: Stranding | None = None
    conductor: Conductor | None = None
    shield: Shield | None = None
    colour: Colour | None = None
    packaging: Packaging | None = None
    pack_length_m: Decimal | None = Field(default=None, gt=0)
    spec_no: str | None = None

    @classmethod
    def of_item(cls, item: Item) -> StatedAttributes:
        """Everything the catalogue knows about the item."""
        attributes = item.attributes
        return cls(
            family=item.family,
            cores=attributes.cores,
            gauge=attributes.gauge,
            stranding=attributes.stranding,
            conductor=attributes.conductor,
            shield=attributes.shield,
            colour=attributes.colour,
            packaging=attributes.packaging,
            pack_length_m=item.pack_multiple,
            spec_no=attributes.spec_no,
        )

    def describe(self) -> str:
        """The description the mock customers print, in a fixed word order.

        ``MULTI-CORE CABLE 2C 0.5mm2 STRANDED TINNED CU FOIL SHIELD BLACK REEL
        300M SPEC SP-5201``; whatever is not stated is left out.
        """
        words: list[str] = []
        if self.family is not None:
            words.append(_FAMILY_WORDS[self.family])
        if self.cores is not None:
            words.append(f"{self.cores}C")
        if self.gauge is not None:
            words.append(self.gauge)
        if self.stranding is not None:
            words.append(self.stranding.upper())
        if self.conductor is not None:
            words.append(_CONDUCTOR_WORDS[self.conductor])
        if self.shield is not None:
            words.append(_SHIELD_WORDS[self.shield])
        if self.colour is not None:
            words.append(self.colour.upper())
        if self.packaging is not None:
            words.append(self.packaging.upper())
        if self.pack_length_m is not None:
            words.append(f"{self.pack_length_m}M")
        if self.spec_no is not None:
            words.append(f"SPEC {self.spec_no}")
        return " ".join(words)


class OrderLine(BaseModel):
    model_config = _FROZEN

    no: int = Field(ge=1)
    customer_item_code: str
    # None: described as the catalogue describes the item the code maps to.
    attributes: StatedAttributes | None = None
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    requested_date: date


class PurchaseOrderDocument(BaseModel):
    """One PO file, attached to message ``message_id`` under ``name``."""

    model_config = _FROZEN

    message_id: str
    name: str
    layout: Literal["xlsx", "xlsx_sheet_per_page", "pdf"]
    customer_code: str
    po_no: str
    revision: int = Field(ge=0)
    po_date: date
    currency: Currency
    remarks: str = ""
    # The intra-group layout: one worksheet per printed page.
    lines_per_page: int | None = Field(default=None, ge=1)
    # The PDF layout only: printed under the buyer's name, and as a second page.
    buyer_address: str = ""
    terms: tuple[str, ...] = ()
    lines: tuple[OrderLine, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _layout_has_what_it_needs(self) -> Self:
        if (self.layout == "xlsx_sheet_per_page") != (self.lines_per_page is not None):
            raise ValueError(
                f"{self.name}: lines_per_page goes with the sheet-per-page layout only"
            )
        # The Excel layouts have no place for them, and a field the file does
        # not print is a fixture edit that silently changes nothing.
        if self.layout != "pdf" and (self.buyer_address or self.terms):
            raise ValueError(f"{self.name}: buyer_address and terms are printed by the PDF only")
        if [line.no for line in self.lines] != list(range(1, len(self.lines) + 1)):
            raise ValueError(f"{self.name}: lines are numbered 1..n in order")
        return self


class QuoteRequestLine(BaseModel):
    model_config = _FROZEN

    no: int = Field(ge=1)
    customer_item_code: str
    attributes: StatedAttributes | None = None
    quantity: Decimal = Field(gt=0)
    target_price: Decimal | None = Field(default=None, gt=0)
    required_date: date


class QuoteRequestDocument(BaseModel):
    """One RFQ file, attached to message ``message_id`` under ``name``."""

    model_config = _FROZEN

    message_id: str
    name: str
    customer_code: str
    rfq_no: str
    rfq_date: date
    quote_due: date
    currency: Currency
    remarks: str = ""
    lines: tuple[QuoteRequestLine, ...] = Field(min_length=1)


class _Catalogue:
    """The slice of master data the documents print: names and descriptions."""

    def __init__(self, data_dir: Path) -> None:
        self.customers = {c.code: c for c in read_records(data_dir / "customers.json", Customer)}
        self.items = {i.prv_code: i for i in read_records(data_dir / "items.json", Item)}
        self.convert = {
            (e.customer_code, e.customer_item_code): e.prv_code
            for e in read_records(data_dir / "convert_list.json", ConvertEntry)
        }

    def describe(
        self, customer_code: str, customer_item_code: str, stated: StatedAttributes | None
    ) -> str:
        if stated is not None:
            return stated.describe()
        prv_code = self.convert.get((customer_code, customer_item_code))
        if prv_code is None:
            raise ValueError(
                f"{customer_code} line {customer_item_code} states no attributes and has no"
                " convert entry, so there is nothing to describe it by"
            )
        return StatedAttributes.of_item(self.items[prv_code]).describe()


def load_purchase_orders(data_dir: Path = DATA_DIR) -> tuple[PurchaseOrderDocument, ...]:
    return read_records(data_dir / "purchase_orders.json", PurchaseOrderDocument)


def load_quote_requests(data_dir: Path = DATA_DIR) -> tuple[QuoteRequestDocument, ...]:
    return read_records(data_dir / "quote_requests.json", QuoteRequestDocument)


def render_attachments(data_dir: Path = DATA_DIR) -> dict[str, bytes]:
    """Every attachment's bytes, by its file name in `attachments/`."""
    catalogue = _Catalogue(data_dir)
    rendered: dict[str, bytes] = {}
    for po in load_purchase_orders(data_dir):
        customer = catalogue.customers[po.customer_code]
        if po.layout == "pdf":
            data = _po_pdf(po, customer, catalogue)
        else:
            data = _po_xlsx(po, customer, catalogue)
        rendered[attachment_file_name(po.message_id, po.name)] = data
    for rfq in load_quote_requests(data_dir):
        customer = catalogue.customers[rfq.customer_code]
        rendered[attachment_file_name(rfq.message_id, rfq.name)] = _rfq_xlsx(
            rfq, customer, catalogue
        )
    return rendered


def main() -> None:
    rendered = render_attachments()
    ATTACHMENTS_DIR.mkdir(exist_ok=True)
    # The directory holds exactly what the fixtures produce. A file left from
    # a renamed or removed attachment would fail the sync test however often
    # this ran.
    for stale in sorted(ATTACHMENTS_DIR.iterdir()):
        if stale.is_file() and stale.name not in rendered:
            stale.unlink()
            print(f"removed {stale.name}")
    for file_name, data in rendered.items():
        (ATTACHMENTS_DIR / file_name).write_bytes(data)
        print(f"wrote {file_name} ({len(data)} bytes)")


# ------------------------------------------------------------------- xlsx --


def _amount(quantity: Decimal, unit_price: Decimal, currency: Currency) -> Decimal:
    return (quantity * unit_price).quantize(_AMOUNT_STEP[currency], ROUND_HALF_UP)


def _total(po: PurchaseOrderDocument) -> Decimal:
    """The sum of the printed line amounts, as a buyer's system adds them."""
    return sum(
        (_amount(line.quantity, line.unit_price, po.currency) for line in po.lines), Decimal(0)
    )


def _header(sheet: Worksheet, rows: Sequence[tuple[str, _CellValue, str, _CellValue]]) -> None:
    """Label/value pairs from row 4, two pairs per row (columns A-B and D-E)."""
    for offset, (label, value, second_label, second_value) in enumerate(rows):
        row = 4 + offset
        sheet.cell(row=row, column=1, value=label)
        cell = sheet.cell(row=row, column=2, value=value)
        if isinstance(value, date):
            cell.number_format = "yyyy-mm-dd"
        if second_label:
            sheet.cell(row=row, column=4, value=second_label)
            second = sheet.cell(row=row, column=5, value=second_value)
            if isinstance(second_value, date):
                second.number_format = "yyyy-mm-dd"


def _table(
    sheet: Worksheet,
    columns: Sequence[str],
    rows: Sequence[Sequence[_CellValue]],
    formats: Sequence[str | None],
) -> int:
    """A header on row 9 and one row per entry; returns the next free row."""
    for column, title in enumerate(columns, start=1):
        sheet.cell(row=9, column=column, value=title)
    for offset, values in enumerate(rows):
        for column, (value, number_format) in enumerate(zip(values, formats, strict=True), start=1):
            cell = sheet.cell(row=10 + offset, column=column, value=value)
            if number_format is not None:
                cell.number_format = number_format
    for letter, width in zip("ABCDEFGH", (6, 18, 72, 12, 6, 13, 15, 15), strict=False):
        sheet.column_dimensions[letter].width = width
    return 10 + len(rows)


def _po_xlsx(po: PurchaseOrderDocument, customer: Customer, catalogue: _Catalogue) -> bytes:
    workbook = _new_workbook()
    page_size = po.lines_per_page or len(po.lines)
    pages = [po.lines[start : start + page_size] for start in range(0, len(po.lines), page_size)]
    for number, lines in enumerate(pages, start=1):
        title = _PO_SHEET[customer.language] if po.lines_per_page is None else f"Page {number}"
        sheet: Worksheet = workbook.create_sheet(title)
        sheet["A1"] = customer.name.upper()
        sheet["A2"] = "PURCHASE ORDER" + _TITLE_SUFFIX[customer.language]
        page_label = ("Page", f"{number} / {len(pages)}") if po.lines_per_page else ("", "")
        _header(
            sheet,
            [
                ("PO No.", po.po_no, "Revision", po.revision),
                ("PO Date", po.po_date, "Currency", po.currency),
                ("Supplier", SELLER_NAME, *page_label),
                ("Remarks", po.remarks, "", ""),
            ],
        )
        rows: list[list[_CellValue]] = [
            [
                line.no,
                line.customer_item_code,
                catalogue.describe(po.customer_code, line.customer_item_code, line.attributes),
                line.quantity,
                "m",
                line.unit_price,
                _amount(line.quantity, line.unit_price, po.currency),
                line.requested_date,
            ]
            for line in lines
        ]
        next_row = _table(
            sheet,
            (
                "No.",
                "Customer Part No.",
                "Description",
                "Quantity",
                "UoM",
                "Unit Price",
                "Amount",
                "Requested Date",
            ),
            rows,
            (
                None,
                None,
                None,
                "#,##0",
                None,
                _PRICE_FORMAT[po.currency],
                _AMOUNT_FORMAT[po.currency],
                "yyyy-mm-dd",
            ),
        )
        if number == len(pages):
            sheet.cell(row=next_row, column=6, value="TOTAL")
            total_cell = sheet.cell(row=next_row, column=7, value=_total(po))
            total_cell.number_format = _AMOUNT_FORMAT[po.currency]
    return _xlsx_bytes(workbook, creator=customer.name, stamp=po.po_date)


def _rfq_xlsx(rfq: QuoteRequestDocument, customer: Customer, catalogue: _Catalogue) -> bytes:
    workbook = _new_workbook()
    sheet: Worksheet = workbook.create_sheet(_RFQ_SHEET[customer.language])
    sheet["A1"] = customer.name.upper()
    sheet["A2"] = "REQUEST FOR QUOTATION" + _RFQ_TITLE_SUFFIX[customer.language]
    _header(
        sheet,
        [
            ("RFQ No.", rfq.rfq_no, "RFQ Date", rfq.rfq_date),
            ("Quote Due", rfq.quote_due, "Currency", rfq.currency),
            ("To", SELLER_NAME, "", ""),
            ("Remarks", rfq.remarks, "", ""),
        ],
    )
    rows: list[list[_CellValue]] = [
        [
            line.no,
            line.customer_item_code,
            catalogue.describe(rfq.customer_code, line.customer_item_code, line.attributes),
            line.quantity,
            "m",
            line.target_price,
            line.required_date,
        ]
        for line in rfq.lines
    ]
    _table(
        sheet,
        (
            "No.",
            "Customer Part No.",
            "Description",
            "Quantity",
            "UoM",
            "Target Price",
            "Required Date",
        ),
        rows,
        (None, None, None, "#,##0", None, _PRICE_FORMAT[rfq.currency], "yyyy-mm-dd"),
    )
    return _xlsx_bytes(workbook, creator=customer.name, stamp=rfq.rfq_date)


def _new_workbook() -> Workbook:
    """A workbook without the default sheet: each document names its own."""
    workbook = Workbook()
    workbook.remove(workbook.worksheets[0])
    return workbook


def _xlsx_bytes(workbook: Workbook, *, creator: str, stamp: date) -> bytes:
    """The workbook as a file whose bytes depend on its content only.

    `ExcelWriter` directly rather than `Workbook.save`, which stamps the
    current time into the document properties.
    """
    if not LXML:
        # Measured: without lxml every workbook serialises differently.
        raise RuntimeError(
            "openpyxl is not writing through lxml, so the workbooks would differ from the"
            " committed ones: run in the dev environment (uv sync --all-packages)"
        )
    moment = datetime(stamp.year, stamp.month, stamp.day)
    workbook.properties.creator = creator
    workbook.properties.created = moment
    workbook.properties.modified = moment
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        ExcelWriter(workbook, archive).save()
    return _fixed_zip(buffer.getvalue())


def _fixed_zip(data: bytes) -> bytes:
    """The same archive with every entry's time and origin fixed.

    `ZipFile.writestr` stamps entries with the current time and the host
    system (Windows or Unix), and deflate output varies with the zlib build;
    any of those would make two machines produce different bytes. Stored, not
    deflated: the files are small and Excel reads either.
    """
    source = zipfile.ZipFile(io.BytesIO(data))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as target:
        for info in source.infolist():
            entry = zipfile.ZipInfo(info.filename, date_time=_ZIP_EPOCH)
            entry.create_system = 3
            entry.external_attr = 0o644 << 16
            target.writestr(entry, source.read(info.filename))
    return buffer.getvalue()


# -------------------------------------------------------------------- pdf --


def _vi_number(value: Decimal) -> str:
    """Vietnamese grouping: ``.`` between thousands, ``,`` before decimals."""
    return f"{value:,}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _vi_date(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _po_pdf(po: PurchaseOrderDocument, customer: Customer, catalogue: _Catalogue) -> bytes:
    """A Vietnamese text PDF: header and lines on page 1, terms on page 2."""
    if customer.language != "vi":
        raise ValueError(f"{po.name}: the PDF layout is the Vietnamese one")
    pdfmetrics.registerFont(TTFont(_FONT, str(FONT_PATH)))
    buffer = io.BytesIO()
    width, height = landscape(A4)
    canvas = Canvas(buffer, pagesize=(width, height), invariant=1, pageCompression=0)
    canvas.setTitle(f"Đơn đặt hàng {po.po_no}")
    canvas.setAuthor(customer.name)
    pages = 2 if po.terms else 1

    def text(x: float, y: float, value: str, size: float = 9, right: bool = False) -> None:
        canvas.setFont(_FONT, size)
        if right:
            canvas.drawRightString(x, y, value)
        else:
            canvas.drawString(x, y, value)

    y = height - 50
    text(40, y, customer.name.upper(), 12)
    if po.buyer_address:
        y -= 14
        text(40, y, po.buyer_address, 8)
    y -= 28
    text(40, y, "ĐƠN ĐẶT HÀNG (PURCHASE ORDER)", 14)
    for label, value in (
        ("Số đơn hàng", po.po_no),
        ("Lần sửa đổi", str(po.revision)),
        ("Ngày đặt hàng", _vi_date(po.po_date)),
        ("Nhà cung cấp", SELLER_NAME),
        ("Đơn vị tiền tệ", po.currency),
    ):
        y -= 15
        text(40, y, f"{label}: {value}")

    # x of each column; numbers are right-aligned on theirs.
    columns: tuple[tuple[str, float, bool], ...] = (
        ("STT", 55, True),
        ("Mã hàng KH", 62, False),
        ("Mô tả hàng hóa", 140, False),
        ("Số lượng", 612, True),
        ("ĐVT", 618, False),
        ("Đơn giá", 690, True),
        ("Thành tiền", 770, True),
        ("Ngày giao", 778, False),
    )
    y -= 26
    for title, x, right in columns:
        text(x, y, title, 8, right)
    for line in po.lines:
        y -= 14
        values = (
            str(line.no),
            line.customer_item_code,
            catalogue.describe(po.customer_code, line.customer_item_code, line.attributes),
            _vi_number(line.quantity),
            "m",
            _vi_number(line.unit_price),
            _vi_number(_amount(line.quantity, line.unit_price, po.currency)),
            _vi_date(line.requested_date),
        )
        for (_, x, right), value in zip(columns, values, strict=True):
            text(x, y, value, 7.5, right)
    y -= 22
    text(770, y, f"Tổng cộng: {_vi_number(_total(po))} {po.currency}", 9, right=True)
    if po.remarks:
        y -= 22
        text(40, y, f"Ghi chú: {po.remarks}", 8)
    text(width - 40, 30, f"Trang 1/{pages}", 8, right=True)
    canvas.showPage()
    if po.terms:
        y = height - 50
        text(40, y, "ĐIỀU KHOẢN CHUNG", 12)
        for number, term in enumerate(po.terms, start=1):
            y -= 18
            text(40, y, f"{number}. {term}", 9)
        text(width - 40, 30, f"Trang 2/{pages}", 8, right=True)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


if __name__ == "__main__":
    main()
