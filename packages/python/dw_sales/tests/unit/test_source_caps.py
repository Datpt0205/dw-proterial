"""A source view opens a file under the caps it was read under (DW1 review,
config, 2026-11-27): the tenant's order rules, never the platform file's
bound when the process started. A PO DW1 read under a company's raised caps
is one Sales can open to confirm, and one its lowered caps refuse to read is
one the view refuses to open.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dw_kernel.errors import DomainError
from dw_sales.adapters.reader_wire import ReaderOp, ReaderReply, ReaderRequest
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


async def _read(world: World) -> tuple[OrderCase, str]:
    """M02, read under the rules in force: a workbook of four sheets."""
    ((_, case),) = (await world.process_each(AN, ["M02"])).values()
    assert isinstance(case, OrderCase)
    sheet = case.header.anchors.po_no.sheet
    assert sheet is not None and case.document.attachment_id is not None
    return case, sheet


async def _company_caps(world: World, **caps: int) -> IntakeCaps:
    """The company's own order rules, its intake caps changed, in force."""
    rules = await world.intake.rules.rules(ALPHA)
    own = rules.model_copy(update={"intake": rules.intake.model_copy(update=caps)})
    world.store.rule_versions.seed_approved(ALPHA.tenant_id.value, own)
    return own.intake


async def test_the_view_asks_the_reader_with_the_company_s_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case, sheet = await _read(world)
    platform = world.policies.order_rules.intake
    raised = await _company_caps(
        world, max_pages=platform.max_pages * 2, max_cells=platform.max_cells * 2
    )

    asked: list[IntakeCaps] = []
    original = InProcessReaderTransport.call

    async def recorded(self: InProcessReaderTransport, request: ReaderRequest) -> ReaderReply:
        if request.operation is ReaderOp.SOURCE_SHEET_GRID:
            assert request.args.caps is not None
            asked.append(request.args.caps)
        return await original(self, request)

    monkeypatch.setattr(InProcessReaderTransport, "call", recorded)
    assert case.document.attachment_id is not None
    await world.services.sources.order_source(
        AN.context(), case.case_id, case.document.attachment_id, page=None, sheet=sheet
    )

    assert asked == [raised]


async def test_a_file_the_company_s_caps_refuse_is_not_opened() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case, sheet = await _read(world)
    # Lowered after the reading: the platform's caps would still open it.
    await _company_caps(world, max_sheets=1)

    assert case.document.attachment_id is not None
    with pytest.raises(DomainError) as refused:
        await world.services.sources.order_source(
            AN.context(), case.case_id, case.document.attachment_id, page=None, sheet=sheet
        )
    assert refused.value.details["reason_code"] == "source_unreadable"
