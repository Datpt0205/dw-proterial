"""A customer's change on an order already in Bravo, through PC and back to
the customer (ticket 29, dw_sales ADR 0010 decision 3), through the services
the API serves.

Over the in-memory world (`dw_sales.evals.world`) with the fictional M04
order (NRV-PO-26-0457: line 2, 3,600 m on 2026-12-04), walked to
`confirmed` (prepared and entered by An, cross-checked by Diệu), and a
synthetic B03-shaped reply in its thread asking to pull line 2 in to
2026-11-20. Ticket 27's reading is `test_change_request_flow.py`'s; PC's
answer before Bravo, `test_pc_requests.py`'s; the store's column,
`test_update_loop_db.py` (integration).
"""

from __future__ import annotations

import io
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import WorkspaceId
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_sales.adapters.policy_files import rule_book
from dw_sales.application.followups import FollowupLane
from dw_sales.application.order_artifacts import upload_rows
from dw_sales.application.ports import SalesScope
from dw_sales.domain.orders import (
    ALLOWED_DISPOSITIONS,
    DispositionKind,
    OrderCase,
    OrderStatus,
)
from dw_sales.evals.graders import AN, CALLERS, DIEU, OUTSIDER, READER
from dw_sales.evals.world import ALPHA, BETA, SampleWith, World, open_world
from dw_sales.evals.world import Directory as Holders

from .test_change_request_flow import PO, _reply, _table

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
HOUR = timedelta(hours=1)
HELD, ASKED, LATER = date(2026, 12, 4), date(2026, 11, 20), date(2026, 11, 25)
QUANTITY = Decimal(3600)
PULL_IN = _table(("58102", "2", PO, "NV-CB4-22-GY", "04-12-26", "20-11-26"))
# The fields of the case an update loop moves; everything else must be as it was.
_LOOP_FIELDS = {"case_version", "update_loop"}


def _version(world: World, case_id: uuid.UUID) -> int:
    return world.order(case_id).case_version


async def _confirmed(world: World) -> uuid.UUID:
    """M04 with every finding decided, prepared and entered in Bravo by An,
    cross-checked by Diệu and confirmed: the order a change arrives on."""
    ((disposition, _),) = (await world.process_each(AN, ["M04"])).values()
    case_id = disposition.case_id
    assert case_id is not None
    commands = world.services.order_commands
    await commands.confirm_mapping(
        AN.context(), case_id, 3, case_version=_version(world, case_id), prv_code="CB-2008"
    )
    for _ in range(20):
        finding = next((f for f in world.order(case_id).findings if f.is_open), None)
        if finding is None:
            break
        assert DispositionKind.ACCEPTED in ALLOWED_DISPOSITIONS[finding.code], finding.key
        await commands.dispose(
            AN.context(),
            case_id,
            finding.key,
            case_version=_version(world, case_id),
            disposition="accepted",
            reason="Đã kiểm tra với khách",
        )
    await world.walk_to_uploaded(AN, case_id)
    await world.cross_check(DIEU, case_id)
    case = await world.confirm(AN, case_id, HELD)
    assert case.status is OrderStatus.CONFIRMED
    assert case.line(2).effective.requested_date == HELD
    return case_id


async def _in_loop(world: World) -> tuple[uuid.UUID, OrderCase]:
    """The confirmed order, its reply read and its one change line confirmed:
    the loop waits to ask PC. Returns the order as it was before the change."""
    case_id = await _confirmed(world)
    await world.process_each(AN, ["R1"])
    before = world.order(case_id)
    opened = await world.services.change_requests.open(
        AN.context(), case_id, case_version=before.case_version, message_id="R1"
    )
    await world.services.change_requests.confirm(
        AN.context(), case_id, opened.request.request_id, 1, case_version=_version(world, case_id)
    )
    return case_id, before


async def _asked(world: World, case_id: uuid.UUID) -> None:
    await world.services.update_loops.ask_pc(
        AN.context(), case_id, case_version=_version(world, case_id)
    )


async def _pc(world: World, case_id: uuid.UUID, *deliveries: tuple[Decimal, date]) -> Any:
    return await world.services.update_loops.pc_answer(
        AN.context(), case_id, 2, case_version=_version(world, case_id), deliveries=deliveries
    )


async def _sent(world: World, case_id: uuid.UUID) -> None:
    await world.services.update_loops.answer_sent(
        AN.context(), case_id, case_version=_version(world, case_id)
    )


async def _answer(world: World, case_id: uuid.UUID, answer: Any, **kw: Any) -> Any:
    return await world.services.update_loops.customer_answer(
        kw.pop("context", AN.context()),
        case_id,
        case_version=kw.pop("case_version", _version(world, case_id)),
        answer=answer,
    )


async def _waiting_customer(world: World, *deliveries: tuple[Decimal, date]) -> uuid.UUID:
    case_id, _ = await _in_loop(world)
    await _asked(world, case_id)
    await _pc(world, case_id, *(deliveries or ((QUANTITY, ASKED),)))
    await _sent(world, case_id)
    return case_id


async def _render(world: World, case_id: uuid.UUID, kind: str) -> Any:
    (record,) = await world.services.artifacts.render_order(
        AN.context(), case_id, kind=kind, case_version=_version(world, case_id)
    )
    return record


def _world(sample: Any) -> World:
    return open_world(REPO, sample, CALLERS)


def _actions(world: World, case_id: uuid.UUID) -> list[str]:
    return [e.action for e in world.audit() if e.resource_id == str(case_id)]


# --------------------------------------------------------- the change --


async def test_a_change_on_a_confirmed_order_joins_the_loop_and_changes_nothing_yet() -> None:
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, before = await _in_loop(world)
        draft = await world.services.update_loops.pc_request(AN.context(), case_id)

    after = world.order(case_id)
    loop = after.update_loop
    assert loop is not None and loop.step == "ask_pc"
    ((line_no, change),) = [(x.line_no, c) for x in loop.lines for c in x.changes]
    assert (line_no, change.field, change.value) == (2, "requested_date", "2026-11-20")
    # The order itself waits on PC and the customer before it changes.
    assert after.status is OrderStatus.CONFIRMED
    assert after.lines == before.lines
    # 6-DW2 is ticket 07's request with the value asked, for a person to copy.
    assert draft.template_ref == "sales_handoffs@1.1.0#pc_request"
    assert draft.lines == [2] and "20/11/2026" in draft.body and "04/12/2026" not in draft.body
    assert "sales.order.update_change_confirmed" in _actions(world, case_id)


async def test_a_change_between_the_bravo_entry_and_the_confirmation_is_held() -> None:
    """Only an order Sales confirmed takes a change into the loop; awaiting
    its cross-check, the line stays open until the order is confirmed."""
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        ((disposition, _),) = (await world.process_each(AN, ["M04"])).values()
        case_id = disposition.case_id
        assert case_id is not None
        world_case = await _confirmed_until_uploaded(world, case_id)
        await world.process_each(AN, ["R1"])
        opened = await world.services.change_requests.open(
            AN.context(), case_id, case_version=world_case.case_version, message_id="R1"
        )
        with pytest.raises(ConflictError) as refused:
            await world.services.change_requests.confirm(
                AN.context(),
                case_id,
                opened.request.request_id,
                1,
                case_version=_version(world, case_id),
            )

    assert refused.value.details["rule"] == "change_status"
    assert world.order(case_id).update_loop is None


async def _confirmed_until_uploaded(world: World, case_id: uuid.UUID) -> OrderCase:
    commands = world.services.order_commands
    await commands.confirm_mapping(
        AN.context(), case_id, 3, case_version=_version(world, case_id), prv_code="CB-2008"
    )
    for _ in range(20):
        finding = next((f for f in world.order(case_id).findings if f.is_open), None)
        if finding is None:
            break
        await commands.dispose(
            AN.context(),
            case_id,
            finding.key,
            case_version=_version(world, case_id),
            disposition="accepted",
            reason="Đã kiểm tra với khách",
        )
    return await world.walk_to_uploaded(AN, case_id)


# ------------------------------------------- acceptance 1: through Bravo --


async def test_a_pull_in_walks_back_to_confirmed_with_every_draft_and_approval_recorded() -> None:
    """Acceptance 1: PC can deliver on the date asked, so 6-DW4 is drafted;
    the customer accepts; the PIC approves the exact Bravo update file (the
    changed line only, PC's first and current dates), it is entered and
    cross-checked by someone who made none of it, and the order is confirmed
    again with the new date. Every step is an event and an audit row, in
    order, and the loop ends."""
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, before = await _in_loop(world)
        await _asked(world, case_id)
        await _pc(world, case_id, (QUANTITY, ASKED))
        assert world.order(case_id).update_loop.verdict == "can_do"  # type: ignore[union-attr]
        available = (
            await world.services.artifacts.order_artifacts(AN.context(), case_id)
        ).available
        draft = await _render(world, case_id, "change_can_do_draft")
        mail = (
            await world.services.artifacts.order_artifact(AN.context(), case_id, draft.artifact_id)
        ).data
        await _sent(world, case_id)
        await _answer(world, case_id, "accept")
        accepted = world.order(case_id)
        full = await _render(world, case_id, "bravo_update")
        await world.services.update_loops.approve(
            AN.context(),
            case_id,
            case_version=_version(world, case_id),
            artifact_id=full.artifact_id,
        )
        approved = world.order(case_id)
        update_file = await world.services.artifacts.order_artifact(
            AN.context(), case_id, full.artifact_id
        )
        await world.services.dw1.record_bravo_entry(
            AN.context(),
            case_id,
            case_version=_version(world, case_id),
            so_no=None,
            entry_compared=True,
        )
        uploaded = world.order(case_id)
        upload_all = await _render(world, case_id, "bravo_upload")
        whole_file = await world.services.artifacts.order_artifact(
            AN.context(), case_id, upload_all.artifact_id
        )
        await world.cross_check(DIEU, case_id)
        confirmed = await world.confirm(AN, case_id, ASKED)

    assert "change_can_do_draft" in available and "change_options_draft" not in available
    assert b"Change to order NRV-PO-26-0457 confirmed" in mail
    # Accepted: the change applied with PC's answer, in change_review.
    assert (accepted.status, accepted.update_loop.step) == (  # type: ignore[union-attr]
        OrderStatus.CHANGE_REVIEW,
        "bravo_update",
    )
    line = accepted.line(2)
    assert line.effective.requested_date == ASKED and line.po_line.requested_date == HELD
    assert line.pc_answer is not None and line.confirmed_delivery_dates == ()
    ((row,),) = [upload_rows(accepted, line)]
    assert (row["first_confirmed_date"], row["confirmed_date"]) == (ASKED, ASKED)
    # The approval names the exact file, and the file holds the changed line only.
    approval = approved.update_loop.approval  # type: ignore[union-attr]
    assert approval is not None
    assert (approval.artifact_id, approval.sha256, approval.by) == (
        full.artifact_id,
        full.sha256,
        AN.user_id,
    )
    rows = load_workbook(io.BytesIO(update_file.data)).worksheets[0].max_row
    all_rows = load_workbook(io.BytesIO(whole_file.data)).worksheets[0].max_row
    assert all_rows - rows == len(before.lines) - 1
    assert uploaded.status is OrderStatus.UPLOADED_TO_BRAVO
    # Confirmed again: the loop ends, the line holds the new date.
    assert confirmed.status is OrderStatus.CONFIRMED and confirmed.update_loop is None
    assert confirmed.line(2).confirmed_delivery_dates == (ASKED,)
    assert confirmed.line(1).effective == before.line(1).effective
    actions = _actions(world, case_id)
    walk = [
        "sales.order.change_request_opened",
        "sales.order.update_change_confirmed",
        "sales.order.update_pc_asked",
        "sales.order.update_pc_answered",
        "sales.order.update_answer_sent",
        "sales.order.update_customer_answered",
        "sales.order.update_approved",
        "sales.order.bravo_recorded",
        "sales.order.cross_checked",
        "sales.order.confirmed",
    ]
    start = actions.index(walk[0])
    assert [a for a in actions[start:] if a in walk] == walk
    answered = [e for e in world.audit() if e.action == "sales.order.update_customer_answered"]
    assert [e.details.get("reason_code") for e in answered] == ["accept"]
    assert "3600" not in str([e.details for e in world.audit() if "update" in e.action])


async def test_pc_proposing_another_date_drafts_the_options_and_code_decides_it() -> None:
    """6-DW3: one of PC's deliveries is not on the date asked, so code drafts
    the options, never the confirmation of the change."""
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, _ = await _in_loop(world)
        await _asked(world, case_id)
        await _pc(world, case_id, (QUANTITY - 600, ASKED), (Decimal(600), LATER))
        available = (
            await world.services.artifacts.order_artifacts(AN.context(), case_id)
        ).available
        draft = await _render(world, case_id, "change_options_draft")
        mail = (
            await world.services.artifacts.order_artifact(AN.context(), case_id, draft.artifact_id)
        ).data

    assert world.order(case_id).update_loop.verdict == "proposes"  # type: ignore[union-attr]
    assert "change_options_draft" in available and "change_can_do_draft" not in available
    assert b"cannot deliver exactly as asked" in mail
    with pytest.raises(ConflictError):
        await world.services.artifacts.render_order(
            AN.context(), case_id, kind="change_can_do_draft", case_version=_version(world, case_id)
        )


# ------------------------------------------- acceptance 2: keep the PO --


async def test_a_customer_keeping_the_original_po_leaves_the_order_as_it_was() -> None:
    """Acceptance 2: the loop ends and every value of the order, its lines,
    PC's deliveries and its confirmation, is what it was before the change;
    the change request is closed. Only the version moved."""
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, before = await _in_loop(world)
        await _asked(world, case_id)
        await _pc(world, case_id, (QUANTITY - 600, ASKED), (Decimal(600), LATER))
        await _sent(world, case_id)
        await _answer(world, case_id, "keep")
        requests = await world.services.change_requests.for_case(AN.context(), case_id)

    after = world.order(case_id)
    assert after.update_loop is None and after.status is OrderStatus.CONFIRMED
    assert after.lines == before.lines
    assert [line.deliveries for line in after.lines] == [line.deliveries for line in before.lines]
    assert after.model_dump(exclude=_LOOP_FIELDS) == before.model_dump(exclude=_LOOP_FIELDS)
    assert after.case_version > before.case_version
    assert [r.state for r in requests] == ["closed"]
    answered = [e for e in world.audit() if e.action == "sales.order.update_customer_answered"]
    assert [e.details.get("reason_code") for e in answered] == ["keep"]


async def test_asking_pc_again_drops_pcs_answer_and_waits_to_ask() -> None:
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id = await _waiting_customer(world, (QUANTITY, LATER))
        await _answer(world, case_id, "ask_pc_again")

    loop = world.order(case_id).update_loop
    assert loop is not None and loop.step == "ask_pc" and loop.verdict is None
    assert all(x.pc_answer is None for x in loop.lines)


# ----------------------------------------------------------- refusals --


async def test_a_customer_answer_while_waiting_on_pc_is_refused() -> None:
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, _ = await _in_loop(world)
        await _asked(world, case_id)
        version = _version(world, case_id)
        for answer in ("keep", "accept", "ask_pc_again"):
            with pytest.raises(ConflictError) as refused:
                await _answer(world, case_id, answer)
            assert refused.value.details["rule"] == "update_step"

    assert _version(world, case_id) == version
    assert world.order(case_id).update_loop.step == "waiting_pc"  # type: ignore[union-attr]


async def test_pc_is_asked_once_every_line_of_the_request_is_decided() -> None:
    two = _table(
        ("58102", "2", PO, "NV-CB4-22-GY", "04-12-26", "20-11-26"),
        ("58101", "1", PO, "NV-HW22-BK", "06-11-26", "30-10-26"),
    )
    with SampleWith([_reply(html=two)]) as sample:
        world = _world(sample)
        case_id = await _confirmed(world)
        await world.process_each(AN, ["R1"])
        opened = await world.services.change_requests.open(
            AN.context(), case_id, case_version=_version(world, case_id), message_id="R1"
        )
        await world.services.change_requests.confirm(
            AN.context(),
            case_id,
            opened.request.request_id,
            1,
            case_version=_version(world, case_id),
        )
        with pytest.raises(ConflictError) as refused:
            await _asked(world, case_id)

    assert refused.value.details["rule"] == "change_request_open"


async def test_a_split_that_does_not_add_up_to_the_quantity_asked_is_refused() -> None:
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, _ = await _in_loop(world)
        await _asked(world, case_id)
        with pytest.raises(ConflictError) as refused:
            await _pc(world, case_id, (QUANTITY - 1, ASKED))

    assert refused.value.details["rule"] == "split_not_summing"


async def test_the_bravo_update_is_entered_only_once_approved() -> None:
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id = await _waiting_customer(world)
        await _answer(world, case_id, "accept")
        with pytest.raises(ConflictError) as refused:
            await world.services.dw1.record_bravo_entry(
                AN.context(),
                case_id,
                case_version=_version(world, case_id),
                so_no=None,
                entry_compared=True,
            )

    assert refused.value.details["rule"] == "bravo_update_not_approved"
    assert world.order(case_id).status is OrderStatus.CHANGE_REVIEW


async def test_a_change_after_the_approval_drops_it() -> None:
    """The approved file is the case's only while the case is as it was
    drawn: a later edit drops the approval, and the file is approved again."""
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id = await _waiting_customer(world)
        await _answer(world, case_id, "accept")
        record = await _render(world, case_id, "bravo_update")
        await world.services.update_loops.approve(
            AN.context(),
            case_id,
            case_version=_version(world, case_id),
            artifact_id=record.artifact_id,
        )
        await world.services.order_commands.confirm_mapping(
            AN.context(), case_id, 3, case_version=_version(world, case_id), prv_code="CB-2008"
        )

    loop = world.order(case_id).update_loop
    assert loop is not None and loop.approval is None


async def test_whoever_approved_the_bravo_update_does_not_cross_check_it() -> None:
    """Separation of duties stands (WIV-03-012 step 9): Diệu approves the
    update file An enters, so Diệu is a maker of it and cannot cross-check."""
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id = await _waiting_customer(world)
        await _answer(world, case_id, "accept")
        record = await _render(world, case_id, "bravo_update")
        await world.services.update_loops.approve(
            DIEU.context(),
            case_id,
            case_version=_version(world, case_id),
            artifact_id=record.artifact_id,
        )
        await world.services.dw1.record_bravo_entry(
            AN.context(),
            case_id,
            case_version=_version(world, case_id),
            so_no=None,
            entry_compared=True,
        )
        assert DIEU.user_id in world.order(case_id).makers
        with pytest.raises(ConflictError):
            await world.cross_check(DIEU, case_id)

    assert world.order(case_id).status is OrderStatus.UPLOADED_TO_BRAVO


async def test_a_stale_case_version_is_refused() -> None:
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, _ = await _in_loop(world)
        stale = _version(world, case_id) - 1
        with pytest.raises(ConflictError) as refused:
            await world.services.update_loops.ask_pc(AN.context(), case_id, case_version=stale)

    assert refused.value.details["rule"] == "stale_case_version"


async def test_another_tenant_or_workspace_finds_no_order() -> None:
    other_workspace = SalesScope(ALPHA.tenant_id, WorkspaceId(uuid.UUID(int=0xA1FC)))
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, _ = await _in_loop(world)
        version = _version(world, case_id)
        loops = world.services.update_loops
        for context in (OUTSIDER.context(BETA), AN.context(other_workspace)):
            with pytest.raises(NotFoundError):
                await loops.pc_request(context, case_id)
            with pytest.raises(NotFoundError):
                await loops.ask_pc(context, case_id, case_version=version)
            with pytest.raises(NotFoundError):
                await loops.customer_answer(context, case_id, case_version=version, answer="keep")

    assert _version(world, case_id) == version


async def test_a_caller_without_the_prepare_scope_moves_nothing() -> None:
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, _ = await _in_loop(world)
        version = _version(world, case_id)
        loops = world.services.update_loops
        with pytest.raises(PermissionDeniedError):
            await loops.ask_pc(READER.context(), case_id, case_version=version)
        with pytest.raises(PermissionDeniedError):
            await loops.customer_answer(
                READER.context(), case_id, case_version=version, answer="keep"
            )
        with pytest.raises(PermissionDeniedError):
            await loops.approve(
                READER.context(), case_id, case_version=version, artifact_id=uuid.uuid4()
            )

    assert _version(world, case_id) == version


# ---------------------------------------------------------- reminders --


def _lane(world: World, clock: FixedClock) -> FollowupLane:
    return FollowupLane(
        uow=world.store,
        policies=rule_book(world.policies, world.store.rule_versions),
        holders=Holders(CALLERS),
        notifications=world.notifications,
        clock=clock,
        ids=Uuid4Generator(),
    )


async def _reminders(world: World, case_id: uuid.UUID, kind: str, hours: int) -> list[str]:
    loop = world.order(case_id).update_loop
    since = loop.since if loop is not None else world.store.clock.now()
    sent = (await _lane(world, FixedClock(since + hours * HOUR)).tick(ALPHA)).sent
    return [key for key in sent if f":{kind}:" in key and str(case_id) in key]


async def test_the_pic_is_reminded_while_pc_and_then_the_customer_have_not_answered() -> None:
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, _ = await _in_loop(world)
        await _asked(world, case_id)
        assert await _reminders(world, case_id, "waiting_pc", 23) == []
        assert len(await _reminders(world, case_id, "waiting_pc", 24)) == 1
        await _pc(world, case_id, (QUANTITY, ASKED))
        await _sent(world, case_id)
        assert await _reminders(world, case_id, "waiting_customer", 23) == []
        assert len(await _reminders(world, case_id, "waiting_customer", 24)) == 1


async def test_no_reminder_is_raised_once_answered() -> None:
    """PC's answer ends the wait on PC, the customer's the wait on them
    (failure-modes #6)."""
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, _ = await _in_loop(world)
        await _asked(world, case_id)
        asked = world.order(case_id).update_loop
        assert asked is not None
        await _pc(world, case_id, (QUANTITY, ASKED))
        pc_sent = (await _lane(world, FixedClock(asked.since + 48 * HOUR)).tick(ALPHA)).sent
        await _sent(world, case_id)
        waiting = world.order(case_id).update_loop
        assert waiting is not None
        await _answer(world, case_id, "keep")
        customer_sent = (await _lane(world, FixedClock(waiting.since + 48 * HOUR)).tick(ALPHA)).sent

    assert not [key for key in pc_sent if ":waiting_pc:" in key]
    assert not [key for key in customer_sent if ":waiting_customer:" in key]
