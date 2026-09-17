"""Platform provisioning API: /api/v1/platform/* (ADR-002).

Operator-only, tenant-less. Every route depends on ``RequireProvisioningContext``,
which refuses to build for a non-operator — so the gate is at the door. The
service owns validation and audit; routes only shape the request/response.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from dw_api.bootstrap import ApiContainer
from dw_api.dependencies.auth import RequireProvisioningContext
from dw_api.dependencies.services import RequireContainer
from dw_kernel.errors import InfrastructureError
from dw_platform.application.provisioning import ProvisioningService

router = APIRouter(prefix="/platform", tags=["platform"])


class TenantView(BaseModel):
    id: UUID
    slug: str
    name: str
    status: str
    plan_id: str | None
    workspace_count: int
    member_count: int
    created_at: datetime


class CreateTenantRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    plan_id: str


class NewTenantView(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    slug: str
    name: str


class RenameTenantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class UserRefView(BaseModel):
    user_id: UUID
    email: str | None
    display_name: str


class AssignOrgAdminRequest(BaseModel):
    email: str


class OperatorView(BaseModel):
    user_id: UUID
    email: str | None
    display_name: str
    note: str | None
    created_at: datetime


class AddOperatorRequest(BaseModel):
    email: str
    note: str | None = None


def _service(container: ApiContainer) -> ProvisioningService:
    if container.provisioning is None:
        raise InfrastructureError("provisioning is not configured")
    return container.provisioning


@router.get("/users", response_model=list[UserRefView])
async def list_users(
    context: RequireProvisioningContext,
    container: RequireContainer,
) -> list[UserRefView]:
    """Every signed-in identity — the picker behind the assign-admin / add-operator
    email boxes, so an operator selects an account instead of retyping it."""
    users = await _service(container).list_users(context)
    return [
        UserRefView(user_id=u.user_id, email=u.email, display_name=u.display_name) for u in users
    ]


@router.get("/tenants", response_model=list[TenantView])
async def list_tenants(
    context: RequireProvisioningContext,
    container: RequireContainer,
) -> list[TenantView]:
    tenants = await _service(container).list_tenants(context)
    return [
        TenantView(
            id=t.id,
            slug=t.slug,
            name=t.name,
            status=t.status,
            plan_id=t.plan_id,
            workspace_count=t.workspace_count,
            member_count=t.member_count,
            created_at=t.created_at,
        )
        for t in tenants
    ]


logger = logging.getLogger(__name__)


async def _install_report_templates(
    container: object, *, tenant_id: UUID, workspace_id: UUID
) -> None:
    """Cấp ba báo cáo chuẩn cho một không gian làm việc vừa mở.

    Nuốt mọi lỗi có chủ ý: một trục trặc bên CRM không đáng chặn việc mở một
    khách hàng mới (spec 015, R5). Lưới an toàn là
    ``scripts/install_report_templates.py`` — chạy lại lúc nào cũng được và tự
    bù đúng chỗ thiếu.
    """
    install = getattr(container, "install_report_templates", None)
    if install is None:
        return
    try:
        await install(tenant_id, workspace_id)
    except Exception:
        logger.exception(
            "không cài được báo cáo chuẩn cho workspace %s của tenant %s",
            workspace_id,
            tenant_id,
        )


@router.post("/tenants", response_model=NewTenantView, status_code=201)
async def create_tenant(
    body: CreateTenantRequest,
    context: RequireProvisioningContext,
    container: RequireContainer,
) -> NewTenantView:
    t = await _service(container).create_tenant(
        context, slug=body.slug, name=body.name, plan_id=body.plan_id
    )
    await _install_report_templates(container, tenant_id=t.tenant_id, workspace_id=t.workspace_id)
    return NewTenantView(
        tenant_id=t.tenant_id, workspace_id=t.workspace_id, slug=t.slug, name=t.name
    )


@router.patch("/tenants/{tenant_id}", response_model=TenantView)
async def rename_tenant(
    tenant_id: UUID,
    body: RenameTenantRequest,
    context: RequireProvisioningContext,
    container: RequireContainer,
) -> TenantView:
    t = await _service(container).rename_tenant(context, tenant_id=tenant_id, name=body.name)
    return TenantView(
        id=t.id,
        slug=t.slug,
        name=t.name,
        status=t.status,
        plan_id=t.plan_id,
        workspace_count=t.workspace_count,
        member_count=t.member_count,
        created_at=t.created_at,
    )


@router.post("/tenants/{tenant_id}/lock", status_code=204)
async def lock_tenant(
    tenant_id: UUID,
    context: RequireProvisioningContext,
    container: RequireContainer,
) -> None:
    await _service(container).set_tenant_status(context, tenant_id=tenant_id, status="locked")


@router.post("/tenants/{tenant_id}/unlock", status_code=204)
async def unlock_tenant(
    tenant_id: UUID,
    context: RequireProvisioningContext,
    container: RequireContainer,
) -> None:
    await _service(container).set_tenant_status(context, tenant_id=tenant_id, status="active")


@router.post("/tenants/{tenant_id}/org-admins", response_model=UserRefView, status_code=201)
async def assign_org_admin(
    tenant_id: UUID,
    body: AssignOrgAdminRequest,
    context: RequireProvisioningContext,
    container: RequireContainer,
) -> UserRefView:
    user = await _service(container).assign_org_admin(
        context, tenant_id=tenant_id, email=body.email
    )
    return UserRefView(user_id=user.user_id, email=user.email, display_name=user.display_name)


@router.get("/operators", response_model=list[OperatorView])
async def list_operators(
    context: RequireProvisioningContext,
    container: RequireContainer,
) -> list[OperatorView]:
    operators = await _service(container).list_operators(context)
    return [
        OperatorView(
            user_id=o.user_id,
            email=o.email,
            display_name=o.display_name,
            note=o.note,
            created_at=o.created_at,
        )
        for o in operators
    ]


@router.post("/operators", response_model=UserRefView, status_code=201)
async def add_operator(
    body: AddOperatorRequest,
    context: RequireProvisioningContext,
    container: RequireContainer,
) -> UserRefView:
    user = await _service(container).add_operator(context, email=body.email, note=body.note)
    return UserRefView(user_id=user.user_id, email=user.email, display_name=user.display_name)


@router.delete("/operators/{user_id}", status_code=204)
async def remove_operator(
    user_id: UUID,
    context: RequireProvisioningContext,
    container: RequireContainer,
) -> None:
    await _service(container).remove_operator(context, user_id=user_id)
