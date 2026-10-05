"""Quote cases in PostgreSQL: the case as the domain serialises it.

`body` holds the whole `QuoteCase` but its id, version and status, which are
columns. The columns a lookup or a constraint needs (`ycbg_no`, `priced_by`,
`approved_by`, `approved_version`, `document_sha256`, `message_id`) are
generated from `body` by the database, so they cannot disagree with it, and
`ck_quote_cases_approver_not_pricer` holds whatever wrote the row.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import (
    claim_version,
    record_event,
    refusals_named,
    scope_values,
)
from dw_sales.application.case_store import CaseEvent, CaseOrigin, Stored
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.quotes import QuoteCase

_Q = tables.quote_cases
_COLUMNS = frozenset({"case_id", "case_version", "status"})


def _body(case: QuoteCase) -> dict[str, Any]:
    return case.model_dump(mode="json", exclude=set(_COLUMNS))


def _case(row: RowMapping) -> QuoteCase:
    return QuoteCase.model_validate(
        {
            **row["body"],
            "case_id": row["id"],
            "case_version": row["case_version"],
            "status": row["status"],
        }
    )


@dataclass(frozen=True)
class SqlQuoteCaseRepository:
    """Implements `QuoteCaseStorePort` inside a unit of work's transaction."""

    session: AsyncSession
    scope: SalesScope

    async def get(self, case_id: uuid.UUID) -> Stored[QuoteCase] | None:
        result = await self.session.execute(sa.select(_Q).where(_Q.c.id == case_id))
        row = result.mappings().first()
        if row is None:
            return None
        origin = CaseOrigin(
            assigned_to=row["assigned_to"], release_manifest_ref=row["release_manifest_ref"]
        )
        return Stored(_case(row), origin)

    async def cases_for_ycbg(self, ycbg_no: str) -> Sequence[QuoteCase]:
        rows = (
            await self.session.execute(
                sa.select(_Q).where(_Q.c.ycbg_no == ycbg_no).order_by(_Q.c.created_at, _Q.c.id)
            )
        ).mappings()
        return [_case(row) for row in rows]

    async def add(self, case: QuoteCase, origin: CaseOrigin, event: CaseEvent) -> None:
        async with refusals_named(self.session, case_id=str(case.case_id)):
            await self.session.execute(
                sa.insert(_Q).values(
                    id=case.case_id,
                    **scope_values(self.scope),
                    case_version=case.case_version,
                    status=case.status.value,
                    body=_body(case),
                    assigned_to=origin.assigned_to,
                    release_manifest_ref=origin.release_manifest_ref,
                )
            )
            await self._event(case, None, event)

    async def save(self, case: QuoteCase, *, expected_version: int, event: CaseEvent) -> None:
        was = await claim_version(
            self.session,
            _Q,
            case.case_id,
            expected_version=expected_version,
            new_version=case.case_version,
        )
        async with refusals_named(self.session, case_id=str(case.case_id)):
            await self.session.execute(
                sa.update(_Q)
                .where(_Q.c.id == case.case_id)
                .values(case_version=case.case_version, status=case.status.value, body=_body(case))
            )
            await self._event(case, was, event)

    async def _event(self, case: QuoteCase, from_status: str | None, event: CaseEvent) -> None:
        await record_event(
            self.session,
            self.scope,
            case_kind=CaseKind.QUOTE,
            case_id=case.case_id,
            case_version=case.case_version,
            from_status=from_status,
            to_status=case.status.value,
            event=event,
        )


@dataclass(frozen=True)
class SqlQuoteCaseLookup:
    """Implements `QuoteCaseLookupPort`: one short read transaction per call."""

    session_factory: async_sessionmaker[AsyncSession]

    async def cases_for_ycbg(self, scope: SalesScope, ycbg_no: str) -> Sequence[QuoteCase]:
        bound = TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)
        async with tenant_session(self.session_factory, bound) as session:
            return await SqlQuoteCaseRepository(session, scope).cases_for_ycbg(ycbg_no)
