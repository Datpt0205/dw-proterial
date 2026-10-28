"""Who sees which case in a tenant that narrows record reads (Đạt,
2026-10-28: "các sales thấy luôn cả các đơn hàng, báo giá của nhau à, đáng lẽ
chỉ có trưởng phòng thấy thôi"). The platform resolves `visible_owners` (the
person and their reports, ADR-003); a PIC sees their own cases, the pool's,
and the ones waiting on a check they may make. Everything else reads as not
found, on every path a person reads a case through."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from dw_kernel.errors import NotFoundError
from dw_platform.application.access_context import AccessContext
from dw_sales.application.visibility import sees_case
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.quotes import QuoteCase
from dw_sales.evals.graders import AN, CALLERS, DIEU, GIANG
from dw_sales.evals.world import Caller, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
OTHER = uuid.UUID(int=0xFEED)


def _restricted(caller: Caller, *reports: Caller) -> AccessContext:
    """The caller in a restricted tenant: themselves and their reports."""
    return caller.context().model_copy(
        update={
            "record_visibility": "restricted",
            "visible_owners": frozenset({caller.user_id, *(r.user_id for r in reports)}),
        }
    )


@pytest.mark.parametrize(
    ("kind", "status", "assigned_to", "seen"),
    [
        (CaseKind.QUOTE, "received", None, True),  # the pool
        (CaseKind.QUOTE, "received", AN.user_id, True),  # their own
        (CaseKind.QUOTE, "received", OTHER, False),  # someone else's
        (CaseKind.QUOTE, "pending_approval", OTHER, False),  # An approves no quote
        (CaseKind.ORDER, "uploaded_to_bravo", OTHER, True),  # a cross-check An may make
        (CaseKind.ORDER, "in_review", OTHER, False),
    ],
)
def test_a_pic_sees_their_own_the_pool_and_what_they_are_asked_to_check(
    kind: CaseKind, status: str, assigned_to: uuid.UUID | None, seen: bool
) -> None:
    assert sees_case(_restricted(AN), kind, status, assigned_to) is seen


def test_the_head_sees_their_reports_cases_and_an_open_tenant_sees_all() -> None:
    head = _restricted(GIANG, AN)
    assert sees_case(head, CaseKind.QUOTE, "received", AN.user_id)
    assert not sees_case(head, CaseKind.QUOTE, "received", OTHER)
    assert sees_case(AN.context(), CaseKind.QUOTE, "received", OTHER)


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _quote_of_dieu(world: World) -> QuoteCase:
    """M10's quote, given to Diệu by the head."""
    ((_, case),) = (await world.process_each(AN, ["M10"])).values()
    assert isinstance(case, QuoteCase)
    await world.services.assignment.reassign(
        GIANG.context(),
        CaseKind.QUOTE,
        case.case_id,
        assignee=DIEU.user_id,
        case_version=case.case_version,
    )
    return world.quote(case.case_id)


async def test_another_pics_quote_is_not_found_on_any_read() -> None:
    world = _world()
    quote = await _quote_of_dieu(world)
    an = _restricted(AN)
    services = world.services

    with pytest.raises(NotFoundError):
        await services.quotes.get(an, quote.case_id)
    with pytest.raises(NotFoundError):
        await services.pipeline.history(an, CaseKind.QUOTE, quote.case_id)
    with pytest.raises(NotFoundError):
        await services.artifacts.quote_artifacts(an, quote.case_id)
    assert quote.case_id not in {s.case_id for s in await services.quotes.summaries(an)}
    board = await services.pipeline.board(an)
    assert quote.case_id not in {card.case_id for card in board.cards}
    inbox = await services.inbox.messages(an)
    assert "M10" not in {m.message_id for m in inbox}
    # A write is refused the same way, before anything is decided.
    with pytest.raises(NotFoundError):
        await services.quote_commands.ycbg(
            an, quote.case_id, case_version=quote.case_version, ycbg_no="YCBG-1"
        )

    # Diệu, and the head she reports to, read it.
    assert (await services.quotes.get(_restricted(DIEU), quote.case_id)).case_id == quote.case_id
    head = _restricted(GIANG, AN, DIEU)
    assert quote.case_id in {s.case_id for s in await services.quotes.summaries(head)}
    assert "M10" in {m.message_id for m in await services.inbox.messages(head)}
