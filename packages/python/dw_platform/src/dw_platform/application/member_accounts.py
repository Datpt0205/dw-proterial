"""Sign-in accounts an Org Admin creates for their own people.

A tenant with no directory of its own (no AD, no corporate IdP) still has to
let people in. `TenantMembersService` decides who belongs to the tenant and
with which roles; this module adds the account they sign in with, in the
identity provider, so the members screen is the one place it all happens
(Đạt, 2026-10-25: "IT bên họ tự add thêm user và gắn quyền").

- **Create.** The account first, with a temporary password the person must
  change at their first sign-in; then the invitation, through
  `TenantMembersService.invite` and every rule it holds (no administrative
  role from a non-Platform-Admin, tenant RLS, audit). An invitation the
  platform refuses deletes the account just made, so a refusal leaves no
  sign-in behind.
- **Reset the password, lock, unlock.** Only for a person of this tenant
  (`manageable_member`), an administrator's only by a Platform Admin, and only
  on an account this tenant created: `LoginAccountsPort` answers NotFoundError
  for any other, so one tenant's admin can never reach another tenant's
  account or an operator's in a shared realm. The audit event is written in
  the transaction that commits once the identity provider has answered.

The temporary password is generated here and returned once, to the admin who
asked. It is never logged, audited or stored by the platform; a lost one is
replaced by resetting it again.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

from dw_kernel.errors import DomainError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.membership_admin import MEMBERS_READ, MEMBERS_WRITE, UserRef
from dw_platform.application.ports import AuthorizationPort, PlatformUnitOfWorkFactory
from dw_platform.application.tenant_members import (
    InviteMember,
    TenantMembersService,
    checked_invitation,
)
from dw_platform.domain.audit import AuditEvent

_LOG = logging.getLogger(__name__)

_RESOURCE = "login_account"
_ACTION_PASSWORD_RESET = "platform.login_account.password_reset"
_ACTION_LOCKED = "platform.login_account.locked"
_ACTION_UNLOCKED = "platform.login_account.unlocked"

# No 0/O, 1/l/I: the admin reads it out or writes it down for the person.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def temporary_password() -> str:
    """Three groups of four, about 70 bits: past the realm's 10-character floor."""
    return "-".join("".join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(3))


@dataclass(frozen=True, slots=True)
class LoginAccount:
    email: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class CreatedAccount:
    member: UserRef
    temporary_password: str


class LoginAccountsPort(Protocol):
    """Sign-in accounts in the identity provider, each owned by the tenant
    that created it.

    Every method but `create` acts only on an account created for
    `tenant_id`; any other account, however it exists, answers NotFoundError.
    """

    async def create(
        self, *, tenant_id: uuid.UUID, email: str, display_name: str, temporary_password: str
    ) -> None:
        """ConflictError (`login_account_exists`) when the email has an account."""
        ...

    async def delete(self, *, tenant_id: uuid.UUID, email: str) -> None: ...

    async def set_temporary_password(
        self, *, tenant_id: uuid.UUID, email: str, temporary_password: str
    ) -> None: ...

    async def set_enabled(self, *, tenant_id: uuid.UUID, email: str, enabled: bool) -> None:
        """Disabling also ends the account's open sessions."""
        ...

    async def list(self, *, tenant_id: uuid.UUID) -> list[LoginAccount]: ...


@dataclass(frozen=True)
class MemberAccountsService:
    members: TenantMembersService
    accounts: LoginAccountsPort
    uow: PlatformUnitOfWorkFactory
    authz: AuthorizationPort
    clock: UtcClock
    ids: IdGenerator
    new_password: Callable[[], str] = temporary_password

    async def list_accounts(self, context: AccessContext) -> list[LoginAccount]:
        await self.authz.require(context=context, action=MEMBERS_READ, resource_type=_RESOURCE)
        return await self.accounts.list(tenant_id=context.tenant_id)

    async def create(self, context: AccessContext, command: InviteMember) -> CreatedAccount:
        await self.authz.require(context=context, action=MEMBERS_WRITE, resource_type=_RESOURCE)
        command = replace(checked_invitation(command), login_account=True)
        password = self.new_password()
        await self.accounts.create(
            tenant_id=context.tenant_id,
            email=command.email,
            display_name=command.display_name,
            temporary_password=password,
        )
        try:
            member = await self.members.invite(context, command)
        except BaseException:
            try:
                await self.accounts.delete(tenant_id=context.tenant_id, email=command.email)
            except Exception:  # the invitation's refusal is the answer; this is housekeeping
                _LOG.exception("could not delete the sign-in account of a refused invitation")
            raise
        return CreatedAccount(member=member, temporary_password=password)

    async def reset_password(self, context: AccessContext, user_id: uuid.UUID) -> str:
        email = await self._manageable_email(context, user_id)
        password = self.new_password()
        async with self.uow(context) as uow:
            await uow.audit.append(self._event(context, _ACTION_PASSWORD_RESET, user_id))
            await self.accounts.set_temporary_password(
                tenant_id=context.tenant_id, email=email, temporary_password=password
            )
            await uow.commit()
        return password

    async def set_enabled(self, context: AccessContext, user_id: uuid.UUID, enabled: bool) -> None:
        if not enabled and user_id == context.principal_id:
            raise DomainError(
                "Bạn không tự khóa đăng nhập của chính mình được.",
                details={"reason_code": "own_sign_in"},
            )
        email = await self._manageable_email(context, user_id)
        action = _ACTION_UNLOCKED if enabled else _ACTION_LOCKED
        async with self.uow(context) as uow:
            await uow.audit.append(self._event(context, action, user_id))
            await self.accounts.set_enabled(
                tenant_id=context.tenant_id, email=email, enabled=enabled
            )
            await uow.commit()

    async def _manageable_email(self, context: AccessContext, user_id: uuid.UUID) -> str:
        member = await self.members.manageable_member(context, user_id)
        if member.email is None:
            raise NotFoundError("Người này chưa có email nên không có tài khoản đăng nhập.")
        return member.email

    def _event(self, context: AccessContext, action: str, user_id: uuid.UUID) -> AuditEvent:
        return AuditEvent(
            id=self.ids.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            actor_id=UserId(context.principal_id),
            action=action,
            resource_type=_RESOURCE,
            resource_id=str(user_id),
            occurred_at=self.clock.now(),
            details={},
        )
