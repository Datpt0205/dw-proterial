"""A layout people mapped and approved (ticket 30), as the readers take it.

`LayoutMapping` is the tenant's data: which label names which value. The
readers keep their own shapes (`ExcelLayout`, `PdfLayout`); these two
functions are the one place one becomes the other, so a stored mapping is read
exactly as a layout written in code is.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from dw_sales.adapters.readers.excel import ExcelLayout
from dw_sales.adapters.readers.pdf import PdfLayout
from dw_sales.domain.layouts import LayoutMapping, label_key
from dw_sales.domain.orders import PoLineField

# A PDF form that groups no thousands still needs a separator the reader can
# tell from the decimal one: a character no PO prints.
_NO_GROUPING: Final = chr(0x202F)


def excel_layout(mapping: LayoutMapping) -> ExcelLayout:
    return ExcelLayout(
        header_labels=MappingProxyType(mapping.header_labels()),
        column_labels=MappingProxyType(mapping.column_labels()),
        page_label=mapping.page_label,
        total_label=mapping.total_label,
        date_format=mapping.date_format,
    )


def pdf_layout(mapping: LayoutMapping) -> PdfLayout:
    """The PDF reader's layout: every title of the table in print order, each
    with the field its label names or none. Refused (ValueError) for a
    mapping whose titles in print order code has not found."""
    if mapping.pdf_columns is None:
        raise ValueError("a PDF layout names its table's titles in print order")
    by_title: dict[str, PoLineField] = {
        label_key(label): field for field, label in mapping.column_labels().items()
    }
    thousands = (
        _NO_GROUPING if mapping.thousands_separator == "none" else mapping.thousands_separator
    )
    return PdfLayout(
        header_labels=MappingProxyType(mapping.header_labels()),
        columns=tuple((title, by_title.get(label_key(title))) for title in mapping.pdf_columns),
        thousands_separator=thousands,
        decimal_separator=mapping.decimal_separator,
        date_format=mapping.date_format,
        total_label=mapping.total_label,
    )
