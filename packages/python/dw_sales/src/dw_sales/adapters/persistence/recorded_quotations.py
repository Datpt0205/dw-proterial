"""`RecordedQuotationsPort` on PostgreSQL (`sales.recorded_quotations`,
migration `c1c192e011e1`): the quotations Sales sent and confirmed, read the
same by the API and the worker, in one transaction bound to the scope."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.application.ports import SalesScope
from dw_sales.application.snapshot_catalog import RecordedQuotation
from dw_sales.domain.catalog import Quotation

_Q = tables.recorded_quotations


@dataclass(frozen=True)
class SqlRecordedQuotations:
    """Implements `RecordedQuotationsPort`."""

    session_factory: async_sessionmaker[AsyncSession]

    def _bound(self, scope: SalesScope) -> TenantScope:
        return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)

    async def recorded(self, scope: SalesScope) -> Sequence[RecordedQuotation]:
        async with tenant_session(self.session_factory, self._bound(scope)) as session:
            rows = await session.execute(
                sa.select(_Q.c.quotation, _Q.c.recorded_at)
                .where(
                    _Q.c.tenant_id == scope.tenant_id.value,
                    _Q.c.workspace_id == scope.workspace_id.value,
                )
                .order_by(_Q.c.recorded_at, _Q.c.quote_no, _Q.c.prv_code)
            )
            return [
                RecordedQuotation(Quotation.model_validate(row.quotation), row.recorded_at)
                for row in rows
            ]

    async def add(self, scope: SalesScope, rows: Sequence[Quotation]) -> None:
        if not rows:
            return
        async with tenant_session(self.session_factory, self._bound(scope)) as session:
            await session.execute(
                insert(_Q)
                .values(
                    [
                        {
                            **scope_values(scope),
                            "quote_no": row.quote_no,
                            "prv_code": row.prv_code,
                            "customer_code": row.customer_code,
                            "quotation": row.model_dump(mode="json"),
                        }
                        for row in rows
                    ]
                )
                .on_conflict_do_nothing()
            )
            # Read back under the same transaction: a row another request
            # recorded first, with other terms, refuses this whole record.
            held = await session.execute(
                sa.select(_Q.c.quotation).where(
                    _Q.c.tenant_id == scope.tenant_id.value,
                    _Q.c.workspace_id == scope.workspace_id.value,
                    sa.tuple_(_Q.c.quote_no, _Q.c.prv_code).in_(
                        [(row.quote_no, row.prv_code) for row in rows]
                    ),
                )
            )
            stored = {
                (q.quote_no, q.prv_code): q
                for q in (Quotation.model_validate(r.quotation) for r in held)
            }
            for row in rows:
                if stored.get((row.quote_no, row.prv_code)) != row:
                    raise ConflictError(
                        "the master list holds this quote number with other terms",
                        details={"quote_no": row.quote_no, "prv_code": row.prv_code},
                    )
