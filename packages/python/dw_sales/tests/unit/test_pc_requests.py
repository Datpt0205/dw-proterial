"""The request to PC, its reminder, and lines split by PC's dates (ticket 07),
through the services the API serves.

Over the in-memory world (`dw_sales.evals.world`) with the fictional M04
order (NRV-PO-26-0457, three lines, each one quantity on one date). PC's
answer is typed by the person; DW1 sends PC nothing. The columns of the
paste sheet are `test_upload_rows_pinned.py`'s; the store's columns,
`test_sales_store.py` (integration).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import WorkspaceId
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_sales.adapters.policy_files import rule_book
from dw_sales.application.followups import FollowupLane
from dw_sales.application.order_artifacts import upload_rows
from dw_sales.application.ports import SalesScope
from dw_sales.domain.orders import Actor, AppliedChange, OrderCase, OrderStatus
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER, READER
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world
from dw_sales.evals.world import Directory as Holders

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
HOUR = timedelta(hours=1)
NOV_20, DEC_05, DEC_12 = date(2026, 11, 20), date(2026, 12, 5), date(2026, 12, 12)


async def _in_review() -> tuple[World, uuid.UUID]:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    ((disposition, _),) = (await world.process_each(AN, ["M04"])).values()
    case_id = disposition.case_id
    assert case_id is not None
    case = world.order(case_id)
    if case.status is OrderStatus.CHECKED:
        await world.services.order_commands.dispose(
            AN.context(),
            case_id,
            case.findings[0].key,
            case_version=case.case_version,
            disposition="open",
        )
    assert world.order(case_id).status is OrderStatus.IN_REVIEW
    assert not any(line.po_line.prints_schedules for line in world.order(case_id).lines)
    return world, case_id


def _quantity(case: OrderCase, line_no: int) -> Decimal:
    return case.line(line_no).effective.quantity


async def _answer(
    world: World, case_id: uuid.UUID, line_no: int, *deliveries: tuple[Decimal, date], **kw: Any
) -> Any:
    return await world.services.pc_requests.answer(
        kw.pop("context", AN.context()),
        case_id,
        line_no,
        case_version=kw.pop("case_version", world.order(case_id).case_version),
        deliveries=list(deliveries),
    )


async def _answer_all(world: World, case_id: uuid.UUID) -> None:
    for line in world.order(case_id).lines:
        await _answer(world, case_id, line.line_no, (line.effective.quantity, DEC_05))


# --------------------------------------------------------------- "Hỏi PC" --


async def test_the_request_is_drafted_from_the_case_and_changes_nothing() -> None:
    world, case_id = await _in_review()
    before = world.order(case_id)

    draft = await world.services.pc_requests.draft(AN.context(), case_id)

    assert draft.lines == [1, 2, 3]
    assert draft.template_ref == "sales_handoffs@1.1.0#pc_request"
    assert before.header.po_no in draft.subject
    assert draft.body.count("- Dòng ") == 3
    assert "06/11/2026" in draft.body  # line 1's requested date, as entered
    assert draft.reminder_at is None
    assert world.order(case_id) == before


async def test_recording_asked_starts_the_wait_and_the_draft_names_the_next_reminder() -> None:
    world, case_id = await _in_review()
    before = world.order(case_id)

    change = await world.services.pc_requests.ask(
        AN.context(), case_id, case_version=before.case_version
    )
    draft = await world.services.pc_requests.draft(AN.context(), case_id)

    after = world.order(case_id)
    assert change.case_version == before.case_version + 1 == after.case_version
    assert after.pc_request is not None
    assert after.pc_request.lines == (1, 2, 3) and after.pc_request.by == AN.user_id
    assert after.status is OrderStatus.IN_REVIEW and after.lines == before.lines
    asked = after.pc_request.at
    # The tenant's `waiting_pc` hours (24 on the platform), never a constant.
    assert draft.reminder_at == asked + 24 * HOUR
    (audited,) = [e for e in world.audit() if e.action == "sales.order.pc_asked"]
    assert audited.resource_id == str(case_id)


# ----------------------------------------------------- acceptance 1: split --


async def test_a_line_pc_splits_in_two_is_two_deliveries_and_two_rows() -> None:
    """Acceptance 1: two deliveries whose quantities add up to the line's,
    each a row of the paste sheet with PC's dates; the case takes its next
    version, the audit row is written with it."""
    world, case_id = await _in_review()
    before = world.order(case_id)
    whole = _quantity(before, 1)
    first, second = whole - 1, Decimal(1)

    change = await _answer(world, case_id, 1, (first, NOV_20), (second, DEC_12))

    after = world.order(case_id)
    assert change.case_version == before.case_version + 1
    line = after.line(1)
    assert line.deliveries == 2 and line.delivery_quantities == (first, second)
    assert line.pc_answer is not None and line.pc_answer.by == AN.user_id
    assert [(d.quantity, d.first_date, d.date) for d in line.pc_answer.deliveries] == [
        (first, NOV_20, NOV_20),
        (second, DEC_12, DEC_12),
    ]
    assert line.po_line == before.line(1).po_line  # the PO's values stay as read
    rows = upload_rows(after, line)
    assert [(r["quantity"], r["first_confirmed_date"], r["confirmed_date"]) for r in rows] == [
        (first, NOV_20, NOV_20),
        (second, DEC_12, DEC_12),
    ]
    assert {r["requested_date"] for r in rows} == {line.effective.requested_date}
    assert {r["line_no"] for r in rows} == {1}
    assert AN.user_id in after.makers
    assert any(
        e.action == "sales.order.pc_answer_recorded" and e.resource_id == str(case_id)
        for e in world.audit()
    )
    # The confirmation then takes one date per PC delivery.
    assert after.line(2).deliveries == 1


async def test_a_split_that_does_not_add_up_is_refused_never_adjusted() -> None:
    world, case_id = await _in_review()
    before = world.order(case_id)
    whole = _quantity(before, 1)

    with pytest.raises(ConflictError) as refused:
        await _answer(world, case_id, 1, (whole, NOV_20), (Decimal(1), DEC_12))

    assert refused.value.details["rule"] == "split_not_summing"
    assert world.order(case_id) == before


async def test_a_line_the_case_does_not_have_takes_no_answer() -> None:
    world, case_id = await _in_review()
    before = world.order(case_id)
    with pytest.raises(ConflictError):
        await _answer(world, case_id, 99, (Decimal(5), NOV_20))
    assert world.order(case_id) == before


# ------------------------------------------- acceptance 2: re-confirmation --


async def test_a_re_confirmation_keeps_the_first_confirmed_date() -> None:
    """Acceptance 2: PC confirms line 2 again with a later date: the first
    date stays, the current one is the new one, and the paste sheet carries
    both (Bravo's "Ngày XN giao hàng lần đầu" and "Ngày XN giao hàng")."""
    world, case_id = await _in_review()
    whole = _quantity(world.order(case_id), 2)
    await _answer(world, case_id, 2, (whole, NOV_20))

    await _answer(world, case_id, 2, (whole, DEC_05))

    line = world.order(case_id).line(2)
    assert line.pc_answer is not None
    ((only),) = line.pc_answer.deliveries
    assert (only.first_date, only.date) == (NOV_20, DEC_05)
    ((row),) = upload_rows(world.order(case_id), line)
    assert (row["first_confirmed_date"], row["confirmed_date"]) == (NOV_20, DEC_05)


async def test_a_line_split_anew_keeps_the_lines_first_date_on_every_delivery() -> None:
    world, case_id = await _in_review()
    whole = _quantity(world.order(case_id), 2)
    await _answer(world, case_id, 2, (whole, NOV_20))

    await _answer(world, case_id, 2, (whole - 1, DEC_05), (Decimal(1), DEC_12))

    answer = world.order(case_id).line(2).pc_answer
    assert answer is not None
    assert [(d.first_date, d.date) for d in answer.deliveries] == [
        (NOV_20, DEC_05),
        (NOV_20, DEC_12),
    ]


# ----------------------------------------------------------- the wait ends --


async def test_the_wait_ends_with_the_last_lines_answer() -> None:
    world, case_id = await _in_review()
    await world.services.pc_requests.ask(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )
    whole = _quantity(world.order(case_id), 1)
    await _answer(world, case_id, 1, (whole, NOV_20))
    assert world.order(case_id).pc_request is not None

    await _answer_all(world, case_id)

    assert world.order(case_id).pc_request is None
    draft = await world.services.pc_requests.draft(AN.context(), case_id)
    # Every line answered: asking again asks PC to confirm them all again.
    assert draft.lines == [1, 2, 3] and draft.reminder_at is None


async def test_a_customer_change_drops_pcs_answer_for_that_line() -> None:
    """PC answered for a quantity or a date the customer has since changed:
    the line is asked again (`OrderCase.changed`)."""
    world, case_id = await _in_review()
    whole = _quantity(world.order(case_id), 1)
    await _answer(world, case_id, 1, (whole - 1, NOV_20), (Decimal(1), DEC_12))
    case = world.order(case_id)
    change = AppliedChange(
        field="quantity",
        value=str(whole + 1),
        request_id=uuid.uuid4(),
        by=AN.user_id,
        at=case.received_at,
    )

    corrected = case.changed(1, change, Actor(user_id=AN.user_id))

    (line,) = [x for x in corrected.lines if x.line_no == 1]
    assert line.pc_answer is None and line.deliveries == 1


# ------------------------------------------------------ the reminder lane --


def _lane(world: World, clock: FixedClock) -> FollowupLane:
    return FollowupLane(
        uow=world.store,
        policies=rule_book(world.policies, world.store.rule_versions),
        holders=Holders(CALLERS),
        notifications=world.notifications,
        clock=clock,
        ids=Uuid4Generator(),
    )


async def _pc_reminders(world: World, case_id: uuid.UUID, hours: int) -> list[str]:
    asked = world.order(case_id).pc_request
    since = asked.at if asked is not None else world.store.clock.now()
    clock = FixedClock(since + hours * HOUR)
    sent = (await _lane(world, clock).tick(ALPHA)).sent
    return [key for key in sent if ":waiting_pc:" in key]


async def test_the_pic_is_reminded_when_pc_has_not_answered() -> None:
    world, case_id = await _in_review()
    await world.services.pc_requests.ask(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )
    assert await _pc_reminders(world, case_id, 23) == []
    assert len(await _pc_reminders(world, case_id, 24)) == 1


async def test_no_pc_reminder_is_raised_after_the_answer() -> None:
    """The reminder stops once PC's dates are recorded (failure-modes #6)."""
    world, case_id = await _in_review()
    await world.services.pc_requests.ask(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )
    asked = world.order(case_id).pc_request
    assert asked is not None
    await _answer_all(world, case_id)

    clock = FixedClock(asked.at + 48 * HOUR)
    sent = (await _lane(world, clock).tick(ALPHA)).sent
    assert not [key for key in sent if ":waiting_pc:" in key]


# ------------------------------------------------------- trust boundaries --


async def test_another_tenant_or_workspace_finds_no_order() -> None:
    world, case_id = await _in_review()
    version = world.order(case_id).case_version
    other_workspace = SalesScope(ALPHA.tenant_id, WorkspaceId(uuid.UUID(int=0xA1FC)))
    whole = _quantity(world.order(case_id), 1)

    for context in (OUTSIDER.context(BETA), AN.context(other_workspace)):
        with pytest.raises(NotFoundError):
            await world.services.pc_requests.draft(context, case_id)
        with pytest.raises(NotFoundError):
            await world.services.pc_requests.ask(context, case_id, case_version=version)
        with pytest.raises(NotFoundError):
            await _answer(world, case_id, 1, (whole, NOV_20), context=context, case_version=version)

    assert world.order(case_id).case_version == version


async def test_a_caller_without_the_prepare_scope_asks_and_records_nothing() -> None:
    world, case_id = await _in_review()
    version = world.order(case_id).case_version
    whole = _quantity(world.order(case_id), 1)

    with pytest.raises(PermissionDeniedError):
        await world.services.pc_requests.draft(READER.context(), case_id)
    with pytest.raises(PermissionDeniedError):
        await world.services.pc_requests.ask(READER.context(), case_id, case_version=version)
    with pytest.raises(PermissionDeniedError):
        await _answer(world, case_id, 1, (whole, NOV_20), context=READER.context())

    assert world.order(case_id).case_version == version


async def test_a_stale_case_version_is_refused() -> None:
    world, case_id = await _in_review()
    stale = world.order(case_id).case_version - 1
    whole = _quantity(world.order(case_id), 1)

    for call in (
        world.services.pc_requests.ask(AN.context(), case_id, case_version=stale),
        _answer(world, case_id, 1, (whole, NOV_20), case_version=stale),
    ):
        with pytest.raises(ConflictError) as refused:
            await call
        assert refused.value.details["rule"] == "stale_case_version"
    assert world.order(case_id).pc_request is None


async def test_pc_is_not_asked_from_dw1_once_the_order_left_review() -> None:
    """Once the order is in Bravo, PC's dates are the update loop's (ticket
    29); a closed case waits on nobody."""
    world, case_id = await _in_review()
    case = world.order(case_id)
    closed = case.model_validate(
        {
            **dict(case),
            "status": OrderStatus.CLOSED,
            "close_reason": "not_an_order",
            "closed_by": AN.user_id,
            "closed_at": case.received_at,
        }
    )
    with pytest.raises(ConflictError) as refused:
        closed.ask_pc(_actor(), case.received_at)
    assert refused.value.details["rule"] == "pc_status"
    with pytest.raises(ConflictError):
        closed.pc_answered(1, [(_quantity(case, 1), NOV_20)], _actor(), case.received_at)


def _actor() -> Actor:
    return Actor(user_id=AN.user_id)


async def test_a_case_that_leaves_review_waits_on_pc_no_longer() -> None:
    """Asking the customer to correct the PO moves the case out of review:
    PC's answer is no longer taken there, so nothing keeps reminding."""
    world, case_id = await _in_review()
    await world.services.pc_requests.ask(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )
    case = world.order(case_id)
    await world.services.order_commands.dispose(
        AN.context(),
        case_id,
        case.findings[0].key,
        case_version=case.case_version,
        disposition="ask_customer",
        reason="Nhờ khách gửi lại PO",
    )
    await world.services.order_commands.request_correction(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )

    after = world.order(case_id)
    assert after.status is OrderStatus.CORRECTION_REQUESTED
    assert after.pc_request is None
