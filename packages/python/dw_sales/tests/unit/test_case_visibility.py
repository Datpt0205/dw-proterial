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
from dw_sales.application.inbox_service import _shown
from dw_sales.application.visibility import sees_case
from dw_sales.domain.dispositions import (
    CaseKind,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
)
from dw_sales.domain.orders import OrderCase
from dw_sales.domain.quotes import QuoteCase
from dw_sales.evals.graders import AN, CALLERS, DIEU, GIANG, KHOA
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


@pytest.mark.parametrize(
    ("caller", "export_held", "seen"),
    [
        (AN, True, True),  # holds sales.compliance.ack: the hold is theirs to decide
        (AN, False, False),  # acknowledged, or never held: the assignee's again
        (KHOA, True, False),  # prepares orders, acknowledges nothing
    ],
)
def test_the_export_control_pic_sees_an_order_only_while_it_holds_on_them(
    caller: Caller, export_held: bool, seen: bool
) -> None:
    """Sales ticket 78: the export-control PIC is told of an NOC/ESF hold on
    an order that is not theirs, so they may open it while it holds."""
    assert (
        sees_case(_restricted(caller), CaseKind.ORDER, "in_review", OTHER, export_held=export_held)
        is seen
    )


async def _held_order_of_dieu(world: World) -> OrderCase:
    """M03 (no NOC/ESF on file) processed, then given to Diệu by the head."""
    ((_, case),) = (await world.process_each(AN, ["M03"])).values()
    assert isinstance(case, OrderCase) and case.awaits_export_control, case
    await world.services.assignment.reassign(
        GIANG.context(),
        CaseKind.ORDER,
        case.case_id,
        assignee=DIEU.user_id,
        case_version=case.case_version,
    )
    return world.order(case.case_id)


async def test_the_export_control_pic_opens_and_decides_a_hold_on_anothers_order() -> None:
    """In a restricted tenant An (the export-control PIC) reads Diệu's held
    order and acknowledges the hold; once acknowledged it reads as not found
    to An again. Khoa, who prepares orders but acknowledges nothing, never
    reads it."""
    world = _world()
    held = await _held_order_of_dieu(world)
    services = world.services
    an, khoa = _restricted(AN), _restricted(KHOA)

    with pytest.raises(NotFoundError):
        await services.orders.get(khoa, held.case_id)
    assert held.case_id not in {s.case_id for s in await services.orders.summaries(khoa)}

    assert (await services.orders.get(an, held.case_id)).case_id == held.case_id
    assert held.case_id in {s.case_id for s in await services.orders.summaries(an)}
    await services.order_commands.dispose(
        an,
        held.case_id,
        "missing_noc_esf:-",
        case_version=held.case_version,
        disposition="accepted",
        reason="Đã nhận NOC và ESF năm nay",
    )
    assert not world.order(held.case_id).awaits_export_control
    with pytest.raises(NotFoundError):
        await services.orders.get(an, held.case_id)


async def test_a_mail_routed_to_a_named_pic_is_theirs_and_their_heads_alone() -> None:
    """M11 (a delivery change) is routed to the customer's Sales PIC, whom
    master data knows by address. Until 2026-11-12 the inbox read that owner
    as a user id, so in a restricted tenant the mail was shown to nobody:
    not the PIC it was routed to, not the head (the DW1 walk on CI)."""
    world = _world()
    await world.process_each(AN, ["M11"])
    (logged,) = [
        m for m in await world.services.inbox.messages(AN.context()) if m.message_id == "M11"
    ]
    assert logged.disposition.kind == "routed_to_sales"
    assert logged.disposition.owner == AN.member().email

    async def sees(context: AccessContext) -> bool:
        return "M11" in {m.message_id for m in await world.services.inbox.messages(context)}

    assert await sees(_restricted(AN))
    assert await sees(_restricted(GIANG, AN, DIEU))
    # Another PIC, and a head the owner does not report to, are not shown it.
    assert not await sees(_restricted(DIEU))
    assert not await sees(_restricted(GIANG, DIEU))


def test_a_routed_mail_whose_pic_is_no_member_is_every_pics_to_pick_up() -> None:
    """A customer's Sales PIC who left is an address no member holds. Their
    case is unassigned (the pool's), and so is their routed mail: hiding it
    would show it to nobody."""
    gone = MessageDisposition(
        message_id="X1",
        kind=DispositionKind.ROUTED_TO_SALES,
        reason=RoutingReason.COMPLAINT,
        owner="nguoi.da.nghi@alpha.local",
    )
    members = {AN.member().email.lower(): AN.user_id}  # type: ignore[union-attr]
    assert _shown(_restricted(DIEU), gone, set(), members)
    # The same mail for a member the caller does not see stays hidden.
    theirs = gone.model_copy(update={"owner": AN.member().email})
    assert not _shown(_restricted(DIEU), theirs, set(), members)
    assert _shown(_restricted(AN), theirs, set(), members)
