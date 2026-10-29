"""Background work that stopped, told to a person and sent back by one.

Đạt, 2026-10-29: "không thể làm hỏng luồng rồi im lặng luôn được". An outbox
event that spends `OUTBOX_MAX_ATTEMPTS` is claimed by no dispatcher again: a
master-data upload stays "đang đọc", a decided rule version is never applied.
Until now only a log line and a gauge said so. Two halves close it:

- **`OutboxAlarms`** (the worker's `outbox_alarms` lane) tells every member
  of the event's workspace who administers the tenant
  (`platform.tenant.settings.write`) in an in-app notice, once per event.
- **`BackgroundFailuresService`** lists the workspace's stopped events and
  sends one back to the queue with its attempts reset, audited in the same
  transaction, under the same scope.

**What is shown is the kind of error, never its text.** A delivery's error
can carry what the failing statement held (a database refusal echoes its
row), and an administrator is not someone who may see every price. The full
text stays in the row and the worker's log, for whoever runs the deployment.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from dw_kernel.errors import NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.admin_console import TENANT_SETTINGS_WRITE
from dw_platform.application.ports import AuthorizationPort
from dw_platform.domain.audit import AuditEvent, system_actor
from dw_platform.domain.outbox import OutboxEvent

logger = logging.getLogger("dw_platform.background_failures")

OUTBOX_ALARMS_LANE: Final = "outbox_alarms"
BACKGROUND_FAILURES_LINK: Final = "/admin/background-failures"
_ACTION_REQUEUE = "platform.outbox.requeued"
_RESOURCE = "outbox_event"


def error_kind(last_error: str | None) -> str:
    """What may be shown of a delivery's error: the exception's name, when the
    dispatcher wrote one (``"Name: text"``), else that it was refused."""
    if not last_error:
        return "Không rõ"
    head, sep, _ = last_error.partition(":")
    return head if sep and head.isidentifier() else "Bị từ chối"


@dataclass(frozen=True, slots=True)
class StalledEvent:
    """An event no dispatcher will claim again, as an administrator sees it."""

    id: uuid.UUID
    event_type: str
    occurred_at: datetime
    attempts: int
    error_kind: str


# ------------------------------------------------------------ the alarm --


class ExhaustedEventsPort(Protocol):
    async def exhausted(self, *, max_attempts: int, limit: int) -> list[OutboxEvent]: ...


class TenantAdminsPort(Protocol):
    async def holding(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, scopes: frozenset[str]
    ) -> list[uuid.UUID]: ...


class NoticePort(Protocol):
    async def deliver(
        self,
        context: AccessContext,
        *,
        recipients: Sequence[uuid.UUID],
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None: ...


@dataclass(frozen=True)
class OutboxAlarms:
    """Tells each stopped event's administrators, once per event: the notice's
    key is the event's id, so a sweep that finds it again sends nothing."""

    events: ExhaustedEventsPort
    admins: TenantAdminsPort
    notices: NoticePort
    max_attempts: int
    batch: int = 100

    async def sweep(self) -> int:
        """Tell what has stopped; how many events were found."""
        found = await self.events.exhausted(max_attempts=self.max_attempts, limit=self.batch)
        for event in found:
            try:
                await self._tell(event)
            except Exception:
                # Broad on purpose: one workspace's notice failing must not
                # leave the next one untold; the next sweep tries it again.
                logger.exception("outbox event %s stopped and its notice failed", event.id)
        return len(found)

    async def _tell(self, event: OutboxEvent) -> None:
        tenant, workspace = event.tenant_id.value, event.workspace_id.value
        recipients = await self.admins.holding(
            tenant, workspace, frozenset({TENANT_SETTINGS_WRITE})
        )
        if not recipients:
            # No one to tell is itself the failure; the log is all that is left.
            logger.error(
                "outbox event %s (%s) stopped and no one administers workspace %s",
                event.id,
                event.event_type,
                workspace,
            )
            return
        await self.notices.deliver(
            AccessContext(
                tenant_id=tenant,
                workspace_id=workspace,
                principal_id=system_actor(OUTBOX_ALARMS_LANE).value,
                roles=frozenset(),
                scopes=frozenset(),
                plan_id="background",
            ),
            recipients=recipients,
            source_key=f"platform.outbox.exhausted:{event.id}",
            title="Một việc nền đã dừng",
            body=(
                f"Việc nền {event.event_type} không chạy được sau {event.attempts} lần thử "
                f"(lỗi: {error_kind(event.last_error)}). Sau khi khắc phục nguyên nhân, "
                "mở trang Việc nền lỗi để chạy lại."
            ),
            link=BACKGROUND_FAILURES_LINK,
        )


# -------------------------------------------------- the admin's page --


class StalledEventsPort(Protocol):
    """The caller's workspace's stopped events (RLS binds the tenant)."""

    async def stalled(self, context: AccessContext, *, max_attempts: int) -> list[StalledEvent]: ...

    async def requeue(
        self, context: AccessContext, *, event_id: uuid.UUID, max_attempts: int, audit: AuditEvent
    ) -> bool:
        """Reset a stopped event's attempts with ``audit`` in one transaction;
        False when the workspace has no such stopped event."""
        ...


@dataclass(frozen=True)
class BackgroundFailuresService:
    repo: StalledEventsPort
    authz: AuthorizationPort
    clock: UtcClock
    id_generator: IdGenerator
    max_attempts: int

    async def stalled(self, context: AccessContext) -> list[StalledEvent]:
        await self.authz.require(
            context=context, action=TENANT_SETTINGS_WRITE, resource_type=_RESOURCE
        )
        return await self.repo.stalled(context, max_attempts=self.max_attempts)

    async def requeue(self, context: AccessContext, event_id: uuid.UUID) -> None:
        await self.authz.require(
            context=context, action=TENANT_SETTINGS_WRITE, resource_type=_RESOURCE
        )
        requeued = await self.repo.requeue(
            context,
            event_id=event_id,
            max_attempts=self.max_attempts,
            audit=AuditEvent(
                id=self.id_generator.new_uuid(),
                tenant_id=TenantId(context.tenant_id),
                workspace_id=WorkspaceId(context.workspace_id),
                actor_id=UserId(context.principal_id),
                action=_ACTION_REQUEUE,
                resource_type=_RESOURCE,
                resource_id=str(event_id),
                occurred_at=self.clock.now(),
                details={},
            ),
        )
        if not requeued:
            raise NotFoundError(
                "this workspace has no stopped background event with that id",
                details={"event_id": str(event_id)},
            )
