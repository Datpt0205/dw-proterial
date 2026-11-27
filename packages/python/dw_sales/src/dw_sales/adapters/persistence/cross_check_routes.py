"""What the cross-check lane did with each order version, and what a person
then decided, in PostgreSQL (ticket 81, migration d533225350dd).

Written once per case version (the key), decided once (`decide` updates
only an undecided row); the measure reads the decided rows of one basis,
led by what RLS supplies (`ix_order_cross_check_routes_basis`).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import refusals_named, scope_values
from dw_sales.application.cross_check_on_match import CrossCheckRoute, Outcome
from dw_sales.application.ports import SalesScope

_X = tables.order_cross_check_routes


def _route(row: RowMapping) -> CrossCheckRoute:
    return CrossCheckRoute(
        case_id=row["case_id"],
        case_version=row["case_version"],
        basis=row["basis"],
        route=row["route"],
        exceptions=tuple(row["exceptions"]),
        outcome=row["outcome"],
        routed_at=row["routed_at"],
        decided_at=row["decided_at"],
    )


@dataclass(frozen=True)
class SqlCrossCheckRoutes:
    """Implements `CrossCheckRoutesPort` inside a unit of work's transaction."""

    session: AsyncSession
    scope: SalesScope

    def _mine(self) -> tuple[sa.ColumnElement[bool], ...]:
        return (_X.c.workspace_id == self.scope.workspace_id.value,)

    async def get(self, case_id: uuid.UUID, case_version: int) -> CrossCheckRoute | None:
        row = (
            (
                await self.session.execute(
                    sa.select(_X).where(
                        *self._mine(), _X.c.case_id == case_id, _X.c.case_version == case_version
                    )
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _route(row)

    async def add(self, route: CrossCheckRoute) -> None:
        async with refusals_named(self.session, case_id=str(route.case_id)):
            await self.session.execute(
                sa.insert(_X).values(
                    **scope_values(self.scope),
                    case_id=route.case_id,
                    case_version=route.case_version,
                    basis=route.basis,
                    route=route.route,
                    exceptions=[e.value for e in route.exceptions],
                    outcome=route.outcome,
                    routed_at=route.routed_at,
                    decided_at=route.decided_at,
                )
            )

    async def decide(
        self, case_id: uuid.UUID, case_version: int, outcome: Outcome, at: datetime
    ) -> bool:
        decided = await self.session.execute(
            sa.update(_X)
            .where(
                *self._mine(),
                _X.c.case_id == case_id,
                _X.c.case_version == case_version,
                _X.c.outcome.is_(None),
            )
            .values(outcome=outcome, decided_at=at)
        )
        return bool(getattr(decided, "rowcount", 0))

    async def passed(self, case_id: uuid.UUID) -> CrossCheckRoute | None:
        row = (
            (
                await self.session.execute(
                    sa.select(_X)
                    .where(
                        *self._mine(),
                        _X.c.case_id == case_id,
                        _X.c.route == "applied",
                        _X.c.outcome.is_(None),
                    )
                    .order_by(_X.c.case_version.desc())
                    .limit(1)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _route(row)

    async def outcomes(self, basis: str) -> Iterable[CrossCheckRoute]:
        rows = await self.session.execute(
            sa.select(_X).where(*self._mine(), _X.c.basis == basis, _X.c.outcome.is_not(None))
        )
        return [_route(row) for row in rows.mappings()]
