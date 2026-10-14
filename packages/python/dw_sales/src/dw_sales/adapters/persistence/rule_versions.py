"""A tenant's own Sales rule versions in PostgreSQL (ticket 19).

`sales.rule_versions` is narrowed by tenant only (migration `57a241ea182b`): a
version applies to the whole tenant, whichever workspace it was proposed in
(`workspace_id` records that). RLS is what keeps one tenant's versions from
another; nothing here names a tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import refusals_named, scope_values
from dw_sales.application.ports import SalesScope
from dw_sales.application.rules import RuleKey, RuleVersion

_V = tables.rule_versions


def _version(row: RowMapping) -> RuleVersion:
    return RuleVersion(
        version_id=row["id"],
        key=RuleKey(row["key"]),
        version=row["version"],
        document=row["document"],
        status=row["status"],
        proposed_by=row["proposed_by"],
        proposed_at=row["proposed_at"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        comment=row["comment"],
        approval_id=row["approval_id"],
    )


@dataclass(frozen=True)
class SqlRuleVersionStore:
    """Implements `RuleVersionStorePort` inside a unit of work's transaction."""

    session: AsyncSession
    scope: SalesScope

    async def list_all(self) -> Sequence[RuleVersion]:
        rows = await self.session.execute(
            sa.select(_V).order_by(_V.c.proposed_at.desc(), _V.c.id.desc())
        )
        return [_version(row) for row in rows.mappings()]

    async def get(self, version_id: uuid.UUID) -> RuleVersion | None:
        row = (
            (await self.session.execute(sa.select(_V).where(_V.c.id == version_id)))
            .mappings()
            .first()
        )
        return None if row is None else _version(row)

    async def add(self, version: RuleVersion) -> None:
        async with refusals_named(self.session, version_id=str(version.version_id)):
            await self.session.execute(
                sa.insert(_V).values(
                    id=version.version_id,
                    **scope_values(self.scope),
                    key=version.key.value,
                    version=version.version,
                    document=dict(version.document),
                    status=version.status,
                    proposed_by=version.proposed_by,
                    proposed_at=version.proposed_at,
                    approval_id=version.approval_id,
                )
            )

    async def decide(self, version: RuleVersion, *, superseding: uuid.UUID | None) -> None:
        details: dict[str, object] = {"version_id": str(version.version_id)}
        async with refusals_named(self.session, **details):
            if superseding is not None:
                await self.session.execute(
                    sa.update(_V)
                    .where(_V.c.id == superseding, _V.c.status == "approved")
                    .values(status="superseded")
                )
            decided = await self.session.execute(
                sa.update(_V)
                .where(_V.c.id == version.version_id, _V.c.status == "proposed")
                .values(
                    status=version.status,
                    decided_by=version.decided_by,
                    decided_at=version.decided_at,
                    comment=version.comment,
                )
                .returning(_V.c.id)
            )
            if decided.first() is None:
                raise ConflictError("the version is decided already", details=details)


@dataclass(frozen=True)
class SqlRuleVersionLookup:
    """Implements `RuleVersionLookupPort`: one short read per call, bound to
    the scope it is asked about."""

    session_factory: async_sessionmaker[AsyncSession]

    async def approved(self, scope: SalesScope, key: RuleKey) -> RuleVersion | None:
        return await self._one(scope, _V.c.key == key.value, _V.c.status == "approved")

    async def find(self, scope: SalesScope, key: RuleKey, version: str) -> RuleVersion | None:
        return await self._one(scope, _V.c.key == key.value, _V.c.version == version)

    async def _one(self, scope: SalesScope, *where: sa.ColumnElement[bool]) -> RuleVersion | None:
        bound = TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)
        async with tenant_session(self.session_factory, bound) as session:
            row = (await session.execute(sa.select(_V).where(*where))).mappings().first()
        return None if row is None else _version(row)
