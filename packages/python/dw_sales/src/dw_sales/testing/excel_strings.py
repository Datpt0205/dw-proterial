"""A workbook's text as Excel stores it, for the unit suite and the evals.

openpyxl writes every string inline in its cell (``t="inlineStr"``). Excel
writes text, rich-text runs included, to the shared-strings table
(``xl/sharedStrings.xml``) and points each cell at its entry. openpyxl reads
the two differently: in read-only mode it reports a run's font only for a
shared string (measured on openpyxl 3.1.5, ticket 20). So a reader that must
see a run's font is tested on both, and `as_excel_writes_it` gives the
second from the first.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Final

_INLINE: Final = re.compile(r'(<c [^>]*?)t="inlineStr"><is>(.*?)</is></c>')
_CONTENT_TYPE: Final = (
    '<Override PartName="/xl/sharedStrings.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
)
_RELATIONSHIP: Final = (
    '<Relationship Id="rIdShared" Type="http://schemas.openxmlformats.org/officeDocument/'
    '2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
)


def as_excel_writes_it(data: bytes) -> bytes:
    """``data``, a workbook openpyxl wrote, with every inline string moved to
    a shared-strings table. Refuses a workbook that has no inline string, so
    a test cannot believe it moved what was never there."""
    shared: list[str] = []

    def to_shared(match: re.Match[str]) -> str:
        shared.append(f"<si>{match.group(2)}</si>")
        return f'{match.group(1)}t="s"><v>{len(shared) - 1}</v></c>'

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        if "xl/sharedStrings.xml" in source.namelist():
            raise ValueError("the workbook already has a shared-strings table")
        for item in source.infolist():
            part = source.read(item.filename)
            if item.filename.startswith("xl/worksheets/"):
                part = _INLINE.sub(to_shared, part.decode()).encode()
            elif item.filename == "[Content_Types].xml":
                part = part.replace(b"</Types>", _CONTENT_TYPE.encode() + b"</Types>")
            elif item.filename == "xl/_rels/workbook.xml.rels":
                part = part.replace(
                    b"</Relationships>", _RELATIONSHIP.encode() + b"</Relationships>"
                )
            target.writestr(item, part)
        if not shared:
            raise ValueError("the workbook has no inline string to move")
        target.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'count="{len(shared)}" uniqueCount="{len(shared)}">{"".join(shared)}</sst>',
        )
    return out.getvalue()
