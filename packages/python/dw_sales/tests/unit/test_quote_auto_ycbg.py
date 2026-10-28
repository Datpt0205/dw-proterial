"""DW1 drafts a complete request's YCBG at once (2026-10-28, Đạt: "AI càng
nhiều càng tốt"): Sales only enters it in Bravo and records the number. A
request still lacking something waits on the PIC, and their last answer drafts
it; pressing "Soạn YCBG" after that changes nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

from dw_sales.domain.quotes import QuoteCase, QuoteStatus
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.world import SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _quote(world: World, message_id: str) -> QuoteCase:
    ((_, case),) = (await world.process_each(AN, [message_id])).values()
    assert isinstance(case, QuoteCase)
    return case


async def test_a_complete_request_has_its_ycbg_drafted_by_dw1() -> None:
    world = _world()
    case = await _quote(world, "M10")
    assert case.status is QuoteStatus.YCBG_DRAFTED
    # On the case's history as DW1's, after the request was received.
    events = [e for e in world.audit() if e.resource_id == str(case.case_id)]
    assert [e.details.get("to_status") for e in events][-2:] == ["received", "ycbg_drafted"]


async def test_a_request_lacking_its_customer_waits_and_the_answer_drafts_it() -> None:
    world = _world()
    case = await _quote(world, "M14")
    assert case.status is QuoteStatus.RECEIVED
    assert [f.code.value for f in case.findings if f.is_open] == ["customer_unknown"]
    view = await world.services.quote_commands.answer_finding(
        AN.context(),
        case.case_id,
        "customer_unknown:-",
        case_version=case.case_version,
        customer_code=case.customer_code,
    )
    assert view.status == QuoteStatus.YCBG_DRAFTED.value


async def test_pressing_soan_ycbg_after_dw1_drafted_it_changes_nothing() -> None:
    world = _world()
    case = await _quote(world, "M10")
    view = await world.services.quote_commands.ycbg(
        AN.context(), case.case_id, case_version=case.case_version, ycbg_no=None
    )
    assert view.case_version == case.case_version
    assert world.quote(case.case_id).case_version == case.case_version
