"""Master-data snapshots in PostgreSQL (ticket 41, migration 511ef1b71dee).

- `SqlCatalogSnapshots`, a catalog unit of work's `snapshots`: the
  workspace's imports, their files until read, their parsed records.
- `SqlCatalogUnitOfWork(Factory)`: one transaction bound to one workspace
  (`bind_tenant`), with the platform's approvals, audit and outbox written in
  it, handed in as factories over the session by the composition root.
- `SqlApprovedLists`, the `ApprovedListsPort` the catalog DW1 reads goes
  through: the approved snapshot's id in one short read bound to the scope,
  then its records, kept in this process by (tenant, workspace, snapshot id).
  A snapshot never changes after its parse, so a kept one is never stale:
  approving another changes the id the first read answers.

`sales.catalog_*` is narrowed by tenant and workspace: RLS is what keeps one
workspace's master data from another; every query here names the scope too.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import (
    TenantScope,
    bind_tenant,
    tenant_session,
)
from dw_platform.application.ports import AuditRepositoryPort
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import refusals_named, scope_values
from dw_sales.application.case_store import RunLessApprovalsPort
from dw_sales.application.catalog_imports import (
    OPEN,
    CatalogSnapshot,
    ImportStatus,
    OutboxPort,
)
from dw_sales.application.ports import SalesScope
from dw_sales.application.snapshot_catalog import ApprovedList
from dw_sales.domain.master_data import CatalogList, RejectedRow, records_of

_S = tables.catalog_snapshots
_F = tables.catalog_import_files
_R = tables.catalog_rows

AuditFactory = Callable[[AsyncSession], AuditRepositoryPort]
ApprovalsFactory = Callable[[AsyncSession], RunLessApprovalsPort]
OutboxFactory = Callable[[AsyncSession], OutboxPort]


def _snapshot(row: RowMapping) -> CatalogSnapshot:
    return CatalogSnapshot(
        snapshot_id=row["id"],
        catalog_list=CatalogList(row["list"]),
        status=row["status"],
        source=row["source"],
        file_name=row["file_name"],
        file_sha256=row["file_sha256"],
        file_size=row["file_size"],
        imported_by=row["imported_by"],
        imported_at=row["imported_at"],
        as_of=row["as_of"],
        error=row["error"],
        row_count=row["row_count"],
        rejected_count=row["rejected_count"],
        rejected=tuple(RejectedRow.model_validate(r) for r in row["rejected"]),
        unknown_headers=tuple(row["unknown_headers"]),
        submitted_by=row["submitted_by"],
        submitted_at=row["submitted_at"],
        approval_id=row["approval_id"],
        base_snapshot_id=row["base_snapshot_id"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        comment=row["comment"],
    )


def _changing(snapshot: CatalogSnapshot) -> dict[str, Any]:
    """What a status change writes: everything but who imported what, when."""
    return {
        "status": snapshot.status,
        "error": snapshot.error,
        "row_count": snapshot.row_count,
        "rejected_count": snapshot.rejected_count,
        "rejected": [r.model_dump(mode="json") for r in snapshot.rejected],
        "unknown_headers": list(snapshot.unknown_headers),
        "submitted_by": snapshot.submitted_by,
        "submitted_at": snapshot.submitted_at,
        "approval_id": snapshot.approval_id,
        "base_snapshot_id": snapshot.base_snapshot_id,
        "decided_by": snapshot.decided_by,
        "decided_at": snapshot.decided_at,
        "comment": snapshot.comment,
    }


@dataclass(frozen=True)
class SqlCatalogSnapshots:
    """Implements `CatalogSnapshotStorePort` inside a unit of work."""

    session: AsyncSession
    scope: SalesScope

    def _mine(self, table: sa.Table) -> tuple[sa.ColumnElement[bool], ...]:
        return (
            table.c.tenant_id == self.scope.tenant_id.value,
            table.c.workspace_id == self.scope.workspace_id.value,
        )

    async def add(self, snapshot: CatalogSnapshot, content: bytes | None) -> None:
        async with refusals_named(self.session, snapshot_id=str(snapshot.snapshot_id)):
            await self.session.execute(
                sa.insert(_S).values(
                    id=snapshot.snapshot_id,
                    **scope_values(self.scope),
                    list=snapshot.catalog_list.value,
                    source=snapshot.source,
                    file_name=snapshot.file_name,
                    file_sha256=snapshot.file_sha256,
                    file_size=snapshot.file_size,
                    imported_by=snapshot.imported_by,
                    imported_at=snapshot.imported_at,
                    as_of=snapshot.as_of,
                    **_changing(snapshot),
                )
            )
            if content is not None:
                await self.session.execute(
                    sa.insert(_F).values(
                        **scope_values(self.scope),
                        snapshot_id=snapshot.snapshot_id,
                        content=content,
                    )
                )

    async def _first(self, *where: sa.ColumnElement[bool]) -> CatalogSnapshot | None:
        row = (
            (await self.session.execute(sa.select(_S).where(*self._mine(_S), *where)))
            .mappings()
            .first()
        )
        return None if row is None else _snapshot(row)

    async def get(self, snapshot_id: uuid.UUID) -> CatalogSnapshot | None:
        return await self._first(_S.c.id == snapshot_id)

    async def open_for(self, catalog_list: CatalogList) -> CatalogSnapshot | None:
        return await self._first(_S.c.list == catalog_list.value, _S.c.status.in_(sorted(OPEN)))

    async def approved(self, catalog_list: CatalogList) -> CatalogSnapshot | None:
        return await self._first(_S.c.list == catalog_list.value, _S.c.status == "approved")

    async def recent(self, catalog_list: CatalogList, limit: int) -> Sequence[CatalogSnapshot]:
        rows = await self.session.execute(
            sa.select(_S)
            .where(*self._mine(_S), _S.c.list == catalog_list.value)
            # `ix_catalog_snapshots_history` carries this order.
            .order_by(_S.c.imported_at.desc(), _S.c.id.desc())
            .limit(limit)
        )
        return [_snapshot(row) for row in rows.mappings()]

    async def content(self, snapshot_id: uuid.UUID) -> bytes | None:
        found = await self.session.scalar(
            sa.select(_F.c.content).where(*self._mine(_F), _F.c.snapshot_id == snapshot_id)
        )
        return None if found is None else bytes(found)

    async def update(self, snapshot: CatalogSnapshot, *, expected: ImportStatus) -> bool:
        details = {"snapshot_id": str(snapshot.snapshot_id)}
        async with refusals_named(self.session, **details):
            written = await self.session.execute(
                sa.update(_S)
                .where(*self._mine(_S), _S.c.id == snapshot.snapshot_id, _S.c.status == expected)
                .values(**_changing(snapshot))
                .returning(_S.c.id)
            )
            if written.first() is None:
                return False
            if snapshot.status != "queued":
                # The file is kept only until it is read, or the import is let go.
                await self.session.execute(
                    sa.delete(_F).where(*self._mine(_F), _F.c.snapshot_id == snapshot.snapshot_id)
                )
        return True

    async def write_records(
        self, snapshot_id: uuid.UUID, records: Sequence[tuple[str, Mapping[str, Any]]]
    ) -> None:
        if not records:
            return
        async with refusals_named(self.session, snapshot_id=str(snapshot_id)):
            await self.session.execute(
                sa.insert(_R),
                [
                    {
                        **scope_values(self.scope),
                        "snapshot_id": snapshot_id,
                        "position": position,
                        "key": key,
                        "record": dict(record),
                    }
                    for position, (key, record) in enumerate(records)
                ],
            )

    async def records(self, snapshot_id: uuid.UUID) -> Sequence[Mapping[str, Any]]:
        rows = await self.session.execute(
            sa.select(_R.c.record)
            .where(*self._mine(_R), _R.c.snapshot_id == snapshot_id)
            .order_by(_R.c.position)
        )
        return [dict(record) for record in rows.scalars()]


class SqlCatalogUnitOfWork:
    """Implements `CatalogUnitOfWork`."""

    snapshots: SqlCatalogSnapshots
    approvals: RunLessApprovalsPort
    audit: AuditRepositoryPort
    outbox: OutboxPort

    def __init__(self, factory: SqlCatalogUnitOfWorkFactory, scope: SalesScope) -> None:
        self._factory = factory
        self._scope = scope
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        session = self._factory.session_factory()
        try:
            await session.begin()
            await bind_tenant(
                session,
                TenantScope(
                    tenant_id=self._scope.tenant_id.value,
                    workspace_id=self._scope.workspace_id.value,
                ),
            )
        except BaseException:
            await session.close()
            raise
        self._session = session
        self.snapshots = SqlCatalogSnapshots(session, self._scope)
        self.approvals = self._factory.approvals(session)
        self.audit = self._factory.audit(session)
        self.outbox = self._factory.outbox(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None, "unit of work not entered"
        try:
            await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        assert self._session is not None, "unit of work not entered"
        await self._session.commit()


@dataclass(frozen=True)
class SqlCatalogUnitOfWorkFactory:
    """Implements `CatalogUnitOfWorkFactory`."""

    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory
    approvals: ApprovalsFactory
    outbox: OutboxFactory

    def __call__(self, scope: SalesScope) -> SqlCatalogUnitOfWork:
        return SqlCatalogUnitOfWork(self, scope)


# How many approved snapshots one process keeps: five lists per workspace,
# for a dozen workspaces; the least recently read goes first.
_KEPT = 64


@dataclass
class SqlApprovedLists:
    """Implements `ApprovedListsPort` (module docstring)."""

    session_factory: async_sessionmaker[AsyncSession]
    kept: int = _KEPT
    _cache: OrderedDict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], ApprovedList] = field(
        default_factory=OrderedDict, repr=False
    )

    async def approved(self, scope: SalesScope, catalog_list: CatalogList) -> ApprovedList | None:
        bound = TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)
        mine = (
            _S.c.tenant_id == scope.tenant_id.value,
            _S.c.workspace_id == scope.workspace_id.value,
        )
        async with tenant_session(self.session_factory, bound) as session:
            found = (
                await session.execute(
                    sa.select(_S.c.id, _S.c.as_of).where(
                        *mine, _S.c.list == catalog_list.value, _S.c.status == "approved"
                    )
                )
            ).first()
            if found is None:
                return None
            # The tenant and the workspace are in the key: a snapshot id is
            # never looked up for any scope but the one RLS just answered.
            key = (scope.tenant_id.value, scope.workspace_id.value, found.id)
            kept = self._cache.get(key)
            if kept is not None:
                self._cache.move_to_end(key)
                return kept
            rows = await session.execute(
                sa.select(_R.c.record)
                .where(
                    _R.c.tenant_id == scope.tenant_id.value,
                    _R.c.workspace_id == scope.workspace_id.value,
                    _R.c.snapshot_id == found.id,
                )
                .order_by(_R.c.position)
            )
            documents = [dict(record) for record in rows.scalars()]
        listed = ApprovedList.of(
            catalog_list, found.id, found.as_of, records_of(catalog_list, documents)
        )
        self._cache[key] = listed
        while len(self._cache) > self.kept:
            self._cache.popitem(last=False)
        return listed
