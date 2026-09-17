"""Approvals API: inbox + decisions (decision resumes the paused run)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from dw_api.dependencies.auth import RequireAccessContext
from dw_api.dependencies.idempotency import RequireIdempotency
from dw_api.dependencies.services import RequireContainer
from dw_kernel.errors import InfrastructureError, NotFoundError
from dw_kernel.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page, PageQuery, page_request


class ApprovalView(BaseModel):
    id: uuid.UUID
    approval_type: str
    reason: str
    status: str
    run_id: uuid.UUID | None
    payload: dict[str, Any]
    created_at: datetime | None
    decided_at: datetime | None
    # The server refuses a blank comment for a strict type; without this the
    # form would have to keep its own copy of the prefix list.
    requires_comment: bool


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approve: bool
    comment: str = ""
    approved_action_ids: list[str] | None = None


router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=Page[ApprovalView])
async def list_pending(
    context: RequireAccessContext,
    container: RequireContainer,
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
) -> Page[ApprovalView]:
    if container.uow_factory is None or container.approval_flow is None:
        raise InfrastructureError("database is not configured")
    await container.authorization.require(
        context=context, action="approvals.read", resource_type="approval_request"
    )
    request = page_request(
        limit=limit,
        cursor=cursor,
        query=PageQuery(key="approvals.pending", filters={"tenant": context.tenant_id}),
    )
    approval_flow = container.approval_flow
    async with container.uow_factory(context) as uow:
        page = await uow.approvals.list_pending(request)
    return page.map_items(
        lambda p: ApprovalView(
            id=p.id,
            approval_type=p.approval_type,
            reason=p.reason,
            status=p.status.value,
            run_id=p.run_id,
            payload=dict(p.payload),
            created_at=p.created_at,
            decided_at=p.decided_at,
            requires_comment=approval_flow.is_strict(p.approval_type),
        )
    )


@router.get("/{approval_id}", response_model=ApprovalView)
async def get_approval(
    approval_id: uuid.UUID, context: RequireAccessContext, container: RequireContainer
) -> ApprovalView:
    if container.uow_factory is None or container.approval_flow is None:
        raise InfrastructureError("database is not configured")
    await container.authorization.require(
        context=context,
        action="approvals.read",
        resource_type="approval_request",
        resource_id=str(approval_id),
    )
    async with container.uow_factory(context) as uow:
        request = await uow.approvals.get(approval_id)
    if request is None:
        raise NotFoundError("approval request not found")
    return ApprovalView(
        id=request.id,
        approval_type=request.approval_type,
        reason=request.reason,
        status=request.status.value,
        run_id=request.run_id,
        payload=dict(request.payload),
        created_at=request.created_at,
        decided_at=request.decided_at,
        requires_comment=container.approval_flow.is_strict(request.approval_type),
    )


# A decision resumes a checkpointed run, and the run is where the side effects
# are — so a retry after a timeout is the one request on this router that must
# never be executed twice. `Idempotency-Key` is honoured here (optional; see
# README), and on nothing else in this module: the two GETs are reads.
@router.post("/{approval_id}/decisions", response_model=ApprovalView)
async def decide(
    approval_id: uuid.UUID,
    body: DecisionRequest,
    context: RequireAccessContext,
    container: RequireContainer,
    idempotency: RequireIdempotency,
) -> ApprovalView:
    if container.approval_flow is None:
        raise InfrastructureError("approval flow is not configured")
    request = await container.approval_flow.decide(
        approval_id=approval_id,
        approve=body.approve,
        comment=body.comment,
        context=context,
        authorization=container.authorization,
        approved_action_ids=body.approved_action_ids,
    )
    return await idempotency.record(
        ApprovalView(
            id=request.id,
            approval_type=request.approval_type,
            reason=request.reason,
            status=request.status.value,
            run_id=request.run_id,
            payload=dict(request.payload),
            created_at=request.created_at,
            decided_at=request.decided_at,
            requires_comment=container.approval_flow.is_strict(request.approval_type),
        )
    )
