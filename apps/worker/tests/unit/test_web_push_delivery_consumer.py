"""The web push lane's decisions (Sales ticket 78), against a fake outbox and a
fake push service: sent when a device took it, cancelled when the person left
the workspace, failed when no device took it, retried with a doubling delay
when the push service raised, failed at the ceiling. And what leaves: title,
place, link and the one inbox tag, never the notification's body."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta

import pytest

from dw_observability.metrics import DW_CHANNEL_DELIVERY_EXHAUSTED_TOTAL
from dw_observability.telemetry import RecordingTelemetry
from dw_worker.consumers.channel_delivery import MAX_ATTEMPTS, backoff
from dw_worker.consumers.scope_failures import ScopesFailedError
from dw_worker.consumers.web_push_delivery import TAG, build_web_push_delivery_consumer

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class _Scope:
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID


@dataclass
class _Row:
    recipient_user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    title: str = "Đơn 007 chờ bạn kiểm chéo"
    link: str | None = "/sales/orders/abc"
    attempts: int = 0
    tenant_name: str = "Acme"
    workspace_name: str = "Sales"
    member: bool = True
    status: str = "pending"
    outcome: tuple[object, ...] | None = None

    async def recipient_may_receive(self) -> bool:
        return self.member

    async def mark_sent(self, external_message_id: str, chat_reference: str) -> None:
        self._settle("sent")

    async def mark_failed(self, reason: str, error: str) -> None:
        self._settle("failed", reason)

    async def mark_cancelled(self, reason: str) -> None:
        self._settle("cancelled", reason)

    async def retry_later(self, error: str, delay: timedelta) -> None:
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
        assert channel == "web_push"
        return [self.scope] if self._due() else []

    def _due(self) -> list[_Row]:
        return [r for r in self.rows if r.status == "pending" and r.outcome is None]

    @asynccontextmanager
    async def claim_next(self, channel: str, scope: _Scope) -> AsyncIterator[_Row | None]:
        due = self._due()
        yield due[0] if due else None


@dataclass(frozen=True)
class _Result:
    reached: int


@dataclass
class _Push:
    reached: int = 1
    fail_with: Exception | None = None
    sent: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, Mapping[str, object]]] = field(
        default_factory=list
    )

    async def push(
        self,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        person: uuid.UUID,
        payload: Mapping[str, object],
    ) -> _Result:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append((tenant_id, workspace_id, person, payload))
        return _Result(self.reached)


def _lane(outbox, push, telemetry=None):  # type: ignore[no-untyped-def]
    return build_web_push_delivery_consumer(
        outbox, push, telemetry=telemetry or RecordingTelemetry()
    )


async def test_a_push_a_device_took_is_sent_with_the_title_place_and_link_only() -> None:
    row, push = _Row(), _Push()
    outbox = _Outbox([row])

    await _lane(outbox, push)()

    assert row.outcome == ("sent",)
    [(tenant, workspace, person, payload)] = push.sent
    assert (tenant, workspace, person) == (
        outbox.scope.tenant_id,
        outbox.scope.workspace_id,
        row.recipient_user_id,
    )
    assert payload == {
        "title": "Đơn 007 chờ bạn kiểm chéo",
        "body": "Acme · Sales",
        "url": "/sales/orders/abc",
        "count": 1,
        "tag": TAG,
    }


async def test_someone_no_longer_in_the_workspace_is_not_pushed() -> None:
    row, push = _Row(member=False), _Push()

    await _lane(_Outbox([row]), push)()

    assert row.outcome == ("cancelled", "recipient_not_member") and push.sent == []


async def test_no_device_taking_it_fails_the_row_and_the_inbox_keeps_it() -> None:
    row = _Row()

    await _lane(_Outbox([row]), _Push(reached=0))()

    assert row.outcome == ("failed", "no_device_reached")


async def test_the_push_service_raising_is_retried_then_given_up() -> None:
    row = _Row()
    lane = _lane(_Outbox([row]), _Push(fail_with=OSError("down")))

    await lane()
    assert row.outcome == ("retry", backoff(1)) and row.status == "pending"

    row.attempts, row.outcome = MAX_ATTEMPTS - 1, None
    await lane()
    assert row.outcome == ("failed", "attempts_exhausted")


async def test_a_scope_that_failed_mid_row_makes_the_tick_raise_after_the_others() -> None:
    """The row rolls back to pending for the next tick; the lane then raises so
    its tick is not recorded as clean (ticket 84)."""

    @dataclass
    class _Broken(_Row):
        async def mark_sent(self, external_message_id: str, chat_reference: str) -> None:
            raise RuntimeError("connection lost")

    row = _Broken()
    with pytest.raises(ScopesFailedError):
        await _lane(_Outbox([row]), _Push())()
    assert row.status == "pending"


async def test_a_push_given_up_on_counts_once_and_no_device_counts_nothing() -> None:
    """Ticket 84: no device taking it is the person's phone, not the system."""
    telemetry = RecordingTelemetry()

    def counted() -> list[float]:
        return [
            float(v)
            for n, v, labels in telemetry.metrics
            if n == DW_CHANNEL_DELIVERY_EXHAUSTED_TOTAL and labels == {"channel": "web_push"}
        ]

    await _lane(_Outbox([_Row()]), _Push(reached=0), telemetry)()
    assert counted() == [0.0]
    await _lane(
        _Outbox([_Row(attempts=MAX_ATTEMPTS - 1)]), _Push(fail_with=OSError("down")), telemetry
    )()
    assert counted() == [0.0, 0.0, 1.0]
