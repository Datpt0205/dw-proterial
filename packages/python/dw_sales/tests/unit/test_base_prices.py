"""Ticket 11: Bravo's "Danh mục Base price" as a master list, read through
the Bravo port (ticket 14), its amounts reaching price readers only.

Every file here is synthetic, shaped as Bravo exports the list (Box B21): a
merged title, Bravo's titles on row 2 with Excel's ``_x000d_`` and a
``{BP Unit}`` inside them, and Bravo's packing columns DW1 does not read."""

from __future__ import annotations

import io
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from dw_kernel.errors import PermissionDeniedError
from dw_sales.adapters.reader_client import ClientTableReader
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.access import SalesScopes
from dw_sales.application.catalog_imports import ExportedMasterList
from dw_sales.domain.master_data import CatalogList
from dw_sales.evals.graders import AN, CALLERS, GIANG
from dw_sales.evals.world import ALPHA, BETA, Caller, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
_LIST = CatalogList.BASE_PRICES
# May import master data and read cases, never an amount.
NO_PRICES = Caller(
    uuid.UUID(int=0x5E),
    "Người nhập không xem giá",
    "no.prices@alpha.local",
    frozenset({SalesScopes.CASE_READ.value, SalesScopes.MASTER_DATA_IMPORT.value}),
)

# Bravo's own titles, as B21 prints them (not customer data).
B21_TITLES = [
    "BP Date",
    "BP Code",
    "Short item description",
    "BP Unit",
    "Convert rate",
    "STD_x000d_ Unit",
    "Spec",
    "Category",
    "CU WT:_x000d_ KG/{BP Unit}",
    "Base price:_x000d_ USD/{BP Unit}",
    "Lead time_x000d_ (Wk)",
    "MOQ",
    "MOQ (km)",
    "LME of BP",
    "%MR of BP",
    "Material cost_x000d_ (USD/Km)",
    "Variable cost",
    "Fix cost",
    "LT-MOQ notice",
    "Remark of BP",
    "Scope/Notes",
    "Packing coil",
    "Bobbin",
    "Drum",
]


def _row(code: str, price: float) -> list[object]:
    return [
        "2026-11-02", code, "Fictional hook-up wire", "km", 1000, "m", "SPV-02-0001", "HK",
        3.6, price, 4, 1, 1, 7750, 35, None, None, None, None, None, None, "1x800", None, None,
    ]  # fmt: skip


def _b21(*rows: list[object]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "grdDetail"
    sheet.append(["Danh mục Base price (MẪU GIẢ LẬP)"])
    sheet.append(B21_TITLES)
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, NO_PRICES))


async def test_bravos_export_reads_as_base_prices_by_bravos_own_titles() -> None:
    world = _world()
    reader = ClientTableReader(InProcessReaderTransport(), world.policies.order_rules.intake)
    table = await reader.read(_b21(_row("BP000101", 412.5), _row("BP000102", 0)), "b21.xlsx")

    parsed = await ExportedMasterList(table).read(ALPHA, _LIST)

    assert parsed.rejected == ()
    first, second = (p.record for p in parsed.records)
    assert (first.bp_code, first.base_price, first.copper_kg) == (  # type: ignore[union-attr]
        "BP000101",
        Decimal("412.5"),
        Decimal("3.6"),
    )
    assert second.base_price == 0  # type: ignore[union-attr]
    # Bravo's columns DW1 does not read are listed, never guessed at.
    assert {"Packing coil", "Bobbin", "Drum"} <= set(parsed.unknown_headers)


async def test_an_approved_list_answers_by_bp_code_in_its_own_workspace_only() -> None:
    world = _world()
    data = _b21(_row("BP000101", 412.5))
    view = await world.services.catalog_imports.upload(AN.context(), _LIST, "b21.xlsx", data)
    assert await world.read_imports() == ["import parsed"]
    await world.services.catalog_imports.submit(AN.context(), view.snapshot_id)
    await world.decide_catalog(GIANG, view.snapshot_id, approve=True, comment="Đồng ý")
    catalog = world.services.catalog_imports.catalog

    found = await catalog.base_price(ALPHA, "BP000101")
    other = await catalog.base_price(BETA, "BP000101")

    assert found.data is not None and found.data.base_price == Decimal("412.5")
    # Another tenant's workspace has no such BP: alpha's approved list is not its.
    assert other.data is None


async def test_an_importer_who_may_not_read_prices_cannot_import_or_preview_them() -> None:
    world = _world()
    data = _b21(_row("BP000101", 412.5))

    with pytest.raises(PermissionDeniedError):
        await world.services.catalog_imports.upload(NO_PRICES.context(), _LIST, "b.xlsx", data)
    view = await world.services.catalog_imports.upload(AN.context(), _LIST, "b21.xlsx", data)
    await world.read_imports()
    with pytest.raises(PermissionDeniedError):
        await world.services.catalog_imports.preview(NO_PRICES.context(), view.snapshot_id)
    state = await world.services.catalog_imports.state(NO_PRICES.context())
    (listed,) = [s for s in state.lists if s.catalog_list is _LIST]
    assert not listed.can_import

