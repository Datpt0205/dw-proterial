"""Org Admin membership management: /api/v1/admin/members.

Grant and revoke a person's access to a workspace of the caller's tenant. The
handlers own every rule (scope, tenant RLS, no privilege escalation, audit); the
route only shapes the request and lets a domain error map to its status.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from dw_api.dependencies.auth import RequireAccessContext
from dw_api.dependencies.idempotency import RequireIdempotency
from dw_api.dependencies.services import RequireContainer
from dw_kernel.errors import InfrastructureError
from dw_platform.application.cache import membership_cache_pattern
from dw_platform.application.membership_admin import GrantMembership, RevokeMembership

router = APIRouter(prefix="/admin/members", tags=["admin"])


class GrantMemberRequest(BaseModel):
    email: str
    workspace_id: UUID
    role_keys: list[str] = Field(min_length=1)
    department: str = "general"


class MemberRefView(BaseModel):
    user_id: UUID
    email: str | None
    display_name: str


# Both routes below honour `Idempotency-Key` (optional; see README). Granting
# and revoking access are the mutations on this API whose duplicate is a
# security event rather than a nuisance: each one writes an audit record and
# invalidates every cached AccessContext in the workspace, so a client that
# retried a timed-out call used to leave a second "who granted what" entry
# behind with nothing to tie the two together.
@router.post("", response_model=MemberRefView, status_code=201)
async def grant_member(
    body: GrantMemberRequest,
    context: RequireAccessContext,
    container: RequireContainer,
    idempotency: RequireIdempotency,
) -> MemberRefView:
    if container.grant_membership is None:
        raise InfrastructureError("database is not configured")
    ref = await container.grant_membership.handle(
        context,
        GrantMembership(
            email=body.email,
            workspace_id=body.workspace_id,
            role_keys=frozenset(body.role_keys),
            department=body.department,
        ),
    )
    # The grant changed this workspace's roles → drop its cached AccessContexts so
    # the new access takes effect at once, not after the TTL.
    if container.cache is not None:
        await container.cache.delete_pattern(
            membership_cache_pattern(context.tenant_id, body.workspace_id)
        )
    return await idempotency.record(
        MemberRefView(user_id=ref.user_id, email=ref.email, display_name=ref.display_name),
        status_code=201,
    )


@router.delete("/{user_id}", status_code=204)
async def revoke_member(
    user_id: UUID,
    workspace_id: UUID,
    context: RequireAccessContext,
    container: RequireContainer,
    idempotency: RequireIdempotency,
) -> None:
    if container.revoke_membership is None:
        raise InfrastructureError("database is not configured")
    await container.revoke_membership.handle(
        context, RevokeMembership(user_id=user_id, workspace_id=workspace_id)
    )
    if container.cache is not None:
        await container.cache.delete_pattern(
            membership_cache_pattern(context.tenant_id, workspace_id)
        )
    await idempotency.record_no_content()
