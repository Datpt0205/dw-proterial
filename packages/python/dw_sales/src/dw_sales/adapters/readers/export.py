"""A customer portal's export, read as rows with the customer's layout (ticket 18).

A customer that sends no PO by mail puts it on its portal; Sales downloads the
export and uploads it ("Tải PO lên"). The export is what Excel saves as
"Unicode text": UTF-16 with its byte-order mark, one tab-separated row per
line (`formats.sniff` says ``csv``). It mixes firm order rows with forecast
rows, and every row names its own PO number.

**Rows of text, nothing else.** The bytes are decoded and split on tabs and
line ends (`csv.reader` with a tab delimiter): a cell is text as written,
never evaluated, so a cell reading ``=1+1`` is those four characters.
Bounded by the order rules' caps: the file's size, and the cells read
(`IntakeCaps.max_cells`).

**The layout is the customer's** (`ExportMapping`, tenant data a person
mapped and another approved): which title heads each column, which column
says firm or forecast, and which of its values mean firm. The titles are
found on the first row holding every one of them; each row under it whose
order type is a firm value is a line, numbered in order; every other row is
a forecast, counted (`PoDocument.forecast_rows`) and never read. A firm row
that does not read refuses the whole file, saying which row and column: a PO
read in part would leave out lines nobody knows are missing.

**What the export does not print** is held where the values it stands with
are, flagged `not_printed` for Sales: the currency the layout states, at the
first line's PO number; a price of zero (and so an amount of zero), at the
line's quantity. A revision is 0, at the PO number, as for a form that
prints none. Each line keeps its own PO number and PO date (`PoLine.line_po`);
the PO's are the first line's, and intake opens one case per PO number
(ticket 19, `po_groups`), each dated by its own first row.

Every anchor is ``CSV!<column><row>`` in the customer's file, which the
source view shows as a sheet of the same rows (`export_grid`).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Final

from openpyxl.utils import get_column_letter
from pydantic import ValidationError

from dw_platform.domain.messages import Attachment, AttachmentContent
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.layouts import (
    NO_FIRM_ROW,
    ExportMapping,
    LabelCell,
    LayoutSource,
    label_key,
)
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.orders import (
    FlaggedValue,
    LinePo,
    PoDocument,
    PoHeader,
    PoHeaderAnchors,
    PoLine,
    PoLineAnchors,
    RegionFlag,
    Unreadable,
)

# 1.1.0 (ticket 19): each line carries its own row's PO date.
PARSER_VERSION: Final = "export_po_reader@1.1.0"
# The one sheet an export is, as anchors and the source view name it.
EXPORT_SHEET: Final = "CSV"
# Where the titles are looked for, and how much of the export a person
# mapping it is shown: the titles sit on the first rows.
_TITLE_ROWS: Final = 20
_SHOWN_ROWS: Final = 60
_LABEL_TEXT: Final = 200
# What the source view shows of an export, as of a sheet.
_GRID_ROWS: Final = 1000
_GRID_COLUMNS: Final = 52
_BOMS: Final = {b"\xff\xfe": "utf-16-le", b"\xfe\xff": "utf-16-be"}
_NOT_PRINTED: Final = RegionFlag.NOT_PRINTED


class _RefusedError(Exception):
    def __init__(self, reason: str, anchor: SourceAnchor | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.anchor = anchor


def export_rows(data: bytes, caps: IntakeCaps) -> list[list[str]]:
    """The export's rows, each a list of its cells as written, blank rows
    kept so a row's number is its line in the file. Refused (ValueError)
    over the caps or when the bytes are no UTF-16 text."""
    if len(data) > caps.max_attachment_bytes:
        raise ValueError("the file is over the size read here")
    encoding = _BOMS.get(data[:2])
    if encoding is None:
        raise ValueError("the export is not UTF-16 text with a byte-order mark")
    try:
        text = data[2:].decode(encoding)
    except UnicodeDecodeError:
        raise ValueError("the export is not UTF-16 text") from None
    rows: list[list[str]] = []
    cells = 0
    for row in csv.reader(io.StringIO(text, newline=""), delimiter="\t", quotechar='"'):
        cells += len(row)
        if cells > caps.max_cells:
            raise ValueError("the export has more cells than are read here")
        rows.append([cell.strip() for cell in row])
    return rows


def _ref(row: int, column: int) -> str:
    return f"{EXPORT_SHEET}!{get_column_letter(column)}{row}"


def export_source(content: AttachmentContent, caps: IntakeCaps) -> LayoutSource | None:
    """The cells a title may be (the first rows' text), and the first rows as
    a person reads them: what the onboarding screen maps from. None for an
    export with no text on its first rows."""
    rows = export_rows(content.data, caps)
    cells = [
        LabelCell(
            ref=_ref(number, column),
            sheet=EXPORT_SHEET,
            row=number,
            column=column,
            text=text[:_LABEL_TEXT],
        )
        for number, row in enumerate(rows[:_TITLE_ROWS], start=1)
        for column, text in enumerate(row, start=1)
        if text and not _is_number(text)
    ]
    if not cells:
        return None
    shown = tuple(
        tuple(text[:_LABEL_TEXT] for text in row) for row in rows[:_SHOWN_ROWS] if any(row)
    )
    return LayoutSource(kind="csv", cells=tuple(cells[:2000]), rows=shown)


def export_grid(data: bytes, caps: IntakeCaps) -> tuple[int, int, bool, list[tuple[int, int, str]]]:
    """The export as the source view shows a sheet: its rows and columns
    shown, whether more were left out, and each non-empty cell by row and
    column with its text."""
    rows = export_rows(data, caps)
    width = max((len(row) for row in rows), default=0)
    shown_rows, shown_columns = min(len(rows), _GRID_ROWS), min(width, _GRID_COLUMNS)
    cells = [
        (number, column, text)
        for number, row in enumerate(rows[:shown_rows], start=1)
        for column, text in enumerate(row[:shown_columns], start=1)
        if text
    ]
    truncated = len(rows) > _GRID_ROWS or width > _GRID_COLUMNS
    return shown_rows, shown_columns, truncated, cells


@dataclass(frozen=True, slots=True)
class _Table:
    attachment: Attachment
    mapping: ExportMapping
    title_row: int
    columns: dict[str, int]

    def anchor(self, row: int, field: str) -> SourceAnchor:
        return SourceAnchor(
            attachment_id=self.attachment.attachment_id,
            attachment_sha256=self.attachment.sha256,
            cell_ref=_ref(row, self.columns[field]),
        )

    def cell(self, cells: Sequence[str], field: str) -> str:
        column = self.columns[field]
        return cells[column - 1] if column <= len(cells) else ""


def read_export(
    content: AttachmentContent, mapping: ExportMapping, caps: IntakeCaps, *, layout_ref: str
) -> PoDocument | Unreadable:
    """The export's firm rows as one PO, read with ``mapping`` (module
    docstring), stamped with ``layout_ref``; or why not."""
    try:
        rows = export_rows(content.data, caps)
        return _read(content.attachment, rows, mapping, layout_ref)
    except _RefusedError as refused:
        return Unreadable(reason=refused.reason[:500], anchor=refused.anchor)
    except ValueError as refused:
        return Unreadable(reason=str(refused)[:500])


def _read(
    attachment: Attachment, rows: list[list[str]], mapping: ExportMapping, layout_ref: str
) -> PoDocument:
    table = _titles(attachment, rows, mapping)
    lines: list[PoLine] = []
    forecast = 0
    first_row = 0
    for number in range(table.title_row + 1, len(rows) + 1):
        cells = rows[number - 1]
        if not any(cells):
            continue
        if not mapping.is_firm(table.cell(cells, "order_type")):
            forecast += 1
            continue
        lines.append(_line(table, number, cells, len(lines) + 1))
        first_row = first_row or number
    if not lines:
        raise _RefusedError(f"{NO_FIRM_ROW} ({forecast} rows marked otherwise, never ordered)")
    first = lines[0]
    assert first.line_po is not None  # every line read here names its PO
    try:
        po_date = _day(table.cell(rows[first_row - 1], "po_date"), mapping, "po date")
    except ValueError as exc:
        raise _RefusedError(f"row {first_row}: {exc}", table.anchor(first_row, "po_date")) from exc
    po_anchor = first.line_po.anchor
    try:
        header = PoHeader(
            po_no=first.line_po.po_no,
            revision=0,
            po_date=po_date,
            currency=mapping.currency,
            anchors=PoHeaderAnchors(
                po_no=po_anchor,
                revision=po_anchor,
                po_date=table.anchor(first_row, "po_date"),
                currency=po_anchor,
            ),
            flags=(FlaggedValue(field="currency", flag=_NOT_PRINTED),),
        )
        return PoDocument(
            attachment_id=attachment.attachment_id,
            attachment_sha256=attachment.sha256,
            parser_version=PARSER_VERSION,
            header=header,
            lines=tuple(lines),
            rows_printed=len(lines),
            regions=(EXPORT_SHEET,),
            layout_ref=layout_ref,
            forecast_rows=forecast,
        )
    except ValidationError as exc:
        raise _RefusedError(f"the rows do not form one PO: {_first_error(exc)}") from exc


def _titles(attachment: Attachment, rows: list[list[str]], mapping: ExportMapping) -> _Table:
    """The first row holding every title of the layout, each once."""
    wanted = {field: label_key(title) for field, title in mapping.titles().items()}
    for number, cells in enumerate(rows[:_TITLE_ROWS], start=1):
        keys = [label_key(cell) for cell in cells]
        if all(keys.count(key) == 1 for key in wanted.values()):
            columns = {field: keys.index(key) + 1 for field, key in wanted.items()}
            return _Table(attachment, mapping, number, columns)
    raise _RefusedError("no row of the export holds every column title the layout names")


def _line(table: _Table, row: int, cells: Sequence[str], line_no: int) -> PoLine:
    mapping = table.mapping
    priced = mapping.unit_price is not None
    try:
        po_no = _text(table.cell(cells, "po_no"), "po no")
        po_date = _day(table.cell(cells, "po_date"), mapping, "po date")
        code = _text(table.cell(cells, "customer_item_code"), "customer item code")
        quantity = _number(table.cell(cells, "quantity"), mapping, "quantity")
        uom = _text(table.cell(cells, "uom"), "uom")
        requested = _day(table.cell(cells, "requested_date"), mapping, "requested date")
        unit_price = (
            _number(table.cell(cells, "unit_price"), mapping, "unit price")
            if priced
            else Decimal(0)
        )
        description = table.cell(cells, "description") if mapping.description is not None else ""
    except ValueError as exc:
        raise _RefusedError(f"row {row}: {exc}", _anchor_of(table, row, str(exc))) from exc
    quantity_at = table.anchor(row, "quantity")
    price_at = table.anchor(row, "unit_price") if priced else quantity_at
    code_at = table.anchor(row, "customer_item_code")
    flags = (
        ()
        if priced
        else (
            FlaggedValue(field="unit_price", flag=_NOT_PRINTED),
            FlaggedValue(field="amount", flag=_NOT_PRINTED),
        )
    )
    try:
        return PoLine(
            line_no=line_no,
            customer_item_code=code,
            description=" ".join(description.split()),
            quantity=quantity,
            uom=uom,
            unit_price=unit_price,
            amount=quantity * unit_price,
            requested_date=requested,
            anchors=PoLineAnchors(
                line_no=table.anchor(row, "po_no"),
                customer_item_code=code_at,
                description=(
                    table.anchor(row, "description") if mapping.description is not None else code_at
                ),
                quantity=quantity_at,
                uom=table.anchor(row, "uom"),
                unit_price=price_at,
                amount=price_at,
                requested_date=table.anchor(row, "requested_date"),
            ),
            flags=flags,
            line_po=LinePo(
                po_no=po_no,
                anchor=table.anchor(row, "po_no"),
                po_date=po_date,
                po_date_anchor=table.anchor(row, "po_date"),
            ),
        )
    except ValidationError as exc:
        raise _RefusedError(f"row {row}: {_first_error(exc)}", quantity_at) from exc


def _anchor_of(table: _Table, row: int, reason: str) -> SourceAnchor | None:
    """The cell a refusal names, by the field its reason starts with."""
    for field in table.columns:
        if reason.startswith(field.replace("_", " ")):
            return table.anchor(row, field)
    return None


# ------------------------------------------------------------------ values --
# Each refusal names the field and what was expected, never the value found.


def _text(value: str, field: str) -> str:
    if not value:
        raise ValueError(f"{field} is blank")
    return " ".join(value.split())


def _number(value: str, mapping: ExportMapping, field: str) -> Decimal:
    plain = value.replace(" ", "")
    if mapping.thousands_separator != "none":
        plain = plain.replace(mapping.thousands_separator, "")
    plain = plain.replace(mapping.decimal_separator, ".")
    try:
        number = Decimal(plain)
    except InvalidOperation:
        raise ValueError(f"{field} is not a number in the layout's notation") from None
    if not number.is_finite():
        raise ValueError(f"{field} is not a number in the layout's notation")
    return number


def _day(value: str, mapping: ExportMapping, field: str) -> date:
    try:
        return datetime.strptime(value.strip(), mapping.date_format).date()
    except ValueError:
        raise ValueError(f"{field} is not a date in the layout's format") from None


def _is_number(text: str) -> bool:
    try:
        Decimal(text.replace(",", "").replace(" ", ""))
    except InvalidOperation:
        return False
    return True


def _first_error(exc: ValidationError) -> str:
    """Where validation failed and why, without the input (the models hide it)."""
    error = exc.errors(include_input=False)[0]
    where = ".".join(str(part) for part in error["loc"])
    return f"{where}: {error['msg']}"
