"""Audit events API (read-only; audit is append-only by construction)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel

from dw_api.dependencies.auth import RequireAccessContext
from dw_api.dependencies.services import RequireContainer
from dw_kernel.errors import InfrastructureError
from dw_kernel.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page, PageQuery, page_request
from dw_platform.domain.audit import AuditActorKind, AuditEntry


class AuditEventView(BaseModel):
    """One audit row as the screen shows it.

    ``actor_id`` is here because it was the one thing the table could not show:
    the column exists on the row and is not inside ``details``, so dropping it
    from this view made "who did this" unanswerable from the UI for every action,
    not only sharing (spec 03.1 BR10 names it explicitly).

    ``actor_display_name`` is the actor's name today (``None`` for an actor
    that is no user, such as a background lane), and ``actor_kind`` says
    whether the actor was the support team acting under a grant: support
    staff are no member of the customer's, so a name alone would not say it.
    """

    actor_id: str
    actor_display_name: str | None
    actor_kind: AuditActorKind
    action: str
    resource_type: str
    resource_id: str
    policy_decision: str | None
    trace_id: str | None
    occurred_at: datetime
    details: dict[str, Any]


router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=Page[AuditEventView])
async def list_events(
    context: RequireAccessContext,
    container: RequireContainer,
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    support_grant_id: Annotated[
        UUID | None, Query(description="Only the events of this support grant.")
    ] = None,
) -> Page[AuditEventView]:
    if container.uow_factory is None:
        raise InfrastructureError("database is not configured")
    # The audit trail's own scope (`director`, `executive`), not the inbox's
    # `approvals.read`, which every `member` holds.
    await container.authorization.require(
        context=context, action="audit.events", resource_type="audit_event"
    )
    # The tenant and workspace are in the fingerprint even though neither comes
    # from the client: a cursor that somehow crossed accounts or workspaces is
    # then refused outright instead of being answered from the other window.
    # The grant filter is in it only when given, so a cursor of the whole trail
    # is not refused for a filter it never had, nor applied to one it did.
    filters: dict[str, object] = {"tenant": context.tenant_id, "workspace": context.workspace_id}
    if support_grant_id is not None:
        filters["support_grant"] = support_grant_id
    request = page_request(
        limit=limit,
        cursor=cursor,
        query=PageQuery(key="audit.events", filters=filters),
    )
    # Only the caller's workspace: RLS on audit_events narrows by tenant only.
    async with container.uow_factory(context) as uow:
        page = await uow.audit.list_page(
            request, workspace_id=context.workspace_id, support_grant_id=support_grant_id
        )
    return page.map_items(_view)


def _view(entry: AuditEntry) -> AuditEventView:
    event = entry.event
    return AuditEventView(
        actor_id=str(event.actor_id),
        actor_display_name=entry.actor_display_name,
        actor_kind=entry.actor_kind,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        policy_decision=event.policy_decision,
        trace_id=event.trace_id,
        occurred_at=event.occurred_at,
        details=dict(event.details),
    )
