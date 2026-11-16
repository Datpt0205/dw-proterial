"""A synthetic export of Bravo's YCBG screen (ticket 16), for tests and demos.

No real export has been seen: the column titles are the ones
`ycbg_exports.COLUMNS` assumes, and every value is fictional. A report
heading above the titles stands in for what Bravo prints there.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import NamedTuple

from openpyxl import Workbook

from dw_sales.application.ycbg_exports import COLUMNS

_ORDER = ("ycbg_no", "line_no", "status", "design_check", "reason", "bp_code")


class ExportRow(NamedTuple):
    """One YCBG line as the export prints it; None is a blank cell."""

    ycbg_no: str
    line_no: int | str
    status: str
    design_check: str | None = None
    reason: str | None = None
    bp_code: str | None = None


def ycbg_export_xlsx(rows: Sequence[ExportRow], *, titles: Sequence[str] | None = None) -> bytes:
    """The workbook's bytes: a heading, the titles (``COLUMNS`` unless
    given), then one row per line."""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "YCBG"
    sheet.append(["Phiếu yêu cầu báo giá (MẪU GIẢ LẬP)"])
    sheet.append(list(titles) if titles is not None else [COLUMNS[f] for f in _ORDER])
    for row in rows:
        sheet.append([getattr(row, field) for field in _ORDER])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
