""" "Gửi cho khách" (2026-10-29): an approved quotation's send draft sent from
the presser's own mailbox through their outbox folder, the flow played by
`FakeFlow`, and the receipt read back by the worker's lane."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.outbox_folder import FakeFlow, FolderOutbox
from dw_platform.application.access_context import AccessContext
from dw_sales.application.outbound_mail import (
    RECEIPT_WITHIN,
    OutboundLane,
    job_name,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.quotes import QuoteStatus
from dw_sales.evals.graders import AN, CALLERS, DIEU, GIANG, OUTSIDER, READER, _quote_duties
from dw_sales.evals.world import ALPHA, BETA, Directory, SampleSet, SampleWith, World, open_world

from .test_update_loop import ASKED, PULL_IN, QUANTITY, _asked, _in_loop, _pc, _render, _reply

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
FIXTURE = json.loads(
    (REPO / "evals/fixtures/cases/sales_pricer_approver_head.json").read_text(encoding="utf-8")
)
SENDER = GIANG  # the pricer, who prepares and sends the quotation


@dataclass
class Told:
    calls: list[tuple[tuple[uuid.UUID, ...], str]] = field(default_factory=list)

    async def deliver(self, context: AccessContext, *, recipients: Any, **kw: Any) -> None:
        self.calls.append((tuple(recipients), kw["title"]))


@dataclass
class Scopes:
    scopes_: list[SalesScope]

    async def scopes(self) -> list[SalesScope]:
        return self.scopes_


@dataclass
class Rig:
    world: World
    case_id: uuid.UUID
    draft_id: uuid.UUID
    root: Path
    lane: OutboundLane
    told: Told
    clock: FixedClock

    def connect(self, mailbox: str = "giang.do@alpha.local") -> None:
        (self.root / mailbox / "outbox").mkdir(parents=True)


async def _rig(tmp_path: Path) -> Rig:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    case_id, _ = await _quote_duties(world, FIXTURE)
    assert world.quote(case_id).status is QuoteStatus.APPROVED
    (draft,) = await world.services.artifacts.render_quote(
        SENDER.context(),
        case_id,
        kind="send_draft",
        case_version=world.quote(case_id).case_version,
    )
    told = Told()
    clock = FixedClock(world.store.clock.now())
    lane = OutboundLane(
        uow=world.store,
        scopes=Scopes([ALPHA]),
        outbox=FolderOutbox(tmp_path),
        artifact_bytes=world.objects,
        quotes=world.services.quote_commands,
        answers=world.services.update_loops,
        access=Directory(CALLERS),
        notifications=told,
        clock=clock,
        ids=Uuid4Generator(),
    )
    return Rig(world, case_id, draft.artifact_id, tmp_path, lane, told, clock)


async def _send(rig: Rig, caller: Any = SENDER) -> Any:
    return await rig.world.services.outbound.send(
        caller.context(),
        CaseKind.QUOTE,
        rig.case_id,
        rig.draft_id,
        case_version=rig.world.quote(rig.case_id).case_version,
    )


async def test_a_pressed_mail_is_sent_from_the_pressers_mailbox_and_marks_the_quote_sent(
    tmp_path: Path,
) -> None:
    rig = await _rig(tmp_path)
    rig.connect()
    mail = await _send(rig)
    assert (mail.status, mail.mailbox) == ("queued", "giang.do@alpha.local")

    await rig.lane.tick()
    job_file = tmp_path / mail.mailbox / "outbox" / f"{job_name(ALPHA, mail.mail_id)}.json"
    job = json.loads(job_file.read_text(encoding="utf-8"))
    assert job["from"] == "giang.do@alpha.local" and job["to"] and job["attachments"]
    for name in job["attachments"]:
        assert (tmp_path / mail.mailbox / "outbox" / "files" / job_file.stem / name).is_file()

    FakeFlow(tmp_path).run()
    await rig.lane.tick()
    (sent,) = (
        await rig.world.services.outbound.mails(SENDER.context(), CaseKind.QUOTE, rig.case_id)
    ).mails
    assert sent.status == "sent"
    assert rig.world.quote(rig.case_id).status is QuoteStatus.SENT
    actions = [e.action for e in rig.world.audit()]
    assert "sales.mail.send_requested" in actions and "sales.mail.sent" in actions


async def test_pressing_twice_sends_one_mail(tmp_path: Path) -> None:
    rig = await _rig(tmp_path)
    rig.connect()
    first, second = await _send(rig), await _send(rig)
    assert first.mail_id == second.mail_id


async def test_someone_with_no_outbox_folder_is_told_and_nothing_is_sent(tmp_path: Path) -> None:
    rig = await _rig(tmp_path)
    await _send(rig)
    await rig.lane.tick()
    (mail,) = (
        await rig.world.services.outbound.mails(SENDER.context(), CaseKind.QUOTE, rig.case_id)
    ).mails
    assert (mail.status, mail.error) == ("failed", "not_connected")
    assert rig.told.calls == [((SENDER.user_id,), "Chưa gửi được thư cho khách")]
    assert rig.world.quote(rig.case_id).status is QuoteStatus.APPROVED


async def test_a_flow_that_fails_or_never_answers_is_said_never_counted_sent(
    tmp_path: Path,
) -> None:
    rig = await _rig(tmp_path)
    rig.connect()
    await _send(rig)
    await rig.lane.tick()
    FakeFlow(tmp_path, answer="failed").run()
    await rig.lane.tick()
    (mail,) = (
        await rig.world.services.outbound.mails(SENDER.context(), CaseKind.QUOTE, rig.case_id)
    ).mails
    assert (mail.status, mail.error) == ("failed", "flow_failed")
    assert rig.world.quote(rig.case_id).status is QuoteStatus.APPROVED

    again = await _send(rig)  # a failed one may be sent again
    assert again.mail_id != mail.mail_id
    await rig.lane.tick()
    rig.clock.advance_to(rig.clock.now() + RECEIPT_WITHIN)
    await rig.lane.tick()
    mails = await rig.world.services.outbound.mails(SENDER.context(), CaseKind.QUOTE, rig.case_id)
    latest = next(m for m in mails.mails if m.mail_id == again.mail_id)
    assert (latest.status, latest.error) == ("stalled", "no_receipt")


async def test_a_receipt_for_another_mailbox_settles_nothing(tmp_path: Path) -> None:
    rig = await _rig(tmp_path)
    rig.connect()
    mail = await _send(rig)
    await rig.lane.tick()
    forged = tmp_path / "an.nguyen@alpha.local" / "receipts"
    forged.mkdir(parents=True)
    (forged / f"{job_name(ALPHA, mail.mail_id)}.json").write_text('{"status": "sent"}')
    await rig.lane.tick()
    (held,) = (
        await rig.world.services.outbound.mails(SENDER.context(), CaseKind.QUOTE, rig.case_id)
    ).mails
    assert held.status == "written"


async def test_a_receipt_of_another_context_is_left_for_its_own_lane(tmp_path: Path) -> None:
    """One outbox folder and one flow serve DW1 and DW2: a receipt whose job
    is not DW1's stays where it is for the lane whose job it is."""
    rig = await _rig(tmp_path)
    theirs = tmp_path / "giang.do@alpha.local" / "receipts"
    theirs.mkdir(parents=True)
    receipt = theirs / f"dw2.{uuid.uuid4()}.{uuid.uuid4()}.{uuid.uuid4()}.json"
    receipt.write_text('{"status": "sent"}')

    await rig.lane.tick()

    assert receipt.exists()


async def test_a_recipient_outside_the_customers_contacts_is_refused(tmp_path: Path) -> None:
    rig = await _rig(tmp_path)
    record = rig.world.store.state(ALPHA).artifacts[rig.draft_id]
    key = record.object_key(ALPHA)
    data = await rig.world.objects.get_object(key)
    await rig.world.objects.put_object(
        key,
        # The draft folds its To header onto the next line.
        data.replace(b"\r\nTo:", b"\r\nTo: stranger@elsewhere.example,", 1),
        "message/rfc822",
    )
    with pytest.raises(ConflictError, match="danh bạ"):
        await _send(rig)


async def test_only_who_prepares_the_case_may_send_and_another_tenant_finds_nothing(
    tmp_path: Path,
) -> None:
    rig = await _rig(tmp_path)
    with pytest.raises(PermissionDeniedError):
        await _send(rig, READER)
    with pytest.raises(NotFoundError):
        await rig.world.services.outbound.send(
            OUTSIDER.context(BETA), CaseKind.QUOTE, rig.case_id, rig.draft_id, case_version=1
        )


async def test_nothing_is_queued_where_the_deployment_has_no_outbox(tmp_path: Path) -> None:
    rig = await _rig(tmp_path)
    off = replace(rig.world.services.outbound, enabled=False)
    with pytest.raises(ConflictError, match="chưa được nối"):
        await off.send(SENDER.context(), CaseKind.QUOTE, rig.case_id, rig.draft_id, case_version=1)
    assert not (await off.mails(AN.context(), CaseKind.QUOTE, rig.case_id)).enabled


# ------------------------------------------- ticket 76: every customer draft


async def test_a_changes_answer_sent_from_dw1_records_it_sent_on_the_receipt(
    tmp_path: Path,
) -> None:
    """A change's answer ("6-DW4", PC can do it) is sent from the PIC's own
    mailbox in one press; the receipt records "Ghi đã gửi khách" as the PIC,
    so the case waits on the customer without a second press."""
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = open_world(REPO, sample, CALLERS)
        case_id, _ = await _in_loop(world)
        await _asked(world, case_id)
        await _pc(world, case_id, (QUANTITY, ASKED))
        draft = await _render(world, case_id, "change_can_do_draft")
        assert world.order(case_id).update_loop.step == "answer_customer"  # type: ignore[union-attr]
        lane = OutboundLane(
            uow=world.store,
            scopes=Scopes([ALPHA]),
            outbox=FolderOutbox(tmp_path),
            artifact_bytes=world.objects,
            quotes=world.services.quote_commands,
            answers=world.services.update_loops,
            access=Directory(CALLERS),
            notifications=Told(),
            clock=FixedClock(world.store.clock.now()),
            ids=Uuid4Generator(),
        )
        mail = await world.services.outbound.send(
            AN.context(),
            CaseKind.ORDER,
            case_id,
            draft.artifact_id,
            case_version=world.order(case_id).case_version,
        )
        (tmp_path / mail.mailbox / "outbox").mkdir(parents=True)
        await lane.tick()
        assert world.order(case_id).update_loop.step == "answer_customer"  # type: ignore[union-attr]
        FakeFlow(tmp_path).run()
        await lane.tick()

        loop = world.order(case_id).update_loop
        assert loop is not None and loop.step == "waiting_customer"
        answered = [e for e in world.audit() if e.action == "sales.order.update_answer_sent"]
        assert [e.actor_id.value for e in answered] == [AN.user_id]


async def test_a_draft_to_design_is_never_a_customer_draft(tmp_path: Path) -> None:
    from dw_sales.application.outbound_mail import INTERNAL_SENDABLE, SENDABLE

    for kind, kinds in SENDABLE.items():
        assert not kinds & INTERNAL_SENDABLE[kind]
        assert "ycbg_draft" not in kinds | INTERNAL_SENDABLE[kind]


async def test_a_request_to_design_goes_to_designs_mailboxes_and_records_it_sent(
    tmp_path: Path,
) -> None:
    """Ticket 77: the YCBG's request to Design is sent from the PIC's mailbox
    in one press, to the tenant's Design mailboxes only; the receipt records
    "Đã gửi Design" as the PIC."""
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    commands = world.services.quote_commands
    seen = await world.process_each(DIEU, [FIXTURE["rfq"]])
    ((disposition, _),) = seen.values()
    case_id = disposition.case_id
    assert case_id is not None

    def version() -> int:
        return world.quote(case_id).case_version

    await commands.ycbg(DIEU.context(), case_id, case_version=version(), ycbg_no=None)
    ycbg = FIXTURE["ycbg"]
    await commands.ycbg(DIEU.context(), case_id, case_version=version(), ycbg_no=ycbg)
    (draft,) = await world.services.artifacts.render_quote(
        DIEU.context(), case_id, kind="design_request_draft", case_version=version()
    )
    lane = OutboundLane(
        uow=world.store,
        scopes=Scopes([ALPHA]),
        outbox=FolderOutbox(tmp_path),
        artifact_bytes=world.objects,
        quotes=world.services.quote_commands,
        answers=world.services.update_loops,
        access=Directory(CALLERS),
        notifications=Told(),
        clock=FixedClock(world.store.clock.now()),
        ids=Uuid4Generator(),
    )
    mail = await world.services.outbound.send(
        DIEU.context(), CaseKind.QUOTE, case_id, draft.artifact_id, case_version=version()
    )
    (tmp_path / mail.mailbox / "outbox").mkdir(parents=True)
    await lane.tick()
    FakeFlow(tmp_path).run()
    await lane.tick()

    assert world.quote(case_id).status is QuoteStatus.SENT_TO_DESIGN
    sent = [e for e in world.audit() if e.action == "sales.quote.sent_to_design"]
    assert [e.actor_id.value for e in sent] == [DIEU.user_id]


@dataclass
class _OtherDesign:
    """Design's mailboxes as configured after the draft named another."""

    async def quote_rules(self, scope: SalesScope) -> Any:
        @dataclass
        class _Rules:
            design_mailboxes: tuple[str, ...] = ("design-moved@alpha.local",)

        return _Rules()


async def test_a_request_to_design_is_refused_when_it_names_no_configured_design_mailbox(
    tmp_path: Path,
) -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    commands = world.services.quote_commands
    ((disposition, _),) = (await world.process_each(DIEU, [FIXTURE["rfq"]])).values()
    case_id = disposition.case_id
    assert case_id is not None
    version = lambda: world.quote(case_id).case_version  # noqa: E731
    await commands.ycbg(DIEU.context(), case_id, case_version=version(), ycbg_no=None)
    await commands.ycbg(DIEU.context(), case_id, case_version=version(), ycbg_no=FIXTURE["ycbg"])
    (draft,) = await world.services.artifacts.render_quote(
        DIEU.context(), case_id, kind="design_request_draft", case_version=version()
    )
    outbound = replace(world.services.outbound, design=_OtherDesign())

    with pytest.raises(ConflictError, match="hộp thư Design"):
        await outbound.send(
            DIEU.context(), CaseKind.QUOTE, case_id, draft.artifact_id, case_version=version()
        )
