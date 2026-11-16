"""Ticket 12: Bravo's "Master list báo giá" read through the Bravo port, as
exported (Box B07's shape, every value fictional): a title, a row of block
labels ("Request for quotation", "Base price(tại thời điểm báo giá)",
"QUOTATION", "RowIdSQ", "Base price (latest)"), then Bravo's titles, where
"LME", "MOQ" and "BP date" each title two columns of different blocks and
RowIdSQ is titled on the block row only."""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from dw_kernel.errors import PermissionDeniedError
from dw_sales.adapters.reader_client import ClientTableReader
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.catalog_imports import ExportedMasterList
from dw_sales.domain.master_data import CatalogList
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
_LIST = CatalogList.BRAVO_QUOTATIONS

_BLOCKS: list[object] = ["Request for quotation", None, "Base price(tại thời điểm báo giá)"]
_BLOCKS += [None, None, "QUOTATION"] + [None] * 10 + ["RowIdSQ", "Base price (latest)", None]
_TITLES: list[object] = ["Customer description", "Status", "BP Code", "LME", "MOQ"]
_TITLES += ["Stt", "Quote No.", "Quotation Date", "Valid date", "Class_x000d_\n(Update/New)"]
_TITLES += ["Direct customer code", "MOQ", "Unit", "Center price", "LME", "Currency"]
_TITLES += [None, "Description", "LME of BP"]


def _row(row_id: str, lme: int) -> list[object]:
    return [
        "Fictional cable", "CLOSE", "BP000101", 7750, 2, 1, "QN-PRV-261020-001",
        "2026-10-20", "2027-04-19", "New", "FG0001", 1, "km", 1450.5, lme, "USD",
        row_id, "Fictional cable", 7750,
    ]  # fmt: skip


def _b07(*rows: list[object]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "grid"
    sheet.append(["Master list báo giá (MẪU GIẢ LẬP)"])
    sheet.append(_BLOCKS)
    sheet.append(_TITLES)
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def test_bravos_master_list_reads_each_title_from_its_own_block() -> None:
    world = _world()
    reader = ClientTableReader(InProcessReaderTransport(), world.policies.order_rules.intake)
    table = await reader.read(_b07(_row("100000000101SQ", 8250)), "b07.xlsx")

    parsed = await ExportedMasterList(table).read(ALPHA, _LIST)

    assert parsed.rejected == ()
    (record,) = (p.record for p in parsed.records)
    # The quotation's own LME and MOQ, never the base price's of the same title.
    assert (record.row_id, record.lme, record.moq, record.bp_code) == (  # type: ignore[union-attr]
        "100000000101SQ",
        Decimal("8250"),
        Decimal("1"),
        "BP000101",
    )
    assert record.center_price == Decimal("1450.5")  # type: ignore[union-attr]


async def test_another_customers_centre_prices_are_for_those_who_may_read_them() -> None:
    world = _world()
    with pytest.raises(PermissionDeniedError):
        await world.services.catalog_imports.upload(
            AN.context(), _LIST, "b07.xlsx", _b07(_row("100000000101SQ", 8250))
        )


def test_bravos_text_moq_reads_its_dot_as_the_decimal_mark_and_refuses_a_comma() -> None:
    from dw_sales.domain.master_data import SPECS, CellError

    (moq,) = [c for c in SPECS[_LIST].columns if c.path == "moq"]
    assert moq.read("0.305") == "0.305"
    assert moq.read("1000.5") == "1000.5"
    assert moq.read(2) == "2"
    with pytest.raises(CellError):
        moq.read("1,000")
