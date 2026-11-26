"""PC's mail read by DW1 while an order waits on PC (ticket 77): a proposal per
line that the PIC confirms or corrects, never a value recorded by itself.

Over the in-memory world with the fictional M04 order (three lines, each one
quantity on one date), asked of PC through `PcRequests`; the lane over M01
(VLX-PO-2609-0118) and PC's mails in a sample mailbox.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_kernel.errors import ConflictError
from dw_kernel.ports import Uuid4Generator
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.case_store import CaseEvent, EventActor
from dw_sales.application.pc_replies import PcReplyLane, answered_by
from dw_sales.application.ports import SalesScope
from dw_sales.domain.orders import Actor, OrderCase, OrderStatus
from dw_sales.evals.graders import AN, CALLERS, GIANG
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, World, measured_gate, open_world

from .test_pc_dates import FAILED, PC_MAIL, RIGHT, Answering
from .test_pc_requests import _in_review

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]

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


# ------------------------------------------------ the lane (ticket 77) --

PC_BOX = "pc@proterial.example"
PO_M01 = "VLX-PO-2609-0118"


class _Scopes:
    def __init__(self, *scopes: SalesScope) -> None:
        self._scopes = list(scopes)

    async def scopes(self) -> list[SalesScope]:
        return self._scopes


class _Down(Recorded):
    """A model server that is down."""

    def __init__(self) -> None:
        super().__init__(raw={})

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        raise ModelUnavailableError("down")


@dataclass
class Rig:
    world: World
    case_id: uuid.UUID
    model: Any
    lane: PcReplyLane
    sample: Any

    def told(self) -> list[Any]:
        return [n for n in self.world.notifications.sent if "PC" in n.title]


def _mail(message_id: str = "PC01", **kw: Any) -> dict[str, Any]:
    return {**PC_MAIL, "message_id": message_id, **kw}


async def _rig(
    mails: Sequence[dict[str, Any]],
    *,
    model: Any = None,
    switch: bool = True,
    mailboxes: tuple[str, ...] = (PC_BOX,),
    ask: bool = True,
) -> Rig:
    from dw_sales.adapters.mock.fixtures import DATA_DIR
    from dw_sales.adapters.order_rules import load_tenant_order_rules
    from dw_sales.evals.world import SampleWith

    model = model or Answering(RIGHT)
    sample = SampleWith(list(mails))
    data = sample.__enter__()
    world = open_world(REPO, data, CALLERS, model=model, measured=False)
    ((disposition, _),) = (await world.process_each(AN, ["M01"])).values()
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
    own = load_tenant_order_rules(DATA_DIR / "policies")
    assert own is not None
    world.store.rule_versions.seed_approved(
        ALPHA.tenant_id.value,
        own.model_copy(
            update={
                "policy_version": "1.5.9",
                "pc_mailboxes": mailboxes,
                "model_assist": own.model_assist.model_copy(update={"pc_reply": switch}),
            }
        ),
    )
    if ask:
        await world.services.pc_requests.ask(
            AN.context(), case_id, case_version=world.order(case_id).case_version
        )
    gate, _ = measured_gate(REPO, ALPHA)
    lane = PcReplyLane(
        uow=world.store,
        scopes=_Scopes(ALPHA),
        inbox=world.inbox,
        rules=world.services.pc_dates.rules,  # type: ignore[arg-type]
        steps=gate,
        model=model,
        notifications=world.notifications,
        clock=world.store.clock,
        ids=Uuid4Generator(),
        worker_id="sales",
        worker_version="1.0.0",
    )
    return Rig(world, case_id, model, lane, sample)


async def test_pcs_reply_is_proposed_on_the_case_with_no_pic_action_and_never_recorded() -> None:
    """Ticket 77's acceptance: a PC reply in the mock mailbox proposes its
    dates on the case by itself; nothing is recorded, the wait stays open,
    and the PIC is told once, with no PO number."""
    rig = await _rig([_mail()])
    try:
        tick = await rig.lane.tick()
        case = rig.world.order(rig.case_id)
        assert (tick.read, tick.proposed) == (1, 1)
        assert _lines(case) == {1: date(2026, 10, 30), 2: date(2026, 11, 5)}
        assert case.pc_reply is not None
        assert [d.quote for d in case.pc_reply.dates] == ["30/10/2026", "05/11"]
        assert all(line.pc_answer is None for line in case.lines)
        assert case.pc_request is not None
        (told,) = rig.told()
        assert AN.user_id in told.recipients
        assert PO_M01 not in told.title + told.body
        assert "sales.order.pc_reply_read" in [e.action for e in rig.world.audit()]

        calls = len(rig.model.calls)
        again = await rig.lane.tick()
        assert again.read == 0 and len(rig.model.calls) == calls  # read once
    finally:
        rig.sample.__exit__(None, None, None)


@pytest.mark.parametrize(
    "mail",
    [
        # From a colleague's address, not one of PC's mailboxes.
        _mail(sender="kho@proterial.example"),
        # The customer's own mail naming its PO.
        _mail(sender="an.trinh@velatrix.example"),
        # Not verified by the mail system.
        _mail(authentication=FAILED),
        # Received before PC was asked.
        _mail(received_at="2026-10-01T09:00:00+07:00"),
        # About another order.
        _mail(subject="Ngày giao VLX-PO-2609-0999"),
    ],
    ids=["colleague", "customer", "unverified", "before_request", "other_order"],
)
async def test_a_mail_that_is_not_pcs_answer_to_this_wait_proposes_nothing(
    mail: dict[str, Any],
) -> None:
    rig = await _rig([mail])
    try:
        await rig.lane.tick()
        assert rig.world.order(rig.case_id).pc_reply is None
        assert rig.model.calls == [] and rig.told() == []
    finally:
        rig.sample.__exit__(None, None, None)


@pytest.mark.parametrize(
    "setup",
    [{"switch": False}, {"mailboxes": ()}, {"ask": False}],
    ids=["switch_off", "no_pc_mailbox", "not_waiting"],
)
async def test_off_unconfigured_or_not_waiting_reads_nothing(setup: dict[str, Any]) -> None:
    rig = await _rig([_mail()], **setup)
    try:
        tick = await rig.lane.tick()
        assert tick.read == 0 and rig.model.calls == []
        assert rig.world.order(rig.case_id).pc_reply is None
    finally:
        rig.sample.__exit__(None, None, None)


async def test_a_step_not_measured_for_the_tenant_reads_nothing() -> None:
    rig = await _rig([_mail()])
    try:
        unmeasured, _ = measured_gate(REPO)
        await replace(rig.lane, steps=unmeasured).tick()
        assert rig.model.calls == [] and rig.world.order(rig.case_id).pc_reply is None
    finally:
        rig.sample.__exit__(None, None, None)


async def test_while_dw1_is_paused_nothing_is_kept() -> None:
    rig = await _rig([_mail()])
    try:
        await rig.world.services.worker.pause(GIANG.context(), "test")
        await rig.lane.tick()
        assert rig.world.order(rig.case_id).pc_reply is None
    finally:
        rig.sample.__exit__(None, None, None)


async def test_a_model_down_keeps_nothing_and_the_mail_is_read_again_next_tick() -> None:
    rig = await _rig([_mail()], model=_Down())
    try:
        await rig.lane.tick()
        await rig.lane.tick()
        assert rig.world.order(rig.case_id).pc_reply is None
        assert len(rig.model.calls) == 2
    finally:
        rig.sample.__exit__(None, None, None)


async def test_a_mail_read_to_no_date_is_kept_as_read_and_not_read_again() -> None:
    rig = await _rig([_mail()], model=Answering({"dates": []}))
    try:
        await rig.lane.tick()
        await rig.lane.tick()
        reply = rig.world.order(rig.case_id).pc_reply
        assert reply is not None and reply.dates == () and reply.messages == ("PC01",)
        assert len(rig.model.calls) == 1 and rig.told() == []
    finally:
        rig.sample.__exit__(None, None, None)


QUOTED = (
    "Đã nhận, PC sẽ báo sau.\n\n"
    "-----Original Message-----\n"
    "From: an.nguyen@alpha.local\n"
    "Subject: [Hỏi PC] Ngày giao cho PO VLX-PO-2609-0118\n\n"
    "- Dòng 1: khách cần ngày 30/10/2026\n"
)


async def test_a_reply_quoting_only_dws_request_proposes_nothing() -> None:
    """PC replies above DW1's request, which prints the customer's requested
    date; only PC's own words are read, so that date is never PC's."""
    model = Answering(RIGHT)
    rig = await _rig([_mail(body=QUOTED)], model=model)
    try:
        await rig.lane.tick()
        _, _, inputs = model.calls[-1]
        assert "30/10/2026" not in inputs["mail"]
        reply = rig.world.order(rig.case_id).pc_reply
        assert reply is not None and reply.dates == ()
    finally:
        rig.sample.__exit__(None, None, None)


@dataclass
class _Header:
    po_no: str


@dataclass
class _Document:
    header: _Header


@dataclass
class _Request:
    at: datetime


@dataclass
class _Waiting:
    document: _Document
    pc_request: _Request
    bravo_so_no: None = None
    pc_reply: None = None


def test_a_mail_naming_two_waiting_orders_answers_neither() -> None:
    """Line numbers repeat across orders: a mail naming both is left to the
    person's own list, never read into either."""
    message = InboundMessage.model_validate(
        {
            "message_id": "PC09",
            "sender": {"address": PC_BOX},
            "subject": "Ngày giao VLX-PO-2609-0118 và NRV-PO-26-0457",
            "received_at": datetime(2026, 10, 28, 2, tzinfo=UTC),
            "body_text": "Dòng 1 giao ngày 30/10/2026.",
            "authentication": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
        }
    )
    asked = _Request(datetime(2026, 10, 5, tzinfo=UTC))
    one = _Waiting(_Document(_Header(PO_M01)), asked)
    two = _Waiting(_Document(_Header("NRV-PO-26-0457")), asked)
    pc = frozenset({PC_BOX})
    assert answered_by(message, [one], pc) is one  # type: ignore[list-item]
    assert answered_by(message, [one, two], pc) is None  # type: ignore[list-item]
