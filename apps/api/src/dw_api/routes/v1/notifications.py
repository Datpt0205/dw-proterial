"""The caller's in-app inbox: the latest notifications and read marks.

No scope beyond membership, like `/me`: the database narrows every read and
update to rows addressed to the verified principal, so a notification that
is someone else's answers exactly as one that never existed.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel

from dw_api.dependencies.auth import RequireAccessContext
from dw_api.dependencies.services import RequireContainer
from dw_kernel.errors import InfrastructureError
from dw_platform.application.notifications import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationView(BaseModel):
    id: UUID
    title: str
    body: str
    # An app-relative path; the database refuses anything else.
    link: str | None
    created_at: datetime
    read_at: datetime | None


class InboxView(BaseModel):
    items: list[NotificationView]
    unread: int


def _service(container: RequireContainer) -> NotificationService:
    if container.notifications is None:
        raise InfrastructureError("database is not configured")
    return container.notifications


@router.get("", response_model=InboxView)
async def list_notifications(
    context: RequireAccessContext, container: RequireContainer
) -> InboxView:
    inbox = await _service(container).latest(context)
    return InboxView(
        items=[
            NotificationView(
                id=n.id,
                title=n.title,
                body=n.body,
                link=n.link,
                created_at=n.created_at,
                read_at=n.read_at,
            )
            for n in inbox.items
        ],
        unread=inbox.unread,
    )


@router.post("/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: UUID, context: RequireAccessContext, container: RequireContainer
) -> Response:
    await _service(container).mark_read(context, notification_id)
    return Response(status_code=204)


@router.post("/read-all", status_code=204)
async def mark_all_notifications_read(
    context: RequireAccessContext, container: RequireContainer
) -> Response:
    await _service(container).mark_all_read(context)
    return Response(status_code=204)
