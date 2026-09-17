"""SQL provisioning repository — runs as ``dw_provisioner`` (ADR-002).

That role has BYPASSRLS (needed to create and list every tenant) but is granted
only the platform provisioning tables, so nothing here can reach a business
schema. Kept in its own session factory bound to the provisioner engine; it must
never share the ``dw_app`` pool.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence import tables
from dw_platform.application.provisioning import (
    OperatorRef,
    TenantSummary,
    UserRef,
)


@dataclass(frozen=True)
class SqlProvisioningRepository:
    """Implements ``ProvisioningRepositoryPort``."""

    session_factory: async_sessionmaker[AsyncSession]

    async def list_tenants(self) -> list[TenantSummary]:
        ws = (
            sa.select(
                tables.workspaces.c.tenant_id,
                sa.func.count().label("n"),
            )
            .group_by(tables.workspaces.c.tenant_id)
            .subquery()
        )
        mem = (
            sa.select(
                tables.memberships.c.tenant_id,
                sa.func.count().label("n"),
            )
            .group_by(tables.memberships.c.tenant_id)
            .subquery()
        )
        stmt = (
            sa.select(
                tables.tenants.c.id,
                tables.tenants.c.slug,
                tables.tenants.c.name,
                tables.tenants.c.status,
                tables.tenants.c.created_at,
                tables.entitlements.c.plan_id,
                sa.func.coalesce(ws.c.n, 0).label("workspace_count"),
                sa.func.coalesce(mem.c.n, 0).label("member_count"),
            )
            .select_from(
                tables.tenants.outerjoin(
                    tables.entitlements,
                    tables.entitlements.c.tenant_id == tables.tenants.c.id,
                )
                .outerjoin(ws, ws.c.tenant_id == tables.tenants.c.id)
                .outerjoin(mem, mem.c.tenant_id == tables.tenants.c.id)
            )
            .order_by(tables.tenants.c.created_at)
        )
        async with self.session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            TenantSummary(
                id=row.id,
                slug=row.slug,
                name=row.name,
                status=row.status,
                plan_id=row.plan_id,
                workspace_count=row.workspace_count,
                member_count=row.member_count,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def list_users(self) -> list[UserRef]:
        stmt = (
            sa.select(
                tables.users.c.id,
                tables.users.c.email,
                tables.users.c.display_name,
            )
            .where(tables.users.c.email.is_not(None))
            .order_by(tables.users.c.display_name)
        )
        async with self.session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            UserRef(user_id=row.id, email=row.email, display_name=row.display_name) for row in rows
        ]

    async def slug_exists(self, slug: str) -> bool:
        async with self.session_factory() as session:
            found = (
                await session.execute(
                    sa.select(tables.tenants.c.id).where(tables.tenants.c.slug == slug)
                )
            ).first()
        return found is not None

    async def plan_exists(self, plan_id: str) -> bool:
        async with self.session_factory() as session:
            found = (
                await session.execute(
                    sa.select(tables.plans.c.plan_id).where(tables.plans.c.plan_id == plan_id)
                )
            ).first()
        return found is not None

    async def create_tenant(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        entitlement_id: UUID,
        slug: str,
        name: str,
        plan_id: str,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            await session.execute(
                sa.insert(tables.tenants).values(
                    id=tenant_id, slug=slug, name=name, status="active"
                )
            )
            await session.execute(
                sa.insert(tables.workspaces).values(
                    id=workspace_id,
                    tenant_id=tenant_id,
                    slug="main",
                    name="Main workspace",
                )
            )
            await session.execute(
                sa.insert(tables.entitlements).values(
                    id=entitlement_id, tenant_id=tenant_id, plan_id=plan_id
                )
            )

    async def set_tenant_status(self, tenant_id: UUID, status: str) -> bool:
        async with self.session_factory() as session, session.begin():
            result = await session.execute(
                sa.update(tables.tenants)
                .where(tables.tenants.c.id == tenant_id)
                .values(status=status)
            )
        assert isinstance(result, CursorResult)
        return bool(result.rowcount)

    async def rename_tenant(self, tenant_id: UUID, name: str) -> bool:
        async with self.session_factory() as session, session.begin():
            result = await session.execute(
                sa.update(tables.tenants).where(tables.tenants.c.id == tenant_id).values(name=name)
            )
        assert isinstance(result, CursorResult)
        return bool(result.rowcount)

    async def main_workspace_id(self, tenant_id: UUID) -> UUID | None:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    sa.select(tables.workspaces.c.id).where(
                        tables.workspaces.c.tenant_id == tenant_id,
                        tables.workspaces.c.slug == "main",
                    )
                )
            ).first()
        return row.id if row else None

    async def find_user_by_email(self, email: str) -> UserRef | None:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    sa.select(
                        tables.users.c.id,
                        tables.users.c.email,
                        tables.users.c.display_name,
                    ).where(sa.func.lower(tables.users.c.email) == email.strip().lower())
                )
            ).first()
        if row is None:
            return None
        return UserRef(user_id=row.id, email=row.email, display_name=row.display_name)

    async def grant_role(
        self,
        *,
        membership_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        role: str,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            existing = (
                await session.execute(
                    sa.select(tables.memberships.c.role_keys).where(
                        tables.memberships.c.tenant_id == tenant_id,
                        tables.memberships.c.workspace_id == workspace_id,
                        tables.memberships.c.user_id == user_id,
                    )
                )
            ).first()
            if existing is None:
                await session.execute(
                    sa.insert(tables.memberships).values(
                        id=membership_id,
                        tenant_id=tenant_id,
                        workspace_id=workspace_id,
                        user_id=user_id,
                        role_keys=[role],
                        department="general",
                    )
                )
                return
            roles = list(existing.role_keys)
            if role not in roles:
                roles.append(role)
                await session.execute(
                    sa.update(tables.memberships)
                    .where(
                        tables.memberships.c.tenant_id == tenant_id,
                        tables.memberships.c.workspace_id == workspace_id,
                        tables.memberships.c.user_id == user_id,
                    )
                    .values(role_keys=roles)
                )

    async def list_operators(self) -> list[OperatorRef]:
        stmt = (
            sa.select(
                tables.platform_operators.c.user_id,
                tables.platform_operators.c.note,
                tables.platform_operators.c.created_at,
                tables.users.c.email,
                tables.users.c.display_name,
            )
            .select_from(
                tables.platform_operators.join(
                    tables.users, tables.platform_operators.c.user_id == tables.users.c.id
                )
            )
            .order_by(tables.platform_operators.c.created_at)
        )
        async with self.session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            OperatorRef(
                user_id=row.user_id,
                email=row.email,
                display_name=row.display_name,
                note=row.note,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def is_operator(self, user_id: UUID) -> bool:
        async with self.session_factory() as session:
            found = (
                await session.execute(
                    sa.select(tables.platform_operators.c.user_id).where(
                        tables.platform_operators.c.user_id == user_id
                    )
                )
            ).first()
        return found is not None

    async def add_operator(self, *, user_id: UUID, note: str | None, created_by: UUID) -> None:
        async with self.session_factory() as session, session.begin():
            await session.execute(
                pg_insert(tables.platform_operators)
                .values(user_id=user_id, note=note, created_by=created_by)
                .on_conflict_do_nothing(index_elements=["user_id"])
            )

    async def remove_operator(self, user_id: UUID) -> bool:
        async with self.session_factory() as session, session.begin():
            result = await session.execute(
                sa.delete(tables.platform_operators).where(
                    tables.platform_operators.c.user_id == user_id
                )
            )
        assert isinstance(result, CursorResult)
        return bool(result.rowcount)

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
    ) -> None:
        async with self.session_factory() as session, session.begin():
            await session.execute(
                sa.insert(tables.provisioning_audit).values(
                    id=audit_id,
                    actor_id=actor_id,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    details=details,
                    occurred_at=occurred_at,
                )
            )
