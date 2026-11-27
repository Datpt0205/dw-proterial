"""The channel delivery lane's decisions, against a fake outbox and a fake chat.

What each due row comes to: sent once, cancelled without a send when the person
left the workspace or unlinked, failed after one try when the chat is gone,
retried with a doubling delay on any other failure and failed at the ceiling.
And what a message says: names, title, link, never the notification's body.
The SQL half (locks, RLS, audit) is `test_channel_delivery_db.py`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta

import pytest

from dw_connectors.ports import ChatRecipientUnreachableError
from dw_kernel.channels import chat_reference
from dw_observability.metrics import DW_CHANNEL_DELIVERY_EXHAUSTED_TOTAL
from dw_observability.telemetry import RecordingTelemetry
from dw_worker.consumers.channel_delivery import (
    BASE_DELAY,
    MAX_ATTEMPTS,
    backoff,
    build_channel_delivery_consumer,
    compose,
)
from dw_worker.consumers.scope_failures import ScopesFailedError

pytestmark = pytest.mark.unit

WEB = "https://portal.example/"


@dataclass(frozen=True)
class _Scope:
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID


@dataclass
class _Row:
    recipient_user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    title: str = "Đơn 007 chờ bạn duyệt"
    link: str | None = "/approvals/abc"
    attempts: int = 0
    tenant_name: str = "Acme"
    workspace_name: str = "Vận hành"
    member: bool = True
    status: str = "pending"
    outcome: tuple[object, ...] | None = None

    async def recipient_may_receive(self) -> bool:
        return self.member

    async def mark_sent(self, external_message_id: str, chat_reference: str) -> None:
        self._settle("sent", external_message_id, chat_reference)

    async def mark_failed(self, reason: str, error: str) -> None:
        self._settle("failed", reason)

    async def mark_cancelled(self, reason: str) -> None:
        self._settle("cancelled", reason)

    async def retry_later(self, error: str, delay: timedelta) -> None:
        # Like the adapter: pending still, one attempt more.
        self.attempts += 1
        self.outcome = ("retry", delay)

    def _settle(self, status: str, *detail: object) -> None:
        assert self.status == "pending", "a settled row was settled again"
        self.status = status
        self.outcome = (status, *detail)


@dataclass
class _Outbox:
    rows: list[_Row]
    scope: _Scope = field(default_factory=lambda: _Scope(uuid.uuid4(), uuid.uuid4()))

    async def due_scopes(self, channel: str) -> list[_Scope]:
        assert channel == "zalo"
        return [self.scope] if self._due() else []

    def _due(self) -> list[_Row]:
        return [r for r in self.rows if r.status == "pending" and r.outcome is None]

    @asynccontextmanager
    async def claim_next(self, channel: str, scope: _Scope) -> AsyncIterator[_Row | None]:
        due = self._due()
        yield due[0] if due else None


@dataclass
class _Chat:
    fail_with: list[Exception] = field(default_factory=list)
    sent: list[tuple[str, str]] = field(default_factory=list)

    async def send_message(self, conversation_id: str, text: str) -> str:
        if self.fail_with:
            raise self.fail_with.pop(0)
        self.sent.append((conversation_id, text))
        return f"m{len(self.sent)}"


def _lane(outbox, chat, links, telemetry=None):  # type: ignore[no-untyped-def]
    async def address_of(user_id: uuid.UUID) -> str | None:
        return links.get(user_id)

    return build_channel_delivery_consumer(
        outbox,
        channel="zalo",
        address_of=address_of,
        sender=chat,
        web_url=WEB,
        telemetry=telemetry or RecordingTelemetry(),
    )


def _exhausted(telemetry: RecordingTelemetry) -> list[float]:
    return [
        float(value)
        for name, value, labels in telemetry.metrics
        if name == DW_CHANNEL_DELIVERY_EXHAUSTED_TOTAL and labels == {"channel": "zalo"}
    ]


async def test_a_linked_member_is_sent_the_message_once() -> None:
    row = _Row()
    chat = _Chat()
    lane = _lane(_Outbox([row]), chat, {row.recipient_user_id: "z-1"})
    await lane()
    await lane()

    assert chat.sent == [
        (
            "z-1",
            "[Acme · Vận hành]\nĐơn 007 chờ bạn duyệt\nhttps://portal.example/approvals/abc",
        )
    ]
    assert row.outcome == ("sent", "m1", chat_reference("zalo", "z-1"))


async def test_a_link_removed_before_the_send_cancels_it_and_sends_nothing() -> None:
    row = _Row()
    chat = _Chat()
    await _lane(_Outbox([row]), chat, {})()
    assert chat.sent == []
    assert row.outcome == ("cancelled", "recipient_unlinked")


async def test_someone_no_longer_in_the_workspace_is_sent_nothing() -> None:
    row = _Row(member=False)
    chat = _Chat()
    await _lane(_Outbox([row]), chat, {row.recipient_user_id: "z-1"})()
    assert chat.sent == []
    assert row.outcome == ("cancelled", "recipient_not_member")


async def test_an_unreachable_chat_fails_after_one_try() -> None:
    row = _Row()
    chat = _Chat(fail_with=[ChatRecipientUnreachableError("blocked")])
    await _lane(_Outbox([row]), chat, {row.recipient_user_id: "z-1"})()
    assert row.outcome == ("failed", "recipient_unreachable")


async def test_a_passing_failure_is_retried_later_with_a_doubling_delay() -> None:
    row = _Row()
    chat = _Chat(fail_with=[RuntimeError("zalo request failed: 502")])
    outbox = _Outbox([row])
    await _lane(outbox, chat, {row.recipient_user_id: "z-1"})()
    assert row.status == "pending" and row.attempts == 1
    assert row.outcome == ("retry", BASE_DELAY)
    assert [backoff(n) for n in (1, 2, 3, 4)] == [BASE_DELAY * k for k in (1, 2, 4, 8)]

    row.outcome = None  # due again
    await _lane(outbox, chat, {row.recipient_user_id: "z-1"})()
    assert row.outcome == ("sent", "m1", chat_reference("zalo", "z-1"))
    assert len(chat.sent) == 1


async def test_the_last_allowed_attempt_failing_fails_the_row() -> None:
    row = _Row(attempts=MAX_ATTEMPTS - 1)
    chat = _Chat(fail_with=[RuntimeError("still down")])
    await _lane(_Outbox([row]), chat, {row.recipient_user_id: "z-1"})()
    assert row.outcome == ("failed", "attempts_exhausted")


async def test_one_row_failing_to_settle_does_not_stop_the_lane() -> None:
    """A database error mid-row is logged and the row stays pending for the
    next tick; the lane then raises, so its tick is not clean (ticket 84)."""

    @dataclass
    class _Broken(_Row):
        async def mark_sent(self, external_message_id: str, chat_reference: str) -> None:
            raise RuntimeError("connection lost")

    row = _Broken()
    with pytest.raises(ScopesFailedError):
        await _lane(_Outbox([row]), _Chat(), {row.recipient_user_id: "z-1"})()
    assert row.status == "pending"


def test_the_message_never_carries_the_body_a_code_or_anything_but_its_four_parts() -> None:
    """`compose` takes no body: whatever a notification's body holds (a
    decision code, a price) has no way into the chat
    (ADR 0006-provider-neutral-channel-delivery-outbox)."""
    text = compose(
        tenant_name="Acme",
        workspace_name="Vận hành",
        title="Có việc cần duyệt",
        link=None,
        web_url="https://portal.example",
    )
    assert text == "[Acme · Vận hành]\nCó việc cần duyệt\nhttps://portal.example/"


async def test_only_a_row_given_up_on_counts_and_the_count_starts_at_zero() -> None:
    """Ticket 84: `DwDeliveryExhausted` reads this. The series exists at 0 from
    the start (or `increase()` would miss the first), a retry and a
    recipient-side end count nothing, and the ceiling counts once."""
    telemetry = RecordingTelemetry()
    retried, gone, given_up = _Row(), _Row(), _Row(attempts=MAX_ATTEMPTS - 1)
    chat = _Chat(
        fail_with=[OSError("down"), ChatRecipientUnreachableError("gone"), OSError("down")]
    )
    links = {r.recipient_user_id: "z" for r in (retried, gone, given_up)}

    lane = _lane(_Outbox([retried, gone, given_up]), chat, links, telemetry)
    assert _exhausted(telemetry) == [0.0]
    await lane()

    assert [retried.outcome and retried.outcome[0], gone.outcome, given_up.outcome] == [
        "retry",
        ("failed", "recipient_unreachable"),
        ("failed", "attempts_exhausted"),
    ]
    assert _exhausted(telemetry) == [0.0, 1.0]


async def test_a_row_given_up_on_whose_commit_failed_is_not_counted() -> None:
    """Counted after the claim's transaction ends: a rollback leaves it pending."""

    @dataclass
    class _CommitFails(_Outbox):
        @asynccontextmanager
        async def claim_next(self, channel: str, scope: _Scope) -> AsyncIterator[_Row | None]:
            due = self._due()
            yield due[0] if due else None
            raise RuntimeError("commit lost")

    telemetry = RecordingTelemetry()
    row = _Row(attempts=MAX_ATTEMPTS - 1)
    with pytest.raises(ScopesFailedError):
        await _lane(
            _CommitFails([row]),
            _Chat(fail_with=[OSError("down")]),
            {row.recipient_user_id: "z"},
            telemetry,
        )()
    assert _exhausted(telemetry) == [0.0]


@dataclass
class _TwoWorkspaces:
    """Two workspaces due, the first one's row failing to settle."""

    first: _Outbox
    second: _Outbox

    async def due_scopes(self, channel: str) -> list[_Scope]:
        return [s for o in (self.first, self.second) for s in await o.due_scopes(channel)]

    def claim_next(self, channel: str, scope: _Scope):  # type: ignore[no-untyped-def]
        outbox = self.first if scope == self.first.scope else self.second
        return outbox.claim_next(channel, scope)


async def test_a_workspace_that_failed_does_not_stop_the_next_one_being_sent() -> None:
    """The raise comes after the last workspace (ticket 84): the one behind the
    failing one is still served this tick."""

    @dataclass
    class _Broken(_Row):
        async def mark_sent(self, external_message_id: str, chat_reference: str) -> None:
            raise RuntimeError("connection lost")

    broken, fine = _Broken(), _Row()
    links = {broken.recipient_user_id: "z-1", fine.recipient_user_id: "z-2"}
    with pytest.raises(ScopesFailedError, match="channel_delivery:zalo: 1 scope"):
        await _lane(_TwoWorkspaces(_Outbox([broken]), _Outbox([fine])), _Chat(), links)()
    assert broken.status == "pending"
    assert fine.outcome == ("sent", "m2", chat_reference("zalo", "z-2"))
