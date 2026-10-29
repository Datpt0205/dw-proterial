"""Background work that stopped is told to a person and sent back by one
(2026-10-29): `OutboxAlarms` and `BackgroundFailuresService` over fakes. The
SQL half is `tests/integration/test_background_failures_db.py`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from dw_kernel.errors import NotFoundError, PermissionDeniedError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.admin_console import TENANT_SETTINGS_WRITE
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.background_failures import (
    BACKGROUND_FAILURES_LINK,
    BackgroundFailuresService,
    OutboxAlarms,
    StalledEvent,
    error_kind,
)
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.outbox import OutboxEvent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
TENANT, WORKSPACE = uuid.uuid4(), uuid.uuid4()
ADMIN, OTHER_ADMIN = uuid.uuid4(), uuid.uuid4()


def _event(error: str | None = "IntegrityError: Key (price)=(18450000) violates") -> OutboxEvent:
    return OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(TENANT),
        workspace_id=WorkspaceId(WORKSPACE),
        event_type="sales.catalog.imported",
        schema_version="1",
        aggregate_id=uuid.uuid4(),
        occurred_at=NOW,
        attempts=5,
        last_error=error,
    )


class Events:
    def __init__(self, events: list[OutboxEvent]) -> None:
        self.events = events

    async def exhausted(self, *, max_attempts: int, limit: int) -> list[OutboxEvent]:
        return [e for e in self.events if e.attempts >= max_attempts][:limit]


class Admins:
    def __init__(self, members: list[uuid.UUID]) -> None:
        self.members = members
        self.asked: list[frozenset[str]] = []

    async def holding(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, scopes: frozenset[str]
    ) -> list[uuid.UUID]:
        self.asked.append(scopes)
        return self.members


class Inbox:
    """Idempotent by key, like the notification store."""

    def __init__(self, *, failing_for: uuid.UUID | None = None) -> None:
        self.sent: dict[str, tuple[list[uuid.UUID], str, str | None]] = {}
        self.failing_for = failing_for

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
        if self.failing_for is not None and str(self.failing_for) in source_key:
            raise ConnectionError("notification store down")
        assert context.scopes == frozenset()
        self.sent.setdefault(source_key, (list(recipients), body, link))


async def test_a_stopped_event_is_told_to_the_tenants_administrators_once() -> None:
    stopped = _event()
    admins, inbox = Admins([ADMIN, OTHER_ADMIN]), Inbox()
    alarms = OutboxAlarms(Events([stopped]), admins, inbox, max_attempts=5)

    assert await alarms.sweep() == 1
    assert await alarms.sweep() == 1

    assert admins.asked[0] == frozenset({TENANT_SETTINGS_WRITE})
    ((recipients, body, link),) = inbox.sent.values()
    assert recipients == [ADMIN, OTHER_ADMIN]
    assert link == BACKGROUND_FAILURES_LINK
    assert "sales.catalog.imported" in body and "IntegrityError" in body
    # The error's text, which can echo a row and its prices, is never told.
    assert "18450000" not in body


async def test_one_notice_failing_leaves_the_next_told() -> None:
    first, second = _event(), _event()
    inbox = Inbox(failing_for=first.id)
    alarms = OutboxAlarms(Events([first, second]), Admins([ADMIN]), inbox, max_attempts=5)

    await alarms.sweep()

    assert list(inbox.sent) == [f"platform.outbox.exhausted:{second.id}"]


async def test_an_event_still_retrying_is_not_told() -> None:
    retrying = _event()
    retrying.attempts = 2
    inbox = Inbox()
    assert (
        await OutboxAlarms(Events([retrying]), Admins([ADMIN]), inbox, max_attempts=5).sweep() == 0
    )
    assert inbox.sent == {}


async def test_a_workspace_no_one_administers_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    inbox = Inbox()
    await OutboxAlarms(Events([_event()]), Admins([]), inbox, max_attempts=5).sweep()
    assert inbox.sent == {}
    assert "no one administers" in caplog.text


@pytest.mark.parametrize(
    ("last_error", "kind"),
    [
        ("RuntimeError: reader down", "RuntimeError"),
        ("the decision is not the settlement's to apply", "Bị từ chối"),
        (None, "Không rõ"),
        ("Key (price)=(1): no", "Bị từ chối"),
    ],
)
def test_only_the_kind_of_error_is_shown(last_error: str | None, kind: str) -> None:
    assert error_kind(last_error) == kind


# ------------------------------------------------------------- the page --


class Repo:
    def __init__(self, stopped: list[uuid.UUID]) -> None:
        self.stopped = set(stopped)
        self.audits: list[AuditEvent] = []

    async def stalled(self, context: AccessContext, *, max_attempts: int) -> list[StalledEvent]:
        return [
            StalledEvent(e, "sales.catalog.imported", NOW, max_attempts, "RuntimeError")
            for e in self.stopped
        ]

    async def requeue(
        self, context: AccessContext, *, event_id: uuid.UUID, max_attempts: int, audit: AuditEvent
    ) -> bool:
        if event_id not in self.stopped:
            return False
        self.stopped.discard(event_id)
        self.audits.append(audit)
        return True


def _context(*scopes: str) -> AccessContext:
    return AccessContext(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        principal_id=ADMIN,
        roles=frozenset({"member"}),
        scopes=frozenset(scopes),
        plan_id="pro",
    )


def _service(repo: Repo) -> BackgroundFailuresService:
    return BackgroundFailuresService(
        repo, ScopeAuthorizationService(), FixedClock(NOW), Uuid4Generator(), max_attempts=5
    )


async def test_an_administrator_sends_a_stopped_event_back_on_the_record() -> None:
    stopped = uuid.uuid4()
    repo = Repo([stopped])
    service = _service(repo)
    admin = _context(TENANT_SETTINGS_WRITE)

    assert [e.id for e in await service.stalled(admin)] == [stopped]
    await service.requeue(admin, stopped)

    (audit,) = repo.audits
    assert (audit.action, audit.actor_id.value, audit.resource_id) == (
        "platform.outbox.requeued",
        ADMIN,
        str(stopped),
    )
    with pytest.raises(NotFoundError):
        await service.requeue(admin, stopped)


async def test_someone_who_does_not_administer_the_tenant_is_refused() -> None:
    stopped = uuid.uuid4()
    repo = Repo([stopped])
    service = _service(repo)
    member = _context("sales.case.read")

    with pytest.raises(PermissionDeniedError):
        await service.stalled(member)
    with pytest.raises(PermissionDeniedError):
        await service.requeue(member, stopped)
    assert repo.stopped == {stopped}
