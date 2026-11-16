"""A customer's SalesOrder filled with the customer's skill and read-only
tools, every cell traced by code (ticket 41). The pairs are ticket 38's
synthetic ones, read the normal way and kept as worked pairs; the skills and
the attacks are `evals/fixtures/cases/sales_salesorder_skill.json`'s. No
customer's data."""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import ModelUnavailableError, estimated_tokens
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_sales.application.salesorder_fill import (
    PROMPT_TOKENS,
    ROWS_PER_CALL,
    SALESORDER_FILL,
    FillSkill,
    PoRow,
    SalesOrderTools,
    check_against,
    po_rows,
    prepared_calls,
    skill_constants,
    trace,
)
from dw_sales.application.salesorder_learning import WorkedPair
from dw_sales.application.salesorder_rules import column_letter
from dw_sales.evals.graders import GIANG
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.salesorder_rules import Bench, load_cases, pair
from dw_sales.evals.salesorder_skill import (
    _gold,
    _with_cell,
    fill,
    kept_pair,
    load_skill_cases,
    skill_of,
    spec_like,
    tools_for,
)
from dw_sales.evals.world import ALPHA, BETA

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
PAIRS = load_cases(REPO)
CASES = load_skill_cases(REPO)


def _bench() -> Bench:
    return Bench.of(REPO, None, (GIANG,))


async def _pair(pair_id: str) -> tuple[Bench, WorkedPair, SalesOrderTools, dict[str, Any]]:
    spec = pair(PAIRS, pair_id)
    bench = _bench()
    worked = await kept_pair(bench, spec)
    tools = tools_for(bench, spec["customer"])
    return bench, worked, tools, _gold(bench, tools, worked, spec)


async def _filled(pair_id: str, answer: dict[str, Any], skill: FillSkill | None = None) -> Any:
    bench, worked, tools, _ = await _pair(pair_id)
    customer = pair(PAIRS, pair_id)["customer"]
    model = Recorded(raw=answer)
    traced = await fill(model, bench.layout, tools, worked, skill or skill_of(CASES, customer))
    return bench, worked, traced, model


def _cell(traced: Any, row: int, column: str) -> Any:
    return next(c for r in traced.rows if r.row == row for c in r.cells if c.column == column)


# ------------------------------------------------------------- the tools --


def test_a_tool_never_answers_with_another_customers_convert_rows_or_items() -> None:
    """Acceptance 4, at the tool: KHA and KHB both print ``B24-R``, each for
    its own item; bound to KHA, the tool answers KHA's row, and no item only
    KHB's list reaches, whatever it is asked."""
    bench = _bench()
    kha, khb = tools_for(bench, "KHA"), tools_for(bench, "KHB")
    assert kha.answer("convert", "B24-R") == {"prv_code": "PRV-C22-WH"}
    assert khb.answer("convert", "B24-R") == {"prv_code": "PRV-B24-RD"}
    assert kha.answer("convert", "B24-K") is None
    assert kha.answer("item", "PRV-B24-RD") is None
    assert kha.answer("item", "PRV-B24-BK") is None
    assert set(kha.items) == {"PRV-C22-WH"}
    assert kha.answer("customer", None) is not None
    assert kha.answer("customer", None)["code"] == "KHA"  # type: ignore[index]


async def test_code_calls_every_look_up_the_po_leads_to_before_the_turn() -> None:
    _, worked, tools, _ = await _pair("SR02")
    rows = po_rows(worked.document, tools, worked.received_on)
    calls = prepared_calls(tools, rows)
    assert [(c.call, c.tool, c.input) for c in calls] == [
        ("c1", "customer", None),
        ("c2", "convert", "B24-K"),
        ("c3", "item", "PRV-B24-BK"),
        ("c4", "convert", "B24-R"),
        ("c5", "item", "PRV-B24-RD"),
    ]
    assert calls[4].result is not None and calls[4].result["colour"] == "red"


# ------------------------------------------------------------ the golden --


@pytest.mark.parametrize("pair_id", ["SR01", "SR02", "SR03"])
async def test_a_pairs_po_filled_from_its_skill_comes_out_as_the_pics_file(pair_id: str) -> None:
    """Every cell traced and the same as the PIC's: copies at their anchor,
    look-ups made again, computations redone, the skill's constants."""
    _, worked, _, gold = await _pair(pair_id)
    bench, worked, traced, model = await _filled(pair_id, gold)
    assert traced.flags == []
    check = check_against(bench.layout, traced, worked.expected)
    assert check.reproduced, check.differing
    assert check.cells_compared > 0
    # One call (two rows), the versioned prompt, the skill's words in it.
    ((prompt, run, inputs),) = model.calls
    assert prompt == SALESORDER_FILL
    assert run.tenant_id == ALPHA.tenant_id.value
    assert set(inputs) == {"skill", "columns", "po_rows", "calls"}
    assert inputs["skill"] == CASES["skills"][pair(PAIRS, pair_id)["customer"]]


async def test_what_is_written_is_codes_value_never_the_models_text() -> None:
    """KHB's quantity in metres: the model writes "1220.000"; code writes the
    number it computed, which the comparison holds equal to it."""
    _, _, _, gold = await _pair("SR02")
    for cell in gold["rows"][0]["cells"]:
        if cell["column"] == "AA":
            cell["value"] = "1220.000"
    _, _, traced, _ = await _filled("SR02", gold)
    written = _cell(traced, 1, "AA")
    assert (written.source, written.flag) == ("computation", None)
    assert isinstance(written.value, Decimal) and written.value == Decimal(1220)


# ----------------------------------------------------------- acceptance 2 --


@pytest.mark.parametrize(
    "attack", CASES["injection"]["attacks"], ids=[a["name"] for a in CASES["injection"]["attacks"]]
)
async def test_an_injected_instruction_obeyed_is_flagged_never_written(
    attack: dict[str, Any],
) -> None:
    """A PO line asks for a price of 0 and another customer's code; every
    answer that obeys it names a source code cannot trace."""
    _, _, _, gold = await _pair("SR01")
    _, _, traced, _ = await _filled("SR01", _with_cell(gold, attack["row"], attack["cell"]))
    cell = _cell(traced, attack["row"], attack["cell"]["column"])
    assert (cell.flag, cell.value) == (attack["flag"], None)
    # Everything else still traced and written.
    assert {(f.row, f.column) for f in traced.flags} == {(attack["row"], cell.column)}


@pytest.mark.parametrize(
    "attack", CASES["missing"]["attacks"], ids=[a["name"] for a in CASES["missing"]["attacks"]]
)
async def test_a_cell_with_no_evidence_is_flagged_never_written(attack: dict[str, Any]) -> None:
    _, _, _, gold = await _pair("SR02")
    _, _, traced, _ = await _filled("SR02", _with_cell(gold, attack["row"], attack["cell"]))
    cell = _cell(traced, attack["row"], attack["cell"]["column"])
    assert (cell.flag, cell.value) == (attack["flag"], None)


async def test_a_price_is_only_the_pos_own() -> None:
    """dw_sales ADR 0008: a price column takes the PO's price, as read or
    through a computation that reads it; a computation from another value is
    flagged even where it gives the same number."""
    _, _, _, gold = await _pair("SR01")
    # 500 x 0.85 = 425; row 1's price from its quantity alone is refused.
    cell = {
        "column": "AE",
        "value": "0.85",
        "source": {
            "kind": "computation",
            "start": {"kind": "po", "anchor": "R1.row_no"},
            "steps": [{"step": "multiply", "source": "usd_rate"}],
        },
    }
    _, _, traced, _ = await _filled("SR01", _with_cell(gold, 1, cell))
    assert _cell(traced, 1, "AE").flag == "price_not_from_po"


async def test_a_column_named_twice_writes_neither() -> None:
    _, _, _, gold = await _pair("SR01")
    gold["rows"][0]["cells"].append({"column": "W", "value": "HK", "source": {"kind": "constant"}})
    _, _, traced, _ = await _filled("SR01", gold)
    assert (_cell(traced, 1, "W").flag, _cell(traced, 1, "W").value) == ("cell_repeated", None)


async def test_an_answer_for_a_row_or_column_the_file_lacks_is_never_written() -> None:
    _, _, _, gold = await _pair("SR01")
    gold["rows"].append(
        {"row": 9, "cells": [{"column": "A", "value": "9", "source": {"kind": "constant"}}]}
    )
    bench, worked, traced, _ = await _filled("SR01", gold)
    assert [r.row for r in traced.rows] == [1, 2]
    assert len(traced.rows[0].cells) == len(bench.layout.columns)
    assert check_against(bench.layout, traced, worked.expected).reproduced


# -------------------------------------------------------- the constants --


def test_a_constant_is_one_the_skills_constants_section_names() -> None:
    words = (
        "Write `HK` in W.\n\n## Constants\n\n- `8001`: the staff code.\n- `CA`\n\n"
        "## Worked pairs\n\nV is `A-1001`.\n"
    )
    assert skill_constants(words) == frozenset({"8001", "CA"})
    assert skill_constants("No section, `HK` named.") == frozenset()


async def test_a_constant_the_skill_names_only_outside_its_section_is_flagged() -> None:
    _, _, _, gold = await _pair("SR01")
    words = CASES["skills"]["KHA"].replace("- `HK`: KHA's group code, in W on every row.\n", "")
    words += "\nW is always `HK`.\n"
    _, _, traced, _ = await _filled(
        "SR01", gold, FillSkill("sales_skill_salesorder_kha@1.1.0", words)
    )
    assert {(f.row, f.column, f.reason) for f in traced.flags} == {
        (1, "W", "constant_not_in_skill"),
        (2, "W", "constant_not_in_skill"),
    }


# ----------------------------------------------------------- acceptance 1 --


async def test_a_line_shape_no_pair_showed_is_filled_where_traced_or_flagged() -> None:
    """A KHB PO with a line in metres and a code its convert list lacks: a
    PRV code for that code is never written, from a guess or a call made for
    another row."""
    unseen = CASES["unseen"]
    spec = spec_like(pair(PAIRS, unseen["form_of"]), unseen)
    spec["file"] = {"common": {}, "rows": [{"A": 1}, {"A": 2}]}
    bench = _bench()
    worked = await kept_pair(bench, spec)
    tools = tools_for(bench, "KHB")
    answer = {
        "rows": [
            {
                "row": 1,
                "cells": [
                    {
                        "column": "T",
                        "value": "PRV-B24-BK",
                        "source": {"kind": "tool", "call": "c2", "key": "prv_code"},
                    },
                    {
                        "column": "AA",
                        "value": "1830",
                        "source": {"kind": "po", "anchor": "R1.quantity"},
                    },
                ],
            },
            {
                "row": 2,
                "cells": [
                    {
                        "column": "T",
                        "value": "PRV-B24-BK",
                        "source": {"kind": "tool", "call": "c2", "key": "prv_code"},
                    },
                    {"column": "V", "value": "yellow"},
                ],
            },
        ]
    }
    traced = await fill(Recorded(raw=answer), bench.layout, tools, worked, skill_of(CASES, "KHB"))
    assert (_cell(traced, 1, "T").value, _cell(traced, 1, "T").flag) == ("PRV-B24-BK", None)
    assert _cell(traced, 1, "AA").flag is None
    assert (_cell(traced, 2, "T").value, _cell(traced, 2, "T").flag) == (None, "call_other_row")
    assert (_cell(traced, 2, "V").value, _cell(traced, 2, "V").flag) == (None, "source_missing")
    # A column the layout fills that the answer left empty is the PIC's, flagged.
    assert _cell(traced, 2, "AA").flag == "not_filled"


# ------------------------------------------------------------- the turn --


async def test_no_usable_answer_is_the_fallbacks_never_a_guess() -> None:
    bench, worked, tools, _ = await _pair("SR01")
    with pytest.raises(ModelUnavailableError):
        await fill(
            Recorded(failure=ModelUnavailableError("down")),
            bench.layout,
            tools,
            worked,
            skill_of(CASES, "KHA"),
        )
    # An answer outside the schema (a step outside the closed set) is none.
    bad = {
        "rows": [
            {"row": 1, "cells": [{"column": "W", "value": "HK", "source": {"kind": "formula"}}]}
        ]
    }
    with pytest.raises(ModelUnavailableError):
        await fill(Recorded(raw=bad), bench.layout, tools, worked, skill_of(CASES, "KHA"))


async def test_a_long_po_is_filled_a_few_rows_a_call() -> None:
    bench, worked, tools, _ = await _pair("SR01")
    rows = po_rows(worked.document, tools, worked.received_on)
    many = [PoRow(n, {**rows[0].values, "row_no": n}) for n in range(1, ROWS_PER_CALL * 2 + 2)]
    model = Recorded(raw={"rows": []})
    from dw_sales.application.salesorder_fill import SalesOrderFiller
    from dw_sales.evals.salesorder_skill import _run_context

    traced = await SalesOrderFiller(model).fill(
        layout=bench.layout,
        rows=many,
        tools=tools,
        skill=skill_of(CASES, "KHA"),
        run=_run_context(),
    )
    assert len(model.calls) == 3
    assert len(traced.rows) == len(many)


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        SALESORDER_FILL.prompt_id,
        SALESORDER_FILL.version,
        {"skill": "", "columns": "[]", "po_rows": "[]", "calls": "[]"},
        tenant_id=uuid.uuid4(),
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS
    for kind in ("po", "tool", "constant", "computation"):
        assert f'"kind": "{kind}"' in rendered.system
    for step in ("unit_factor", "shift_days", "round", "cut", "concat", "multiply"):
        assert f'"step": "{step}"' in rendered.system


def test_the_generic_skill_ships_no_constant_and_fits() -> None:
    from dw_sales.adapters.skill_files import load_salesorder_skill

    generic = load_salesorder_skill(REPO / "configs" / "skills" / "dw1-salesorder")
    assert generic.ref == "sales_skill_salesorder@1.0.0"
    assert skill_constants(generic.instructions) == frozenset()


# ---------------------------------------------------------- the trace alone --


async def test_a_trace_with_no_answer_flags_every_column_the_layout_fills() -> None:
    bench, worked, tools, _ = await _pair("SR01")
    rows = po_rows(worked.document, tools, worked.received_on)
    traced = trace(bench.layout, rows, prepared_calls(tools, rows), tools, "", [])
    filled = {
        column_letter(i)
        for i, c in enumerate(bench.layout.columns)
        if not c.blank and c.field not in ("first_confirmed_date", "confirmed_date")
    }
    assert {c.column for c in traced[0].cells if c.flag == "not_filled"} == filled
    assert all(c.value is None for c in traced[0].cells)


async def test_a_pair_is_its_workspaces_only() -> None:
    bench = _bench()
    await kept_pair(bench, pair(PAIRS, "SR01"))
    assert bench.store.state(BETA).pairs == []
    assert [p.customer_code for p in bench.store.state(ALPHA).pairs] == ["KHA"]
