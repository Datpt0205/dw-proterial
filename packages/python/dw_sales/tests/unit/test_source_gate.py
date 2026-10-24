"""What a person must have been served before prepare or cross-check (spec
decision 12): the order's source, and every page or sheet holding a value read
from a flagged region or typed by Sales."""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.reader_client import ClientPoReaders, ClientQuoteForms
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.case_store import ServedSource, SourceRegion
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.application.source import OpenedSources, required_regions
from dw_sales.application.views import ValueState
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import Actor, CorrectedBySales, OrderCase
from dw_sales.evals.graders import AN as PIC_AN
from dw_sales.evals.graders import CALLERS, DIEU, READER
from dw_sales.evals.world import NOW, Caller, SampleSet, World, open_world

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
REPO = Path(__file__).resolve().parents[5]
POLICIES = REPO / "configs" / "policies"
AN = Actor(user_id=uuid.UUID(int=0xA1))
AT = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
_IDS = itertools.count(1)


class _NoCases:
    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Sequence[OrderCase]:
        return ()


async def _case(message_id: str) -> OrderCase:
    inbox = MockInbox.load(SCOPE)
    intake = OrderIntake(
        catalog=MockSalesCatalog.load(SCOPE),
        inbox=inbox,
        reader=ClientPoReaders(InProcessReaderTransport()),
        quote_forms=ClientQuoteForms(InProcessReaderTransport()),
        rules=PlatformOrderRules(load_order_rules(POLICIES / "sales_order_rules@1.6.0.yaml")),
        cases=_NoCases(),
        new_case_id=lambda: uuid.UUID(int=next(_IDS)),
    )
    message = await inbox.get_message(SCOPE, message_id)
    assert message is not None
    outcome = await intake.process(SCOPE, message)
    assert outcome.case is not None
    return outcome.case.start_review()


def _sheet(case: OrderCase, line_no: int) -> str | None:
    return case.line(line_no).po_line.anchors.quantity.sheet


async def test_a_clean_order_needs_only_its_own_source() -> None:
    case = await _case("M01")
    anchor = case.header.anchors.po_no
    assert anchor.attachment_id is not None

    assert required_regions(case) == {SourceRegion(anchor.attachment_id, None, anchor.sheet)}


async def test_a_pdf_order_is_needed_by_page() -> None:
    case = await _case("M03")

    (region,) = required_regions(case)

    assert (region.page, region.sheet) == (1, None)


async def test_each_sheet_holding_a_flagged_value_is_needed() -> None:
    case = await _case("M27")

    regions = required_regions(case)

    # Line 2's row is hidden on the first sheet; lines 4-6 sit on a hidden one.
    assert {r.sheet for r in regions} >= {_sheet(case, 2), _sheet(case, 5)}
    assert len({r.sheet for r in regions}) >= 2


async def test_the_sheet_of_a_typed_value_is_needed() -> None:
    case = await _case("M21")  # line_total_mismatch, on the total
    total = case.document.total
    assert total is not None
    key = next(f.key for f in case.findings if f.code.value == "line_total_mismatch")

    typed = case.dispose(
        key,
        CorrectedBySales(value="1000", source="bản in", by=AN.user_id, at=AT),
        AN,
    )

    assert total.anchor.attachment_id is not None
    assert SourceRegion(total.anchor.attachment_id, None, total.anchor.sheet) in required_regions(
        typed
    )


# ------------------------------------------- what a case view says was opened --
#
# M02 reads 18 lines from four sheets, and only the sheet holding its PO number
# is asked for before prepare: the case to show a value nobody opened on.


async def _m02(world: World) -> OrderCase:
    """M02, its one blocking finding (line 11's LME band) accepted."""
    ((_, case),) = (await world.process_each(PIC_AN, ["M02"])).values()
    assert isinstance(case, OrderCase)
    for finding in case.findings:
        await world.services.order_commands.dispose(
            PIC_AN.context(),
            case.case_id,
            finding.key,
            case_version=world.order(case.case_id).case_version,
            disposition="accepted",
            reason="đã hỏi trưởng phòng",
        )
    return world.order(case.case_id)


def _sheets(case: OrderCase) -> dict[int, str]:
    sheets = {line.line_no: _sheet(case, line.line_no) for line in case.lines}
    assert None not in sheets.values()
    return {n: s for n, s in sheets.items() if s is not None}


async def _serve(world: World, caller: Caller, case: OrderCase, sheet: str) -> None:
    await world.services.sources.order_source(
        caller.context(), case.case_id, case.document.attachment_id, page=None, sheet=sheet
    )


async def test_a_prepared_value_is_checked_only_where_its_preparer_opened_it() -> None:
    """Audit gap 1: prepare relabelled every unflagged value "Đã kiểm"."""
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case = await _m02(world)
    sheets = _sheets(case)
    first = case.header.anchors.po_no.sheet
    second, third = sorted(set(sheets.values()) - {first})[:2]
    # Another person's opening is not the preparer's check.
    await _serve(world, DIEU, case, second)
    await world.open_sources(PIC_AN, case.case_id)
    await world.services.order_commands.prepare(
        PIC_AN.context(), case.case_id, case_version=world.order(case.case_id).case_version
    )
    # Nor is an opening after the step.
    world.store.clock.advance_to(NOW + timedelta(hours=1))
    await _serve(world, PIC_AN, case, third)

    view = await world.services.orders.get(PIC_AN.context(), case.case_id)

    for line in view.lines:
        checked = sheets[line.line_no] == first
        expected = ValueState.CONFIRMED if checked else ValueState.NOT_OPENED
        assert set(line.value_states.values()) == {expected}, line.line_no
    assert any(sheets[n] == first for n in sheets) and any(sheets[n] != first for n in sheets)


async def test_an_unprepared_value_stays_as_dw1_read_it_whoever_opened_it() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case = await _m02(world)
    await world.open_sources(PIC_AN, case.case_id)

    view = await world.services.orders.get(PIC_AN.context(), case.case_id)

    assert {s for line in view.lines for s in line.value_states.values()} == {ValueState.DW}


async def test_the_cross_checker_is_shown_the_values_nobody_opened_before_their_step() -> None:
    """Audit gap 5, from the served records: what no person opened before
    the order was recorded in Bravo. The checker's own opening during the
    step does not hide what the makers never opened."""
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case = await _m02(world)
    sheets = _sheets(case)
    first = case.header.anchors.po_no.sheet
    await world.walk_to_uploaded(PIC_AN, case.case_id)
    world.store.clock.advance_to(NOW + timedelta(hours=1))
    second = sorted(set(sheets.values()) - {first})[0]
    await _serve(world, DIEU, case, second)

    view = await world.services.orders.get(DIEU.context(), case.case_id)

    assert view.unopened_values is not None
    listed_lines = {v.line_no for v in view.unopened_values if v.line_no is not None}
    assert listed_lines == {n for n, sheet in sheets.items() if sheet != first}
    header = world.order(case.case_id).header.anchors
    for value in view.unopened_values:
        if value.line_no is None and value.field in type(header).model_fields:
            assert getattr(header, value.field).sheet != first
    assert ("po_no", None) not in {(v.field, v.line_no) for v in view.unopened_values}


async def test_who_opened_what_is_not_shown_without_the_cross_check_scope() -> None:
    """Decided: the list tells how colleagues read the case, and only the
    cross-checker acts on it, so a reader without the scope is not given it."""
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case = await _m02(world)
    await world.walk_to_uploaded(PIC_AN, case.case_id)

    view = await world.services.orders.get(READER.context(), case.case_id)

    assert view.unopened_values is None


async def test_a_page_of_another_file_under_the_same_id_was_not_opened() -> None:
    """A revision's file may reuse an attachment id; its sha256 tells them apart."""
    case = await _case("M01")
    anchor = case.header.anchors.po_no
    assert anchor.attachment_id is not None and anchor.sheet is not None

    def served(sha256: str) -> ServedSource:
        return ServedSource(
            principal_id=PIC_AN.user_id,
            case_kind=CaseKind.ORDER,
            case_id=case.case_id,
            case_version=case.case_version,
            attachment_id=anchor.attachment_id,
            attachment_sha256=sha256,
            sheet=anchor.sheet,
            served_at=AT,
        )

    assert OpenedSources.of([served(anchor.attachment_sha256)]).holds(anchor)
    assert not OpenedSources.of([served("0" * 64)]).holds(anchor)
