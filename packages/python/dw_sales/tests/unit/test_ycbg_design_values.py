"""Ticket 11, first slice: Design's QUOTE read from Bravo's "RFQ List" export
carries what a Design reply line holds, in the one file (Box B16): the spec
number ("Bản vẽ/ Specification"), copper per BP unit ("CU WT: (KG/BP Unit)")
and the BP unit ("Unit BP"), each with the export row it was read from, so
a later step can anchor them in that file (dw_sales ADR 0005 unchanged).

Read, never decided: the case's status stays where ticket 16 leaves it. An
export from before these columns reads as it did. Base price amounts are
not read here: Bravo's price list answers them to price readers only
(`design_prices`).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_sales.application.ycbg_exports import (
    COLUMNS,
    BravoYcbgLine,
    DesignChecks,
    ExportedYcbg,
    parse_export,
)
from dw_sales.domain.master_data import CellValue, ImportedTable, TableRow
from dw_sales.domain.quotes import QuoteStatus
from dw_sales.evals.graders import CALLERS, DIEU
from dw_sales.evals.world import NOW, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
M10_YCBG = "RFQ260930-030"
M10_WORDS = "MULTI-CORE CABLE 4C AWG22 STRANDED TINNED CU BRAID SHIELD GREY REEL 300M SPEC SP-5406"
SHA = "b" * 64
_BASE = ("ycbg_no", "line_no", "status", "design_check", "reason", "bp_code", "description")
_DESIGN = ("spec_no", "copper_kg_per_bp_unit", "bp_unit")
# Bravo's own titles, as B16 prints them (``_x000D_`` and a line break inside).
_B16_TITLES = ("Bản vẽ/ Specification", "CU WT: _x000D_\n(KG/BP Unit)", "Unit BP")


def _table(*rows: list[CellValue], titles: list[str]) -> ImportedTable:
    body: list[list[CellValue]] = [["RFQ List"], list(titles), *rows]
    return ImportedTable(
        sheet="RFQ List",
        rows=[TableRow(row=i + 1, cells=cells) for i, cells in enumerate(body)],
    )


def _titles(*, design: bool = True) -> list[str]:
    base = [COLUMNS[f].header for f in _BASE]
    return [*base, *_B16_TITLES] if design else base


def test_the_spec_copper_and_unit_are_read_with_their_row() -> None:
    parsed = parse_export(
        _table(
            [M10_YCBG, 1, "CLOSE", "QUOTE", None, "BP003833", M10_WORDS, "SPV-02-1788", 5.59, "km"],
            titles=_titles(),
        )
    )

    assert parsed.rejected == ()
    (line,) = parsed.lines
    assert (line.spec_no, line.copper_kg_per_bp_unit, line.bp_unit, line.row) == (
        "SPV-02-1788",
        Decimal("5.59"),
        "km",
        3,
    )


def test_an_export_without_those_columns_reads_as_before() -> None:
    parsed = parse_export(
        _table(
            [M10_YCBG, 1, "CLOSE", "QUOTE", None, "BP003833", M10_WORDS],
            titles=_titles(design=False),
        )
    )

    assert parsed.rejected == ()
    (line,) = parsed.lines
    assert (line.spec_no, line.copper_kg_per_bp_unit, line.bp_unit) == (None, None, None)


@pytest.mark.parametrize("copper", ["năm", -1, "5,59"])
def test_copper_that_is_not_a_plain_number_rejects_the_row_naming_its_column(
    copper: CellValue,
) -> None:
    parsed = parse_export(
        _table(
            [
                M10_YCBG,
                1,
                "CLOSE",
                "QUOTE",
                None,
                "BP003833",
                M10_WORDS,
                "SPV-02-1788",
                copper,
                "km",
            ],
            titles=_titles(),
        )
    )

    assert parsed.lines == ()
    assert [r.column for r in parsed.rejected] == [COLUMNS["copper_kg_per_bp_unit"].header]


# ------------------------------------------------- recorded on the case --


async def _waiting(world: World) -> uuid.UUID:
    seen = await world.process_each(DIEU, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None
    commands = world.services.quote_commands

    def version() -> int:
        return world.quote(case_id).case_version

    context = DIEU.context()
    await commands.ycbg(context, case_id, case_version=version(), ycbg_no=None)
    await commands.ycbg(context, case_id, case_version=version(), ycbg_no=M10_YCBG)
    await commands.design_sent(context, case_id, case_version=version())
    return case_id


async def test_the_quote_carries_designs_values_onto_the_case_and_moves_nothing() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case_id = await _waiting(world)
    line = BravoYcbgLine.model_validate(
        {
            "ycbg_no": M10_YCBG,
            "line_no": 1,
            "status": "close",
            "verdict": "quote",
            "bp_code": "BP003833",
            "description": M10_WORDS,
            "spec_no": "SPV-02-1788",
            "copper_kg_per_bp_unit": "5.59",
            "bp_unit": "km",
            "row": 5,
        }
    )
    checks = DesignChecks(world.store, world.store, FixedClock(NOW), Uuid4Generator())

    (outcome,) = await checks.take(DIEU.context(), ExportedYcbg((line,)), file_sha256=SHA)

    assert outcome.outcome == "recorded"
    case = world.quote(case_id)
    assert case.status is QuoteStatus.SENT_TO_DESIGN
    assert case.design_check is not None
    (checked,) = case.design_check.lines
    assert (checked.spec_no, checked.copper_kg_per_bp_unit, checked.bp_unit, checked.row) == (
        "SPV-02-1788",
        Decimal("5.59"),
        "km",
        5,
    )


def test_a_decline_carries_none_of_designs_values() -> None:
    from dw_sales.domain.quotes import DesignCheckLine

    with pytest.raises(ValueError):
        DesignCheckLine(
            line_no=1, verdict="decline", reason="không làm được", spec_no="SPV-02-1788"
        )
