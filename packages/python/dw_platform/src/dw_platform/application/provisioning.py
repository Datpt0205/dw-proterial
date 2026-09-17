"""Platform provisioning: create/lock tenants, assign the first Org Admin, and
manage the Platform Operator allowlist (ADR-002).

This path is deliberately *tenant-less*. A ``ProvisioningContext`` carries only
the operator's principal id — the FastAPI dependency refuses to build one for a
non-operator, so every method here already runs on behalf of a verified
operator. The repository runs as ``dw_provisioner``, whose grants reach only the
platform provisioning tables, so nothing here can touch a tenant's business data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from dw_kernel.errors import ConflictError, DomainError, NotFoundError
from dw_kernel.ports import IdGenerator, UtcClock

# A tenant slug is a URL-safe handle: lowercase, digits, single hyphens.
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ORG_ADMIN_ROLE = "org_admin"
_MAIN_WORKSPACE_SLUG = "main"
_TENANT_STATUSES = frozenset({"active", "locked"})


@dataclass(frozen=True, slots=True)
class ProvisioningContext:
    """A verified Platform Operator acting outside any tenant."""

    principal_id: UUID


@dataclass(frozen=True, slots=True)
class TenantSummary:
    id: UUID
    slug: str
    name: str
    status: str
    plan_id: str | None
    workspace_count: int
    member_count: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OperatorRef:
    user_id: UUID
    email: str | None
    display_name: str
    note: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class UserRef:
    user_id: UUID
    email: str | None
    display_name: str


@dataclass(frozen=True, slots=True)
class NewTenant:
    tenant_id: UUID
    workspace_id: UUID
    slug: str
    name: str


class ProvisioningRepositoryPort(Protocol):
    """Cross-tenant writes on the platform provisioning tables. Implemented over
    the ``dw_provisioner`` role, which cannot read any business schema."""

    async def list_tenants(self) -> list[TenantSummary]: ...

    async def list_users(self) -> list[UserRef]:
        """Every signed-in identity — the picker behind the email boxes."""
        ...

    async def slug_exists(self, slug: str) -> bool: ...

    async def plan_exists(self, plan_id: str) -> bool: ...

    async def create_tenant(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        entitlement_id: UUID,
        slug: str,
        name: str,
        plan_id: str,
    ) -> None: ...

    async def set_tenant_status(self, tenant_id: UUID, status: str) -> bool:
        """Returns False if no tenant had that id."""
        ...

    async def rename_tenant(self, tenant_id: UUID, name: str) -> bool:
        """Change a tenant's display name. Returns False if no tenant had that id."""
        ...

    async def main_workspace_id(self, tenant_id: UUID) -> UUID | None: ...

    async def find_user_by_email(self, email: str) -> UserRef | None: ...

    async def grant_role(
        self,
        *,
        membership_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        role: str,
    ) -> None:
        """Add ``role`` to the user's membership in that workspace, creating the
        membership if absent. Idempotent in the role set."""
        ...

    async def list_operators(self) -> list[OperatorRef]: ...

    async def is_operator(self, user_id: UUID) -> bool: ...

    async def add_operator(self, *, user_id: UUID, note: str | None, created_by: UUID) -> None: ...

    async def remove_operator(self, user_id: UUID) -> bool:
        """Returns False if the user was not an operator."""
        ...

    async def record_audit(
        self,
        *,
        audit_id: UUID,
        actor_id: UUID,
        action: str,
        target_type: str,
        target_id: str | None,
        details: dict[str, object],
        occurred_at: datetime,
    ) -> None: ...


@dataclass(frozen=True)
class ProvisioningService:
    """The operator's use-cases. Each write leaves a provisioning-audit row."""

    repo: ProvisioningRepositoryPort
    clock: UtcClock
    ids: IdGenerator

    async def list_tenants(self, context: ProvisioningContext) -> list[TenantSummary]:
        return await self.repo.list_tenants()

    async def list_users(self, context: ProvisioningContext) -> list[UserRef]:
        return await self.repo.list_users()

    async def create_tenant(
        self, context: ProvisioningContext, *, slug: str, name: str, plan_id: str
    ) -> NewTenant:
        slug = slug.strip().lower()
        name = name.strip()
        if not _SLUG.match(slug):
            raise DomainError(
                "tenant slug must be lowercase letters, digits and single hyphens",
                details={"slug": slug},
            )
        if not name:
            raise DomainError("tenant name must not be blank")
        if not await self.repo.plan_exists(plan_id):
            raise NotFoundError("unknown plan", details={"plan_id": plan_id})
        if await self.repo.slug_exists(slug):
            raise ConflictError("a tenant with that slug already exists", details={"slug": slug})

        tenant = NewTenant(
            tenant_id=self.ids.new_uuid(),
            workspace_id=self.ids.new_uuid(),
            slug=slug,
            name=name,
        )
        await self.repo.create_tenant(
            tenant_id=tenant.tenant_id,
            workspace_id=tenant.workspace_id,
            entitlement_id=self.ids.new_uuid(),
            slug=slug,
            name=name,
            plan_id=plan_id,
        )
        await self._audit(
            context,
            "platform.tenant.create",
            "tenant",
            str(tenant.tenant_id),
            {"slug": slug, "name": name, "plan_id": plan_id},
        )
        return tenant

    async def set_tenant_status(
        self, context: ProvisioningContext, *, tenant_id: UUID, status: str
    ) -> None:
        if status not in _TENANT_STATUSES:
            raise DomainError("status must be 'active' or 'locked'", details={"status": status})
        changed = await self.repo.set_tenant_status(tenant_id, status)
        if not changed:
            raise NotFoundError("unknown tenant", details={"tenant_id": str(tenant_id)})
        await self._audit(
            context, "platform.tenant.status", "tenant", str(tenant_id), {"status": status}
        )

    async def rename_tenant(
        self, context: ProvisioningContext, *, tenant_id: UUID, name: str
    ) -> TenantSummary:
        name = name.strip()
        if not name:
            raise DomainError("tenant name must not be blank")
        changed = await self.repo.rename_tenant(tenant_id, name)
        if not changed:
            raise NotFoundError("unknown tenant", details={"tenant_id": str(tenant_id)})
        await self._audit(
            context, "platform.tenant.rename", "tenant", str(tenant_id), {"name": name}
        )
        for tenant in await self.repo.list_tenants():
            if tenant.id == tenant_id:
                return tenant
        raise NotFoundError("unknown tenant", details={"tenant_id": str(tenant_id)})

    async def assign_org_admin(
        self, context: ProvisioningContext, *, tenant_id: UUID, email: str
    ) -> UserRef:
        workspace_id = await self.repo.main_workspace_id(tenant_id)
        if workspace_id is None:
            raise NotFoundError("unknown tenant", details={"tenant_id": str(tenant_id)})
        user = await self.repo.find_user_by_email(email)
        if user is None:
            raise NotFoundError(
                "no user with that email has signed in yet", details={"email": email}
            )
        await self.repo.grant_role(
            membership_id=self.ids.new_uuid(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user.user_id,
            role=_ORG_ADMIN_ROLE,
        )
        await self._audit(
            context,
            "platform.org_admin.assign",
            "membership",
            str(user.user_id),
            {"tenant_id": str(tenant_id), "workspace_id": str(workspace_id)},
        )
        return user

    async def list_operators(self, context: ProvisioningContext) -> list[OperatorRef]:
        return await self.repo.list_operators()

    async def add_operator(
        self, context: ProvisioningContext, *, email: str, note: str | None
    ) -> UserRef:
        user = await self.repo.find_user_by_email(email)
        if user is None:
            raise NotFoundError(
                "no user with that email has signed in yet", details={"email": email}
            )
        await self.repo.add_operator(
            user_id=user.user_id, note=note, created_by=context.principal_id
        )
        await self._audit(
            context, "platform.operator.add", "operator", str(user.user_id), {"email": email}
        )
        return user

    async def remove_operator(self, context: ProvisioningContext, *, user_id: UUID) -> None:
        if user_id == context.principal_id:
            # Fail closed: never let the last operator lock themselves out by a
            # slip; removing yourself must go through another operator.
            raise DomainError("an operator cannot remove themselves")
        removed = await self.repo.remove_operator(user_id)
        if not removed:
            raise NotFoundError("not a platform operator", details={"user_id": str(user_id)})
        await self._audit(context, "platform.operator.remove", "operator", str(user_id), {})

    async def _audit(
        self,
        context: ProvisioningContext,
        action: str,
        target_type: str,
        target_id: str | None,
        details: dict[str, object],
    ) -> None:
        await self.repo.record_audit(
            audit_id=self.ids.new_uuid(),
            actor_id=context.principal_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            occurred_at=self.clock.now(),
        )
