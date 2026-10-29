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
from dw_platform.application.access_context import AccessContext
from dw_sales.adapters.outbox_folder import FakeFlow, FolderOutbox
from dw_sales.application.outbound_mail import (
    RECEIPT_WITHIN,
    OutboundLane,
    job_name,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.quotes import QuoteStatus
from dw_sales.evals.graders import AN, CALLERS, GIANG, OUTSIDER, READER, _quote_duties
from dw_sales.evals.world import ALPHA, BETA, Directory, SampleSet, World, open_world

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
