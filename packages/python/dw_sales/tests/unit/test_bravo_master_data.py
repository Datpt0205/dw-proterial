"""Ticket 14: Bravo's master lists read through one port per list
(`BravoMasterDataPort`), and a list that fails to read never weakens what is
in force. Every file here is synthetic, shaped as Bravo exports its lists
(Box B05): a merged title row, Bravo's own column titles on row 2."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from dw_sales.application.catalog_imports import ExportedMasterList
from dw_sales.domain.master_data import CatalogList, ImportedTable, TableRow
from dw_sales.evals.graders import AN, CALLERS, GIANG, OUTSIDER
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
_CUSTOMERS = CatalogList.CUSTOMERS


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, OUTSIDER))


def _export(titles: list[str], *rows: list[object]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Control_Explorer"
    sheet.append(["Danh mục đối tượng (MẪU GIẢ LẬP)"])
    sheet.append(titles)
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


_TITLES = ["Code", "Nhóm KH", "Tên đối tượng", "Nhóm mẹ", "Tên miền email", "Ngôn ngữ"]
_TITLES += ["PIC phụ trách", "E-mail liên hệ"]
_ROW: list[object] = ["FG0001", "PRV", "Công ty Mẫu", "01.CUSTOMER", "@mau.example"]
_ROW += ["English", "Người Mẫu", "nguoi@mau.example"]


async def _imported(world: World, data: bytes) -> str:
    view = await world.services.catalog_imports.upload(AN.context(), _CUSTOMERS, "kh.xlsx", data)
    (outcome,) = await world.read_imports()
    if outcome == "import parsed":
        await world.services.catalog_imports.submit(AN.context(), view.snapshot_id)
        await world.decide_catalog(GIANG, view.snapshot_id, approve=True, comment="Đồng ý")
    return outcome


async def _in_force(world: World) -> tuple[object, int, str | None]:
    """The snapshot in force, how many customers DW1 reads, and the error of
    the import that failed (both imports carry the test clock's one time)."""
    state = await world.services.catalog_imports.state(AN.context())
    (customers,) = [s for s in state.lists if s.catalog_list is _CUSTOMERS]
    read = await world.services.catalog_imports.catalog.customers(ALPHA)
    snapshot = customers.in_force.snapshot
    failed = [h.error for h in customers.history if h.status == "failed"]
    return (
        None if snapshot is None else snapshot.snapshot_id,
        len(read.data),
        failed[0] if failed else None,
    )


async def test_an_export_read_through_the_port_is_the_lists_records() -> None:
    table = ImportedTable(
        sheet="Control_Explorer",
        rows=[
            TableRow(row=1, cells=["Danh mục đối tượng"]),
            TableRow(row=2, cells=list(_TITLES)),
            TableRow(row=3, cells=list(_ROW)),
        ],
    )

    parsed = await ExportedMasterList(table).read(ALPHA, _CUSTOMERS)

    assert [record.key for record in parsed.records] == ["FG0001"]
    assert parsed.rejected == ()


@pytest.mark.parametrize(
    "broken",
    [
        _export(_TITLES[1:], _ROW[1:]),  # Bravo's "Code" column left out
        _export(_TITLES),  # the titles and no row: an empty list
        _export(_TITLES, ["FG0002", *_ROW[1:4], None, None, None, None]),  # no row usable
    ],
    ids=["missing_column", "no_rows", "no_usable_row"],
)
async def test_a_list_that_fails_to_read_leaves_the_one_in_force_and_says_so(
    broken: bytes,
) -> None:
    """Acceptance 2: never an empty list that passes everything."""
    world = _world()
    assert await _imported(world, _export(_TITLES, _ROW)) == "import parsed"
    approved, customers, _ = await _in_force(world)
    assert approved is not None and customers == 1

    assert await _imported(world, broken) == "import failed"

    snapshot, after, error = await _in_force(world)
    assert (snapshot, after) == (approved, customers)
    # Said on the list's own state: its newest read failed, and why.
    assert error
