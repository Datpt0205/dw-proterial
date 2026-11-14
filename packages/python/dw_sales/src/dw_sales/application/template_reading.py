"""A company's Bravo import template, read by code and mapped by a model
("Tạo từ tệp mẫu", phase 1).

The person uploads the Excel template their Bravo imports; DW1 proposes a
`sales_bravo_upload` version from it, which the person reviews and sends
through the rules editor like any other proposal (`rules.SalesRulesService`).
This module is the part that decides, and it decides in code (dw_sales ADR
0005): the model only says, column by column, where a column's value comes
from.

- **What is read** (`header_row`): the first visible sheet with a row of at
  least `MIN_HEADERS` visible text cells; that row is the template's header
  row, its cells in column order, and the visible text of each row above it
  (a title, group labels: Bravo's "Import Sales Order" prints both above row
  3). A hidden sheet, row or column, and a cell whose text cannot be seen
  (its font the colour of its fill, white on no fill, or 2pt and smaller:
  `text_unseen`, which the reader sandbox sets) are dropped before anything
  else: a person reviewing the template cannot see them, so an instruction
  hidden there never reaches the model (`visible`). Below the header row,
  a column whose filled rows all hold one visible value has that value read
  too (`repeated_values`): what a fixed value can be taken from.
- **What the model is asked** (`ModelBravoMapping`): for each column, by its
  letter, one source: a field code computes (`UploadField`), a value of the
  customer's record (`CustomerAttribute`), or a fixed text; a column it does
  not name is left blank. Columns are named by letter, never by header: a
  template prints the same header twice (Bravo's repeats "Delivery mode",
  "Delivery term" and "Destination" at line level), and a header names no
  one column.
- **What code accepts** (`verify`): every column the model names is a
  visible cell of the header row, named once, with at most one source; a
  fixed text is the value every filled row of that column holds; no field
  is two columns; the fields every upload needs are named
  (`REQUIRED_UPLOAD_FIELDS`, and the item by one of `UPLOAD_ITEM_FIELDS`);
  the sheet is the one read; and the whole document passes
  `BravoUploadLayout`. Anything else is refused, with the fields and cells
  named and never a word of the model's.
- **What is drafted**: every column at its place in the template, from A to
  the last header (a column with no visible header is blank and headless),
  the rows above the header row as the layout's ``banner``, each text over
  the columns up to the next one's, and each column's number format as the
  version in force has it for the same source.
- **What the person is shown**: each value the machine filled is listed by
  its document path (`machine_read`) with the cell it came from
  (`evidence`, ``Sheet!C1``); a template column left blank is listed, for
  the person to check it is meant to be.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_agent_runtime.model.interpretation import estimated_tokens
from dw_sales.application.artifact_content import (
    REQUIRED_UPLOAD_FIELDS,
    UPLOAD_HEADER_MAX,
    UPLOAD_ITEM_FIELDS,
    BravoUploadLayout,
    CustomerAttribute,
    UploadField,
)
from dw_sales.application.source import SheetCell, SheetGrid

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# A header row has at least this many visible text cells: a title line or a
# note above the table has fewer.
MIN_HEADERS: Final = 4
# How many sheets of a workbook are looked at for a header row.
MAX_SHEETS: Final = 10
# The longest header a layout may hold: a longer one is refused as
# `header_too_long`.
HEADER_LIMIT: Final = UPLOAD_HEADER_MAX
# How much of a header or a value the model is shown at most; less when the
# template is too long for the model's input (`mapping_inputs`).
SHOWN_LIMIT: Final = 64

UPLOAD_FIELDS: Final[tuple[UploadField, ...]] = get_args(UploadField)
CUSTOMER_ATTRIBUTES: Final[tuple[CustomerAttribute, ...]] = get_args(CustomerAttribute)


class TemplateHeader(BaseModel):
    """One visible cell of the header row (or a row above it), as the
    workbook holds it."""

    model_config = _FROZEN

    ref: str = Field(pattern=r"^[A-Z]{1,3}[1-9][0-9]{0,6}$")
    column: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=2000)


class TemplateRow(BaseModel):
    """The template's header row: its sheet, its row number, its cells, and
    the visible cells of each row above it, from row 1 (an empty tuple for a
    row with none)."""

    model_config = _FROZEN

    sheet: str = Field(min_length=1, max_length=200)
    row: int = Field(ge=1)
    headers: tuple[TemplateHeader, ...] = Field(min_length=MIN_HEADERS)
    above: tuple[tuple[TemplateHeader, ...], ...] = ()

    def at(self, header: TemplateHeader) -> str:
        """Where a value was read: ``Sheet!C1``."""
        return f"{self.sheet}!{header.ref}"

    @property
    def span(self) -> str:
        """The header row as a range: ``Sheet!A1:H1``."""
        return f"{self.sheet}!{self.headers[0].ref}:{self.headers[-1].ref}"


def plain(text: str) -> str:
    """A header as compared and as written: NFC, without surrounding spaces.
    A workbook may hold Vietnamese decomposed (NFD) and a model answers
    composed; neither is a different header."""
    return unicodedata.normalize("NFC", text).strip()


def visible(cell: SheetCell) -> bool:
    """Whether a person looking at the sheet sees this cell's text."""
    return not (cell.hidden_row or cell.hidden_column or cell.font_matches_fill or cell.text_unseen)


def _shown(grid: SheetGrid) -> dict[int, list[SheetCell]]:
    """The visible text cells of a sheet, by row, each row in column order."""
    rows: dict[int, list[SheetCell]] = {}
    for cell in grid.cells:
        if visible(cell) and cell.text.strip():
            rows.setdefault(cell.row, []).append(cell)
    return {number: sorted(cells, key=lambda c: c.column) for number, cells in rows.items()}


def _header(cell: SheetCell) -> TemplateHeader:
    return TemplateHeader(ref=cell.ref, column=cell.column, text=cell.text[:2000])


def header_row(grid: SheetGrid) -> TemplateRow | None:
    """The first row of a visible sheet with `MIN_HEADERS` visible text
    cells, with the rows above it, or None. Hidden cells are dropped first
    (module docstring)."""
    if grid.hidden_sheet:
        return None
    rows = _shown(grid)
    for number in sorted(rows):
        if len(rows[number]) >= MIN_HEADERS:
            return TemplateRow(
                sheet=grid.sheet,
                row=number,
                headers=tuple(_header(c) for c in rows[number]),
                above=tuple(
                    tuple(_header(c) for c in rows.get(above, ())) for above in range(1, number)
                ),
            )
    return None


def repeated_values(grid: SheetGrid, row: TemplateRow) -> dict[int, TemplateHeader]:
    """By column, the one value every filled row below the header row holds
    in it, where they hold one (the first such cell, to cite): what a fixed
    value of the column can be read from. Hidden cells are dropped first."""
    seen: dict[int, list[SheetCell]] = {}
    for number, cells in _shown(grid).items():
        if number > row.row:
            for cell in cells:
                seen.setdefault(cell.column, []).append(cell)
    return {
        column: _header(cells[0])
        for column, cells in seen.items()
        if len({plain(c.text) for c in cells}) == 1 and len(plain(cells[0].text)) <= HEADER_LIMIT
    }


# ------------------------------------------------------------- the model --


class ModelColumnSource(BaseModel):
    """One template column, by its letter, and where its value comes from:
    at most one of the three; none leaves it blank."""

    model_config = _FROZEN

    column: str = Field(pattern=r"^[A-Z]{1,3}$")
    field: UploadField | None = None
    customer: CustomerAttribute | None = None
    constant: str | None = Field(default=None, max_length=HEADER_LIMIT)


class ModelBravoMapping(BaseModel):
    """The model's answer: the columns it gives a source, by letter."""

    model_config = _FROZEN

    columns: tuple[ModelColumnSource, ...] = Field(default=(), max_length=200)


def _letters(ref: str) -> str:
    return re.sub(r"\d", "", ref)


def mapping_inputs(
    row: TemplateRow, repeated: Mapping[int, TemplateHeader], room: int
) -> dict[str, str]:
    """The header row as code-built JSON, a column's repeated value beside
    its header, each text cut to fit ``room`` tokens (at most `SHOWN_LIMIT`
    characters)."""
    width = SHOWN_LIMIT
    while True:
        shown: list[dict[str, str]] = []
        for header in row.headers:
            column = {"column": _letters(header.ref), "header": plain(header.text)[:width]}
            if (value := repeated.get(header.column)) is not None:
                column["every_row"] = plain(value.text)[:width]
            shown.append(column)
        headers = json.dumps(shown, ensure_ascii=False)
        if estimated_tokens(headers) <= room or width <= 16:
            return {"headers": headers}
        width //= 2


# ---------------------------------------------------------- verification --

ProblemCode = Literal[
    # A template column no source was given: left blank in the draft, for the
    # person to check it is meant to be.
    "column_unmapped",
    # The model named a column the header row does not have.
    "header_not_in_template",
    # The header is longer than a layout's column holds (`HEADER_LIMIT`).
    "header_too_long",
    # A draft of the first layout schema named a header printed twice; kept
    # so a draft stored before 2.0 still reads.
    "header_ambiguous",
    # A column was answered twice.
    "header_twice",
    # One field was given to two columns.
    "field_twice",
    # A column was given more than one source.
    "source_invalid",
    # A fixed value that is not the value every filled row of its column
    # holds in the template.
    "constant_not_in_template",
    # A field every upload needs was given no column.
    "required_missing",
    # The proposal is no valid layout (`where`: the path that failed).
    "layout_invalid",
    # The sheet's name cannot name an upload sheet; the version's is kept.
    "sheet_name_invalid",
    # No usable answer: the model is down, answered outside the schema, is not
    # configured on this host, or the plan's day is spent.
    "model_unavailable",
    "model_not_configured",
    "model_quota",
    # A change in words (`rule_words`, ADR 0006): `where` names the path.
    "nothing_understood",
    "path_unknown",
    "type_changed",
    "placeholder_changed",
    "digit_invented",
    "document_invalid",
]


class DraftProblem(BaseModel):
    """Why a draft is not, or not wholly, what the template says. Names a
    field, a cell and that cell's own text: never a word of the model's."""

    model_config = _FROZEN

    code: ProblemCode
    field: UploadField | None = None
    ref: str | None = Field(default=None, max_length=12)
    header: str | None = Field(default=None, max_length=200)
    where: str | None = Field(default=None, max_length=200)


@dataclass(frozen=True, slots=True)
class Proposal:
    """A whole `sales_bravo_upload` document, what in it the machine filled
    (document paths, ``columns.0.header``), where each was read, and the
    problems the person is told about."""

    document: dict[str, Any]
    machine_read: tuple[str, ...]
    evidence: Mapping[str, str]
    problems: tuple[DraftProblem, ...] = ()


@dataclass(frozen=True, slots=True)
class Refused:
    problems: tuple[DraftProblem, ...]


def _base(layout: BravoUploadLayout) -> dict[str, Any]:
    return layout.model_dump(mode="json", by_alias=True)


def _source(entry: ModelColumnSource) -> dict[str, str]:
    """The sources an answer gives one column, an empty text read as none."""
    given = {
        "field": entry.field,
        "customer": entry.customer,
        "constant": plain(entry.constant) if entry.constant is not None else None,
    }
    return {kind: value for kind, value in given.items() if value}


def _sources(
    answer: ModelBravoMapping, row: TemplateRow, repeated: Mapping[int, TemplateHeader]
) -> tuple[dict[int, dict[str, str]], list[DraftProblem]]:
    """Each named column's one source, by column number, and what is wrong
    with the answer column by column."""
    cells = {_letters(h.ref): h for h in row.headers}
    answered = Counter(entry.column for entry in answer.columns)
    problems: list[DraftProblem] = []
    chosen: dict[int, dict[str, str]] = {}
    for entry in answer.columns:
        source, cell = _source(entry), cells.get(entry.column)
        if cell is None:
            if source:
                problems.append(
                    DraftProblem(code="header_not_in_template", field=entry.field, ref=entry.column)
                )
            continue
        if answered[entry.column] > 1:
            problems.append(DraftProblem(code="header_twice", field=entry.field, ref=cell.ref))
        elif len(source) > 1:
            problems.append(DraftProblem(code="source_invalid", field=entry.field, ref=cell.ref))
        elif "constant" in source and (
            (fixed := repeated.get(cell.column)) is None or plain(fixed.text) != source["constant"]
        ):
            problems.append(DraftProblem(code="constant_not_in_template", ref=cell.ref))
        elif source:
            chosen[cell.column] = source
    fields = Counter(s["field"] for s in chosen.values() if "field" in s)
    problems += [
        DraftProblem.model_validate({"code": "field_twice", "field": name})
        for name, count in fields.items()
        if count > 1
    ]
    named = set(fields)
    problems += [
        DraftProblem(code="required_missing", field=name)
        for name in UPLOAD_FIELDS
        if name in REQUIRED_UPLOAD_FIELDS and name not in named
    ]
    if not named & UPLOAD_ITEM_FIELDS:
        problems.append(DraftProblem(code="required_missing", field="customer_item_code"))
    problems += [
        DraftProblem(code="header_too_long", ref=h.ref)
        for h in row.headers
        if len(plain(h.text)) > HEADER_LIMIT
    ]
    return chosen, list(dict.fromkeys(problems))


def _banner(row: TemplateRow, width: int) -> list[list[dict[str, Any]]]:
    """The rows above the header row, each text merged up to the next one."""
    banner: list[list[dict[str, Any]]] = []
    for cells in row.above:
        ends = [c.column - 1 for c in cells[1:]] + [width] if cells else []
        banner.append(
            [
                {"text": plain(c.text)[:HEADER_LIMIT], "first": c.column, "last": end}
                for c, end in zip(cells, ends, strict=True)
            ]
        )
    return banner


def _formats(base: BravoUploadLayout) -> dict[tuple[str, str], str]:
    """The version in force's number format for each source that has one."""
    found: dict[tuple[str, str], str] = {}
    for column in base.columns:
        if column.number_format is None:
            continue
        if column.field is not None:
            found[("field", column.field)] = column.number_format
        elif column.customer is not None:
            found[("customer", column.customer)] = column.number_format
    return found


def verify(
    answer: ModelBravoMapping,
    row: TemplateRow,
    base: BravoUploadLayout,
    repeated: Mapping[int, TemplateHeader],
) -> Proposal | Refused:
    """The model's mapping as a layout code accepts, or refused (module
    docstring)."""
    chosen, problems = _sources(answer, row, repeated)
    if problems:
        return Refused(tuple(problems))
    by_column = {h.column: h for h in row.headers}
    width = max(by_column)
    formats = _formats(base)
    columns: list[dict[str, Any]] = []
    evidence = {"sheet_name": row.span}
    for number in range(1, width + 1):
        cell, source = by_column.get(number), chosen.get(number, {})
        column: dict[str, Any] = {"header": plain(cell.text) if cell else "", **source}
        for kind, value in source.items():
            if (number_format := formats.get((kind, value))) is not None:
                column["number_format"] = number_format
        index = len(columns)
        if cell is not None:
            evidence[f"columns.{index}.header"] = row.at(cell)
        for kind in source:
            cited = repeated[number] if kind == "constant" else cell
            assert cited is not None  # a source is only given to a header cell
            evidence[f"columns.{index}.{kind}"] = row.at(cited)
        columns.append(column)
    banner = _banner(row, width)
    for r, cells in enumerate(row.above):
        for k, cell in enumerate(cells):
            evidence[f"banner.{r}.{k}.text"] = row.at(cell)
    document = {
        **_base(base),
        # The company's own template, not the platform's placeholder.
        "schema_version": "2.0",
        "mock": False,
        "description": "",
        "sheet_name": row.sheet,
        "banner": banner,
        "columns": columns,
    }
    try:
        BravoUploadLayout.model_validate(document)
    except ValidationError as invalid:
        return Refused(
            tuple(
                DraftProblem(code="layout_invalid", where=".".join(str(p) for p in e["loc"])[:200])
                for e in invalid.errors()[:20]
            )
        )
    return Proposal(
        document=document,
        machine_read=tuple(evidence),
        evidence=evidence,
        problems=tuple(
            DraftProblem(code="column_unmapped", ref=h.ref, header=h.text[:200])
            for h in row.headers
            if h.column not in chosen
        ),
    )


def offered(row: TemplateRow, base: BravoUploadLayout) -> Proposal:
    """What a person starts from when no mapping was accepted: the version
    in force with only the sheet the template names, a fact code read. The
    columns are not guessed; the template's headers are offered as choices."""
    document = {**_base(base), "description": "", "sheet_name": row.sheet}
    try:
        BravoUploadLayout.model_validate(document)
    except ValidationError:
        return Proposal(
            document={**_base(base), "description": ""},
            machine_read=(),
            evidence={},
            problems=(DraftProblem(code="sheet_name_invalid", where="sheet_name"),),
        )
    return Proposal(
        document=document, machine_read=("sheet_name",), evidence={"sheet_name": row.span}
    )
