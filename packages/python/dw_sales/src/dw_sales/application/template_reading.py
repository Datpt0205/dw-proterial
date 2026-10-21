"""A company's Bravo import template, read by code and mapped by a model
("Tạo từ tệp mẫu", phase 1).

The person uploads the Excel template their Bravo imports; DW1 proposes a
`sales_bravo_upload` version from it, which the person reviews and sends
through the rules editor like any other proposal (`rules.SalesRulesService`).
This module is the part that decides, and it decides in code (dw_sales ADR
0005): the model only says which template column holds which upload field.

- **What is read** (`header_row`): the first visible sheet with a row of at
  least `MIN_HEADERS` visible text cells; that row is the template's header
  row, its cells in column order. A hidden sheet, row or column, and a cell
  whose font is the colour of its fill, are dropped before anything else: a
  person reviewing the template cannot see them, so an instruction hidden
  there never reaches the model (`visible`).
- **What the model is asked** (`ModelBravoMapping`, one optional header per
  `UploadField`, built from that list so the two cannot drift): which header
  names which field, copied exactly, or null.
- **What code accepts** (`verify`): every header the model names is exactly
  one visible cell of the header row, no cell is named for two fields, the
  fields every upload needs are named (`REQUIRED_UPLOAD_FIELDS`), the columns
  come in the template's own order, the sheet is the one read, and the whole
  document passes `BravoUploadLayout`. Anything else is refused, with the
  fields named and never a word of the model's.
- **What the person is shown**: each value the machine filled is listed by
  its document path (`machine_read`) with the cell it came from
  (`evidence`, ``Sheet!C1``); template columns no field takes are listed as
  problems, since a layout cannot hold a blank column yet (open).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Final, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from dw_sales.application.artifact_content import (
    REQUIRED_UPLOAD_FIELDS,
    BravoUploadLayout,
    UploadField,
)
from dw_sales.application.model_reading import estimated_tokens
from dw_sales.application.source import SheetCell, SheetGrid

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# A header row has at least this many visible text cells: a title line or a
# note above the table has fewer.
MIN_HEADERS: Final = 4
# How many sheets of a workbook are looked at for a header row.
MAX_SHEETS: Final = 10
# The longest header a layout may hold (`UploadColumn.header`): a longer one is
# sent cut to it, and so never matches the cell it was cut from.
HEADER_LIMIT: Final = 64

UPLOAD_FIELDS: Final[tuple[UploadField, ...]] = get_args(UploadField)


class TemplateHeader(BaseModel):
    """One visible cell of the header row, as the workbook holds it."""

    model_config = _FROZEN

    ref: str = Field(pattern=r"^[A-Z]{1,3}[1-9][0-9]{0,6}$")
    column: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=2000)


class TemplateRow(BaseModel):
    """The template's header row: its sheet, its row number, its cells."""

    model_config = _FROZEN

    sheet: str = Field(min_length=1, max_length=200)
    row: int = Field(ge=1)
    headers: tuple[TemplateHeader, ...] = Field(min_length=MIN_HEADERS)

    def at(self, header: TemplateHeader) -> str:
        """Where a value was read: ``Sheet!C1``."""
        return f"{self.sheet}!{header.ref}"

    @property
    def span(self) -> str:
        """The header row as a range: ``Sheet!A1:H1``."""
        return f"{self.sheet}!{self.headers[0].ref}:{self.headers[-1].ref}"


def visible(cell: SheetCell) -> bool:
    """Whether a person looking at the sheet sees this cell's text."""
    return not (cell.hidden_row or cell.hidden_column or cell.font_matches_fill)


def header_row(grid: SheetGrid) -> TemplateRow | None:
    """The first row of a visible sheet with `MIN_HEADERS` visible text
    cells, or None. Hidden cells are dropped first (module docstring)."""
    if grid.hidden_sheet:
        return None
    rows: dict[int, list[SheetCell]] = {}
    for cell in grid.cells:
        if visible(cell) and cell.text.strip():
            rows.setdefault(cell.row, []).append(cell)
    for number in sorted(rows):
        cells = sorted(rows[number], key=lambda c: c.column)
        if len(cells) >= MIN_HEADERS:
            return TemplateRow(
                sheet=grid.sheet,
                row=number,
                headers=tuple(
                    TemplateHeader(ref=c.ref, column=c.column, text=c.text[:2000]) for c in cells
                ),
            )
    return None


# ------------------------------------------------------------- the model --

_Header = Annotated[str, Field(max_length=200)]

# One optional header per upload field, built from `UploadField` itself: a
# field added there is asked here without a second list to forget.
_ASKED: Final[dict[str, Any]] = dict.fromkeys(UPLOAD_FIELDS, (_Header | None, None))
ModelBravoMapping: Final[type[BaseModel]] = create_model(
    "ModelBravoMapping", __config__=_FROZEN, **_ASKED
)


def _letters(ref: str) -> str:
    return re.sub(r"\d", "", ref)


def mapping_inputs(row: TemplateRow, room: int) -> dict[str, str]:
    """The header row as code-built JSON, each header cut to fit ``room``
    tokens (at most `HEADER_LIMIT` characters, the longest a layout holds)."""
    width = HEADER_LIMIT
    while True:
        headers = json.dumps(
            [{"column": _letters(h.ref), "header": h.text[:width]} for h in row.headers],
            ensure_ascii=False,
        )
        if estimated_tokens(headers) <= room or width <= 16:
            return {"headers": headers}
        width //= 2


# ---------------------------------------------------------- verification --

ProblemCode = Literal[
    # A template column no upload field takes (a layout has no blank column).
    "column_unmapped",
    # The model named a header the header row does not hold, exactly.
    "header_not_in_template",
    # The header the model named is printed on two columns.
    "header_ambiguous",
    # Two fields were given the same column.
    "header_twice",
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


def verify(
    answer: Mapping[str, object], row: TemplateRow, base: BravoUploadLayout
) -> Proposal | Refused:
    """The model's mapping as a layout code accepts, or refused (module
    docstring). An empty header is read as none."""
    problems: list[DraftProblem] = []
    chosen: dict[UploadField, TemplateHeader] = {}
    named: set[UploadField] = set()
    for name in UPLOAD_FIELDS:
        header = answer.get(name)
        if not isinstance(header, str) or not header:
            continue
        named.add(name)
        found = [h for h in row.headers if h.text == header]
        if not found:
            problems.append(DraftProblem(code="header_not_in_template", field=name))
        elif len(found) > 1:
            problems.append(DraftProblem(code="header_ambiguous", field=name))
        else:
            chosen[name] = found[0]
    taken = Counter(cell.ref for cell in chosen.values())
    problems += [
        DraftProblem(code="header_twice", field=name, ref=cell.ref)
        for name, cell in chosen.items()
        if taken[cell.ref] > 1
    ]
    problems += [
        DraftProblem(code="required_missing", field=name)
        for name in UPLOAD_FIELDS
        if name in REQUIRED_UPLOAD_FIELDS and name not in named
    ]
    if problems:
        return Refused(tuple(problems))
    ordered = sorted(chosen.items(), key=lambda item: item[1].column)
    document = {
        **_base(base),
        # The company's own template, not the platform's placeholder.
        "mock": False,
        "description": "",
        "sheet_name": row.sheet,
        "columns": [{"field": name, "header": cell.text} for name, cell in ordered],
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
    evidence = {"sheet_name": row.span}
    for index, (_, cell) in enumerate(ordered):
        evidence[f"columns.{index}.field"] = row.at(cell)
        evidence[f"columns.{index}.header"] = row.at(cell)
    used = {cell.ref for cell in chosen.values()}
    return Proposal(
        document=document,
        machine_read=tuple(evidence),
        evidence=evidence,
        problems=tuple(
            DraftProblem(code="column_unmapped", ref=h.ref, header=h.text[:200])
            for h in row.headers
            if h.ref not in used
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
