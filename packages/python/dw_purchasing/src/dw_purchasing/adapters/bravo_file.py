"""`SpreadsheetPort` over openpyxl: the Bravo import file's bytes.

Every cell through the platform's `put` (a string is text, never a formula: a
description reading ``=HYPERLINK(...)`` stays those characters). The same rows
write the same bytes: the workbook's own dates are the drafting time, and the
zip entries carry it too, so a file drawn again is the file drawn before.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime

from openpyxl import Workbook

from dw_platform.adapters.spreadsheet import put
from dw_purchasing.domain.orders import Cell


class BravoFile:
    """Implements `SpreadsheetPort`."""

    def write(
        self, sheet: str, rows: Sequence[Sequence[Cell]], *, date_format: str, at: datetime
    ) -> bytes:
        book = Workbook()
        target = book.active
        assert target is not None
        target.title = sheet
        stamp = at.astimezone(UTC).replace(tzinfo=None, microsecond=0)
        book.properties.created = stamp
        book.properties.modified = stamp
        book.properties.creator = "DW2"
        for r, row in enumerate(rows, start=1):
            for c, value in enumerate(row, start=1):
                put(target, r, c, value, bold=r == 1, date_format=date_format)
        raw = io.BytesIO()
        book.save(raw)
        return _fixed_times(raw.getvalue(), stamp)


_MODIFIED = re.compile(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)")


def _fixed_times(data: bytes, stamp: datetime) -> bytes:
    """The archive again, every entry and the workbook's own modified date
    ``stamp``: openpyxl dates both at save (measured, openpyxl 3.1)."""
    written = stamp.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(data)) as source,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for item in source.infolist():
            entry = zipfile.ZipInfo(item.filename, date_time=stamp.timetuple()[:6])
            entry.compress_type = zipfile.ZIP_DEFLATED
            content = source.read(item.filename)
            if item.filename == "docProps/core.xml":
                content = _MODIFIED.sub(rb"\g<1>" + written + rb"\g<2>", content)
            target.writestr(entry, content)
    return out.getvalue()
