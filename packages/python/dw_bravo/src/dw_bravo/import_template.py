"""An Import template as Bravo stores it (`B00ImportSetting.LayoutData`, a
ZIP holding one `Xml`, the same way a layout is stored), read into which
column of the sheet each field of each table comes from (ticket 51).

The shape, as the SO screen's templates carry it on UAT (11-20):

    <root><Tables>
      <BizDoc><nSelectedSheetIndex>..</nSelectedSheetIndex>
              <Cols><DocDate>B</DocDate>...</Cols><txtRowRange>4</txtRowRange></BizDoc>
      <Detail>...<txtForeignKey>A</txtForeignKey><txtParentKey>A</txtParentKey>
              <Cols><POLine>S</POLine>...</Cols></Detail>
    </Tables></root>

A part this reader does not know refuses the whole template
(`UndecidableError`): DW never guesses what a template it cannot read asks.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from dw_bravo.expression import UndecidableError

_COLUMN: Final = re.compile(r"^[A-Z]{1,3}$")
_FIELD: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_SETTINGS: Final = frozenset(
    {"nSelectedSheetIndex", "txtRowRange", "txtForeignKey", "txtParentKey"}
)


@dataclass(frozen=True)
class TemplateTable:
    """One table of a template: each field and its sheet column, the row
    the data starts on, and the column joining lines to their header."""

    columns: Mapping[str, str]
    first_row: int | None = None
    sheet_index: int | None = None
    foreign_key: str | None = None
    parent_key: str | None = None


@dataclass(frozen=True)
class ImportTemplate:
    tables: Mapping[str, TemplateTable]

    def columns_read(self) -> frozenset[str]:
        """Every sheet column the template reads, keys included."""
        found: set[str] = set()
        for table in self.tables.values():
            found |= set(table.columns.values())
            found |= {k for k in (table.foreign_key, table.parent_key) if k is not None}
        return frozenset(found)


def _int(text: str | None, where: str) -> int:
    if text is None or not text.strip().isdigit():
        raise UndecidableError(f"{where} is not a number")
    return int(text.strip())


def _column(text: str | None, where: str) -> str:
    value = (text or "").strip()
    if not _COLUMN.match(value):
        raise UndecidableError(f"{where} is not a sheet column")
    return value


def read_import_template(xml: str) -> ImportTemplate:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as broken:
        raise UndecidableError(f"the template is not XML: {broken}") from None
    tables = root.find("Tables") if root.tag == "root" else None
    if tables is None or len(root) != 1:
        raise UndecidableError("the template is not <root><Tables>")
    read: dict[str, TemplateTable] = {}
    for table in tables:
        if not _FIELD.match(table.tag) or table.tag in read:
            raise UndecidableError(f"table {table.tag!r} cannot be read")
        columns: dict[str, str] = {}
        settings: dict[str, str | None] = {}
        for part in table:
            if part.tag == "Cols":
                for col in part:
                    if not _FIELD.match(col.tag) or col.tag in columns or len(col):
                        raise UndecidableError(f"{table.tag}.{col.tag} cannot be read")
                    columns[col.tag] = _column(col.text, f"{table.tag}.{col.tag}")
            elif part.tag in _SETTINGS and part.tag not in settings and not len(part):
                settings[part.tag] = part.text
            else:
                raise UndecidableError(f"{table.tag}.{part.tag} is not a part DW knows")
        if not columns:
            raise UndecidableError(f"{table.tag} reads no column")

        read[table.tag] = TemplateTable(
            columns=MappingProxyType(columns),
            first_row=None
            if settings.get("txtRowRange") is None
            else _int(settings.get("txtRowRange"), "txtRowRange"),
            sheet_index=None
            if settings.get("nSelectedSheetIndex") is None
            else _int(settings.get("nSelectedSheetIndex"), "nSelectedSheetIndex"),
            foreign_key=None
            if settings.get("txtForeignKey") is None
            else _column(settings.get("txtForeignKey"), "txtForeignKey"),
            parent_key=None
            if settings.get("txtParentKey") is None
            else _column(settings.get("txtParentKey"), "txtParentKey"),
        )
    if not read:
        raise UndecidableError("the template has no table")
    return ImportTemplate(MappingProxyType(read))
