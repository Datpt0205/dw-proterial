"""The PO layouts people mapped and decided (ticket 30), in `sales.po_layouts`.

`SqlLayoutStore` is the unit of work's (`LayoutStorePort`): the onboarding
screen's writes, in the transaction that audits them. `SqlLayoutLookup` is
intake's (`LayoutLookupPort`): one short read per call, bound to the scope it
is asked about, as `SqlOrderCaseLookup` is. Both read under the workspace's row
security: another tenant's or workspace's layout is not there to be found.

The record is stored as the domain serialises it (`body`); the columns beside
it are what the constraints and lookups need, written from the same record.
`ck_po_layouts_checker_not_maker` refuses a decision by the proposer whatever
writes the row.
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
from dw_sales.domain.layouts import LayoutStatus, PoLayout

_L = tables.po_layouts
_R = tables.order_revisions


def _layout(row: RowMapping) -> PoLayout:
    return PoLayout.model_validate(row["body"])


def _columns(layout: PoLayout) -> dict[str, object]:
    return {
        "customer_code": layout.customer_code,
        "kind": layout.kind,
        "version": layout.version,
        "status": layout.status,
        "proposed_by": layout.proposed_by,
        "decided_by": layout.decided_by,
        "approval_id": layout.approval_id,
        "body": layout.model_dump(mode="json"),
    }


@dataclass(frozen=True)
class SqlLayoutStore:
    """Implements `LayoutStorePort` inside a unit of work's transaction."""

    session: AsyncSession
    scope: SalesScope

    async def get(self, layout_id: uuid.UUID) -> PoLayout | None:
        row = (
            (await self.session.execute(sa.select(_L).where(_L.c.id == layout_id)))
            .mappings()
            .first()
        )
        return None if row is None else _layout(row)

    async def list_all(self) -> Sequence[PoLayout]:
        rows = await self.session.execute(
            sa.select(_L).order_by(_L.c.created_at.desc(), _L.c.id.desc())
        )
        return [_layout(row) for row in rows.mappings()]

    async def add(self, layout: PoLayout) -> None:
        async with refusals_named(self.session, layout_id=str(layout.layout_id)):
            await self.session.execute(
                sa.insert(_L).values(
                    id=layout.layout_id, **scope_values(self.scope), **_columns(layout)
                )
            )

    async def save(self, layout: PoLayout, *, expected: LayoutStatus) -> None:
        async with refusals_named(self.session, layout_id=str(layout.layout_id)):
            written = await self.session.execute(
                sa.update(_L)
                .where(_L.c.id == layout.layout_id, _L.c.status == expected)
                .values(**_columns(layout))
                .returning(_L.c.id)
            )
        if written.first() is None:
            raise ConflictError(
                "the layout was decided meanwhile",
                details={"layout_id": str(layout.layout_id), "rule": "layout_decided"},
            )


@dataclass(frozen=True)
class SqlLayoutLookup:
    """Implements `LayoutLookupPort`: one short read transaction per call."""

    session_factory: async_sessionmaker[AsyncSession]

    async def approved(self, scope: SalesScope, customer_code: str) -> Sequence[PoLayout]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            rows = await session.execute(
                sa.select(_L).where(_L.c.customer_code == customer_code, _L.c.status == "approved")
            )
            return [_layout(row) for row in rows.mappings()]

    async def read_count(self, scope: SalesScope, layout_ref: str) -> int:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            count = await session.scalar(
                sa.select(sa.func.count(sa.distinct(_R.c.case_id))).where(
                    _R.c.document["layout_ref"].astext == layout_ref
                )
            )
        return int(count or 0)


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)
