"""Bravo YCBG exports in PostgreSQL (ticket 16, migration 10d5dfc1a3f1).

`SqlYcbgExports` is a unit of work's `ycbg_exports`: the workspace's uploaded
exports and their files until read. It rides the catalog unit of work
(`SqlCatalogUnitOfWork`), which already binds one workspace and carries the
platform's audit and outbox in its transaction.

`sales.ycbg_export*` is narrowed by tenant and workspace: RLS is what keeps
one workspace's exports from another; every query here names the scope too.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import refusals_named, scope_values
from dw_sales.application.ports import SalesScope
from dw_sales.application.ycbg_exports import YcbgExport, YcbgOutcome
from dw_sales.domain.master_data import RejectedRow

_E = tables.ycbg_exports
_F = tables.ycbg_export_files


def _export(row: RowMapping) -> YcbgExport:
    return YcbgExport(
        export_id=row["id"],
        status=row["status"],
        uploaded_by=row["uploaded_by"],
        uploaded_at=row["uploaded_at"],
        file_name=row["file_name"],
        file_sha256=row["file_sha256"],
        file_size=row["file_size"],
        outcomes=tuple(YcbgOutcome.model_validate(o) for o in row["outcomes"]),
        rejected=tuple(RejectedRow.model_validate(r) for r in row["rejected"]),
        error=row["error"],
    )


def _outcome(export: YcbgExport) -> dict[str, object]:
    """What settling writes: everything but who uploaded which file, when."""
    return {
        "status": export.status,
        "outcomes": [o.model_dump(mode="json") for o in export.outcomes],
        "rejected": [r.model_dump(mode="json") for r in export.rejected],
        "error": export.error,
    }


@dataclass(frozen=True)
class SqlYcbgExports:
    """Implements `YcbgExportStorePort` inside a unit of work."""

    session: AsyncSession
    scope: SalesScope

    def _mine(self, table: sa.Table) -> tuple[sa.ColumnElement[bool], ...]:
        return (
            table.c.tenant_id == self.scope.tenant_id.value,
            table.c.workspace_id == self.scope.workspace_id.value,
        )

    async def add(self, export: YcbgExport, content: bytes) -> None:
        async with refusals_named(self.session, export_id=str(export.export_id)):
            await self.session.execute(
                sa.insert(_E).values(
                    id=export.export_id,
                    **scope_values(self.scope),
                    uploaded_by=export.uploaded_by,
                    uploaded_at=export.uploaded_at,
                    file_name=export.file_name,
                    file_sha256=export.file_sha256,
                    file_size=export.file_size,
                    **_outcome(export),
                )
            )
            await self.session.execute(
                sa.insert(_F).values(
                    **scope_values(self.scope), export_id=export.export_id, content=content
                )
            )

    async def get(self, export_id: uuid.UUID) -> YcbgExport | None:
        row = (
            (await self.session.execute(sa.select(_E).where(*self._mine(_E), _E.c.id == export_id)))
            .mappings()
            .first()
        )
        return None if row is None else _export(row)

    async def latest(self, limit: int) -> Sequence[YcbgExport]:
        # `ix_ycbg_exports_uploaded` carries the order.
        rows = (
            await self.session.execute(
                sa.select(_E)
                .where(*self._mine(_E))
                .order_by(_E.c.uploaded_at.desc(), _E.c.id.desc())
                .limit(limit)
            )
        ).mappings()
        return [_export(row) for row in rows]

    async def content(self, export_id: uuid.UUID) -> bytes | None:
        found = await self.session.scalar(
            sa.select(_F.c.content).where(*self._mine(_F), _F.c.export_id == export_id)
        )
        return None if found is None else bytes(found)

    async def settle(self, export: YcbgExport) -> bool:
        async with refusals_named(self.session, export_id=str(export.export_id)):
            written = await self.session.execute(
                sa.update(_E)
                .where(*self._mine(_E), _E.c.id == export.export_id, _E.c.status == "queued")
                .values(**_outcome(export))
                .returning(_E.c.id)
            )
            if written.first() is None:
                return False
            # The file is kept only until it is read.
            await self.session.execute(
                sa.delete(_F).where(*self._mine(_F), _F.c.export_id == export.export_id)
            )
        return True

    async def prune(self, before: datetime) -> int:
        # `ix_ycbg_exports_uploaded` carries this; the files go by cascade.
        pruned = await self.session.execute(
            sa.delete(_E).where(*self._mine(_E), _E.c.uploaded_at < before).returning(_E.c.id)
        )
        return len(pruned.all())

    async def queued_before(self, before: datetime) -> Sequence[YcbgExport]:
        rows = (
            await self.session.execute(
                sa.select(_E)
                .where(*self._mine(_E), _E.c.status == "queued", _E.c.uploaded_at < before)
                .order_by(_E.c.uploaded_at)
            )
        ).mappings()
        return [_export(row) for row in rows]
