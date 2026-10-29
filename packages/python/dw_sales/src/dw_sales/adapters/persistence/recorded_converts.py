"""`RecordedConvertsPort` on PostgreSQL (`sales.recorded_convert_entries`,
migration `bbf5aa95bf6f`): the item codes Sales confirmed, read the same by
the API and the worker, in one transaction bound to the scope."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.application.ports import SalesScope
from dw_sales.application.snapshot_catalog import RecordedConvert
from dw_sales.domain.catalog import ConvertEntry

_C = tables.recorded_convert_entries


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


@dataclass(frozen=True)
class SqlRecordedConverts:
    """Implements `RecordedConvertsPort`."""

    session_factory: async_sessionmaker[AsyncSession]

    async def converts(self, scope: SalesScope) -> Sequence[RecordedConvert]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            rows = await session.execute(
                sa.select(_C)
                .where(
                    _C.c.tenant_id == scope.tenant_id.value,
                    _C.c.workspace_id == scope.workspace_id.value,
                )
                .order_by(_C.c.customer_code, _C.c.customer_item_code)
            )
            return [
                RecordedConvert(
                    ConvertEntry(
                        customer_code=row.customer_code,
                        customer_item_code=row.customer_item_code,
                        prv_code=row.prv_code,
                    ),
                    row.recorded_at,
                )
                for row in rows
            ]

    async def learn(
        self, scope: SalesScope, entry: ConvertEntry, *, by: uuid.UUID, case_id: uuid.UUID
    ) -> None:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            await session.execute(
                insert(_C)
                .values(
                    **scope_values(scope),
                    customer_code=entry.customer_code,
                    customer_item_code=entry.customer_item_code,
                    prv_code=entry.prv_code,
                    confirmed_by=by,
                    case_id=case_id,
                )
                .on_conflict_do_nothing()
            )
