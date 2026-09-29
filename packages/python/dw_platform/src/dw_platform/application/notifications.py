"""A member's in-app inbox: what the platform has told them, and read marks.

Reading and marking need no scope beyond being a member, like `/me`: the
inbox is the caller's own, and the database narrows every read and update
to rows addressed to them (migration 855ae928c3fa). A sender (a bounded
context's worker) delivers through the repository directly; it does not go
through this service, which only serves the person reading.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from dw_kernel.errors import NotFoundError
from dw_platform.application.access_context import AccessContext

# The inbox shows the latest few; older ones are still there until pruned.
INBOX_LIMIT = 50


@dataclass(frozen=True, slots=True)
class Notification:
    id: uuid.UUID
    title: str
    body: str
    link: str | None
    created_at: datetime
    read_at: datetime | None


@dataclass(frozen=True, slots=True)
class Inbox:
    items: tuple[Notification, ...]
    unread: int


class NotificationInboxPort(Protocol):
    async def latest(self, context: AccessContext, *, limit: int) -> Inbox: ...

    async def mark_read(self, context: AccessContext, notification_id: uuid.UUID) -> bool:
        """Mark one of the caller's own as read; False if there is none by
        that id for them (someone else's reads as not existing)."""
        ...

    async def mark_all_read(self, context: AccessContext) -> None: ...


@dataclass(frozen=True)
class NotificationService:
    inbox: NotificationInboxPort

    async def latest(self, context: AccessContext) -> Inbox:
        return await self.inbox.latest(context, limit=INBOX_LIMIT)

    async def mark_read(self, context: AccessContext, notification_id: uuid.UUID) -> None:
        if not await self.inbox.mark_read(context, notification_id):
            raise NotFoundError(
                "no such notification", details={"notification_id": str(notification_id)}
            )

    async def mark_all_read(self, context: AccessContext) -> None:
        await self.inbox.mark_all_read(context)
