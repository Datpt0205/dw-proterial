"""A master-data file as rows of cells (ticket 41), in the reader sandbox.

A workbook (an ``.xlsx``, or an ``.xls`` the sandbox converted first) is read
from the sheet a caller names (DW2's master data reads one per list), else its
sheet named "Dữ liệu", the template's, else its first visible sheet;
a CSV is read as UTF-8 (Excel's "CSV UTF-8"), its delimiter a comma, a
semicolon or a tab. Each cell comes back as its value (text, a number, a
yes/no) and a date as ISO text; what the cells mean is the worker's to decide
(`dw_sales.domain.master_data.parse_rows`), not the sandbox's.

A row that labels a group of rows (one label merged across the row, beside
it only formulas: Bravo's "3. Đã duyệt" over its SUBTOTAL) is left out by its
shape (`_group_labels`), as are empty rows.

Bounded like every reader here: the order rules' caps on the file and on
what a workbook unpacks to (`open_for_viewing`), and `MAX_ROWS` rows of at
most `_MAX_COLUMNS` columns. A refusal is a ValueError whose sentence the
importer reads, so it is in Vietnamese and quotes nothing of the file.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date, datetime, time
from typing import Final

from openpyxl.worksheet.worksheet import Worksheet

from dw_sales.adapters.formats import sniff
from dw_sales.adapters.readers.excel import open_for_viewing
from dw_sales.domain.bravo_exports import TableGroup
from dw_sales.domain.master_data import MAX_ROWS, CellValue, ImportedTable, TableRow
from dw_sales.domain.order_checks import IntakeCaps

DATA_SHEET: Final = "Dữ liệu"
# Bravo exports run wide: "Customer order information" has 81 columns
# (B02, ticket 03).
_MAX_COLUMNS: Final = 100
_CSV_SHEET: Final = "CSV"


def _cell(value: object) -> CellValue:
    if value is None:
        return None
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0) else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _rows(
    values: Iterable[Iterable[object]], skipped: frozenset[int] = frozenset()
) -> tuple[list[TableRow], bool]:
    """Non-empty rows, numbered from 1, header included, but the ``skipped``
    ones; whether more were left."""
    rows: list[TableRow] = []
    for number, raw in enumerate(values, start=1):
        cells = [_cell(v) for v in list(raw)[:_MAX_COLUMNS]]
        if all(c is None for c in cells) or number in skipped:
            continue
        if len(rows) > MAX_ROWS:
            return rows, True
        rows.append(TableRow(row=number, cells=cells))
    return rows, False


def _group_labels(sheet: Worksheet, formulas: Worksheet) -> dict[int, str]:
    """The rows that label a group of the rows under them, by their shape
    alone, never by their words: one label merged across columns of a single
    row, and nothing else in the row but formulas (Bravo's "3. Đã duyệt" over
    A3:K3 with its SUBTOTAL beside it, B04). A title row has no formula.
    Each with its label's text: a list kept by approval state reads its rows'
    state from it (ticket 04)."""
    labels: dict[int, str] = {}
    for merged in sheet.merged_cells.ranges:
        if merged.min_row != merged.max_row or merged.min_col == merged.max_col:
            continue
        row = merged.min_row
        others = [
            cell
            for cell in formulas[row]
            if not merged.min_col <= cell.column <= merged.max_col and cell.value is not None
        ]
        if others and all(cell.data_type == "f" for cell in others):
            text = _cell(sheet.cell(row=row, column=merged.min_col).value)
            labels[row] = str(text)[:200] if text is not None else ""
    return labels


def _workbook(data: bytes, caps: IntakeCaps, named: str | None) -> ImportedTable:
    try:
        values, formulas = open_for_viewing(data, _table_caps(caps))
    except ValueError:
        raise ValueError("không mở được bảng tính này (hỏng, có mật khẩu hoặc có macro)") from None
    visible = [sheet for sheet in values.worksheets if sheet.sheet_state == "visible"]
    if not visible:
        raise ValueError("bảng tính không có trang nào đang hiện")
    if named is not None:
        found = next((s for s in visible if s.title == named), None)
        if found is None:
            raise ValueError("bảng tính không có trang được yêu cầu")
        sheet = found
    else:
        sheet = next((s for s in visible if s.title == DATA_SHEET), visible[0])
    labels = _group_labels(sheet, formulas[sheet.title])
    rows, truncated = _rows(sheet.iter_rows(values_only=True), frozenset(labels))
    groups = tuple(
        TableGroup(row=row, label=label) for row, label in sorted(labels.items()) if label
    )
    return ImportedTable(sheet=sheet.title[:200], rows=rows, truncated=truncated, groups=groups)


def _table_caps(caps: IntakeCaps) -> IntakeCaps:
    """The caps a list is opened under: a PO's, but a sheet as large as the
    rows and columns a list is read to (`MAX_ROWS` by `_MAX_COLUMNS`), which a
    PO's cell cap is far below (Bravo's item list: 12,273 rows of 28 columns).
    The zip-bomb bound on what the workbook unpacks to stays the PO's."""
    return caps.model_copy(update={"max_cells": max(caps.max_cells, MAX_ROWS * _MAX_COLUMNS)})


def _csv(data: bytes, caps: IntakeCaps) -> ImportedTable:
    if len(data) > caps.max_attachment_bytes:
        raise ValueError("tệp quá lớn")
    if b"\x00" in data[:4096] and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValueError("tệp không phải bảng tính (.xlsx, .xls) hay CSV")
    try:
        text = (
            data.decode("utf-16")
            if data.startswith((b"\xff\xfe", b"\xfe\xff"))
            else data.decode("utf-8-sig")
        )
    except UnicodeDecodeError:
        raise ValueError(
            "tệp CSV phải lưu dạng UTF-8 (trong Excel: Lưu thành > CSV UTF-8)"
        ) from None
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(
            text[:8192], delimiters=",;\t"
        )
    except csv.Error:
        dialect = csv.excel
    rows, truncated = _rows(csv.reader(io.StringIO(text), dialect))
    return ImportedTable(sheet=_CSV_SHEET, rows=rows, truncated=truncated)


def read_table(data: bytes, caps: IntakeCaps, sheet: str | None = None) -> ImportedTable:
    """The file's rows (module docstring). ``data`` is an ``.xlsx`` already
    when the file was a legacy workbook (`operations._readable_bytes`)."""
    match sniff(data):
        case "xlsx":
            return _workbook(data, caps, sheet)
        case None | "csv":
            # A UTF-16 tab-separated file sniffs ``csv`` (ticket 18): the
            # same rows as any CSV here.
            return _csv(data, caps)
        case _:
            raise ValueError("tệp không phải bảng tính (.xlsx, .xls) hay CSV")
