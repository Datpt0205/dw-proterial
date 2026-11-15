"""An order's confirmation sent, then the customer's agreement in words or by
silence, each recorded by a person (ticket 28, dw_sales ADR 0011), through
the services the API serves.

Over the in-memory world with the fictional M04 order (customer NRV), walked
to the confirmation as ticket 29's tests walk it, and synthetic replies in
its thread. The days of silence are the tenant's order rules: the sample's
own version has none (acceptance 1), and a test that needs them writes a
version with NRV's.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import yaml

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import WorkspaceId
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.domain.messages import Attachment, EmailAddress, InboundMessage
from dw_sales.adapters.policy_files import rule_book
from dw_sales.application.case_store import ArtifactRecord
from dw_sales.application.confirmations import CONFIRMATION_EXCEL, confirmation_copy
from dw_sales.application.followups import FollowupLane
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import ImpliedTerm, OrderCase, OrderStatus
from dw_sales.domain.reply_intent import ReadIntent, ReplyQuote, ReplyReading, proposed_step
from dw_sales.evals.graders import AN, CALLERS, DIEU, OUTSIDER, READER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, BETA, SampleSet, SampleWith, World, open_world
from dw_sales.evals.world import Directory as Holders

from .test_change_request_flow import M04_ID, _reply
from .test_update_loop import HELD, PULL_IN, _in_loop, _version
from .test_update_loop import _confirmed as _sent_to_customer

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
HANOI = ZoneInfo("Asia/Ho_Chi_Minh")
DAY = timedelta(days=1)
ACCEPT = "We accept the confirmation as sent."
REJECT = "We cannot accept these delivery dates."


def _world(sample: SampleSet, model: Any = None) -> World:
    return open_world(REPO, sample, CALLERS, model=model)


def _with_days(sample: SampleSet, **term: Any) -> SampleSet:
    """The sample's own order rules, a version on, with NRV's days of silence."""
    policies = sample.data_dir / "policies"
    (found,) = sorted(policies.glob("sales_order_rules@*.yaml"))
    document = yaml.safe_load(found.read_bytes())
    document["policy_version"] = "1.5.9"
    document["implied_acceptance"] = {"NRV": term}
    found.unlink()
    (policies / "sales_order_rules@1.5.9.yaml").write_text(
        yaml.safe_dump(document, allow_unicode=True), encoding="utf-8"
    )
    return sample


def _lane(world: World, at: datetime) -> FollowupLane:
    return FollowupLane(
        uow=world.store,
        policies=rule_book(world.policies, world.store.rule_versions),
        holders=Holders(CALLERS),
        notifications=world.notifications,
        clock=FixedClock(at),
        ids=Uuid4Generator(),
    )


async def _told(world: World, case_id: uuid.UUID, at: datetime) -> list[str]:
    sent = (await _lane(world, at).tick(ALPHA)).sent
    return [key for key in sent if ":implied_acceptance:" in key and str(case_id) in key]


async def _agree(world: World, case_id: uuid.UUID, how: Any, **kw: Any) -> Any:
    return await world.services.confirmations.agreed(
        kw.pop("context", AN.context()),
        case_id,
        case_version=kw.pop("case_version", _version(world, case_id)),
        how=how,
        **kw,
    )


# ------------------------------------------------------- the term itself --


def test_silence_counts_from_midnight_after_the_last_calendar_day() -> None:
    sent = datetime(2026, 10, 5, 10, 0, tzinfo=HANOI)  # a Monday
    term = ImpliedTerm(days=3)
    assert term.implied_from(sent, date(2026, 9, 1), HANOI) == datetime(
        2026, 10, 9, 0, 0, tzinfo=HANOI
    )


def test_business_days_from_the_po_date_skip_the_weekend() -> None:
    """Customer 1's shape: 5 business days after the PO date (Friday 2 Oct):
    Mon to Fri of the next week, so silence counts from Saturday 00:00."""
    term = ImpliedTerm(days=5, day_count="business", counted_from="po_date")
    at = term.implied_from(datetime(2026, 10, 20, tzinfo=UTC), date(2026, 10, 2), HANOI)
    assert at == datetime(2026, 10, 10, 0, 0, tzinfo=HANOI)


# --------------------------------------------- the confirmation sent --


async def test_the_confirmation_button_records_it_sent_and_the_order_waits_on_the_customer() -> (
    None
):
    with SampleWith([]) as sample:
        world = _world(sample)
        case_id = await _sent_to_customer(world)

    case = world.order(case_id)
    assert case.status is OrderStatus.CONFIRMATION_SENT
    assert case.confirmation is not None and case.confirmation.message_id is None
    assert case.confirmation.sent_at == case.confirmed_at == world.store.clock.now()
    actions = [e.action for e in world.audit() if e.resource_id == str(case_id)]
    assert "sales.order.confirmation_sent" in actions


async def test_acceptance_1_no_customer_days_never_implied_whatever_the_wait() -> None:
    with SampleWith([]) as sample:
        world = _world(sample)
        case_id = await _sent_to_customer(world)
        sent = world.order(case_id)
        assert sent.confirmation is not None
        assert sent.confirmation.term is None and sent.confirmation.implied_from is None
        later = world.store.clock.now() + 365 * DAY
        assert await _told(world, case_id, later) == []
        world.store.clock.advance_to(later)
        with pytest.raises(ConflictError) as refused:
            await _agree(world, case_id, "implied")

    assert refused.value.details["rule"] == "no_implied_term"
    assert world.order(case_id).status is OrderStatus.CONFIRMATION_SENT


async def test_the_lane_tells_the_pic_once_the_days_pass_and_the_pic_records_it() -> None:
    with SampleWith([]) as sample:
        world = _world(_with_days(sample, days=3))
        case_id = await _sent_to_customer(world)
        sent = world.order(case_id).confirmation
        assert sent is not None and sent.term == ImpliedTerm(days=3)
        # Sent Monday 5 Oct 10:00 Hanoi: Tue, Wed, Thu are the customer's.
        due = datetime(2026, 10, 9, 0, 0, tzinfo=HANOI)
        assert sent.implied_from == due
        # An hour before (23:59 itself is outside the working hours: deferred).
        assert await _told(world, case_id, due - timedelta(hours=1)) == []
        with pytest.raises(ConflictError) as early:
            await _agree(world, case_id, "implied")
        told = await _told(world, case_id, due)
        again = await _told(world, case_id, due + DAY)
        # The lane told; it moved nothing.
        assert world.order(case_id).status is OrderStatus.CONFIRMATION_SENT
        world.store.clock.advance_to(due)
        await _agree(world, case_id, "implied")

    assert early.value.details["rule"] == "implied_too_early"
    assert len(told) == 1 and again == []
    case = world.order(case_id)
    assert case.status is OrderStatus.CONFIRMED
    assert case.agreement is not None
    assert (case.agreement.how, case.agreement.by, case.agreement.message_id) == (
        "implied",
        AN.user_id,
        None,
    )
    (audited,) = [e for e in world.audit() if e.action == "sales.order.customer_agreed"]
    assert audited.details["reason_code"] == "implied"


# ------------------------------------------------ the customer's answer --


async def test_acceptance_2_a_reply_read_accepts_proposes_and_the_pic_records_it() -> None:
    model = Recorded(raw={"intents": [{"quote_spans": [ACCEPT], "intent": "accepts"}]})
    with SampleWith([_reply("R1", html=None, body=f"Dear Sales,\n\n{ACCEPT}\n\nHana")]) as sample:
        world = _world(sample, model)
        case_id = await _sent_to_customer(world)
        await world.process_each(AN, ["R1"])
        view = await world.services.orders.get(AN.context(), case_id)
        # Proposed, not taken.
        assert world.order(case_id).status is OrderStatus.CONFIRMATION_SENT
        await _agree(world, case_id, "accepted", message_id="R1")

    assert [r.proposal for r in view.replies] == ["record_accepted"]
    case = world.order(case_id)
    assert case.status is OrderStatus.CONFIRMED and case.agreement is not None
    assert (case.agreement.how, case.agreement.message_id) == ("accepted", "R1")
    assert case.agreement.quotes == (ACCEPT,)


async def test_acceptance_3_rejects_after_the_confirmation_moves_to_change_review() -> None:
    model = Recorded(raw={"intents": [{"quote_spans": [REJECT], "intent": "rejects"}]})
    with SampleWith([_reply("R1", html=None, body=f"Dear Sales,\n\n{REJECT}\n\nHana")]) as sample:
        world = _world(sample, model)
        case_id = await _sent_to_customer(world)
        await world.process_each(AN, ["R1"])
        view = await world.services.orders.get(AN.context(), case_id)
        assert world.order(case_id).status is OrderStatus.CONFIRMATION_SENT
        await world.services.confirmations.declined(
            AN.context(), case_id, case_version=_version(world, case_id)
        )

    assert [r.proposal for r in view.replies] == ["record_declined"]
    case = world.order(case_id)
    assert case.status is OrderStatus.CHANGE_REVIEW
    assert (case.confirmation, case.agreement, case.confirmed_by, case.cross_checked_by) == (
        None,
        None,
        None,
        None,
    )


async def test_a_person_records_agreement_with_no_reading_at_all() -> None:
    """The intents step is off for a tenant: the PIC still records it."""
    with SampleWith([]) as sample:
        world = _world(sample)
        case_id = await _sent_to_customer(world)
        await _agree(world, case_id, "accepted")

    agreed = world.order(case_id).agreement
    assert agreed is not None and (agreed.how, agreed.message_id, agreed.quotes) == (
        "accepted",
        None,
        (),
    )


async def test_another_mail_than_a_reply_on_the_order_is_not_found() -> None:
    """M05 is another customer's PO: no reply on this order."""
    with SampleWith([]) as sample:
        world = _world(sample)
        case_id = await _sent_to_customer(world)
        await world.process_each(AN, ["M05"])
        version = _version(world, case_id)
        for message_id in ("M05", "M04", "nothing-by-this-id"):
            with pytest.raises(NotFoundError):
                await _agree(world, case_id, "accepted", message_id=message_id)

    assert _version(world, case_id) == version


async def test_a_reply_before_the_confirmation_left_does_not_accept_it() -> None:
    with SampleWith([_reply("R1", html=None, body=ACCEPT, hour=9)]) as sample:
        world = _world(sample)
        case_id = await _sent_to_customer(world)
        await world.process_each(AN, ["R1"])
        with pytest.raises(ConflictError) as refused:
            await _agree(world, case_id, "accepted", message_id="R1")

    assert refused.value.details["rule"] == "reply_before_confirmation"


async def test_silence_names_no_reply() -> None:
    with SampleWith([_reply("R1", html=None, body=ACCEPT)]) as sample:
        world = _world(_with_days(sample, days=1))
        case_id = await _sent_to_customer(world)
        await world.process_each(AN, ["R1"])
        world.store.clock.advance_to(world.store.clock.now() + 30 * DAY)
        with pytest.raises(ConflictError) as refused:
            await _agree(world, case_id, "implied", message_id="R1")

    assert refused.value.details["rule"] == "silence_names_no_reply"


async def test_the_answer_is_the_loops_while_a_change_runs() -> None:
    """Ticket 29's loop starts on an order whose confirmation left; the
    customer's answer there is the loop's, not the confirmation's."""
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id, _ = await _in_loop(world)
        assert world.order(case_id).status is OrderStatus.CONFIRMATION_SENT
        with pytest.raises(ConflictError) as agreeing:
            await _agree(world, case_id, "accepted")
        with pytest.raises(ConflictError) as declining:
            await world.services.confirmations.declined(
                AN.context(), case_id, case_version=_version(world, case_id)
            )

    assert agreeing.value.details["rule"] == declining.value.details["rule"] == "update_running"


async def test_a_change_after_the_customer_agreed_still_joins_the_loop() -> None:
    with SampleWith([_reply(html=PULL_IN)]) as sample:
        world = _world(sample)
        case_id = await _sent_to_customer(world)
        await _agree(world, case_id, "accepted")
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

    case = world.order(case_id)
    assert case.status is OrderStatus.CONFIRMED and case.update_loop is not None
    assert case.line(2).effective.requested_date == HELD


# ----------------------------------------------- the boundaries --


async def test_a_stale_case_version_is_refused() -> None:
    with SampleWith([]) as sample:
        world = _world(sample)
        case_id = await _sent_to_customer(world)
        stale = _version(world, case_id) - 1
        with pytest.raises(ConflictError) as agreeing:
            await _agree(world, case_id, "accepted", case_version=stale)
        with pytest.raises(ConflictError) as declining:
            await world.services.confirmations.declined(AN.context(), case_id, case_version=stale)

    assert agreeing.value.details["rule"] == declining.value.details["rule"]
    assert agreeing.value.details["rule"] == "stale_case_version"


async def test_another_tenant_or_workspace_finds_no_order() -> None:
    other_workspace = SalesScope(ALPHA.tenant_id, WorkspaceId(uuid.UUID(int=0xA1FC)))
    with SampleWith([]) as sample:
        world = _world(sample)
        case_id = await _sent_to_customer(world)
        version = _version(world, case_id)
        for context in (OUTSIDER.context(BETA), AN.context(other_workspace)):
            with pytest.raises(NotFoundError):
                await _agree(world, case_id, "accepted", context=context)
            with pytest.raises(NotFoundError):
                await world.services.confirmations.declined(context, case_id, case_version=version)

    assert _version(world, case_id) == version


async def test_a_caller_without_the_prepare_scope_records_nothing() -> None:
    with SampleWith([]) as sample:
        world = _world(sample)
        case_id = await _sent_to_customer(world)
        version = _version(world, case_id)
        for caller in (READER, DIEU):
            if "sales.order.prepare" in caller.scopes:
                continue
            with pytest.raises(PermissionDeniedError):
                await _agree(world, case_id, "accepted", context=caller.context())
            with pytest.raises(PermissionDeniedError):
                await world.services.confirmations.declined(
                    caller.context(), case_id, case_version=version
                )

    assert _version(world, case_id) == version


# --------------------------------------------------- the sent copy --


def _record(case: OrderCase, sha: str, **changes: Any) -> ArtifactRecord:
    values: dict[str, Any] = {
        "artifact_id": uuid.uuid4(),
        "case_kind": CaseKind.ORDER,
        "case_id": case.case_id,
        "case_version": case.case_version,
        "kind": CONFIRMATION_EXCEL,
        "template_ref": "sales_bravo_upload@2.1.0",
        "sha256": sha,
        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "size_bytes": 10,
        "created_by": AN.user_id,
        "created_at": datetime(2026, 10, 5, tzinfo=UTC),
    }
    return ArtifactRecord.model_validate({**values, **changes})


def _copy(sha: str, message_id: str = "S1") -> InboundMessage:
    return InboundMessage(
        message_id=message_id,
        sender=EmailAddress(address=AN.email),
        subject="PO confirmation",
        received_at=datetime(2026, 10, 5, 2, 0, tzinfo=UTC),
        body_text="Please find our confirmation attached.",
        attachments=(
            Attachment(
                attachment_id=f"{message_id}-A1",
                name="processed.xlsx",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                size=10,
                sha256=sha,
            ),
        ),
    )


SHA, OTHER = "a" * 64, "b" * 64


async def test_a_sent_copy_carrying_this_versions_excel_proposes_and_no_other_does() -> None:
    with SampleWith([]) as sample:
        world = _world(sample)
        case_id = await _sent_to_customer(world)
    sent = world.order(case_id)
    # Rebuild the order as it stood before the confirmation, where it waits.
    waiting = OrderCase.model_validate(
        {
            **dict(sent),
            "status": OrderStatus.CROSS_CHECKED,
            "confirmed_by": None,
            "confirmed_at": None,
            "confirmation": None,
        }
    )
    match = _copy(SHA)
    assert confirmation_copy(waiting, [match], [_record(waiting, SHA)]) == match
    # Another file, another version, another kind or another case: nothing.
    assert confirmation_copy(waiting, [_copy(OTHER)], [_record(waiting, SHA)]) is None
    stale = _record(waiting, SHA, case_version=waiting.case_version - 1)
    assert confirmation_copy(waiting, [match], [stale]) is None
    other_kind = _record(waiting, SHA, kind="cross_check_sheet")
    assert confirmation_copy(waiting, [match], [other_kind]) is None
    other_case = _record(waiting, SHA, case_id=uuid.uuid4())
    assert confirmation_copy(waiting, [match], [other_case]) is None
    # Once sent, the confirmation is no longer what the order waits on.
    assert confirmation_copy(sent, [match], [_record(sent, SHA)]) is None


async def test_a_sent_copy_the_server_does_not_find_is_refused() -> None:
    """The request names a mail; the server finds the copy itself, and a mail
    on no thread of the case, or carrying no Excel of this version, is
    refused before anything is written."""
    with SampleWith([]) as sample:
        world = _world(sample)
        ((disposition, _),) = (await world.process_each(AN, ["M04"])).values()
        assert disposition.case_id is not None
        case_id = disposition.case_id
        # Walk it to the confirmation as `_confirmed` does, then try a copy.
        await _walk_to_cross_checked(world, case_id)
        version = _version(world, case_id)
        with pytest.raises(ConflictError) as refused:
            await world.services.confirmations.sent(
                AN.context(),
                case_id,
                case_version=version,
                delivery_dates={
                    x.line_no: [HELD] * x.deliveries for x in world.order(case_id).lines
                },
                sent_message_id="M05",
            )

    assert refused.value.details["rule"] == "not_the_confirmation"
    assert _version(world, case_id) == version


async def _walk_to_cross_checked(world: World, case_id: uuid.UUID) -> None:
    from dw_sales.domain.orders import ALLOWED_DISPOSITIONS, DispositionKind

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


def test_the_proposals_are_the_customers_on_a_confirmation_sent_only() -> None:
    def reading(intent: Any) -> ReplyReading:
        quote = ReplyQuote(text="x", start=0, end=1)
        return ReplyReading(
            prompt="sales.reply_intent@2.0.0",
            model_profile="onprem",
            route="default",
            rules="sales_order_rules@1.14.0",
            outcome="read",
            intents=(ReadIntent(intent=intent, quotes=(quote,)),),
        )

    assert proposed_step("customer", "order", "confirmation_sent", reading("accepts")) == (
        "record_accepted"
    )
    assert proposed_step("customer", "order", "confirmation_sent", reading("rejects")) == (
        "record_declined"
    )
    # Sales' own words, an order already agreed, or one whose change runs in
    # the loop propose nothing.
    assert proposed_step("sales", "order", "confirmation_sent", reading("accepts")) is None
    assert proposed_step("customer", "order", "confirmed", reading("accepts")) is None
    assert proposed_step("customer", "order", "in_update_loop", reading("accepts")) is None


async def _processed_excel(tmp: Path) -> Path:
    """The paste sheet DW1 makes for M04 once cross-checked, as the PIC would
    download it and attach it to their own mail: renders are byte-stable,
    so another world walked the same way makes the same file."""
    with SampleWith([]) as sample:
        world = _world(sample)
        ((disposition, _),) = (await world.process_each(AN, ["M04"])).values()
        assert disposition.case_id is not None
        await _walk_to_cross_checked(world, disposition.case_id)
        (record,) = await world.services.artifacts.render_order(
            AN.context(),
            disposition.case_id,
            kind=CONFIRMATION_EXCEL,
            case_version=_version(world, disposition.case_id),
        )
        (data,) = [v for k, v in world.objects.held.items() if k.endswith(str(record.artifact_id))]
    path = tmp / "processed.xlsx"
    path.write_bytes(data)
    return path


def _sales_copy(path: Path, message_id: str = "S1") -> dict[str, Any]:
    """A copy of the PIC's own confirmation mail in M04's thread."""
    return {
        "message_id": message_id,
        "sender": AN.email,
        "recipients": ["hana.westbrook@norvanta.example"],
        "subject": "RE: PO NRV-PO-26-0457 - confirmation",
        "received_at": "2026-10-05T09:30:00+07:00",
        "body": "Dear Hana,\n\nPlease find our confirmation attached.\n\nAn",
        "authentication": {"spf": "none", "dkim": "none", "dmarc": "none"},
        "references": [M04_ID],
        "attachments": [
            {
                "attachment_id": f"{message_id}-A1",
                "name": "NRV-PO-26-0457-xu-ly.xlsx",
                "media_type": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                "file": str(path),
            }
        ],
    }


async def test_the_pic_records_the_confirmation_from_the_sent_copy_at_its_time(
    tmp_path: Path,
) -> None:
    excel = await _processed_excel(tmp_path)
    with SampleWith([_sales_copy(excel)]) as sample:
        world = _world(sample)
        ((disposition, _),) = (await world.process_each(AN, ["M04"])).values()
        case_id = disposition.case_id
        assert case_id is not None
        await _walk_to_cross_checked(world, case_id)
        before = (await world.services.orders.get(AN.context(), case_id)).confirmation_copy
        await world.services.artifacts.render_order(
            AN.context(), case_id, kind=CONFIRMATION_EXCEL, case_version=_version(world, case_id)
        )
        view = await world.services.orders.get(AN.context(), case_id)
        # Proposed only; the order waits on the PIC's press.
        assert world.order(case_id).status is OrderStatus.CROSS_CHECKED
        await world.services.confirmations.sent(
            AN.context(),
            case_id,
            case_version=_version(world, case_id),
            delivery_dates={x.line_no: [HELD] * x.deliveries for x in world.order(case_id).lines},
            sent_message_id="S1",
        )

    # Before DW1 made the Excel of this version, nothing matched.
    assert before is None
    assert view.confirmation_copy is not None and view.confirmation_copy.message_id == "S1"
    sent = world.order(case_id).confirmation
    assert sent is not None and sent.message_id == "S1"
    assert sent.sent_at == datetime(2026, 10, 5, 9, 30, tzinfo=HANOI)


async def test_a_sent_copy_whose_excel_differs_proposes_nothing(tmp_path: Path) -> None:
    other = tmp_path / "edited.xlsx"
    other.write_bytes((await _processed_excel(tmp_path)).read_bytes() + b"\0")
    with SampleWith([_sales_copy(other)]) as sample:
        world = _world(sample)
        ((disposition, _),) = (await world.process_each(AN, ["M04"])).values()
        case_id = disposition.case_id
        assert case_id is not None
        await _walk_to_cross_checked(world, case_id)
        await world.services.artifacts.render_order(
            AN.context(), case_id, kind=CONFIRMATION_EXCEL, case_version=_version(world, case_id)
        )
        view = await world.services.orders.get(AN.context(), case_id)
        version = _version(world, case_id)
        with pytest.raises(ConflictError) as refused:
            await world.services.confirmations.sent(
                AN.context(),
                case_id,
                case_version=version,
                delivery_dates={
                    x.line_no: [HELD] * x.deliveries for x in world.order(case_id).lines
                },
                sent_message_id="S1",
            )

    assert view.confirmation_copy is None
    assert refused.value.details["rule"] == "not_the_confirmation"
    assert _version(world, case_id) == version


async def test_a_reply_on_another_order_does_not_accept_this_one() -> None:
    """R1 is NRV's reply on M04; M01 is VLX's order with its confirmation
    sent: naming R1 there finds no reply on M01."""
    with SampleWith([_reply("R1", html=None, body=ACCEPT)]) as sample:
        world = _world(sample)
        await _sent_to_customer(world)
        await world.process_each(AN, ["R1"])
        ((disposition, _),) = (await world.process_each(AN, ["M01"])).values()
        other = disposition.case_id
        assert other is not None
        await world.walk_to_uploaded(AN, other)
        await world.cross_check(DIEU, other)
        await world.confirm(AN, other, HELD)
        assert world.order(other).status is OrderStatus.CONFIRMATION_SENT
        version = _version(world, other)
        with pytest.raises(NotFoundError):
            await _agree(world, other, "accepted", message_id="R1")

    assert _version(world, other) == version
