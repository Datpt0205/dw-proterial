"""DW's copy of Bravo's read tables (ticket 50, migration ffd0c95da906):
`MirrorStore` for the `bravo_sync` lane, bound to one tenant, and the state
Sales' page reads. Each call is one transaction bound to its tenant; RLS is
forced, and nothing is ever deleted: a row Bravo deleted is marked gone."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_bravo.sync import Cursor, SyncRow
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.application.bravo_facts import TableState


@dataclass(frozen=True)
class SqlBravoMirror:
    session_factory: async_sessionmaker[AsyncSession]

    def for_tenant(self, tenant_id: uuid.UUID) -> TenantMirror:
        return TenantMirror(self.session_factory, tenant_id)

    async def state(self, tenant_id: uuid.UUID) -> Sequence[TableState]:
        """Per table: rows held, rows Bravo deleted, and when Bravo was read."""
        async with tenant_session(self.session_factory, TenantScope(tenant_id=tenant_id)) as s:
            counts = {
                r.table_name: (r.held, r.gone)
                for r in (
                    await s.execute(
                        sa.text(
                            "SELECT table_name, count(*) FILTER (WHERE gone_at IS NULL) AS held,"
                            " count(*) FILTER (WHERE gone_at IS NOT NULL) AS gone"
                            " FROM bravo.mirror_rows GROUP BY table_name"
                        )
                    )
                ).all()
            }
            cursors = (
                await s.execute(
                    sa.text(
                        "SELECT table_name, last_read_at, last_full_at, last_error, last_error_at"
                        " FROM bravo.mirror_cursors ORDER BY table_name"
                    )
                )
            ).all()
        read = {c.table_name: c for c in cursors}
        return [
            TableState(
                table=name,
                rows=counts.get(name, (0, 0))[0],
                gone=counts.get(name, (0, 0))[1],
                last_read_at=None if name not in read else read[name].last_read_at,
                last_full_at=None if name not in read else read[name].last_full_at,
                last_error=None if name not in read else read[name].last_error,
                last_error_at=None if name not in read else read[name].last_error_at,
            )
            for name in sorted(set(read) | set(counts))
        ]


@dataclass(frozen=True)
class TenantMirror:
    """`dw_bravo.sync.MirrorStore` for one tenant."""

    session_factory: async_sessionmaker[AsyncSession]
    tenant_id: uuid.UUID

    async def cursor(self, table: str) -> Cursor:
        async with tenant_session(self.session_factory, TenantScope(tenant_id=self.tenant_id)) as s:
            row = (
                await s.execute(
                    sa.text(
                        "SELECT last_row_version, last_full_at, last_read_at, target"
                        " FROM bravo.mirror_cursors WHERE table_name = :t"
                    ),
                    {"t": table},
                )
            ).first()
        return Cursor() if row is None else Cursor(*row)

    async def keep(self, table: str, rows: Sequence[SyncRow], at: datetime) -> None:
        async with tenant_session(self.session_factory, TenantScope(tenant_id=self.tenant_id)) as s:
            await s.execute(
                sa.text(
                    "INSERT INTO bravo.mirror_rows (tenant_id, table_name, row_id, row_version,"
                    " data, read_at) VALUES (:tenant, :t, :id, :rv, CAST(:data AS jsonb), :at)"
                    " ON CONFLICT (tenant_id, table_name, row_id) DO UPDATE SET"
                    " row_version = EXCLUDED.row_version, data = EXCLUDED.data,"
                    " read_at = EXCLUDED.read_at, gone_at = NULL"
                ),
                [
                    {
                        "tenant": self.tenant_id,
                        "t": table,
                        "id": r.row_id,
                        "rv": r.row_version,
                        "data": json.dumps(r.data, ensure_ascii=False, sort_keys=True),
                        "at": at,
                    }
                    for r in rows
                ],
            )

    async def finish(
        self,
        table: str,
        *,
        target: str,
        last_row_version: str | None,
        at: datetime,
        full_pass_seen: frozenset[int] | None,
    ) -> None:
        async with tenant_session(self.session_factory, TenantScope(tenant_id=self.tenant_id)) as s:
            await s.execute(
                sa.text(
                    "INSERT INTO bravo.mirror_cursors (tenant_id, table_name, last_row_version,"
                    " last_full_at, last_read_at, target)"
                    " VALUES (:tenant, :t, :rv, :full, :at, :target)"
                    " ON CONFLICT (tenant_id, table_name) DO UPDATE SET"
                    " last_row_version = EXCLUDED.last_row_version, target = EXCLUDED.target,"
                    " last_full_at = COALESCE(EXCLUDED.last_full_at,"
                    " bravo.mirror_cursors.last_full_at),"
                    " last_read_at = EXCLUDED.last_read_at, last_error = NULL,"
                    " last_error_at = NULL"
                ),
                {
                    "tenant": self.tenant_id,
                    "t": table,
                    "rv": last_row_version,
                    "full": at if full_pass_seen is not None else None,
                    "at": at,
                    "target": target,
                },
            )
            if full_pass_seen is not None:
                await s.execute(
                    sa.text(
                        "UPDATE bravo.mirror_rows SET gone_at = :at"
                        " WHERE table_name = :t AND gone_at IS NULL"
                        " AND NOT (row_id = ANY(:seen))"
                    ),
                    {"at": at, "t": table, "seen": sorted(full_pass_seen)},
                )

    async def restart(self, table: str, at: datetime) -> None:
        async with tenant_session(self.session_factory, TenantScope(tenant_id=self.tenant_id)) as s:
            await s.execute(
                sa.text(
                    "UPDATE bravo.mirror_rows SET gone_at = :at"
                    " WHERE table_name = :t AND gone_at IS NULL"
                ),
                {"at": at, "t": table},
            )
            await s.execute(
                sa.text(
                    "UPDATE bravo.mirror_cursors SET last_row_version = NULL,"
                    " last_full_at = NULL, target = NULL WHERE table_name = :t"
                ),
                {"t": table},
            )

    async def failed(self, table: str, error: str, at: datetime) -> None:
        async with tenant_session(self.session_factory, TenantScope(tenant_id=self.tenant_id)) as s:
            await s.execute(
                sa.text(
                    "INSERT INTO bravo.mirror_cursors (tenant_id, table_name, last_error,"
                    " last_error_at) VALUES (:tenant, :t, :e, :at)"
                    " ON CONFLICT (tenant_id, table_name) DO UPDATE SET"
                    " last_error = EXCLUDED.last_error, last_error_at = EXCLUDED.last_error_at"
                ),
                {"tenant": self.tenant_id, "t": table, "e": error[:300], "at": at},
            )
