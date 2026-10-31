"""Writing one spreadsheet cell so a string is text, never a formula.

Lifted from Sales' artifact writer (G29) when DW2's Bravo import file became
its second caller (docs/adr/0013: what a second context shares moves to the
platform). openpyxl reads a string that starts with ``=`` as a formula; every
string cell is set back to type ``s``, and one that a spreadsheet would read
as a formula once edited (``= + - @``, a tab or a carriage return first) also
gets Excel's quote prefix. A description reading ``=HYPERLINK(...)`` stays
those characters, whoever wrote it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Final

from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

# What a spreadsheet reads as the start of a formula once a cell is edited.
FORMULA_START: Final = ("=", "+", "-", "@", "\t", "\r")

CellValue = str | int | Decimal | date | None


def put(
    sheet: Worksheet,
    row: int,
    col: int,
    value: CellValue,
    *,
    bold: bool = False,
    date_format: str = "yyyy-mm-dd",
) -> None:
    """``value`` at (``row``, ``col``): text as text, a Decimal with the
    places it holds, a date in ``date_format``; nothing for None."""
    if value is None:
        return
    cell = sheet.cell(row=row, column=col)
    cell.value = value
    if isinstance(value, str):
        # openpyxl typed a leading "=" as a formula when assigned: text it is.
        cell.data_type = "s"
        if value.startswith(FORMULA_START):
            cell.quotePrefix = True
    elif isinstance(value, Decimal):
        # The places the value holds, so 0.6890 prints as 0.6890, not 0.689.
        places = -value.as_tuple().exponent  # type: ignore[operator]
        cell.number_format = "0." + "0" * places if places > 0 else "0"
    elif isinstance(value, date):
        cell.number_format = date_format
    if bold:
        cell.font = Font(bold=True)
