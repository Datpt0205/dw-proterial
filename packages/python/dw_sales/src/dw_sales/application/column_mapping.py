"""A master-data file of any column layout, its columns matched by the model
(the AI list, item 2; ticket 41).

An import is read by header: each column of the list's template has its
header and aliases (`master_data.Column`), and a file whose header row is not
the first one, or names a column some other way ("Tên KH" for the
customer's name, a Japanese header, a merged title row above), was refused
("thiếu cột ..."), and someone retyped it into the template. Now the worker,
where the file is read (`CatalogParsing`), asks the model which row is the
header and which of its cells is which of the list's columns, as the
importer (one call through the one-call door, their plan's allowance).

- **Code checks** the answer: the header row is one of the rows shown; each
  header named is that row's cell, as written; no column and no cell is
  named twice; every required column is named. Anything else and the file
  is refused as before.
- **Code reads** the file through the match exactly as through a template
  (`master_data.parse_rows`): every row validated, every reference checked,
  nothing the model said about a value.
- **The head still approves**, and sees the match: the snapshot keeps which
  of the file's headers was read as which column (`column_map`), shown on
  the import's preview, marked as the machine's.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import QuotaExceededError
from dw_sales.application.model_reading import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_sales.domain.master_data import SPECS, CatalogList, ImportedTable, TableRow

# The prompt the columns are matched with. Its file is
# `configs/prompts/sales/catalog_columns@1.0.0.yaml`; a test holds the two
# together, and the rendered prompt under `PROMPT_TOKENS`.
CATALOG_COLUMNS: Final = PromptRef("sales.catalog_columns", "1.0.0")
PROMPT_TOKENS: Final = 900
_OUTPUT_TOKENS: Final = 600
# The rows the model is shown: the header is among the first of them.
SHOWN_ROWS: Final = 8
_CELL_CHARS: Final = 60

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ModelColumn(BaseModel):
    model_config = _FROZEN

    path: str = Field(min_length=1, max_length=60)
    header: str = Field(min_length=1, max_length=200)


class ModelColumnMap(BaseModel):
    """What the model answers: the header row, and which of its cells is
    which of the list's columns."""

    model_config = _FROZEN

    header_row: int = Field(ge=1)
    columns: list[ModelColumn] = Field(min_length=1, max_length=40)


def _cell(value: object) -> str:
    return "" if value is None else str(value).strip()


def remapped(
    catalog_list: CatalogList, table: ImportedTable, answer: ModelColumnMap
) -> tuple[ImportedTable, tuple[tuple[str, str], ...]] | None:
    """The table as its template would have it (the header row the list's
    own headers, every row above it dropped), and which of the file's headers
    each column was read from; None when the answer does not hold."""
    spec = SPECS[catalog_list]
    shown = table.rows[:SHOWN_ROWS]
    header = next((r for r in shown if r.row == answer.header_row), None)
    if header is None:
        return None
    texts = [_cell(c) for c in header.cells]
    known = {c.path: c for c in spec.columns}
    positions: dict[int, str] = {}
    paths: set[str] = set()
    for column in answer.columns:
        if column.path not in known or column.path in paths:
            return None
        where = [i for i, text in enumerate(texts) if text == column.header.strip()]
        if len(where) != 1 or where[0] in positions:
            return None
        positions[where[0]] = column.path
        paths.add(column.path)
    if any(c.required and c.path not in paths for c in spec.columns):
        return None
    width = max(len(header.cells), *(len(r.cells) for r in table.rows))
    canonical = TableRow(
        row=header.row,
        cells=[known[positions[i]].header if i in positions else None for i in range(width)],
    )
    body = [
        TableRow(
            row=r.row,
            cells=[c if i in positions else None for i, c in enumerate(r.cells)],
        )
        for r in table.rows
        if r.row > header.row
    ]
    matched = tuple((known[path].header, texts[i]) for i, path in sorted(positions.items()))
    return (
        ImportedTable(sheet=table.sheet, rows=[canonical, *body], truncated=table.truncated),
        matched,
    )


def _facts(catalog_list: CatalogList, table: ImportedTable) -> tuple[str, str]:
    spec = SPECS[catalog_list]
    columns = [
        {"path": c.path, "header": c.header, "meaning": c.hint, "required": c.required}
        for c in spec.columns
    ]
    rows = [
        {"row": r.row, "cells": [_cell(c)[:_CELL_CHARS] for c in r.cells]}
        for r in table.rows[:SHOWN_ROWS]
    ]
    return (
        json.dumps(columns, ensure_ascii=False, indent=1),
        json.dumps(rows, ensure_ascii=False, indent=1),
    )


@dataclass(frozen=True)
class ColumnMatcher:
    """Matches a file's columns to a list's (module docstring)."""

    model: InterpretationPort

    async def match(
        self, catalog_list: CatalogList, table: ImportedTable, *, run: RunContext
    ) -> tuple[ImportedTable, tuple[tuple[str, str], ...]] | None:
        columns, rows = _facts(catalog_list, table)
        if estimated_tokens(columns + rows) > self.model.max_input_tokens - PROMPT_TOKENS:
            return None
        try:
            answer = await self.model.interpret(
                CATALOG_COLUMNS,
                {"columns": columns, "rows": rows},
                ModelColumnMap,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return None
        return remapped(catalog_list, table, answer)
