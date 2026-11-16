"""A customer's worked pairs in PostgreSQL (ticket 41, migration
711e8b760139).

`SqlWorkedPairs` is a unit of work's `pairs`, beside its `examples`
(`SqlCatalogUnitOfWork`): the worker writes a pair in the transaction that
settles the example it was read from. `sales.salesorder_pairs` is narrowed
by tenant and workspace by RLS, and append-only (`dw_app` holds SELECT and
INSERT); every query here names the scope too.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import refusals_named, scope_values
from dw_sales.application.ports import SalesScope
from dw_sales.application.salesorder_learning import WorkedPair
from dw_sales.domain.orders import PoDocument

_P = tables.salesorder_pairs


def _pair(row: RowMapping) -> WorkedPair:
    return WorkedPair(
        pair_id=row["id"],
        example_id=row["example_id"],
        customer_code=row["customer_code"],
        received_on=row["received_on"],
        layout_ref=row["layout_ref"],
        document=PoDocument.model_validate(row["document"]),
        expected=tuple(row["expected"]),
        added_by=row["added_by"],
        added_at=row["added_at"],
    )


@dataclass(frozen=True)
class SqlWorkedPairs:
    """Implements `WorkedPairStorePort` inside a unit of work."""

    session: AsyncSession
    scope: SalesScope

    async def add(self, pair: WorkedPair) -> None:
        async with refusals_named(self.session, pair_id=str(pair.pair_id)):
            await self.session.execute(
                sa.insert(_P).values(
                    id=pair.pair_id,
                    **scope_values(self.scope),
                    example_id=pair.example_id,
                    customer_code=pair.customer_code,
                    received_on=pair.received_on,
                    layout_ref=pair.layout_ref,
                    document=pair.document.model_dump(mode="json"),
                    expected=[dict(row) for row in pair.expected],
                    added_by=pair.added_by,
                    added_at=pair.added_at,
                )
            )

    async def for_customer(self, customer_code: str, limit: int) -> Sequence[WorkedPair]:
        # `ix_salesorder_pairs_tenant_id_workspace_id_customer_code_added_at`.
        rows = await self.session.execute(
            sa.select(_P)
            .where(
                _P.c.tenant_id == self.scope.tenant_id.value,
                _P.c.workspace_id == self.scope.workspace_id.value,
                _P.c.customer_code == customer_code,
            )
            .order_by(_P.c.added_at.desc(), _P.c.id)
            .limit(limit)
        )
        return [_pair(row) for row in rows.mappings()]
