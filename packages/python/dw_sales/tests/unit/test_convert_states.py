"""Ticket 04: Bravo's convert list goes through approval states 1 → 2 → 3,
and only a row Bravo approved ("3. Đã duyệt") answers a PO line; one still
waiting is held as waiting, never used. Every file here is synthetic, shaped
as Bravo exports the list (Box B04): a merged title, the header on row 2,
then each state's label merged across its row with a SUBTOTAL beside it,
then that state's rows."""

from __future__ import annotations

import io
import uuid
from collections.abc import Sequence
from pathlib import Path

import pytest
from openpyxl import Workbook

from dw_sales.adapters.reader_client import ClientTableReader, ReaderMismatchError
from dw_sales.adapters.reader_wire import ReaderOp, ReaderReply, ReaderRequest
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.catalog_imports import ExportedMasterList
from dw_sales.domain.master_data import CatalogList
from dw_sales.evals.graders import AN, CALLERS, GIANG
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
HEADERS = [
    "Input date", "PRV code", "PRV item name", "Specification", "Direct customer code",
    "Direct customer name", "Converting description", "Invoice description",
    "All customer code", "All customer description", "Remark", "Id",
]  # fmt: skip


def _row(code: str, words: str, prv: str = "HW-1001") -> list[object]:
    return ["2026-11-09", prv, "Fictional", None, code, "Fictional Co", words, *[None] * 5]


def _b04(groups: Sequence[tuple[str, Sequence[list[object]]]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Control_Explorer"
    width = len(HEADERS)
    sheet.append(["Converting customer to PRV item (MẪU GIẢ LẬP)"])
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    sheet.append(HEADERS)
    for label, rows in groups:
        at = sheet.max_row + 1
        sheet.append([label, *[None] * (width - 2), f"=SUBTOTAL(3,L{at + 1}:L{at + len(rows)})"])
        sheet.merge_cells(start_row=at, start_column=1, end_row=at, end_column=width - 1)
        for row in rows:
            sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


EXPORT = _b04(
    [
        ("2. Chờ duyệt", [_row("VLX", "WAITING-WORDS")]),
        ("3. Đã duyệt", [_row("VLX", "APPROVED-WORDS", "HW-1002")]),
    ]
)


async def test_each_row_takes_the_state_of_the_group_above_it() -> None:
    world = _world()
    reader = ClientTableReader(InProcessReaderTransport(), world.policies.order_rules.intake)
    table = await reader.read(EXPORT, "b04.xlsx")

    parsed = await ExportedMasterList(table).read(ALPHA, CatalogList.CONVERT_LIST)

    assert {(p.record.customer_item_code, p.record.bravo_state) for p in parsed.records} == {  # type: ignore[union-attr]
        ("WAITING-WORDS", "waiting"),
        ("APPROVED-WORDS", "approved"),
    }


async def test_only_a_row_bravo_approved_answers_a_po_line() -> None:
    world = _world()
    view = await world.services.catalog_imports.upload(
        AN.context(), CatalogList.CONVERT_LIST, "b04.xlsx", EXPORT
    )
    assert await world.read_imports() == ["import parsed"]
    await world.services.catalog_imports.submit(AN.context(), view.snapshot_id)
    await world.decide_catalog(GIANG, view.snapshot_id, approve=True, comment="Đồng ý")
    catalog = world.services.catalog_imports.catalog

    approved = await catalog.convert_entry(ALPHA, "VLX", "APPROVED-WORDS")
    waiting = await catalog.convert_entry(ALPHA, "VLX", "WAITING-WORDS")

    assert approved.data is not None and approved.data.prv_code == "HW-1002"
    assert waiting.data is None


class _ReaderBeforeGroups:
    """A reader image older than ticket 04: its table answer has no groups,
    so a waiting row would read as approved. It is refused instead."""

    async def call(self, request: ReaderRequest) -> ReaderReply:
        reply = await InProcessReaderTransport().call(request)
        if request.operation is ReaderOp.TABLE_ROWS and isinstance(reply.result, dict):
            older = {k: v for k, v in reply.result.items() if k != "groups"}
            return reply.model_copy(update={"result": older})
        return reply


async def test_a_reader_that_sends_no_groups_is_refused_never_read_as_approved() -> None:
    world = _world()
    reader = ClientTableReader(_ReaderBeforeGroups(), world.policies.order_rules.intake)

    with pytest.raises(ReaderMismatchError):
        await reader.read(EXPORT, "b04.xlsx")


async def test_sales_sees_the_mappings_it_confirmed_that_bravo_does_not_hold_yet() -> None:
    """Ticket 04: a code Sales confirmed in DW1 stays usable until Bravo has
    the row; DW1 lists each one Bravo lacks, or holds only as waiting, for
    Sales to enter and approve in Bravo, and Bravo's own waiting rows."""
    from dw_sales.domain.catalog import ConvertEntry

    world = _world()
    catalog = world.services.catalog_imports.catalog

    async def confirm(words: str, prv: str) -> None:
        await catalog.learn_convert(  # type: ignore[attr-defined]
            ALPHA,
            ConvertEntry(customer_code="VLX", customer_item_code=words, prv_code=prv),
            by=AN.user_id,
            case_id=uuid.uuid4(),
        )

    # Confirmed in DW1 before Bravo approved it: Bravo's row answers now.
    await confirm("APPROVED-WORDS", "HW-1002")
    view = await world.services.catalog_imports.upload(
        AN.context(), CatalogList.CONVERT_LIST, "b04.xlsx", EXPORT
    )
    await world.read_imports()
    await world.services.catalog_imports.submit(AN.context(), view.snapshot_id)
    await world.decide_catalog(GIANG, view.snapshot_id, approve=True, comment="Đồng ý")
    await confirm("WAITING-WORDS", "HW-1003")
    await confirm("NEW", "HW-1004")

    gaps = await world.services.convert_gaps.list(AN.context())

    assert {(g.customer_item_code, g.state, g.prv_code, g.bravo_prv_code) for g in gaps.gaps} == {
        ("WAITING-WORDS", "waiting_in_bravo", "HW-1003", "HW-1001"),
        ("NEW", "not_in_bravo", "HW-1004", None),
    }
    assert gaps.bravo_read
