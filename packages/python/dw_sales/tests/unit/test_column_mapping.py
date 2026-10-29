"""A master-data file in its own layout, its columns matched by the model
(the AI list, item 2): what code accepts of the match, and that the file is
then read and checked as a template is."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook

from dw_sales.application.column_mapping import (
    CATALOG_COLUMNS,
    PROMPT_TOKENS,
    ModelColumnMap,
    remapped,
)
from dw_sales.application.model_reading import ModelUnavailableError, estimated_tokens
from dw_sales.domain.master_data import SPECS, CatalogList, ImportedTable, TableRow
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
LME = CatalogList.LME
TITLE = "Bảng giá đồng LME theo tháng (nội bộ)"


def _their(header: str) -> str:
    """How the company's own file names a column: not a template header."""
    return f"[{header}]"


async def _lme_file(world: World) -> bytes:
    """The sample's LME months, in the company's layout: a title, a blank
    row, then its own headers."""
    spec = SPECS[LME]
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append([TITLE])
    sheet.append([])
    sheet.append([_their(c.header) for c in spec.columns])
    for month in (await world.catalog.lme_months(ALPHA)).data:
        cells = spec.cells(month.model_dump(mode="json"))  # type: ignore[attr-defined]
        sheet.append([cells.get(c.header) or None for c in spec.columns])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


class Matching(Recorded):
    """Answers the match a careful reader gives: the third row, each column
    by its own header."""

    def __init__(self, answer: dict[str, Any] | None = None) -> None:
        super().__init__(raw={})
        self.answer = answer

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        if self.answer is not None:
            return schema.model_validate(self.answer)
        rows = json.loads(inputs["rows"])
        header = next(r for r in rows if r["cells"] and r["cells"][0].startswith("["))
        columns = [
            {"path": c["path"], "header": _their(c["header"])}
            for c in json.loads(inputs["columns"])
        ]
        return schema.model_validate({"header_row": header["row"], "columns": columns})


def _table(rows: list[list[Any]]) -> ImportedTable:
    return ImportedTable(
        sheet="Sheet",
        rows=[TableRow(row=i, cells=cells) for i, cells in enumerate(rows, start=1) if cells],
    )


def _answer(**change: Any) -> ModelColumnMap:
    spec = SPECS[LME]
    base = {
        "header_row": 3,
        "columns": [{"path": c.path, "header": _their(c.header)} for c in spec.columns],
    }
    return ModelColumnMap.model_validate({**base, **change})


def _header_rows() -> ImportedTable:
    spec = SPECS[LME]
    return _table([[TITLE], [], [_their(c.header) for c in spec.columns]])


def test_a_match_becomes_the_templates_header_with_the_rows_below_it() -> None:
    found = remapped(LME, _header_rows(), _answer())
    assert found is not None
    table, matched = found
    assert table.rows[0].cells == [c.header for c in SPECS[LME].columns]
    assert matched == tuple((c.header, _their(c.header)) for c in SPECS[LME].columns)


@pytest.mark.parametrize("header_row", [1, 99])
def test_a_header_row_that_is_not_the_header_or_not_shown_is_refused(header_row: int) -> None:
    assert remapped(LME, _header_rows(), _answer(header_row=header_row)) is None


def test_a_match_naming_nothing_is_no_answer() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _answer(columns=[])


def test_a_header_the_row_lacks_or_a_column_named_twice_or_a_required_one_missing() -> None:
    spec = SPECS[LME]
    first, *rest = [{"path": c.path, "header": _their(c.header)} for c in spec.columns]
    assert (
        remapped(LME, _header_rows(), _answer(columns=[{**first, "header": "Khác"}, *rest])) is None
    )
    assert remapped(LME, _header_rows(), _answer(columns=[first, first, *rest])) is None
    required = next(c.path for c in spec.columns if c.required)
    assert (
        remapped(
            LME,
            _header_rows(),
            _answer(columns=[c for c in [first, *rest] if c["path"] != required]),
        )
        is None
    )


async def _import(world: World, data: bytes) -> Any:
    view = await world.services.catalog_imports.upload(
        AN.context(), LME, "lme-cua-cong-ty.xlsx", data
    )
    await world.read_imports()
    return await world.services.catalog_imports.preview(AN.context(), view.snapshot_id)


async def test_a_file_in_its_own_layout_is_read_through_the_models_match() -> None:
    model = Matching()
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=model, measured=False)
    preview = await _import(world, await _lme_file(world))
    assert preview.snapshot.status == "parsed", preview.snapshot
    assert preview.snapshot.row_count == len((await world.catalog.lme_months(ALPHA)).data)
    assert [tuple(pair) for pair in preview.snapshot.column_map] == [
        (c.header, _their(c.header)) for c in SPECS[LME].columns
    ]
    _, run, _ = model.calls[-1]
    assert (run.tenant_id, run.actor_id) == (ALPHA.tenant_id.value, AN.user_id)


@pytest.mark.parametrize("model", [None, Recorded(failure=ModelUnavailableError("down"))])
async def test_without_a_usable_model_such_a_file_is_refused_as_before(model: Any) -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=model, measured=False)
    preview = await _import(world, await _lme_file(world))
    assert preview.snapshot.status == "failed"
    assert preview.snapshot.error is not None and preview.snapshot.error.startswith("thiếu cột")


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    from dw_agent_runtime.model.prompts import PromptRegistry

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        CATALOG_COLUMNS.prompt_id,
        CATALOG_COLUMNS.version,
        {"columns": "", "rows": ""},
        tenant_id=ALPHA.tenant_id.value,
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS


def _with_note() -> ImportedTable:
    spec = SPECS[LME]
    return _table([[TITLE], [], [*(_their(c.header) for c in spec.columns), "[Ghi chú]"]])


def test_one_cell_read_as_two_columns_is_refused() -> None:
    first, second, *rest = [
        {"path": c.path, "header": _their(c.header)} for c in SPECS[LME].columns
    ]
    same_cell = [first, {**second, "header": first["header"]}, *rest]
    assert remapped(LME, _with_note(), _answer(columns=same_cell)) is None


def test_one_column_read_from_two_cells_is_refused() -> None:
    columns = [{"path": c.path, "header": _their(c.header)} for c in SPECS[LME].columns]
    twice = [*columns, {"path": columns[0]["path"], "header": "[Ghi chú]"}]
    assert remapped(LME, _with_note(), _answer(columns=twice)) is None
    assert remapped(LME, _with_note(), _answer(columns=columns)) is not None
