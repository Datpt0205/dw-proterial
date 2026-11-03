"""An RFQ sent from the buyer's own mailbox (`application.rfq_mail`): who may
press, what is refused before anything is queued, and what the worker's lane
does with the outbox folder, the flow's receipt and its silence. The flow is
played by the platform's `FakeFlow` over a temporary folder."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.outbox_folder import FakeFlow, FolderOutbox
from dw_platform.application.rule_versions import ContextScope
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.ports import Person
from dw_purchasing.application.rfq_mail import (
    OUTBOUND_LANE,
    RECEIPT_WITHIN,
    RfqMail,
    RfqMailLane,
    job_name,
)
from dw_purchasing.testing.world import ALPHA, BETA, BUYER, World, caller, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
INTAKE = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)
SOURCING = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_sourcing.json").read_text(encoding="utf-8")
)
MAILBOX = "buyer@alpha.local"
SCOPE = ContextScope.of(caller())


class Told:
    def __init__(self) -> None:
        self.calls: list[tuple[RfqMail, str]] = []

    async def unsent(self, scope: ContextScope, mail: RfqMail, why: Any) -> None:
        self.calls.append((mail, why))


async def _world() -> tuple[World, uuid.UUID, str]:
    from datetime import UTC, datetime

    world = open_world(REPO, INTAKE["answers"])
    world.model.by_schema = {
        "ModelOffer": SOURCING["answers"],
        "RfqWording": {"PR-2611-004": SOURCING["rfq_words"]["good"]},
    }
    world.people.people[BUYER] = Person("Nguyễn Văn Mua", "Mua hàng", MAILBOX)
    item = await world.service.read_mail(caller(), "P01")
    assert item.case_id is not None
    await world.approvals.submit(caller(), item.case_id, case_version=1)
    case = await world.service.case(caller(), item.case_id)
    assert case.approval is not None
    world.store.decide(
        case.approval.approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=True,
        decided_by=uuid.UUID(int=0x4EAD),
        at=datetime(2026, 11, 2, 9, tzinfo=UTC),
        comment="ok",
    )
    await world.settlement.settle(
        case.approval.approval_id, caller(principal=uuid.UUID(int=0x4EAD))
    )
    await world.sourcing.draft_rfq(caller(), item.case_id, case_version=3)
    drafted = await world.service.case(caller(), item.case_id)
    assert drafted.rfq is not None
    written = next(d for d in drafted.rfq.drafts if d.written_by != "pending")
    return world, item.case_id, written.supplier_code


def _lane(world: World, root: Path, told: Told, clock: FixedClock | None = None) -> RfqMailLane:
    return RfqMailLane(
        world.rfq_mail_rows, FolderOutbox(root), told, clock or world.clock, Uuid4Generator()
    )


# --------------------------------------------------------------- the press --


async def test_a_press_queues_one_mail_from_the_pressers_own_mailbox() -> None:
    world, case_id, supplier = await _world()

    sent = await world.rfq_mails.send(caller(), case_id, supplier)

    assert (sent.status, sent.mailbox, sent.supplier_code) == ("queued", MAILBOX, supplier)
    (mail,) = world.rfq_mail_rows.rows[ALPHA].values()
    case = await world.service.case(caller(), case_id)
    assert case.rfq is not None
    draft = case.rfq.asked(supplier)
    assert draft is not None
    assert (mail.subject, mail.body, mail.recipients) == (
        draft.subject,
        draft.body,
        tuple(a.lower() for a in draft.to),
    )
    assert world.rfq_mail_rows.audit[-1].action == "purchasing.rfq.mail_queued"
    with pytest.raises(ConflictError):
        await world.rfq_mails.send(caller(), case_id, supplier)


async def test_who_does_not_prepare_rfqs_sends_nothing_and_another_tenant_finds_nothing() -> None:
    world, case_id, supplier = await _world()
    reader = caller(scopes=frozenset({PurchasingScopes.REQUEST_READ.value}))

    with pytest.raises(PermissionDeniedError):
        await world.rfq_mails.send(reader, case_id, supplier)
    with pytest.raises(NotFoundError):
        await world.rfq_mails.send(caller(BETA), case_id, supplier)
    assert world.rfq_mail_rows.rows == {}
    assert await world.rfq_mails.of_case(caller(BETA), case_id) == []


async def test_a_recipient_no_longer_the_suppliers_contact_is_refused() -> None:
    world, case_id, supplier = await _world()
    case = await world.service.case(caller(), case_id)
    assert case.rfq is not None
    forged = case.rfq.model_copy(
        update={
            "drafts": tuple(
                d.model_copy(update={"to": ("someone@elsewhere.example",)})
                if d.supplier_code == supplier
                else d
                for d in case.rfq.drafts
            )
        }
    )
    held = world.store.scopes[ALPHA].cases[case_id]
    world.store.scopes[ALPHA].cases[case_id] = held.model_copy(update={"rfq": forged})

    with pytest.raises(ConflictError) as refused:
        await world.rfq_mails.send(caller(), case_id, supplier)
    assert refused.value.details["rule"] == "recipient_not_listed"
    assert world.rfq_mail_rows.rows == {}


async def test_nothing_is_queued_without_an_outbox_or_a_sign_in_address() -> None:
    world, case_id, supplier = await _world()
    disabled = world.rfq_mails.__class__(
        **{**world.rfq_mails.__dict__, "enabled": False}  # a deployment with no share
    )
    with pytest.raises(ConflictError) as refused:
        await disabled.send(caller(), case_id, supplier)
    assert refused.value.details["rule"] == "outbox_disabled"
    world.people.people[BUYER] = Person("Nguyễn Văn Mua", "Mua hàng", None)
    with pytest.raises(ConflictError) as refused:
        await world.rfq_mails.send(caller(), case_id, supplier)
    assert refused.value.details["rule"] == "no_mailbox"
    assert world.rfq_mail_rows.rows == {}


# ---------------------------------------------------------------- the lane --


async def test_the_lane_writes_the_job_and_the_flows_receipt_settles_it_sent(
    tmp_path: Path,
) -> None:
    world, case_id, supplier = await _world()
    sent = await world.rfq_mails.send(caller(), case_id, supplier)
    (tmp_path / MAILBOX / "outbox").mkdir(parents=True)
    told = Told()
    lane = _lane(world, tmp_path, told)

    await lane.tick(SCOPE)
    job = json.loads(
        (tmp_path / MAILBOX / "outbox" / f"{job_name(SCOPE, sent.mail_id)}.json").read_text(
            encoding="utf-8"
        )
    )
    FakeFlow(tmp_path).run()
    await lane.tick(SCOPE)

    assert (job["from"], job["job"]) == (MAILBOX, str(sent.mail_id))
    (mail,) = await world.rfq_mails.of_case(caller(), case_id)
    assert mail.status == "sent" and told.calls == []
    settled = world.rfq_mail_rows.audit[-1]
    assert settled.details["actor"] == f"system:{OUTBOUND_LANE}"


async def test_someone_with_no_outbox_folder_is_told_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    world, case_id, supplier = await _world()
    await world.rfq_mails.send(caller(), case_id, supplier)
    told = Told()

    await _lane(world, tmp_path, told).tick(SCOPE)

    (mail,) = await world.rfq_mails.of_case(caller(), case_id)
    assert (mail.status, mail.error) == ("failed", "not_connected")
    assert [why for _, why in told.calls] == ["not_connected"]
    assert not (tmp_path / MAILBOX).exists()
    # A failed mail may be sent again.
    assert (await world.rfq_mails.send(caller(), case_id, supplier)).status == "queued"


async def test_a_flow_that_never_answers_is_stalled_and_never_counted_sent(
    tmp_path: Path,
) -> None:
    world, case_id, supplier = await _world()
    await world.rfq_mails.send(caller(), case_id, supplier)
    (tmp_path / MAILBOX / "outbox").mkdir(parents=True)
    told = Told()
    clock = FixedClock(world.clock.now())
    lane = _lane(world, tmp_path, told, clock)
    await lane.tick(SCOPE)

    clock.advance_to(clock.now() + RECEIPT_WITHIN + timedelta(seconds=1))
    await lane.tick(SCOPE)

    (mail,) = await world.rfq_mails.of_case(caller(), case_id)
    assert (mail.status, mail.error) == ("stalled", "no_receipt")
    assert [why for _, why in told.calls] == ["no_receipt"]


async def test_a_receipt_of_dw1_or_of_another_mailbox_settles_nothing(tmp_path: Path) -> None:
    world, case_id, supplier = await _world()
    sent = await world.rfq_mails.send(caller(), case_id, supplier)
    (tmp_path / MAILBOX / "outbox").mkdir(parents=True)
    lane = _lane(world, tmp_path, Told())
    await lane.tick(SCOPE)
    theirs = tmp_path / MAILBOX / "receipts"
    theirs.mkdir(parents=True)
    dw1 = theirs / f"{ALPHA[0]}.{ALPHA[1]}.{uuid.uuid4()}.json"
    dw1.write_text('{"status": "sent"}')
    forged = tmp_path / "other@alpha.local" / "receipts"
    forged.mkdir(parents=True)
    (forged / f"{job_name(SCOPE, sent.mail_id)}.json").write_text('{"status": "sent"}')

    await lane.tick(SCOPE)

    (mail,) = await world.rfq_mails.of_case(caller(), case_id)
    assert mail.status == "written"
    # DW1's receipt is DW1's lane's to read.
    assert dw1.exists()


async def test_an_rfq_no_one_wrote_yet_is_not_sent() -> None:
    world, case_id, supplier = await _world()
    case = await world.service.case(caller(), case_id)
    assert case.rfq is not None
    unwritten = case.rfq.model_copy(
        update={
            "drafts": tuple(
                d.model_copy(update={"subject": "", "body": "", "written_by": "pending"})
                if d.supplier_code == supplier
                else d
                for d in case.rfq.drafts
            )
        }
    )
    held = world.store.scopes[ALPHA].cases[case_id]
    world.store.scopes[ALPHA].cases[case_id] = held.model_copy(update={"rfq": unwritten})

    with pytest.raises(ConflictError) as refused:
        await world.rfq_mails.send(caller(), case_id, supplier)
    assert refused.value.details["rule"] == "rfq_words_pending"
    assert world.rfq_mail_rows.rows == {}


async def test_a_dw2_receipt_of_another_workspace_is_left_for_its_own_lane(
    tmp_path: Path,
) -> None:
    world, _, _ = await _world()
    folder = tmp_path / MAILBOX / "receipts"
    folder.mkdir(parents=True)
    theirs = folder / f"{job_name(ContextScope.of(caller(BETA)), uuid.uuid4())}.json"
    theirs.write_text('{"status": "sent"}')

    await _lane(world, tmp_path, Told()).tick(SCOPE)

    assert theirs.exists()
