"""Reporting hierarchy and the data-scope roll-up (ADR-003).

Two use-cases and one resolver:

- An Org Admin views the org chart and sets each member's manager
  (``platform.members.read`` / ``.write`` — the same rails as membership admin).
  A manager assignment is refused if it would make a cycle.
- The dashboard asks ``visible_owner_ids`` for the caller: the set of owners
  whose records they may see — themselves plus everyone who reports up to them,
  resolved under the caller's tenant RLS. That is the roll-up.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from dw_kernel.errors import DomainError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.ports import AuthorizationPort
from dw_platform.domain.audit import AuditEvent

MEMBERS_READ = "platform.members.read"
MEMBERS_WRITE = "platform.members.write"

_ACTION_SET_MANAGER = "platform.hierarchy.set_manager"
_RESOURCE = "membership"


@dataclass(frozen=True, slots=True)
class HierarchyMember:
    user_id: uuid.UUID
    display_name: str
    email: str | None
    role_keys: tuple[str, ...]
    manager_user_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class SetManager:
    """Point ``user_id`` at a manager, or clear it when ``manager_user_id`` is None."""

    user_id: uuid.UUID
    manager_user_id: uuid.UUID | None


class HierarchyRepositoryPort(Protocol):
    async def list_members(self, context: AccessContext) -> list[HierarchyMember]:
        """Every membership in the caller's workspace, with its manager link."""
        ...

    async def is_member(self, context: AccessContext, user_id: uuid.UUID) -> bool:
        """Whether ``user_id`` has a membership in the caller's workspace."""
        ...

    async def subtree_user_ids(
        self, context: AccessContext, root_user_id: uuid.UUID
    ) -> frozenset[uuid.UUID]:
        """``root`` plus everyone who reports up to it, transitively, in the
        caller's tenant + workspace."""
        ...

    async def set_manager(
        self,
        context: AccessContext,
        *,
        user_id: uuid.UUID,
        manager_user_id: uuid.UUID | None,
        audit: AuditEvent,
    ) -> bool:
        """Set/clear the manager link; False if the member does not exist here."""
        ...


class HierarchyResolverPort(Protocol):
    """The read-only data-scope resolver the dashboard consumes."""

    async def visible_owner_ids(self, context: AccessContext) -> frozenset[uuid.UUID]: ...

    async def subtree_of(
        self, context: AccessContext, root_user_id: uuid.UUID
    ) -> frozenset[uuid.UUID]:
        """``root`` plus everyone who reports up to it — the team a leader may
        drill into. Resolved under the caller's RLS, so it never reaches past
        the workspace; the caller's own scope still bounds what they may focus."""
        ...


@dataclass(frozen=True)
class HierarchyService:
    """Implements ``HierarchyResolverPort`` and the Org Admin org-chart ops."""

    repo: HierarchyRepositoryPort
    authz: AuthorizationPort
    clock: UtcClock
    id_generator: IdGenerator

    async def get_tree(self, context: AccessContext) -> list[HierarchyMember]:
        await self.authz.require(context=context, action=MEMBERS_READ, resource_type=_RESOURCE)
        return await self.repo.list_members(context)

    async def set_manager(self, context: AccessContext, command: SetManager) -> None:
        await self.authz.require(context=context, action=MEMBERS_WRITE, resource_type=_RESOURCE)

        if command.manager_user_id is not None:
            if command.manager_user_id == command.user_id:
                raise DomainError("a member cannot report to themselves")
            if not await self.repo.is_member(context, command.manager_user_id):
                raise NotFoundError(
                    "no such manager in this workspace",
                    details={"manager_user_id": str(command.manager_user_id)},
                )
            # A cycle is refused: the proposed manager must not already report up
            # to this member (i.e. must not be inside this member's subtree).
            subtree = await self.repo.subtree_user_ids(context, command.user_id)
            if command.manager_user_id in subtree:
                raise DomainError(
                    "that would create a cycle — the manager reports to this member",
                    details={"manager_user_id": str(command.manager_user_id)},
                )

        changed = await self.repo.set_manager(
            context,
            user_id=command.user_id,
            manager_user_id=command.manager_user_id,
            audit=AuditEvent(
                id=self.id_generator.new_uuid(),
                tenant_id=TenantId(context.tenant_id),
                workspace_id=WorkspaceId(context.workspace_id),
                actor_id=UserId(context.principal_id),
                action=_ACTION_SET_MANAGER,
                resource_type=_RESOURCE,
                resource_id=str(command.user_id),
                occurred_at=self.clock.now(),
                details={
                    "manager_user_id": (
                        str(command.manager_user_id) if command.manager_user_id else None
                    )
                },
            ),
        )
        if not changed:
            raise NotFoundError(
                "no such member in this workspace",
                details={"user_id": str(command.user_id)},
            )

    async def visible_owner_ids(self, context: AccessContext) -> frozenset[uuid.UUID]:
        # Self plus the subtree. The resolver is called after the route has
        # already authorised a team read, so it does not re-check scope here.
        return await self.repo.subtree_user_ids(context, context.principal_id)

    async def subtree_of(
        self, context: AccessContext, root_user_id: uuid.UUID
    ) -> frozenset[uuid.UUID]:
        # The caller (a leader drilling into a sub-team) has already passed the
        # route's scope check; the route also verifies the result is within what
        # they may see before using it, so this only resolves the tree.
        return await self.repo.subtree_user_ids(context, root_user_id)
