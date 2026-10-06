"""Approvals API: inbox + decisions (decision resumes the paused run).

The inbox and a single request are served only to the people who may decide
them and to the one who asked (`ApprovalAudience`): a request's payload is
the decider's working material, not every member's reading. Holding
`approvals.read` opens the inbox; what is in it is the audience's.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

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


_ReasonKey = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_:.-]+$")]
_Reason = Annotated[str, Field(min_length=1, max_length=1000, pattern=r"\S")]


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    approve: bool
    comment: str = Field(default="", max_length=2000)
    approved_action_ids: list[str] | None = None
    # A reason per item the approval names (a quote's blocking price
    # findings, by finding key); the approval type's guard says which.
    reasons: dict[_ReasonKey, _Reason] = Field(default_factory=dict, max_length=100)
    # The version of the subject the decider was shown; the type's guard
    # refuses a decision on a version the subject has since left behind.
    subject_version: int | None = Field(default=None, ge=1)


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
    audience = approval_flow.audience(context, container.authorization)
    async with container.uow_factory(context) as uow:
        page = await uow.approvals.list_pending(request, audience)
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
    # Not the caller's to decide and not theirs to have asked: not found,
    # the same answer as a request that does not exist.
    audience = container.approval_flow.audience(context, container.authorization)
    if request is None or not audience.may_see(request):
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
        reasons=body.reasons,
        subject_version=body.subject_version,
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
