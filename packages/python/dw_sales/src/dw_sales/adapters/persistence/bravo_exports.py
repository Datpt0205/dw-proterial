"""Bravo exports and sales orders read back, in PostgreSQL (tickets 16, 03).

`SqlBravoExports` is a unit of work's `bravo_exports`: the workspace's
uploaded Bravo exports, of every screen, and their files until read.
`SqlReadBacks` is its `read_backs`: each order case's sales order as Bravo
held it when last read. Both ride the catalog unit of work
(`SqlCatalogUnitOfWork`), which already binds one workspace and carries the
platform's audit and outbox in its transaction.

`sales.bravo_export*` and `sales.order_bravo_read_backs` are narrowed by
tenant and workspace: RLS is what keeps one workspace's rows from another;
every query here names the scope too.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import refusals_named, scope_values
from dw_sales.application.bravo_exports import BravoExport, BravoScreen, ExportOutcome
from dw_sales.application.bravo_sales_orders import BravoReadBack
from dw_sales.application.ports import SalesScope
from dw_sales.domain.bravo_sales_orders import SoDifference
from dw_sales.domain.master_data import RejectedRow

_E = tables.bravo_exports
_F = tables.bravo_export_files
_R = tables.order_bravo_read_backs


def _export(row: RowMapping) -> BravoExport:
    return BravoExport(
        export_id=row["id"],
        screen=row["screen"],
        status=row["status"],
        uploaded_by=row["uploaded_by"],
        uploaded_at=row["uploaded_at"],
        file_name=row["file_name"],
        file_sha256=row["file_sha256"],
        file_size=row["file_size"],
        outcomes=tuple(ExportOutcome.model_validate(o) for o in row["outcomes"]),
        rejected=tuple(RejectedRow.model_validate(r) for r in row["rejected"]),
        error=row["error"],
    )


def _outcome(export: BravoExport) -> dict[str, object]:
    """What settling writes: everything but who uploaded which file, when."""
    return {
        "status": export.status,
        "outcomes": [o.model_dump(mode="json") for o in export.outcomes],
        "rejected": [r.model_dump(mode="json") for r in export.rejected],
        "error": export.error,
    }


@dataclass(frozen=True)
class _Scoped:
    session: AsyncSession
    scope: SalesScope

    def _mine(self, table: sa.Table) -> tuple[sa.ColumnElement[bool], ...]:
        return (
            table.c.tenant_id == self.scope.tenant_id.value,
            table.c.workspace_id == self.scope.workspace_id.value,
        )


@dataclass(frozen=True)
class SqlBravoExports(_Scoped):
    """Implements `BravoExportStorePort` inside a unit of work."""

    async def add(self, export: BravoExport, content: bytes) -> None:
        async with refusals_named(self.session, export_id=str(export.export_id)):
            await self.session.execute(
                sa.insert(_E).values(
                    id=export.export_id,
                    **scope_values(self.scope),
                    screen=export.screen,
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

    async def get(self, export_id: uuid.UUID) -> BravoExport | None:
        row = (
            (await self.session.execute(sa.select(_E).where(*self._mine(_E), _E.c.id == export_id)))
            .mappings()
            .first()
        )
        return None if row is None else _export(row)

    async def latest(self, screen: BravoScreen, limit: int) -> Sequence[BravoExport]:
        # `ix_bravo_exports_uploaded` carries the order.
        rows = (
            await self.session.execute(
                sa.select(_E)
                .where(*self._mine(_E), _E.c.screen == screen)
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

    async def settle(self, export: BravoExport) -> bool:
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
        # `ix_bravo_exports_uploaded` carries this; the files go by cascade.
        pruned = await self.session.execute(
            sa.delete(_E).where(*self._mine(_E), _E.c.uploaded_at < before).returning(_E.c.id)
        )
        return len(pruned.all())

    async def queued_before(self, before: datetime) -> Sequence[BravoExport]:
        rows = (
            await self.session.execute(
                sa.select(_E)
                .where(*self._mine(_E), _E.c.status == "queued", _E.c.uploaded_at < before)
                .order_by(_E.c.uploaded_at)
            )
        ).mappings()
        return [_export(row) for row in rows]


@dataclass(frozen=True)
class SqlReadBacks(_Scoped):
    """Implements `ReadBackStorePort` inside a unit of work."""

    async def put(self, read_back: BravoReadBack) -> None:
        values = {
            "case_version": read_back.case_version,
            "po_no": read_back.po_no,
            "so_no": read_back.so_no,
            "differences": [d.model_dump(mode="json") for d in read_back.differences],
            "rows_read": read_back.rows_read,
            "file_sha256": read_back.file_sha256,
            "read_by": read_back.read_by,
            "read_at": read_back.read_at,
            "source": read_back.source,
        }
        statement = pg_insert(_R).values(
            **scope_values(self.scope), case_id=read_back.case_id, **values
        )
        async with refusals_named(self.session, case_id=str(read_back.case_id)):
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[_R.c.tenant_id, _R.c.workspace_id, _R.c.case_id],
                    set_=values,
                )
            )

    async def get(self, case_id: uuid.UUID) -> BravoReadBack | None:
        row = (
            (
                await self.session.execute(
                    sa.select(_R).where(*self._mine(_R), _R.c.case_id == case_id)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return BravoReadBack(
            case_id=row["case_id"],
            case_version=row["case_version"],
            po_no=row["po_no"],
            so_no=row["so_no"],
            differences=tuple(SoDifference.model_validate(d) for d in row["differences"]),
            rows_read=row["rows_read"],
            file_sha256=row["file_sha256"],
            read_by=row["read_by"],
            read_at=row["read_at"],
            source=row["source"],
        )
