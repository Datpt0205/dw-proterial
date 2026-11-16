"""The waits tickets 06, 09 and 16 left unreminded, and the follow-ups' words
as the tenant's copy (ticket 42 family 6).

- **06**: an order line Sales asked Design to create a PRV code for reminds
  the PIC a day later (the platform's `waiting_design_code`), and nothing
  once the line's code is confirmed.
- **09**: an order waiting on a quote case opened from it reminds the PIC a
  day later (`waiting_quote`), read from the quote's own status: nothing once
  the quote is declined or approved, nor once the order is past review.
- **16**: a quote whose Design result was read from Bravo's YCBG export is
  not chased for Design's answer, though its status stays `sent_to_design`.
- **Words**: every reminder, brief and push line is the tenant's
  `sales_reminders` copy; a version written before a template existed reads
  it as the platform has it, another tenant's never reaches this one, and a
  template naming a value its reminder does not fill is refused.

Domain rules first (`owed`), then the lane over the in-memory world, whose
follow-up store reads the waits as `SqlFollowupStore` does
(`test_followup_waits_db.py` repeats that read on PostgreSQL).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import RuleScope, RuleVersion
from dw_sales.adapters.policy_files import rule_book
from dw_sales.application.followups import FollowupLane, parse_source_key
from dw_sales.application.reminder_copy import ReminderCopy
from dw_sales.application.rules import RuleKey
from dw_sales.application.ycbg_exports import BravoYcbgLine, DesignChecks, ExportedYcbg
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import Followup, SalesFollowups, WaitingCase, owed
from dw_sales.domain.orders import OrderStatus
from dw_sales.domain.quotes import DeclineReason, QuoteStatus
from dw_sales.evals.graders import AN, CALLERS, DIEU
from dw_sales.evals.world import ALPHA, BETA, NOW, SampleSet, World, open_world
from dw_sales.evals.world import Directory as Holders
from dw_sales.testing.followups import platform_followups, platform_reminder_copy

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)
T0 = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)
# M10's one line as the fictional request reads it (`test_ycbg_bravo_shape`).
M10_WORDS = "MULTI-CORE CABLE 4C AWG22 STRANDED TINNED CU BRAID SHIELD GREY REEL 300M SPEC SP-5406"


# ------------------------------------------------------- the rule (owed) --


def _order(status: OrderStatus = OrderStatus.IN_REVIEW, **waits: Any) -> WaitingCase:
    return WaitingCase(
        kind=CaseKind.ORDER,
        case_id=uuid.UUID(int=6),
        status=status.value,
        reference="PO-1",
        customer_code="C-1",
        received_at=T0,
        status_since=T0,
        assigned_to=uuid.UUID(int=1),
        due=None,
        **waits,
    )


def _sent_to_design(*, checked: bool) -> WaitingCase:
    return replace(
        _order(),
        kind=CaseKind.QUOTE,
        status=QuoteStatus.SENT_TO_DESIGN.value,
        design_checked=checked,
    )


def _owed(
    case: WaitingCase, at: datetime, policy: SalesFollowups | None = None
) -> list[tuple[str, str, datetime]]:
    return [
        (d.followup.value, d.stage.value, d.since)
        for d in owed(policy or platform_followups(), [case], at)
    ]


def test_a_line_waiting_on_design_reminds_the_pic_a_day_after_the_request() -> None:
    case = _order(design_asked_at=T0)
    assert ("waiting_design_code", "remind", T0) not in _owed(case, T0 + 24 * HOUR - MINUTE)
    found = owed(platform_followups(), [case], T0 + 24 * HOUR)
    waits = [d for d in found if d.followup is Followup.WAITING_DESIGN_CODE]
    assert [(d.since, d.notify) for d in waits] == [(T0, ("pic",))]


def test_no_line_waiting_on_design_reminds_nobody_about_design() -> None:
    """The domain drops a request as the line's code is confirmed, a new
    revision arrives or the order leaves review: no request, no wait."""
    assert not [f for f, _, _ in _owed(_order(), T0 + 99 * HOUR) if f == "waiting_design_code"]


@pytest.mark.parametrize("status", [OrderStatus.CHECKED, OrderStatus.IN_REVIEW])
def test_an_order_waiting_on_its_quote_reminds_the_pic_a_day_after_it_was_opened(
    status: OrderStatus,
) -> None:
    case = _order(status, quote_open_since=T0)
    assert ("waiting_quote", "remind", T0) not in _owed(case, T0 + 24 * HOUR - MINUTE)
    assert ("waiting_quote", "remind", T0) in _owed(case, T0 + 24 * HOUR)


@pytest.mark.parametrize(
    "case",
    [
        # Every linked quote approved or declined: the store reads no open one.
        _order(quote_open_since=None),
        # Past review: the order was prepared once its quote settled, and a
        # quote priced again later is not a wait of this order's any more.
        _order(OrderStatus.PREPARED, quote_open_since=T0),
        _order(OrderStatus.CLOSED, quote_open_since=T0),
    ],
)
def test_an_order_that_waits_on_no_open_quote_is_not_reminded_of_one(case: WaitingCase) -> None:
    assert not [f for f, _, _ in _owed(case, T0 + 99 * HOUR) if f == "waiting_quote"]


def test_a_quote_whose_design_result_was_read_from_bravo_is_not_chased() -> None:
    """Ticket 16: Design answered in Bravo's YCBG; the status stays
    `sent_to_design`, but nothing is left to chase Design for."""
    later = T0 + 99 * HOUR
    assert ("quote_waiting_design", "remind", T0) in _owed(_sent_to_design(checked=False), later)
    assert not [
        f for f, _, _ in _owed(_sent_to_design(checked=True), later) if f == "quote_waiting_design"
    ]


def test_each_new_wait_switched_off_reminds_nobody() -> None:
    document = platform_followups().model_dump(mode="json")
    for name in ("waiting_design_code", "waiting_quote"):
        document[name] = {**document[name], "enabled": False}
    off = SalesFollowups.model_validate(document)
    case = _order(design_asked_at=T0, quote_open_since=T0)
    found = {f for f, _, _ in _owed(case, T0 + 99 * HOUR, off)}
    assert not found & {"waiting_design_code", "waiting_quote"}


# --------------------------------------------- the lane over the world --


@dataclass
class Sender:
    """`NotificationSenderPort` keeping (follow-up, title, body, recipients)."""

    calls: list[tuple[str, str, str, tuple[uuid.UUID, ...]]] = field(default_factory=list)

    async def deliver(
        self,
        context: AccessContext,
        *,
        recipients: Sequence[uuid.UUID],
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None:
        key = parse_source_key(source_key)
        assert key is not None
        self.calls.append((key.followup, title, body, tuple(recipients)))

    def of(self, followup: Followup) -> list[tuple[str, str, tuple[uuid.UUID, ...]]]:
        return [(t, b, r) for f, t, b, r in self.calls if f == followup.value]


class StoredWords:
    """`RuleVersionLookupPort` holding one tenant's approved version of the
    reminder copy, as ``document`` (any shape, as a version written under an
    earlier schema is stored), and nothing else of anyone's."""

    def __init__(self, tenant_id: uuid.UUID, document: Mapping[str, Any]) -> None:
        self.tenant_id, self.document = tenant_id, document

    def _version(self, scope: RuleScope, key: str) -> RuleVersion | None:
        if scope.tenant_id.value != self.tenant_id or key != RuleKey.REMINDERS.value:
            return None
        return RuleVersion(
            version_id=uuid.UUID(int=0x42),
            key=key,
            version=str(self.document["version"]),
            document=self.document,
            status="approved",
            proposed_by=uuid.UUID(int=1),
            proposed_at=T0,
            decided_by=uuid.UUID(int=2),
            decided_at=T0,
        )

    async def approved(self, scope: RuleScope, key: str) -> RuleVersion | None:
        return self._version(scope, key)

    async def find(self, scope: RuleScope, key: str, version: str) -> RuleVersion | None:
        found = self._version(scope, key)
        return found if found is not None and found.version == version else None


def _lane(world: World, sender: Sender, clock: FixedClock, words: StoredWords | None) -> Any:
    stored = words if words is not None else world.store.rule_versions
    return FollowupLane(
        uow=world.store,
        policies=rule_book(world.policies, stored),
        holders=Holders(CALLERS),
        notifications=sender,
        clock=clock,
        ids=Uuid4Generator(),
    )


async def _tick(world: World, at: datetime, words: StoredWords | None = None) -> Sender:
    """One tick at ``at``: what it delivered. What an earlier tick recorded
    is not delivered again (the world keeps the record), so a test asks
    after the wait ended in a tick of its own."""
    sender = Sender()
    await _lane(world, sender, FixedClock(at), words).tick(ALPHA)
    return sender


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _m04_waiting_on_design(world: World) -> tuple[uuid.UUID, datetime]:
    """M04 (NRV-PO-26-0457) in review, line 3 asked of Design (ticket 06)."""
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
    await world.services.design_requests.ask(
        AN.context(), case_id, 3, case_version=world.order(case_id).case_version
    )
    (request,) = world.order(case_id).design_requests
    return case_id, request.at


async def test_the_pic_is_reminded_while_design_has_not_named_the_code() -> None:
    world = _world()
    _, asked = await _m04_waiting_on_design(world)
    assert (await _tick(world, asked + 24 * HOUR - MINUTE)).of(Followup.WAITING_DESIGN_CODE) == []

    ((title, body, recipients),) = (await _tick(world, asked + 24 * HOUR)).of(
        Followup.WAITING_DESIGN_CODE
    )

    assert recipients == (AN.user_id,)
    assert title == "Nhắc: PO NRV-PO-26-0457 đang chờ Design tạo mã"
    assert "hơn 24 giờ" in body and "DW1 không gửi thư cho Design" in body


async def test_the_reminder_stops_the_moment_the_lines_code_is_confirmed() -> None:
    world = _world()
    case_id, asked = await _m04_waiting_on_design(world)
    await world.services.order_commands.confirm_mapping(
        AN.context(), case_id, 3, case_version=world.order(case_id).case_version, prv_code="CB-2018"
    )
    assert world.order(case_id).design_requests == ()

    assert (await _tick(world, asked + 99 * HOUR)).of(Followup.WAITING_DESIGN_CODE) == []


async def _m03_with_its_quote(world: World) -> tuple[uuid.UUID, uuid.UUID, datetime]:
    """M03 (line 2 without a valid quotation) with "Mở báo giá" opened."""
    ((disposition, _),) = (await world.process_each(AN, ["M03"])).values()
    case_id = disposition.case_id
    assert case_id is not None
    view = await world.services.order_quotes.open(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )
    (link,) = world.order(case_id).quote_links
    return case_id, view.quote_case_id, link.at


async def test_the_pic_is_reminded_while_the_order_waits_on_its_quote() -> None:
    world = _world()
    _, _, opened = await _m03_with_its_quote(world)
    assert (await _tick(world, opened + 24 * HOUR - MINUTE)).of(Followup.WAITING_QUOTE) == []

    ((title, body, recipients),) = (await _tick(world, opened + 24 * HOUR)).of(
        Followup.WAITING_QUOTE
    )

    assert recipients == (AN.user_id,)
    assert title == "Nhắc: PO BRN-PO-2609-031 đang chờ báo giá"
    assert "chưa chuẩn bị được" in body


async def test_the_reminder_stops_the_moment_the_quote_is_settled() -> None:
    """Read from the quote's own status at the tick: declined, nothing."""
    world = _world()
    _, quote_id, opened = await _m03_with_its_quote(world)
    await world.services.quote_commands.decline(
        AN.context(),
        quote_id,
        case_version=world.quote(quote_id).case_version,
        reason=DeclineReason.COMMERCIAL,
        note=None,
    )

    assert (await _tick(world, opened + 99 * HOUR)).of(Followup.WAITING_QUOTE) == []


async def _m10_sent_to_design(world: World) -> tuple[uuid.UUID, str]:
    seen = await world.process_each(DIEU, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None
    commands, context = world.services.quote_commands, DIEU.context()
    ycbg = "RFQ260930-030"
    for number in (None, ycbg):
        await commands.ycbg(
            context, case_id, case_version=world.quote(case_id).case_version, ycbg_no=number
        )
    await commands.design_sent(context, case_id, case_version=world.quote(case_id).case_version)
    return case_id, ycbg


async def test_a_quote_whose_design_check_was_read_is_not_chased_for_design() -> None:
    """Ticket 16: two worlds, one case each, both `sent_to_design`; the one
    whose Design result was read from the export is not chased."""
    later = NOW + 99 * HOUR
    unread = _world()
    await _m10_sent_to_design(unread)
    assert len((await _tick(unread, later)).of(Followup.QUOTE_WAITING_DESIGN)) == 1

    world = _world()
    case_id, ycbg = await _m10_sent_to_design(world)
    line = BravoYcbgLine.model_validate(
        {
            "ycbg_no": ycbg,
            "line_no": 1,
            "status": "close",
            "verdict": "quote",
            "bp_code": "BP-26-0187",
            "reason": None,
            # The request's own words for the line, as Sales entered them.
            "description": M10_WORDS,
        }
    )
    checks = DesignChecks(world.store, world.store, FixedClock(NOW), Uuid4Generator())
    (outcome,) = await checks.take(DIEU.context(), ExportedYcbg((line,)), file_sha256="a" * 64)
    assert outcome.outcome == "recorded"
    assert world.quote(case_id).status is QuoteStatus.SENT_TO_DESIGN

    assert (await _tick(world, later)).of(Followup.QUOTE_WAITING_DESIGN) == []


# ----------------------------------------------------------- the words --


def _words_without(path: tuple[str, str], **changed: tuple[str, str, str]) -> dict[str, Any]:
    """The platform's copy as a tenant's version 1.0.1: ``changed`` templates
    reworded (section, template, field -> words), and ``path`` left out, as a
    version written before that template existed."""
    document = platform_reminder_copy().model_dump(mode="json")
    document["version"] = "1.0.1"
    for section, name, text in changed.values():
        document[section][name] = {**document[section][name], "title": text}
    del document[path[0]][path[1]]
    return document


async def test_a_tenants_words_are_said_and_a_template_it_lacks_is_the_platforms() -> None:
    world = _world()
    _, _, opened = await _m03_with_its_quote(world)
    words = StoredWords(
        ALPHA.tenant_id.value,
        _words_without(
            ("reminders", "waiting_quote"),
            pc=("reminders", "waiting_pc", "Nhắc PC: PO {ref}"),
        ),
    )
    book = rule_book(world.policies, words)
    copy = await book.reminder_copy(ALPHA)
    assert copy.reminders.waiting_pc.title == "Nhắc PC: PO {ref}"
    assert copy.reminders.waiting_quote == platform_reminder_copy().reminders.waiting_quote

    ((title, _, _),) = (await _tick(world, opened + 24 * HOUR, words)).of(Followup.WAITING_QUOTE)

    assert title == "Nhắc: PO BRN-PO-2609-031 đang chờ báo giá"


async def test_a_tenants_words_reach_its_own_reminders_and_no_other_tenants() -> None:
    world = _world()
    _, _, opened = await _m03_with_its_quote(world)
    words = StoredWords(
        ALPHA.tenant_id.value,
        _words_without(
            ("reminders", "waiting_design_code"),
            quote=("reminders", "waiting_quote", "Đơn {ref} chờ báo giá"),
        ),
    )
    ((title, _, _),) = (await _tick(world, opened + 24 * HOUR, words)).of(Followup.WAITING_QUOTE)
    assert title == "Đơn BRN-PO-2609-031 chờ báo giá"

    book = rule_book(world.policies, words)
    assert await book.reminder_copy(BETA) == platform_reminder_copy()


@pytest.mark.parametrize(
    ("section", "name", "field_name", "text"),
    [
        # A due date is no fact of a wait on a quote.
        ("reminders", "waiting_quote", "body", "PO {ref} hạn {due}"),
        # Attribute access, never a value code fills.
        ("reminders", "waiting_pc", "title", "{ref.__class__}"),
        ("brief", "title", None, "Tóm tắt {customer}"),
        # A push never carries the case's number in its words, nor anything else.
        ("push", "waiting_quote", None, "Chờ {ref}"),
        ("next_steps", "other", None, "Mở {ref}"),
    ],
)
def test_a_template_naming_a_value_its_reminder_does_not_fill_is_refused(
    section: str, name: str, field_name: str | None, text: str
) -> None:
    document = platform_reminder_copy().model_dump(mode="json")
    if field_name is None:
        document[section][name] = text
    else:
        document[section][name] = {**document[section][name], field_name: text}
    with pytest.raises(ValidationError):
        ReminderCopy.model_validate(document)


def test_the_brief_names_every_bucket_once() -> None:
    document = platform_reminder_copy().model_dump(mode="json")
    del document["brief"]["waits_on"]["design"]
    with pytest.raises(ValidationError):
        ReminderCopy.model_validate(document)


def test_every_followup_has_its_words() -> None:
    """A follow-up added to `Followup` fails here until it has a reminder and
    a push in the platform's copy."""
    reminders = set(type(platform_reminder_copy().reminders).model_fields)
    pushes = set(type(platform_reminder_copy().push).model_fields)
    for followup in set(Followup) - {Followup.YOUR_TURN, Followup.WAITING_CUSTOMER}:
        assert any(name.startswith(followup.value) for name in reminders), followup
        assert any(name.startswith(followup.value) for name in pushes), followup
