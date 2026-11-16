"""One reader for every file Bravo exports (dw_sales ticket 14, ADR 0026).

Until the vendor's API reads Bravo, a person exports a Bravo screen to Excel
and uploads it. Every such file has one shape (Box B02, B04, B05, B06, B07,
B16, B21; `Bravo-export/_ANH.md`, outside git): a title above, sometimes a
row of block labels ("Request for quotation", "Base price"), then the
column titles, then the rows; a screen with groups ("3. Đã duyệt") puts a
label row before each group, which the reader sandbox leaves out
(`adapters/readers/tables.py`). Where the titles are is not fixed: row 2 on
most screens, row 3 under B07's block labels, row 4 on B16's report.

So a file is read **by its columns' titles, never by position**
(`find_header`): the header is the row among the first few that titles the
most of the columns asked for; a required column it does not title is
refused by name (`MissingColumnsError`), and a column the file has that
nothing asked for is listed (`Header.extra`), never guessed at. A title is
matched by `header_key`: no case, diacritics, spacing or punctuation, and
none of the ``_x000D_`` Excel writes for a line break inside a title (B07,
B16, B21). Bravo writes many titles in two languages ("Số thứ tự/ No."):
a column lists each form it is known by, as Bravo prints it.

What a cell means is the caller's: the master lists
(`master_data.parse_rows`), Design's result on a YCBG
(`application.ycbg_exports`) and a sales order read back (ticket 03) each
read their own columns through this one header.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# A cell as the reader hands it over: text, a number, a yes/no, or nothing.
# A date cell arrives as ISO text (``2026-10-01``).
CellValue = str | int | float | bool | None


class TableRow(BaseModel):
    """One non-empty row of the sheet, numbered as the spreadsheet numbers it."""

    model_config = _FROZEN

    row: int = Field(ge=1)
    cells: list[CellValue]


class ImportedTable(BaseModel):
    """What the reader read from a file: one sheet's rows, the header first."""

    model_config = _FROZEN

    sheet: str = Field(max_length=200)
    rows: list[TableRow]
    # The sheet held more rows than are read (`master_data.MAX_ROWS`).
    truncated: bool = False


# Excel's escape for a character XML cannot hold, ``_x000D_`` for a carriage
# return: openpyxl hands it over as written.
_EXCEL_ESCAPE: Final = re.compile(r"_x[0-9a-fA-F]{4}_")


def header_key(text: str) -> str:
    """A title as it is matched: no diacritics, no case, no spacing or
    punctuation, no Excel escape. "Mã khách hàng" and "MA_KHACH_HANG" read
    the same, as do "Base price _x000D_ code" and "Base price code"."""
    text = _EXCEL_ESCAPE.sub("", text)
    decomposed = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    bare = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", bare.casefold())


class TitledColumn(Protocol):
    """A column a file is read by: the title it is named by, every form it is
    known by, whether a file must have it, and whether its cells add up when
    a file titles it twice (Bravo's customer list has two "E-mail liên hệ")."""

    @property
    def header(self) -> str: ...

    @property
    def keys(self) -> frozenset[str]: ...

    @property
    def required(self) -> bool: ...

    @property
    def repeatable(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class ExportColumn:
    """A column of a Bravo screen, as its export titles it."""

    header: str
    # Every other form Bravo titles it by: the other language, another screen.
    aliases: tuple[str, ...] = ()
    required: bool = True
    repeatable: bool = False

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(header_key(title) for title in (self.header, *self.aliases))


class MissingColumnsError(ValueError):
    """The file lacks a column it must have: nothing of it is read."""

    def __init__(self, headers: Sequence[str]) -> None:
        super().__init__("thiếu cột: " + ", ".join(headers))
        self.headers = tuple(headers)


# Where the header may be: among the first rows, under what an export prints
# above it.
HEADER_WITHIN: Final = 10
# How many titles nothing asked for are listed, each cut to this: the file's
# own text, shown back to the person who uploaded it, bounded.
_EXTRA_LISTED: Final = 20
_EXTRA_CHARS: Final = 100


def _title(cell: CellValue) -> str | None:
    if not isinstance(cell, str):
        return None
    text = cell.strip()
    return text or None


@dataclass(frozen=True)
class Header:
    """Where a file's header is and which cell is which column."""

    # Into the rows searched; the rows below it are the data.
    index: int
    at: Mapping[int, TitledColumn]
    # The titles no column matched, as the file prints them (bounded).
    extra: tuple[str, ...]

    def cell(self, row: TableRow, column: TitledColumn) -> CellValue:
        """The row's cell under ``column``, the first where it repeats; None
        for a column the file does not title, or a row that ends before it."""
        for index, found in self.at.items():
            if found is column:
                return row.cells[index] if index < len(row.cells) else None
        return None


def _matched(row: TableRow, columns: Sequence[TitledColumn]) -> dict[int, TitledColumn]:
    by_key = {key: column for column in columns for key in column.keys}
    found: dict[int, TitledColumn] = {}
    for index, cell in enumerate(row.cells):
        title = _title(cell)
        column = None if title is None else by_key.get(header_key(title))
        if column is not None:
            found[index] = column
    return found


def find_header(
    rows: Sequence[TableRow], columns: Sequence[TitledColumn], *, within: int = HEADER_WITHIN
) -> Header:
    """The header among the first ``within`` rows: the one titling the most
    of ``columns``, the earliest of equals (module docstring). Raises
    `MissingColumnsError` naming each required column it lacks, and a
    ValueError for a column titled twice that does not add up."""
    best: tuple[int, dict[int, TitledColumn]] | None = None
    for index, row in enumerate(rows[:within]):
        found = _matched(row, columns)
        if found and (best is None or _distinct(found) > _distinct(best[1])):
            best = (index, found)
    if best is None:
        raise MissingColumnsError([c.header for c in columns if c.required])
    index, at = best
    seen: set[int] = set()
    for column in at.values():
        if id(column) in seen and not column.repeatable:
            raise ValueError(f"cột '{column.header}' xuất hiện hai lần")
        seen.add(id(column))
    missing = [c.header for c in columns if c.required and id(c) not in seen]
    if missing:
        raise MissingColumnsError(missing)
    extra = tuple(
        title[:_EXTRA_CHARS]
        for position, cell in enumerate(rows[index].cells)
        if position not in at and (title := _title(cell)) is not None
    )[:_EXTRA_LISTED]
    return Header(index=index, at=at, extra=extra)


def _distinct(found: Mapping[int, TitledColumn]) -> int:
    return len(set(map(id, found.values())))
