"""GET /api/v1/auth/bootstrap — identity-only "who am I / which workspaces?".

Called by the web app right after OIDC login, before a workspace is selected.
A brand-new verified identity is provisioned into the default demo tenant as a
plain member; existing users keep their memberships.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from dw_api.bootstrap import ApiContainer
from dw_api.dependencies.auth import RequireVerifiedIdentity, get_container
from dw_kernel.errors import InfrastructureError


class WorkspaceMembershipModel(BaseModel):
    tenant_id: UUID
    tenant_slug: str
    tenant_name: str
    workspace_id: UUID
    workspace_slug: str
    workspace_name: str
    roles: list[str]
    # What the membership may do: its roles' scopes and its permission sets'.
    # A screen reads it to decide what to offer; the API checks again.
    scopes: list[str]
    # Each role key's name from the role catalogue, for the screen to show.
    role_names: dict[str, str] = Field(default_factory=dict)


class BootstrapResponse(BaseModel):
    principal_id: UUID
    subject: str
    email: str | None
    display_name: str
    memberships: list[WorkspaceMembershipModel]
    is_platform_operator: bool = False
    is_support_staff: bool = False


router = APIRouter(tags=["identity"])


@router.get("/auth/bootstrap", response_model=BootstrapResponse)
async def bootstrap(
    identity: RequireVerifiedIdentity,
    container: Annotated[ApiContainer, Depends(get_container)],
) -> BootstrapResponse:
    if container.identity_bootstrap is None:
        raise InfrastructureError(
            "identity bootstrap is not configured",
            details={"hint": "set DW_API_DATABASE_URL"},
        )
    view = await container.identity_bootstrap.bootstrap(identity)
    return BootstrapResponse(
        principal_id=view.principal_id,
        subject=view.subject,
        email=view.email,
        display_name=view.display_name,
        memberships=[
            WorkspaceMembershipModel(
                tenant_id=m.tenant_id,
                tenant_slug=m.tenant_slug,
                tenant_name=m.tenant_name,
                workspace_id=m.workspace_id,
                workspace_slug=m.workspace_slug,
                workspace_name=m.workspace_name,
                roles=list(m.roles),
                scopes=list(m.scopes),
                role_names=dict(m.role_names),
            )
            for m in view.memberships
        ],
        is_platform_operator=view.is_platform_operator,
        is_support_staff=view.is_support_staff,
    )
