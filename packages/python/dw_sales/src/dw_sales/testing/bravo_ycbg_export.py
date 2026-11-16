"""A synthetic export of Bravo's YCBG lines (ticket 16), for tests and demos.

Shaped as Bravo's "RFQ List" export is (Box B16, seen 11-14; the shape only,
every value here fictional): the screen's title, two blank rows, the column
titles on row 4 in Bravo's two languages with Excel's ``_x000D_`` inside some
of them, Bravo's other columns around the ones DW1 reads, the line's "Số thứ
tự" blank, and a "Tổng cộng:" row under the lines.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import NamedTuple

from openpyxl import Workbook

# Bravo's titles, in its order, for the columns this fixture fills; the
# others are Bravo's and stay blank.
TITLES: tuple[str, ...] = (
    "Received date",
    "RFQ No",
    "Nhóm KH/ Group customer",
    "Số thứ tự/_x000D_ No.",
    "Mô tả của KH/Customer item description",
    "Status",
    "Design check",
    "Decline reason",
    "Base price _x000D_ code",
    "Giá cơ bản/_x000D_ Base price",
    "Người thiết kế/_x000D_ Designer",
    "Mail title",
)


class ExportRow(NamedTuple):
    """One YCBG line as the export prints it; None is a blank cell."""

    ycbg_no: str
    line_no: int | str | None
    status: str
    design_check: str | None = None
    reason: str | None = None
    bp_code: str | None = None
    description: str | None = None


def _cells(row: ExportRow) -> list[object]:
    return [
        "2026-11-03",
        row.ycbg_no,
        "PRV",
        row.line_no,
        row.description,
        row.status,
        row.design_check,
        row.reason,
        row.bp_code,
        None,
        None,
        None,
    ]


def ycbg_export_xlsx(rows: Sequence[ExportRow], *, titles: Sequence[str] | None = None) -> bytes:
    """The workbook's bytes (module docstring); ``titles`` replaces Bravo's."""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "RFQ List"
    sheet.append(["RFQ List (MẪU GIẢ LẬP)"])
    sheet.append([])
    sheet.append([])
    sheet.append(list(titles) if titles is not None else list(TITLES))
    for row in rows:
        sheet.append(_cells(row))
    sheet.append(["Tổng cộng:"])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
