"""Ticket 03, decided 2026-11-17 (Đạt left it to the agent's recommendation):
a sales order read back from Bravo that differs from the paste sheet, at the
case version being cross-checked, refuses "Kiểm chéo đạt". Bravo's import
skips a refused row without a log, so a difference is a line Bravo lost or
holds wrong, and passing the cross-check over it would confirm an order Bravo
does not hold.

What it does not block: no read-back at all (the manual path stays, the
panel says nothing was read), a read-back of an older version (the case
changed since; the panel says so), and "Trả lại", which is how the
difference gets fixed. Enforced where the decision is taken
(`CaseDecisions._decide`), so the platform's guard refuses it before the
decision is recorded, whichever screen asked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dw_kernel.errors import ConflictError
from dw_sales.application.bravo_sales_orders import BravoReadBack
from dw_sales.domain.bravo_sales_orders import SoDifference
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderStatus
from dw_sales.evals.graders import AN, CALLERS, DIEU
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
READ_AT = datetime(2026, 11, 17, 2, 0, tzinfo=UTC)


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _uploaded(world: World) -> uuid.UUID:
    """M03 prepared and recorded in Bravo by An: it waits on Diệu's cross-check."""
    seen = await world.process_each(AN, ["M03"])
    case_id = seen["M03"][0].case_id
    assert case_id is not None
    await world.services.order_commands.dispose(
        AN.context(),
        case_id,
        "quotation_missing:2",
        case_version=world.order(case_id).case_version,
        disposition="accepted",
        reason="Giá theo báo giá gia hạn qua thư",
    )
    await world.walk_to_uploaded(AN, case_id)
    return case_id


async def _read_back(world: World, case_id: uuid.UUID, *, differs: bool, version: int) -> None:
    case = world.order(case_id)
    differences = (
        (
            SoDifference(
                po_no=case.header.po_no or "PO",
                line_no=1,
                field="missing_row",
            ),
        )
        if differs
        else ()
    )
    async with world.bravo_store(ALPHA) as work:
        await work.read_backs.put(
            BravoReadBack(
                case_id=case_id,
                case_version=version,
                po_no=case.header.po_no or "PO",
                so_no="SO26-1001",
                differences=differences,
                rows_read=1,
                file_sha256="d" * 64,
                read_by=AN.user_id,
                read_at=READ_AT,
            )
        )
        await work.commit()


async def test_a_read_back_that_differs_refuses_the_cross_check() -> None:
    world = _world()
    case_id = await _uploaded(world)
    await _read_back(world, case_id, differs=True, version=world.order(case_id).case_version)

    with pytest.raises(ConflictError) as refused:
        await world.cross_check(DIEU, case_id)

    assert refused.value.details["rule"] == "bravo_read_back_differs"
    assert "Bravo" in refused.value.message
    assert world.order(case_id).status is OrderStatus.UPLOADED_TO_BRAVO


async def test_the_cross_checker_may_still_return_it() -> None:
    world = _world()
    case_id = await _uploaded(world)
    await _read_back(world, case_id, differs=True, version=world.order(case_id).case_version)

    await world.open_sources(DIEU, case_id)
    await world.decide(DIEU, CaseKind.ORDER, case_id, approve=False, comment="Bravo thiếu dòng 1")

    assert world.order(case_id).status is not OrderStatus.CROSS_CHECKED


@pytest.mark.parametrize("read", ["equal", "older_version", "none"])
async def test_the_cross_check_passes_without_a_current_difference(read: str) -> None:
    world = _world()
    case_id = await _uploaded(world)
    version = world.order(case_id).case_version
    if read == "equal":
        await _read_back(world, case_id, differs=False, version=version)
    elif read == "older_version":
        await _read_back(world, case_id, differs=True, version=version - 1)

    assert (await world.cross_check(DIEU, case_id)).status is OrderStatus.CROSS_CHECKED
