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
from dw_sales.evals.world import ALPHA, NOW, SampleSet, World, open_world

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


# ------------------------------------- the request's rows, kept as its source --

_FULL = [*_titles(), "Ngày hoàn thành BP/ Complete date"]
OTHER_YCBG = "RFQ261110-009"


def _row(number: str, words: str, *, spec: str | None = "SPV-02-1788") -> list[CellValue]:
    return [number, None, "CLOSE", "QUOTE", None, "BP003833", words, spec, 5.59, "km", "2026-11-12"]


async def _recorded_from_export(world: World) -> uuid.UUID:
    """M10 waiting on Design; an export listing M10's YCBG and another
    customer's, read through the screen as Diệu."""
    from dw_sales.application.ycbg_exports import YcbgScreen

    case_id = await _waiting(world)
    table = _table(
        _row(OTHER_YCBG, "another customer's cable"),
        _row(M10_YCBG, M10_WORDS),
        titles=_FULL,
    )
    screen = YcbgScreen(DesignChecks(world.store, world.store, FixedClock(NOW), Uuid4Generator()))
    outcomes, rejected = await screen.take(DIEU.context(), table, file_sha256=SHA)
    assert rejected == ()
    assert [o.outcome for o in outcomes if o.key == M10_YCBG] == ["recorded"]
    return case_id


async def test_the_case_keeps_its_own_rows_of_the_export_and_no_other_requests() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case_id = await _recorded_from_export(world)

    check = world.quote(case_id).design_check
    assert check is not None and check.snapshot is not None
    rows = check.snapshot.rows
    assert [r.row for r in rows] == [2, 4]  # the titles, then M10's own row
    shown = " ".join(c for r in rows for c in r.cells if c)
    assert OTHER_YCBG not in shown and "another customer's cable" not in shown
    assert check.lines[0].places["spec_no"] == "H4"


async def test_designs_quote_becomes_the_reply_anchored_in_those_rows() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case_id = await _recorded_from_export(world)

    after = world.quote(case_id).design_from_bravo()

    assert after.status is QuoteStatus.DESIGN_REPLIED
    reply = after.design_reply
    assert reply is not None and reply.attachment is not None
    snapshot = world.quote(case_id).design_check.snapshot  # type: ignore[union-attr]
    assert reply.attachment.attachment_id == snapshot.attachment_id  # type: ignore[union-attr]
    (line,) = reply.document.lines
    assert (line.bp_code.value, line.spec_no.value) == ("BP003833", "SPV-02-1788")
    assert line.spec_no.source.cell_ref == "RFQ List!H4"
    assert line.copper_kg_per_km is not None and line.copper_kg_per_km.value == Decimal("5.59")
    assert reply.document.reply_date.source.cell_ref == "RFQ List!K4"


async def test_copper_per_another_unit_is_left_unknown_not_converted() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case_id = await _recorded_from_export(world)
    case = world.quote(case_id)
    check = case.design_check
    assert check is not None
    per_pcs = check.model_copy(
        update={"lines": tuple(ln.model_copy(update={"bp_unit": "pcs"}) for ln in check.lines)}
    )

    after = case.model_copy(update={"design_check": per_pcs}).design_from_bravo()

    assert after.design_reply is not None
    assert after.design_reply.document.lines[0].copper_kg_per_km is None


async def test_nothing_is_recorded_without_the_rows_or_over_a_decline() -> None:
    from dw_kernel.errors import ConflictError

    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case_id = await _recorded_from_export(world)
    case = world.quote(case_id)
    check = case.design_check
    assert check is not None

    with pytest.raises(ConflictError) as no_rows:
        case.model_copy(
            update={"design_check": check.model_copy(update={"snapshot": None})}
        ).design_from_bravo()
    assert no_rows.value.details["rule"] == "no_snapshot"

    from dw_sales.domain.quotes import DesignCheckLine

    declined = check.model_copy(
        update={"lines": (DesignCheckLine(line_no=1, verdict="decline", reason="không làm được"),)}
    )
    with pytest.raises(ConflictError) as over_decline:
        case.model_copy(update={"design_check": declined}).design_from_bravo()
    assert over_decline.value.details["rule"] == "design_declined"


# ----------------------------------------------- the command and the pane --


async def _open_rows(world: World, case_id: uuid.UUID, caller: object = DIEU) -> object:
    check = world.quote(case_id).design_check
    assert check is not None and check.snapshot is not None
    return await world.services.sources.quote_source(
        caller.context(),  # type: ignore[attr-defined]
        case_id,
        check.snapshot.attachment_id,
        page=None,
        sheet=check.snapshot.sheet,
    )


async def test_the_pane_draws_only_the_requests_rows_with_designs_cells_marked() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case_id = await _recorded_from_export(world)

    view = await _open_rows(world, case_id)

    texts = {c.text for c in view.grid.cells}  # type: ignore[attr-defined]
    assert "SPV-02-1788" in texts and OTHER_YCBG not in texts
    assert "another customer's cable" not in texts
    marked = {(a.field, a.anchor.cell) for a in view.anchors}  # type: ignore[attr-defined]
    assert ("spec_no", "H4") in marked and ("bp_code", "F4") in marked


async def test_designs_result_is_recorded_once_its_rows_were_opened() -> None:
    from dw_kernel.errors import ConflictError

    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case_id = await _recorded_from_export(world)
    commands = world.services.quote_commands

    with pytest.raises(ConflictError) as unopened:
        await commands.design_from_bravo(
            DIEU.context(), case_id, case_version=world.quote(case_id).case_version
        )
    assert unopened.value.details["rule"] == "source_not_served"
    assert world.quote(case_id).status is QuoteStatus.SENT_TO_DESIGN

    await _open_rows(world, case_id)
    await commands.design_from_bravo(
        DIEU.context(), case_id, case_version=world.quote(case_id).case_version
    )

    case = world.quote(case_id)
    assert case.status is QuoteStatus.DESIGN_REPLIED
    events = [e.action for e in world.store.state(ALPHA).events if e.case_id == case_id]
    assert events[-1] == "quote.design_replied"


async def test_a_reader_cannot_record_it_and_another_workspace_cannot_find_it() -> None:
    from dw_kernel.errors import NotFoundError, PermissionDeniedError
    from dw_sales.evals.graders import OUTSIDER, READER
    from dw_sales.evals.world import BETA

    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case_id = await _recorded_from_export(world)
    version = world.quote(case_id).case_version
    commands = world.services.quote_commands

    with pytest.raises(PermissionDeniedError):
        await commands.design_from_bravo(READER.context(), case_id, case_version=version)
    with pytest.raises(NotFoundError):
        await commands.design_from_bravo(OUTSIDER.context(BETA), case_id, case_version=version)
    with pytest.raises(NotFoundError):
        await _open_rows(world, case_id, _Beta(OUTSIDER))
    assert world.quote(case_id).status is QuoteStatus.SENT_TO_DESIGN


class _Beta:
    def __init__(self, caller: object) -> None:
        self.caller = caller

    def context(self) -> object:
        from dw_sales.evals.world import BETA

        return self.caller.context(BETA)  # type: ignore[attr-defined]


def test_the_kept_rows_hold_no_column_dw1_does_not_read_prices_among_them() -> None:
    """B16's rows carry "Target price", "Giá cơ bản" and the cost split: the
    case keeps only the columns DW1 reads, so no amount reaches a case
    reader through the snapshot (ui-quality §6)."""
    from dw_sales.application.ycbg_exports import snapshots_of

    titles = [*_FULL, "Giá cơ bản/ Base price", "Target price (USD/km or USD/pcs)"]
    table = _table([*_row(M10_YCBG, M10_WORDS), 122.88, 99.5], titles=titles)
    parsed = parse_export(table)

    (snapshot,) = snapshots_of(table, parsed, SHA).values()

    shown = [c for r in snapshot.rows for c in r.cells if c is not None]
    assert "122.88" not in shown and "99.5" not in shown
    assert "Giá cơ bản/ Base price" not in shown and "SPV-02-1788" in shown
