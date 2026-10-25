"""Sign-in accounts an Org Admin creates: /api/v1/admin/accounts.

The handlers in `member_accounts.py` own every rule (scope, tenant, the
administrator's sign-in kept to a Platform Admin, the account owned by this
tenant, audit); a route shapes the request. A body that carries a temporary
password is sent with `Cache-Control: no-store`, and a replay of the same
`Idempotency-Key` answers without it (`temporary_password: null`): the
password is never written to the idempotency table.

503 with `details.reason_code` `login_accounts_not_configured` when the
deployment has no `dw-accounts` client: the screen disables its buttons and
says why, and no other door opens instead.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field

from dw_api.bootstrap import ApiContainer
from dw_api.dependencies.auth import RequireAccessContext
from dw_api.dependencies.idempotency import RequireIdempotency
from dw_api.dependencies.services import RequireContainer
from dw_api.routes.v1.admin_members import WorkspaceRolesBody, _drop_cached_contexts, _rows
from dw_kernel.errors import InfrastructureError
from dw_platform.application.member_accounts import MemberAccountsService
from dw_platform.application.tenant_members import InviteMember

router = APIRouter(prefix="/admin/accounts", tags=["admin"])

_NO_STORE = "no-store"


class LoginAccountView(BaseModel):
    email: str
    enabled: bool


class CreateAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=4, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    memberships: list[WorkspaceRolesBody] = Field(min_length=1)


class CreatedAccountView(BaseModel):
    user_id: UUID
    email: str | None
    display_name: str
    # Shown once; null on a replay of the same Idempotency-Key.
    temporary_password: str | None


class TemporaryPasswordView(BaseModel):
    user_id: UUID
    temporary_password: str | None


class SetEnabledRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


def _accounts(container: ApiContainer) -> MemberAccountsService:
    if container.member_accounts is None:
        raise InfrastructureError(
            "Máy chủ này chưa bật tạo tài khoản đăng nhập (thiếu cấu hình Keycloak"
            " dw-accounts). Hãy báo FPT.",
            details={"reason_code": "login_accounts_not_configured"},
        )
    return container.member_accounts


@router.get("", response_model=list[LoginAccountView])
async def list_accounts(
    context: RequireAccessContext, container: RequireContainer
) -> list[LoginAccountView]:
    """The sign-in accounts this tenant created, and whether each may sign in."""
    accounts = await _accounts(container).list_accounts(context)
    return [LoginAccountView(email=a.email, enabled=a.enabled) for a in accounts]


@router.post("", response_model=CreatedAccountView, status_code=201)
async def create_account(
    body: CreateAccountRequest,
    response: Response,
    context: RequireAccessContext,
    container: RequireContainer,
    idempotency: RequireIdempotency,
) -> CreatedAccountView:
    """Create the person, their roles and their sign-in account, with a
    temporary password they must change at their first sign-in."""
    created = await _accounts(container).create(
        context,
        InviteMember(
            display_name=body.display_name, email=body.email, memberships=_rows(body.memberships)
        ),
    )
    await _drop_cached_contexts(
        container, context.tenant_id, [row.workspace_id for row in body.memberships]
    )
    response.headers["Cache-Control"] = _NO_STORE
    view = CreatedAccountView(
        user_id=created.member.user_id,
        email=created.member.email,
        display_name=created.member.display_name,
        temporary_password=created.temporary_password,
    )
    return await idempotency.record(
        view, status_code=201, stored=view.model_copy(update={"temporary_password": None})
    )


@router.post("/{user_id}/password-reset", response_model=TemporaryPasswordView)
async def reset_password(
    user_id: UUID,
    response: Response,
    context: RequireAccessContext,
    container: RequireContainer,
    idempotency: RequireIdempotency,
) -> TemporaryPasswordView:
    """A new temporary password; the old one stops working at once."""
    password = await _accounts(container).reset_password(context, user_id)
    response.headers["Cache-Control"] = _NO_STORE
    view = TemporaryPasswordView(user_id=user_id, temporary_password=password)
    return await idempotency.record(
        view, stored=view.model_copy(update={"temporary_password": None})
    )


@router.put("/{user_id}/enabled", status_code=204)
async def set_enabled(
    user_id: UUID,
    body: SetEnabledRequest,
    context: RequireAccessContext,
    container: RequireContainer,
    idempotency: RequireIdempotency,
) -> None:
    """Lock (and end the open sessions of) or unlock a person's sign-in."""
    await _accounts(container).set_enabled(context, user_id, body.enabled)
    await idempotency.record_no_content()
