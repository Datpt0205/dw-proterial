"""PC's mail read by DW1 while an order waits on PC (ticket 77): a proposal per
line that the PIC confirms or corrects, never a value recorded by itself.

Over the in-memory world with the fictional M04 order (three lines, each one
quantity on one date), asked of PC through `PcRequests`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from dw_kernel.errors import ConflictError
from dw_sales.application.case_store import CaseEvent, EventActor
from dw_sales.domain.orders import Actor, OrderCase
from dw_sales.evals.graders import AN
from dw_sales.evals.world import ALPHA, World

from .test_pc_requests import _in_review

pytestmark = pytest.mark.unit

DEC_05, DEC_12 = date(2026, 12, 5), date(2026, 12, 12)
MINUTE = timedelta(minutes=1)


async def _asked() -> tuple[World, uuid.UUID]:
    world, case_id = await _in_review()
    await world.services.pc_requests.ask(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )
    return world, case_id


def _read(case: OrderCase, message_id: str, *dates: tuple[int, date], late: int = 1) -> OrderCase:
    asked = (
        case.pc_request.at if case.pc_request is not None else datetime(2026, 11, 20, tzinfo=UTC)
    )
    at = asked + late * MINUTE
    return case.read_pc_reply(
        message_id,
        at,
        [(line_no, 1, day, day.strftime("%d/%m/%Y")) for line_no, day in dates],
        at=at,
        prompt_ref="sales.pc_dates@1.0.0",
        model_profile="test",
    )


def _lines(case: OrderCase) -> dict[int, date]:
    assert case.pc_reply is not None
    return {d.line_no: d.date for d in case.pc_reply.dates}


async def test_a_read_reply_proposes_dates_and_records_nothing() -> None:
    world, case_id = await _asked()
    case = world.order(case_id)

    read = _read(case, "PC01", (1, DEC_05), (2, DEC_12))

    assert _lines(read) == {1: DEC_05, 2: DEC_12}
    assert read.lines == case.lines  # no answer recorded, no value changed
    assert read.pc_request == case.pc_request and read.case_version == case.case_version + 1


async def test_a_reply_is_read_only_while_waiting_after_the_request_and_once() -> None:
    world, case_id = await _in_review()
    with pytest.raises(ConflictError, match="does not wait on PC"):
        _read(world.order(case_id), "PC01", (1, DEC_05))

    world, case_id = await _asked()
    case = world.order(case_id)
    with pytest.raises(ConflictError, match="before PC was asked"):
        _read(case, "PC01", (1, DEC_05), late=-1)
    once = _read(case, "PC01", (1, DEC_05))
    with pytest.raises(ConflictError, match="read already"):
        _read(once, "PC01", (2, DEC_12))


async def test_two_mails_answering_different_lines_both_stand_and_the_newer_wins_a_line() -> None:
    world, case_id = await _asked()
    first = _read(world.order(case_id), "PC01", (1, DEC_05))
    second = _read(first, "PC02", (2, DEC_12), late=2)
    assert _lines(second) == {1: DEC_05, 2: DEC_12}
    third = _read(second, "PC03", (1, DEC_12), late=3)
    assert _lines(third) == {1: DEC_12, 2: DEC_12}
    # An older mail read late does not overwrite a newer one's line.
    fourth = _read(third, "PC00", (1, DEC_05), late=1)
    assert _lines(fourth)[1] == DEC_12
    assert fourth.pc_reply is not None and fourth.pc_reply.messages == (
        "PC01",
        "PC02",
        "PC03",
        "PC00",
    )


async def test_a_mail_with_no_date_is_still_remembered_as_read() -> None:
    world, case_id = await _asked()
    read = _read(world.order(case_id), "PC01")
    assert read.pc_reply is not None and read.pc_reply.dates == ()
    with pytest.raises(ConflictError, match="read already"):
        _read(read, "PC01", (1, DEC_05))


async def test_asking_again_starts_a_new_wait_with_nothing_proposed() -> None:
    world, case_id = await _asked()
    read = _read(world.order(case_id), "PC01", (1, DEC_05))
    again = read.ask_pc(Actor(user_id=AN.user_id), read.pc_request.at + 5 * MINUTE)  # type: ignore[union-attr]
    assert again.pc_reply is None


async def test_answering_a_line_drops_its_proposal_and_the_last_answer_ends_both() -> None:
    """The person's answer consumes the line's proposal; answering the last
    line asked closes the wait and the proposal with it, never refused."""
    world, case_id = await _asked()
    read = _read(world.order(case_id), "PC01", (1, DEC_05), (2, DEC_12))
    async with world.store(ALPHA) as work:
        await work.orders.save(
            read,
            expected_version=read.case_version - 1,
            event=CaseEvent(
                action="order.pc_reply_read",
                actor=EventActor.worker("dw1", "1.0.0", initiated_by=None),
                occurred_at=read.pc_request.at,  # type: ignore[union-attr]
            ),
        )
        await work.commit()

    async def answer(line_no: int) -> None:
        line = world.order(case_id).line(line_no)
        await world.services.pc_requests.answer(
            AN.context(),
            case_id,
            line_no,
            case_version=world.order(case_id).case_version,
            deliveries=[(line.effective.quantity, DEC_05)],
        )

    await answer(1)
    assert _lines(world.order(case_id)) == {2: DEC_12}
    await answer(3)
    await answer(2)
    after = world.order(case_id)
    assert after.pc_request is None and after.pc_reply is None


async def test_a_proposal_names_only_lines_asked_and_never_outlives_the_wait() -> None:
    world, case_id = await _asked()
    case = world.order(case_id)
    read = _read(case, "PC01", (1, DEC_05))
    assert read.pc_reply is not None
    document = {**dict(read), "pc_request": None}
    with pytest.raises(ValidationError, match="only while the case waits on PC"):
        OrderCase.model_validate(document)
    stray = read.pc_reply.model_copy(
        update={"dates": (read.pc_reply.dates[0].model_copy(update={"line_no": 9}),)}
    )
    with pytest.raises(ValidationError, match="only for the lines asked"):
        OrderCase.model_validate({**dict(read), "pc_reply": stray})
