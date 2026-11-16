"""A case's Bravo upload file filled with its customer's SalesOrder skill
where the step runs, its learned rules otherwise (ticket 41, the gate and the
fallback). Drawn as `test_artifacts` draws it, over the fictional mock."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook

from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_kernel.errors import ConflictError
from dw_kernel.ports import Uuid4Generator
from dw_sales.adapters.memory_rules import MemoryRuleVersions
from dw_sales.adapters.mock.catalog import MockSalesCatalog
from dw_sales.adapters.skill_files import load_dw1_skills, skills_book
from dw_sales.application.artifacts_service import ArtifactService
from dw_sales.application.local_time import local_day
from dw_sales.application.ports import SalesScope
from dw_sales.application.salesorder_case_fill import CaseSalesOrderFill, case_rows
from dw_sales.application.salesorder_fill import SalesOrderFiller, SalesOrderTools, prepared_calls
from dw_sales.application.salesorder_rules import column_letter
from dw_sales.domain.order_checks import ModelStep, OrderRules
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.salesorder_skill import gold_answer

from .test_artifacts import (
    _INTAKE_RULES,
    AN,
    ARTIFACT_COPY,
    BOOK,
    SCOPE,
    World,
    _prepared_m01,
    context,
    in_review,
    render,
    service,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


@dataclass
class _Gate:
    """`ModelStepGatePort`: the step runs where ``on`` says so; every ask
    recorded."""

    on: bool
    asked: list[ModelStep] = field(default_factory=list)

    async def allows(self, scope: SalesScope, rules: OrderRules, step: ModelStep) -> bool:
        self.asked.append(step)
        return self.on


def _filling(model: Any, gate: _Gate) -> CaseSalesOrderFill:
    stored = MemoryRuleVersions()
    return CaseSalesOrderFill(
        rules=_INTAKE_RULES,
        gate=gate,
        copy=BOOK,
        catalog=MockSalesCatalog.load(SCOPE),
        book=skills_book(
            REPO / "configs" / "skills",
            load_dw1_skills(REPO / "configs" / "skills" / "dw1"),
            stored,
        ),
        filler=SalesOrderFiller(model),
        ids=Uuid4Generator(),
        worker_id="sales-dw1",
        worker_version="1.0.0",
    )


def _with(world: World, filling: CaseSalesOrderFill) -> ArtifactService:
    return replace(service(world), salesorder_skill=filling)


def _sheets(world: World, view_id: Any) -> tuple[list[list[Any]], list[list[Any]]]:
    record = world.artifacts[(SCOPE, view_id)]
    book = load_workbook(io.BytesIO(world.objects[record.object_key(SCOPE)]))
    upload, about = book.worksheets[0], book.worksheets[1]
    return (
        [[c.value for c in row] for row in upload.iter_rows()],
        [[c.value for c in row] for row in about.iter_rows()],
    )


async def _rules_file(case: OrderCase) -> list[list[Any]]:
    world = World()
    (view,) = await render(world, case, "bravo_upload")
    return _sheets(world, view.artifact_id)[0]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


async def _answer(case: OrderCase, drawn: list[list[Any]]) -> dict[str, Any]:
    """What a person filling from the skill would answer: every cell of the
    file the rules draw, with its source in the layout."""
    layout = ARTIFACT_COPY.upload
    expected = [
        {column_letter(i): _text(v) for i, v in enumerate(row)}
        for row in drawn[len(layout.banner) + 1 :]
    ]
    catalog = MockSalesCatalog.load(SCOPE)
    customer = (await catalog.customer_by_code(SCOPE, case.customer_code)).data
    assert customer is not None
    tools = SalesOrderTools.bound(
        customer, (await catalog.convert_list(SCOPE)).data, (await catalog.items(SCOPE)).data
    )
    rows = case_rows(case, local_day(case.received_at, ARTIFACT_COPY.zone))
    return gold_answer(layout, rows, prepared_calls(tools, rows), None, expected)


async def test_off_the_rules_fill_the_file_and_no_model_is_asked() -> None:
    """The step's switch off (or below its bar): the gate is asked, the model
    never, and the file is the one the rules draw."""
    case = await _prepared_m01()
    gate = _Gate(on=False)
    model = Recorded(raw={"rows": []})
    world = World()
    world.put(case)
    (view,) = await _with(world, _filling(model, gate)).render_order(
        context(), case.case_id, kind="bravo_upload", case_version=case.case_version
    )
    assert gate.asked == [ModelStep.SALESORDER_SKILL]
    assert model.calls == []
    assert _sheets(world, view.artifact_id)[0] == await _rules_file(case)


async def test_on_the_skill_fills_the_file_cell_by_cell_traced() -> None:
    """The step on: the file is the skill's fill, every cell traced; the same
    file as the rules' where the skill says the same, stamped with the skill
    and the prompt it was filled with."""
    case = await _prepared_m01()
    drawn = await _rules_file(case)
    model = Recorded(raw=await _answer(case, drawn))
    world = World()
    world.put(case)
    (view,) = await _with(world, _filling(model, _Gate(on=True))).render_order(
        context(), case.case_id, kind="bravo_upload", case_version=case.case_version
    )
    upload, about = _sheets(world, view.artifact_id)
    assert upload == drawn
    assert len(model.calls) == 1
    assert model.calls[0][1].actor_id == AN
    assert "sales.salesorder_fill@1.0.0" in json.dumps(about, default=str)


async def test_an_injected_price_is_left_blank_and_listed_for_the_pic() -> None:
    """Acceptance 2 on a case's file: an answer writing a price of 0 is
    flagged; the cell stays blank in the file, and the file says why."""
    case = await _prepared_m01()
    drawn = await _rules_file(case)
    answer = await _answer(case, drawn)
    layout = ARTIFACT_COPY.upload
    price = next(column_letter(i) for i, c in enumerate(layout.columns) if c.field == "unit_price")
    for row in answer["rows"]:
        for cell in row["cells"]:
            if cell["column"] == price:
                cell.update(value="0", source={"kind": "constant"})
    world = World()
    world.put(case)
    (view,) = await _with(world, _filling(Recorded(raw=answer), _Gate(on=True))).render_order(
        context(), case.case_id, kind="bravo_upload", case_version=case.case_version
    )
    upload, about = _sheets(world, view.artifact_id)
    header = len(layout.banner) + 1
    index = next(i for i, c in enumerate(layout.columns) if c.field == "unit_price")
    assert all(row[index] is None for row in upload[header:])
    assert all(row[index] not in (None, 0) for row in drawn[header:])
    assert f"{price}1: giá không lấy từ PO" in json.dumps(about, ensure_ascii=False, default=str)


async def test_no_usable_answer_falls_back_to_the_rules() -> None:
    case = await _prepared_m01()
    world = World()
    world.put(case)
    down = Recorded(failure=ModelUnavailableError("down"))
    (view,) = await _with(world, _filling(down, _Gate(on=True))).render_order(
        context(), case.case_id, kind="bravo_upload", case_version=case.case_version
    )
    assert _sheets(world, view.artifact_id)[0] == await _rules_file(case)


async def test_no_model_is_asked_for_a_file_the_draw_refuses() -> None:
    """A case not yet prepared cannot draw its upload file: the fill is not
    asked either, so a caller cannot spend the model on a refused draw."""
    case = await in_review("M01")
    gate = _Gate(on=True)
    model = Recorded(raw={"rows": []})
    world = World()
    world.put(case)
    with pytest.raises(ConflictError):
        await _with(world, _filling(model, gate)).render_order(
            context(), case.case_id, kind="bravo_upload", case_version=case.case_version
        )
    assert (gate.asked, model.calls) == ([], [])
