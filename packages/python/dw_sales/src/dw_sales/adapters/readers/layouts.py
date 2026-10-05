"""The fictional customers' PO layouts, by customer code.

Data, not code: a customer whose PO prints differently gets an entry here, never
a branch in a reader. Each layout is what `adapters/mock/README.md` documents
for the mock attachments. A real customer's layout is a fact about that
customer's documents; it does not belong in a public repository and arrives
with the adapter that replaces the mocks.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from dw_sales.adapters.readers.excel import ExcelLayout
from dw_sales.adapters.readers.pdf import PdfLayout
from dw_sales.domain.orders import PoHeaderField, PoLineField

# The layout every mock customer's system prints, in English whatever the
# customer's language.
_excel_header: dict[PoHeaderField, str] = {
    "po_no": "PO No.",
    "revision": "Revision",
    "po_date": "PO Date",
    "currency": "Currency",
}
_excel_columns: dict[PoLineField, str] = {
    "line_no": "No.",
    "customer_item_code": "Customer Part No.",
    "description": "Description",
    "quantity": "Quantity",
    "uom": "UoM",
    "unit_price": "Unit Price",
    "amount": "Amount",
    "requested_date": "Requested Date",
}
_EXCEL_HEADER = MappingProxyType(_excel_header)
_EXCEL_COLUMNS = MappingProxyType(_excel_columns)

ONE_SHEET = ExcelLayout(header_labels=_EXCEL_HEADER, column_labels=_EXCEL_COLUMNS)
# The intra-group customer prints one sheet per page, "Page" beside "n / N".
SHEET_PER_PAGE = ExcelLayout(
    header_labels=_EXCEL_HEADER, column_labels=_EXCEL_COLUMNS, page_label="Page"
)

# The Vietnamese PDF: Vietnamese labels, "6.100" for 6100, dates as dd/mm/yyyy.
_vietnamese_header: dict[PoHeaderField, str] = {
    "po_no": "Số đơn hàng",
    "revision": "Lần sửa đổi",
    "po_date": "Ngày đặt hàng",
    "currency": "Đơn vị tiền tệ",
}
VIETNAMESE_PDF = PdfLayout(
    header_labels=MappingProxyType(_vietnamese_header),
    columns=(
        ("STT", "line_no"),
        ("Mã hàng KH", "customer_item_code"),
        ("Mô tả hàng hóa", "description"),
        ("Số lượng", "quantity"),
        ("ĐVT", "uom"),
        ("Đơn giá", "unit_price"),
        ("Thành tiền", "amount"),
        ("Ngày giao", "requested_date"),
    ),
    thousands_separator=".",
    decimal_separator=",",
    date_format="%d/%m/%Y",
    total_label="Tổng cộng",
)

MOCK_EXCEL_LAYOUTS: Mapping[str, ExcelLayout] = MappingProxyType(
    {
        "VLX": ONE_SHEET,
        "NRV": ONE_SHEET,
        "KMH": ONE_SHEET,
        "QRL": ONE_SHEET,
        "TZ2609": ONE_SHEET,
        "CVG": SHEET_PER_PAGE,
    }
)
MOCK_PDF_LAYOUTS: Mapping[str, PdfLayout] = MappingProxyType({"BRN": VIETNAMESE_PDF})
