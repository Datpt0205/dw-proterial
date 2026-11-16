"""`NotationLedgerPort` on PostgreSQL (`sales.customer_notations`, migration
`99ae8f7eb765`): each customer's notation, read the same by the API and the
worker, and written with its audit row in one transaction bound to the scope
(ticket 37)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.notation import NotationKind
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.adapters.persistence.uow import AuditFactory
from dw_sales.application.ports import SalesScope
from dw_sales.domain.customer_notation import NotationEntry

_N = tables.customer_notations
# What a row holds beside its key, in the entry's own names.
_EVIDENCE = ("source", "case_kind", "case_id", "field", "written", "confirmed")


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


def _scoped(scope: SalesScope, customer_code: str) -> list[sa.ColumnElement[bool]]:
    return [
        _N.c.tenant_id == scope.tenant_id.value,
        _N.c.workspace_id == scope.workspace_id.value,
        _N.c.customer_code == customer_code,
    ]


@dataclass(frozen=True)
class SqlCustomerNotations:
    """Implements `NotationLedgerPort`."""

    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditFactory

    async def entries(self, scope: SalesScope, customer_code: str) -> Sequence[NotationEntry]:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            rows = (
                await session.execute(
                    sa.select(_N).where(*_scoped(scope, customer_code)).order_by(_N.c.kind)
                )
            ).all()
        return [
            NotationEntry(
                customer_code=row.customer_code,
                kind=row.kind,
                value=row.value,
                **{name: getattr(row, name) for name in _EVIDENCE},
                by=row.decided_by,
                at=row.decided_at,
            )
            for row in rows
        ]

    async def keep(self, scope: SalesScope, entry: NotationEntry, event: AuditEvent) -> bool:
        """The entry, replacing the kind's row only where its value or its
        source changes: a confirmation of what is known already keeps the
        evidence it was first learned from, and writes no audit row."""
        values = {
            **scope_values(scope),
            "customer_code": entry.customer_code,
            "kind": entry.kind,
            "value": entry.value,
            **{name: getattr(entry, name) for name in _EVIDENCE},
            "decided_by": entry.by,
            "decided_at": entry.at,
        }
        statement = insert(_N).values(**values)
        changed = sa.or_(
            _N.c.value != statement.excluded.value, _N.c.source != statement.excluded.source
        )
        upsert = statement.on_conflict_do_update(
            index_elements=[_N.c.tenant_id, _N.c.workspace_id, _N.c.customer_code, _N.c.kind],
            set_={
                name: statement.excluded[name]
                for name in ("value", *_EVIDENCE, "decided_by", "decided_at")
            },
            where=changed,
        ).returning(_N.c.kind)
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            written = (await session.execute(upsert)).first() is not None
            if written:
                await self.audit(session).append(event)
        return written

    async def forget(
        self, scope: SalesScope, customer_code: str, kind: NotationKind, event: AuditEvent
    ) -> bool:
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            gone = (
                await session.execute(
                    sa.delete(_N)
                    .where(*_scoped(scope, customer_code), _N.c.kind == kind)
                    .returning(_N.c.kind)
                )
            ).first() is not None
            if gone:
                await self.audit(session).append(event)
        return gone
