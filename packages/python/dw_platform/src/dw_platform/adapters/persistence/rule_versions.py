"""A tenant's own rule versions in PostgreSQL, for every context that
registers keys (`application.rule_versions`; Sales ticket 19, ADR 0013).

`platform.rule_versions` is narrowed by tenant only: a version applies to the
whole tenant, whichever workspace it was proposed in (`workspace_id` records
that). RLS is what keeps one tenant's versions from another; nothing here
names a tenant.

**A refusal never echoes the row**: Postgres reports a CHECK violation with
the whole failing row in its DETAIL, and a document can hold prices. An
integrity error becomes a `ConflictError` naming the constraint, raised
`from None`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Collection, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.rule_versions import (
    ONE_OPEN_PROPOSAL,
    RuleScope,
    RuleStatus,
    RuleVersion,
)

_V = tables.rule_versions
# A key's second proposal while one waits; the engine names the waiting
# version, its proposer and when.
_ONE_PROPOSED: Final = "uq_rule_versions_one_proposed"


def _version(row: RowMapping) -> RuleVersion:
    return RuleVersion(
        version_id=row["id"],
        key=row["key"],
        version=row["version"],
        document=row["document"],
        status=row["status"],
        proposed_by=row["proposed_by"],
        proposed_at=row["proposed_at"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        comment=row["comment"],
        approval_id=row["approval_id"],
        applied_directly=row["applied_directly"],
    )


def _constraint(error: IntegrityError) -> str:
    cause = getattr(error.orig, "__cause__", None)
    name = getattr(cause, "constraint_name", None)
    return name if isinstance(name, str) else "unknown"


@asynccontextmanager
async def _refusals_named(session: AsyncSession, **details: object) -> AsyncIterator[None]:
    """Writes in a savepoint; a refusal comes out as a conflict naming the
    constraint and ``details`` (ids only), and nothing the row held."""
    try:
        async with session.begin_nested():
            yield
    except IntegrityError as exc:
        constraint = _constraint(exc)
        if constraint == _ONE_PROPOSED:
            raise ConflictError(
                "quy tắc này đã có một phiên bản chờ duyệt",
                details={**details, "constraint": constraint, "rule": ONE_OPEN_PROPOSAL},
            ) from None
        raise ConflictError(
            "the rule store refused the change", details={**details, "constraint": constraint}
        ) from None


def _scope(scope: RuleScope) -> dict[str, uuid.UUID]:
    return {"tenant_id": scope.tenant_id.value, "workspace_id": scope.workspace_id.value}


@dataclass(frozen=True)
class SqlRuleVersionStore:
    """Implements `RuleVersionStorePort` inside a unit of work's transaction."""

    session: AsyncSession
    scope: RuleScope

    async def list_all(
        self,
        *,
        keys: Collection[str] | None = None,
        statuses: Collection[RuleStatus] | None = None,
    ) -> Sequence[RuleVersion]:
        query = sa.select(_V).order_by(_V.c.proposed_at.desc(), _V.c.id.desc())
        if keys is not None:
            query = query.where(_V.c.key.in_(list(keys)))
        if statuses is not None:
            query = query.where(_V.c.status.in_(list(statuses)))
        rows = await self.session.execute(query)
        return [_version(row) for row in rows.mappings()]

    async def get(self, version_id: uuid.UUID) -> RuleVersion | None:
        row = (
            (await self.session.execute(sa.select(_V).where(_V.c.id == version_id)))
            .mappings()
            .first()
        )
        return None if row is None else _version(row)

    async def add(self, version: RuleVersion) -> None:
        async with _refusals_named(self.session, version_id=str(version.version_id)):
            await self.session.execute(
                sa.insert(_V).values(
                    id=version.version_id,
                    **_scope(self.scope),
                    key=version.key,
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
        async with _refusals_named(self.session, **details):
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

    async def apply(self, version: RuleVersion, *, superseding: uuid.UUID | None) -> None:
        async with _refusals_named(self.session, version_id=str(version.version_id)):
            if superseding is not None:
                await self.session.execute(
                    sa.update(_V)
                    .where(_V.c.id == superseding, _V.c.status == "approved")
                    .values(status="superseded")
                )
            await self.session.execute(
                sa.insert(_V).values(
                    id=version.version_id,
                    **_scope(self.scope),
                    key=version.key,
                    version=version.version,
                    document=dict(version.document),
                    status=version.status,
                    proposed_by=version.proposed_by,
                    proposed_at=version.proposed_at,
                    decided_by=version.decided_by,
                    decided_at=version.decided_at,
                    applied_directly=True,
                )
            )


@dataclass(frozen=True)
class SqlRuleVersionLookup:
    """Implements `RuleVersionLookupPort`: one short read per call, bound to
    the scope it is asked about."""

    session_factory: async_sessionmaker[AsyncSession]

    async def approved(self, scope: RuleScope, key: str) -> RuleVersion | None:
        return await self._one(scope, _V.c.key == key, _V.c.status == "approved")

    async def find(self, scope: RuleScope, key: str, version: str) -> RuleVersion | None:
        return await self._one(scope, _V.c.key == key, _V.c.version == version)

    async def _one(self, scope: RuleScope, *where: sa.ColumnElement[bool]) -> RuleVersion | None:
        bound = TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)
        async with tenant_session(self.session_factory, bound) as session:
            row = (await session.execute(sa.select(_V).where(*where))).mappings().first()
        return None if row is None else _version(row)
