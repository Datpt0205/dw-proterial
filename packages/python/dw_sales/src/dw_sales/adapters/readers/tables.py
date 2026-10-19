"""A master-data file as rows of cells (ticket 41), in the reader sandbox.

A workbook (an ``.xlsx``, or an ``.xls`` the sandbox converted first) is read
from its sheet named "Dữ liệu", the template's, else its first visible sheet;
a CSV is read as UTF-8 (Excel's "CSV UTF-8"), its delimiter a comma, a
semicolon or a tab. Each cell comes back as its value (text, a number, a
yes/no) and a date as ISO text; what the cells mean is the worker's to decide
(`dw_sales.domain.master_data.parse_rows`), not the sandbox's.

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

from dw_sales.adapters.formats import sniff
from dw_sales.adapters.readers.excel import open_for_viewing
from dw_sales.domain.master_data import MAX_ROWS, CellValue, ImportedTable, TableRow
from dw_sales.domain.order_checks import IntakeCaps

DATA_SHEET: Final = "Dữ liệu"
_MAX_COLUMNS: Final = 60
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


def _rows(values: Iterable[Iterable[object]]) -> tuple[list[TableRow], bool]:
    """Non-empty rows, numbered from 1, header included; whether more were left."""
    rows: list[TableRow] = []
    for number, raw in enumerate(values, start=1):
        cells = [_cell(v) for v in list(raw)[:_MAX_COLUMNS]]
        if all(c is None for c in cells):
            continue
        if len(rows) > MAX_ROWS:
            return rows, True
        rows.append(TableRow(row=number, cells=cells))
    return rows, False


def _workbook(data: bytes, caps: IntakeCaps) -> ImportedTable:
    try:
        values, _ = open_for_viewing(data, caps)
    except ValueError:
        raise ValueError("không mở được bảng tính này (hỏng, có mật khẩu hoặc có macro)") from None
    visible = [sheet for sheet in values.worksheets if sheet.sheet_state == "visible"]
    if not visible:
        raise ValueError("bảng tính không có trang nào đang hiện")
    sheet = next((s for s in visible if s.title == DATA_SHEET), visible[0])
    rows, truncated = _rows(sheet.iter_rows(values_only=True))
    return ImportedTable(sheet=sheet.title[:200], rows=rows, truncated=truncated)


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


def read_table(data: bytes, caps: IntakeCaps) -> ImportedTable:
    """The file's rows (module docstring). ``data`` is an ``.xlsx`` already
    when the file was a legacy workbook (`operations._readable_bytes`)."""
    match sniff(data):
        case "xlsx":
            return _workbook(data, caps)
        case None:
            return _csv(data, caps)
        case _:
            raise ValueError("tệp không phải bảng tính (.xlsx, .xls) hay CSV")
