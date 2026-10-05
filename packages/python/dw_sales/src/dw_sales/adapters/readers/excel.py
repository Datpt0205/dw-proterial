"""Excel POs, read with openpyxl, every value with its ``Sheet!B10`` anchor.

Values are found by their printed labels, never by fixed addresses: a label's
value is the cell just right of it, and a table column is the column its title
heads. A customer's `ExcelLayout` says which labels and titles their PO prints;
the code that reads them is the same for everyone.

**What a person would not see is read and flagged, never skipped.** A value in
a hidden sheet, row or column, in a font the colour of its fill, or a formula
with no cached value, carries a `RegionFlag`; the checks raise
`value_uncertain` on it. Skipping it would make the lines read differ from the
lines the file holds, and refusing the file would hide the rest of the PO.

The reader refuses (`Unreadable`) only what it cannot read at all: no PO table,
a value that does not parse, pages missing or repeated, a page showing another
PO's header, a macro-enabled workbook, or a file past the policy's caps. The
caps are checked before openpyxl expands anything in memory. A refusal names
fields, rows and cells, never a value from the file (spec decision 8).
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import get_args

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.cell_range import CellRange
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import ValidationError

from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.messages import Attachment, AttachmentContent
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.orders import (
    FlaggedValue,
    PoDocument,
    PoHeader,
    PoHeaderAnchors,
    PoHeaderField,
    PoLine,
    PoLineAnchors,
    PoLineField,
    PrintedBuyer,
    PrintedTotal,
    RegionFlag,
    Unreadable,
)

PARSER_VERSION = "excel_po_reader@1.1.0"
_PAGE_NUMBER = re.compile(r"(\d{1,3})\s*/\s*(\d{1,3})")
_PLAIN_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
# The part a macro-enabled workbook carries its VBA in: such a file is not read (decision 13).
MACROS_PART = "xl/vbaProject.bin"


@dataclass(frozen=True)
class ExcelLayout:
    """Where one customer's Excel PO prints each value.

    ``header_labels``: the label beside each header value. ``column_labels``:
    the title above each table column. ``page_label``: for a customer printing
    one sheet per page, the label beside the sheet's ``n / N``.
    ``total_label``: the label in the row under the lines whose amount column
    holds the printed total.
    """

    header_labels: Mapping[PoHeaderField, str]
    column_labels: Mapping[PoLineField, str]
    page_label: str | None = None
    total_label: str = "TOTAL"

    def __post_init__(self) -> None:
        if set(self.header_labels) != set(get_args(PoHeaderField)):
            raise ValueError(f"an Excel layout labels every header field {get_args(PoHeaderField)}")
        if set(self.column_labels) != set(get_args(PoLineField)):
            raise ValueError(f"an Excel layout titles every line field {get_args(PoLineField)}")


class ExcelPoReader:
    """Reads an .xlsx PO with the layout of the customer who sent it.

    ``buyer_cell``: where every PO this reader takes prints its buyer's name,
    which is how a PO forwarded by someone who is not the customer is
    attributed. None for a deployment whose POs print it nowhere fixed.
    """

    def __init__(
        self, layouts: Mapping[str, ExcelLayout], *, buyer_cell: str | None = "A1"
    ) -> None:
        self._layouts = dict(layouts)
        self._buyer_cell = buyer_cell

    def read(
        self, document: AttachmentContent, customer_code: str, caps: IntakeCaps
    ) -> PoDocument | Unreadable:
        layout = self._layouts.get(customer_code)
        if layout is None:
            return Unreadable(reason=f"no Excel PO layout for customer {customer_code}")
        try:
            values, formulas = _open(document.data, caps)
            book = _Book(values, formulas, document.attachment)
            return _read(book, layout, self._buyer(book))
        except _RefusedError as refused:
            return Unreadable(reason=refused.reason, anchor=refused.anchor)

    def buyer(self, document: AttachmentContent, caps: IntakeCaps) -> PrintedBuyer | None:
        """The buyer the workbook names, or None when it names none it can read."""
        try:
            values, formulas = _open(document.data, caps)
        except _RefusedError:
            return None
        return self._buyer(_Book(values, formulas, document.attachment))

    def _buyer(self, book: _Book) -> PrintedBuyer | None:
        if self._buyer_cell is None or not book.sheets:
            return None
        sheet = book.sheets[0]
        cell = sheet.worksheet[self._buyer_cell]
        if not isinstance(cell, Cell) or not isinstance(cell.value, str) or not cell.value.strip():
            return None
        name = " ".join(cell.value.split())[:200]
        return PrintedBuyer(name=name, anchor=sheet.anchor(cell))


class _RefusedError(Exception):
    def __init__(self, reason: str, anchor: SourceAnchor | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.anchor = anchor


def _open(data: bytes, caps: IntakeCaps) -> tuple[Workbook, Workbook]:
    """The workbook twice: last computed values (what was printed), and formulas."""
    if len(data) > caps.max_attachment_bytes:
        raise _RefusedError(f"the file is over the {caps.max_attachment_bytes} bytes read here")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise _RefusedError("not an .xlsx workbook") from exc
    if any(entry.filename == MACROS_PART for entry in entries):
        raise _RefusedError("a macro-enabled workbook is not read")
    unpacked = sum(entry.file_size for entry in entries)
    if unpacked > caps.max_unpacked_bytes:
        raise _RefusedError(
            f"the workbook unpacks past the {caps.max_unpacked_bytes} bytes this reader opens"
        )
    try:
        values = load_workbook(io.BytesIO(data), data_only=True, keep_links=False)
        formulas = load_workbook(io.BytesIO(data), data_only=False, keep_links=False)
    except Exception as exc:  # any parser failure on a sender's file is "unreadable"
        raise _RefusedError("not an .xlsx workbook openpyxl can open") from exc
    if len(values.worksheets) > caps.max_sheets:
        raise _RefusedError(f"the workbook has more than the {caps.max_sheets} sheets read here")
    cells = sum(ws.max_row * ws.max_column for ws in values.worksheets)
    if cells > caps.max_cells:
        raise _RefusedError(f"the workbook spans more than the {caps.max_cells} cells read here")
    return values, formulas


def open_for_viewing(data: bytes, caps: IntakeCaps) -> tuple[Workbook, Workbook]:
    """The workbook twice (printed values, formulas) under the caps reading
    uses, for showing a person the sheet; a refusal is a ValueError naming
    why, never a value from the file."""
    try:
        return _open(data, caps)
    except _RefusedError as refused:
        raise ValueError(refused.reason) from None


class _Book:
    def __init__(self, values: Workbook, formulas: Workbook, attachment: Attachment) -> None:
        self.sheets = [
            _Sheet(worksheet, formulas[worksheet.title], attachment)
            for worksheet in values.worksheets
        ]


@dataclass(frozen=True)
class _Table:
    sheet: _Sheet
    columns: Mapping[PoLineField, int]
    first_row: int


def _read(book: _Book, layout: ExcelLayout, buyer: PrintedBuyer | None) -> PoDocument:
    tables = [table for sheet in book.sheets if (table := _table(sheet, layout)) is not None]
    if not tables:
        raise _RefusedError("no sheet has the PO table")
    if layout.page_label is None:
        if len(tables) > 1:
            names = ", ".join(t.sheet.title for t in tables)
            raise _RefusedError(f"{len(tables)} sheets have a PO table: {names}")
        pages = tables
    else:
        pages = _in_page_order(tables, layout.page_label)

    header = _header(pages[0].sheet, layout)
    for page in pages[1:]:
        other = _header(page.sheet, layout)
        if other.model_dump(
            include={"po_no", "revision", "po_date", "currency"}
        ) != header.model_dump(include={"po_no", "revision", "po_date", "currency"}):
            raise _RefusedError(
                f"sheet {page.sheet.title} shows another PO header than {pages[0].sheet.title}",
                other.anchors.po_no,
            )
    lines: list[PoLine] = []
    printed = 0
    for page in pages:
        read, numbered = _lines(page)
        lines.extend(read)
        printed += numbered
    if not lines:
        raise _RefusedError("the PO table has no lines")
    used = {page.sheet.title for page in pages}
    attachment = pages[0].sheet.attachment
    try:
        return PoDocument(
            attachment_id=attachment.attachment_id,
            attachment_sha256=attachment.sha256,
            parser_version=PARSER_VERSION,
            header=header,
            lines=tuple(lines),
            rows_printed=printed,
            regions=tuple(page.sheet.title for page in pages),
            unchecked_regions=tuple(
                s.title for s in book.sheets if s.title not in used and s.holds_anything()
            ),
            buyer=buyer.name if buyer is not None else None,
            buyer_anchor=buyer.anchor if buyer is not None else None,
            total=_total(pages[-1], layout),
        )
    except ValidationError as exc:
        raise _RefusedError(f"the lines do not form one PO: {_first_error(exc)}") from exc


class _Sheet:
    """One worksheet with its labels indexed, merged ranges resolved."""

    def __init__(self, worksheet: Worksheet, formulas: Worksheet, attachment: Attachment) -> None:
        self.worksheet = worksheet
        self.title = worksheet.title
        self.attachment = attachment
        self._formulas = formulas
        self._labels: dict[str, list[Cell]] = {}
        for row in worksheet.iter_rows():
            for cell in row:
                if isinstance(cell, Cell) and isinstance(cell.value, str):
                    self._labels.setdefault(_label_key(cell.value), []).append(cell)

    def holds_anything(self) -> bool:
        return any(not _blank(cell.value) for row in self.worksheet.iter_rows() for cell in row)

    def find(self, label: str) -> Cell | None:
        found = self._labels.get(_label_key(label), [])
        if len(found) > 1:
            raise _RefusedError(
                f"a label of the layout appears {len(found)} times on sheet {self.title}",
                self.anchor(found[1]),
            )
        return found[0] if found else None

    def value_beside(self, label: Cell) -> Cell:
        """The cell right of ``label``, past the label's merged range."""
        merged = self._merged(label.row, label.column)
        last_column = merged.max_col if merged is not None else label.column
        return self.at(label.row, last_column + 1)

    def at(self, row: int, column: int) -> Cell:
        """The cell at ``row``/``column``: inside a merged range, its top-left cell."""
        merged = self._merged(row, column)
        if merged is not None:
            row, column = merged.min_row, merged.min_col
        cell = self.worksheet.cell(row=row, column=column)
        if not isinstance(cell, Cell):  # pragma: no cover - a top-left cell is never merged
            raise _RefusedError(f"a cell on sheet {self.title} is not readable")
        return cell

    def bottom(self, cell: Cell) -> int:
        """The last row ``cell`` spans: a header cell may be merged downwards."""
        merged = self._merged(cell.row, cell.column)
        return merged.max_row if merged is not None else cell.row

    def anchor(self, cell: Cell) -> SourceAnchor:
        return SourceAnchor(
            attachment_id=self.attachment.attachment_id,
            attachment_sha256=self.attachment.sha256,
            cell_ref=f"{self.title}!{cell.coordinate}",
        )

    def flags(self, cell: Cell) -> tuple[RegionFlag, ...]:
        """Why a person looking at the sheet would not see this cell's value."""
        found: list[RegionFlag] = []
        if self.worksheet.sheet_state != "visible":
            found.append(RegionFlag.HIDDEN_SHEET)
        row = self.worksheet.row_dimensions.get(cell.row)
        if row is not None and row.hidden:
            found.append(RegionFlag.HIDDEN_ROW)
        if any(
            column.hidden
            and column.min is not None
            and column.max is not None
            and column.min <= cell.column <= column.max
            for column in self.worksheet.column_dimensions.values()
        ):
            found.append(RegionFlag.HIDDEN_COLUMN)
        if font_matches_fill(cell):
            found.append(RegionFlag.FONT_MATCHES_FILL)
        formula = self._formulas[cell.coordinate]
        if isinstance(formula, Cell) and formula.data_type == "f" and cell.value is None:
            found.append(RegionFlag.FORMULA_WITHOUT_CACHED_VALUE)
        return tuple(found)

    def _merged(self, row: int, column: int) -> CellRange | None:
        ranges: Iterable[CellRange] = self.worksheet.merged_cells.ranges
        for merged in ranges:
            if (
                merged.min_row <= row <= merged.max_row
                and merged.min_col <= column <= merged.max_col
            ):
                return merged
        return None


def font_matches_fill(cell: Cell) -> bool:
    """Text drawn in its own background colour: there, and invisible."""
    fill = cell.fill
    if fill is None or fill.fill_type != "solid":
        return False
    font_colour = cell.font.color.rgb if cell.font is not None and cell.font.color else None
    fill_colour = fill.fgColor.rgb if fill.fgColor is not None else None
    return isinstance(font_colour, str) and font_colour == fill_colour


def _table(sheet: _Sheet, layout: ExcelLayout) -> _Table | None:
    """The sheet's PO table: every column title found, all on one row."""
    titles = {field: sheet.find(label) for field, label in layout.column_labels.items()}
    found = {field: cell for field, cell in titles.items() if cell is not None}
    if len(found) != len(titles) or len({cell.row for cell in found.values()}) != 1:
        return None
    return _Table(
        sheet=sheet,
        columns={field: cell.column for field, cell in found.items()},
        first_row=max(sheet.bottom(cell) for cell in found.values()) + 1,
    )


def _in_page_order(tables: list[_Table], page_label: str) -> list[_Table]:
    """The sheets of a one-sheet-per-page PO, page 1 first, every page there once."""
    pages: dict[int, _Table] = {}
    totals: set[int] = set()
    for table in tables:
        sheet = table.sheet
        label = sheet.find(page_label)
        if label is None:
            raise _RefusedError(f"sheet {sheet.title} has no page number")
        cell = sheet.value_beside(label)
        match = _PAGE_NUMBER.fullmatch(str(cell.value or "").strip())
        if match is None:
            raise _RefusedError("the page number is not 'n / N'", sheet.anchor(cell))
        number, total = int(match.group(1)), int(match.group(2))
        if number in pages:
            raise _RefusedError(f"page {number} appears twice", sheet.anchor(cell))
        pages[number] = table
        totals.add(total)
    expected = set(range(1, max(totals) + 1))
    if len(totals) != 1 or set(pages) != expected:
        raise _RefusedError(f"pages {sorted(pages)} of {sorted(totals)}: the PO is not complete")
    return [pages[number] for number in sorted(pages)]


def _header(sheet: _Sheet, layout: ExcelLayout) -> PoHeader:
    values: dict[str, object] = {}
    anchors: dict[str, SourceAnchor] = {}
    flags: list[FlaggedValue] = []
    for field, label in layout.header_labels.items():
        label_cell = sheet.find(label)
        if label_cell is None:
            raise _RefusedError(f"sheet {sheet.title} has no {field.replace('_', ' ')} label")
        cell = sheet.value_beside(label_cell)
        anchor = sheet.anchor(cell)
        try:
            values[field] = _HEADER_VALUES[field](cell.value)
        except ValueError as exc:
            raise _RefusedError(f"{field.replace('_', ' ')} {exc}", anchor) from exc
        anchors[field] = anchor
        flags.extend(FlaggedValue(field=field, flag=flag) for flag in sheet.flags(cell))
    try:
        return PoHeader.model_validate(
            {**values, "anchors": PoHeaderAnchors(**anchors), "flags": tuple(flags)}
        )
    except ValidationError as exc:
        failed = str(exc.errors()[0]["loc"][0])
        raise _RefusedError(f"header: {_first_error(exc)}", anchors.get(failed)) from exc


def _lines(table: _Table) -> tuple[list[PoLine], int]:
    """The lines read, and how many rows the table numbers (a gap ends the reading)."""
    sheet = table.sheet
    number_column = table.columns["line_no"]
    lines: list[PoLine] = []
    row = table.first_row
    while row <= sheet.worksheet.max_row and not _blank(sheet.at(row, number_column).value):
        lines.append(_line(table, row))
        row += 1
    # A numbered row under the end: the table had a gap, and what follows it
    # is counted as printed and not read, which `line_total_mismatch` reports.
    later = sum(
        1
        for below in range(row + 1, sheet.worksheet.max_row + 1)
        if _is_number(sheet.at(below, number_column).value)
    )
    return lines, len(lines) + later


def _line(table: _Table, row: int) -> PoLine:
    sheet = table.sheet
    values: dict[str, object] = {}
    anchors: dict[str, SourceAnchor] = {}
    flags: list[FlaggedValue] = []
    for field, column in table.columns.items():
        cell = sheet.at(row, column)
        anchor = sheet.anchor(cell)
        try:
            values[field] = _LINE_VALUES[field](cell.value)
        except ValueError as exc:
            raise _RefusedError(f"row {row}: {field.replace('_', ' ')} {exc}", anchor) from exc
        anchors[field] = anchor
        flags.extend(FlaggedValue(field=field, flag=flag) for flag in sheet.flags(cell))
    try:
        return PoLine.model_validate(
            {**values, "anchors": PoLineAnchors(**anchors), "flags": tuple(flags)}
        )
    except ValidationError as exc:
        failed = str(exc.errors()[0]["loc"][0])
        raise _RefusedError(f"row {row}: {_first_error(exc)}", anchors.get(failed)) from exc


def _total(table: _Table, layout: ExcelLayout) -> PrintedTotal | None:
    """The amount in the total row under the last page's lines, if it prints one."""
    sheet = table.sheet
    label = sheet.find(layout.total_label)
    if label is None or label.row < table.first_row:
        return None
    cell = sheet.at(label.row, table.columns["amount"])
    try:
        amount = _number(cell.value)
    except ValueError as exc:
        raise _RefusedError(f"the total {exc}", sheet.anchor(cell)) from exc
    return PrintedTotal(
        amount=amount,
        anchor=sheet.anchor(cell),
        flags=tuple(FlaggedValue(field="amount", flag=flag) for flag in sheet.flags(cell)),
    )


# ------------------------------------------------------------------ values --
# Each refusal names what was expected, never the value found: the value is
# the customer's, and a refusal travels into logs.


def _label_key(text: str) -> str:
    """A label as compared: NFKC, casefolded, single-spaced, without a trailing colon."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split()).rstrip(":").rstrip()


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _text(value: object) -> str:
    """A cell as one line of text; a whole number typed as a number is its digits."""
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    raise ValueError("is not text")


def _whole_number(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError("is not a whole number")


def _number(value: object) -> Decimal:
    """A numeric cell as the number printed.

    Excel stores binary floats; twelve significant digits is past any price or
    quantity a PO prints and short of the noise a float carries, so a computed
    0.042000000000000003 reads as the 0.042 on the page.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(format(value, ".12g"))
    if isinstance(value, str) and _PLAIN_NUMBER.fullmatch(value.strip()):
        return Decimal(value.strip())
    raise ValueError("is not a number")


def _day(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError("is not a date")


def _currency(value: object) -> str:
    return _text(value).upper()


_HEADER_VALUES: Mapping[PoHeaderField, Callable[[object], object]] = {
    "po_no": _text,
    "revision": _whole_number,
    "po_date": _day,
    "currency": _currency,
}
_LINE_VALUES: Mapping[PoLineField, Callable[[object], object]] = {
    "line_no": _whole_number,
    "customer_item_code": _text,
    "description": _text,
    "quantity": _number,
    # As printed: a unit DW1 has no word for is `uom_mismatch` on the line.
    "uom": _text,
    "unit_price": _number,
    "amount": _number,
    "requested_date": _day,
}


def _first_error(exc: ValidationError) -> str:
    """Where validation failed and why, without the input (the models hide it)."""
    error = exc.errors(include_input=False)[0]
    where = ".".join(str(part) for part in error["loc"])
    return f"{where}: {error['msg']}"
