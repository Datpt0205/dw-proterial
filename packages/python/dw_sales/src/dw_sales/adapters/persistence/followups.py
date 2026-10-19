"""SQL side of DW1's follow-ups (ticket 42, migration d2b1394c67b1).

- `SqlFollowupStore`, a unit of work's `followups`: the cases the lane reads,
  without their documents, each with when it entered its current status (its
  latest event into that status from another one, its arrival when none
  says), and the record of what was delivered, inside the workspace's
  transaction and its RLS.
- `SqlFollowupScopes`, the worker's list of workspaces to visit:
  `sales.followup_scopes()` (SECURITY DEFINER, ids only).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.application.followups import BRIEF, FollowupKey, SentFollowup
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import WaitingCase

_D = tables.followup_deliveries
_O = tables.order_cases
_Q = tables.quote_cases
_E = tables.case_events
_SCOPES = sa.text("SELECT tenant_id, workspace_id FROM sales.followup_scopes()")


def _entered(kind: CaseKind, case: sa.Table) -> sa.ScalarSelect[datetime]:
    """When the case entered its current status: its latest event into it
    from another status."""
    return (
        sa.select(sa.func.max(_E.c.occurred_at))
        .where(
            _E.c.tenant_id == case.c.tenant_id,
            _E.c.case_id == case.c.id,
            _E.c.case_kind == kind.value,
            _E.c.to_status == case.c.status,
            _E.c.from_status.is_distinct_from(_E.c.to_status),
        )
        .scalar_subquery()
    )


def _day(text: str | None) -> date | None:
    return None if text is None else date.fromisoformat(text)


def _case(kind: CaseKind, row: RowMapping) -> WaitingCase:
    return WaitingCase(
        kind=kind,
        case_id=row["id"],
        status=row["status"],
        reference=row["reference"],
        customer_code=row["customer_code"],
        received_at=row["received_at"],
        status_since=row["since"],
        assigned_to=row["assigned_to"],
        due=_day(row["due"]),
    )


@dataclass(frozen=True)
class SqlFollowupStore:
    """Implements `FollowupStorePort`."""

    session: AsyncSession
    scope: SalesScope

    async def cases(
        self, statuses: Mapping[CaseKind, frozenset[str]], *, received_since: datetime
    ) -> Sequence[WaitingCase]:
        orders = sa.select(
            _O.c.id,
            _O.c.status,
            _O.c.po_no.label("reference"),
            _O.c.customer_code,
            _O.c.received_at,
            _O.c.assigned_to,
            _O.c.due,
            sa.func.coalesce(_entered(CaseKind.ORDER, _O), _O.c.received_at).label("since"),
        ).where(
            sa.or_(
                _O.c.status.in_(sorted(statuses.get(CaseKind.ORDER, frozenset()))),
                _O.c.received_at >= received_since,
            )
        )
        rfq_no = _Q.c.body[("request", "document", "rfq_no", "value")].astext
        quotes = sa.select(
            _Q.c.id,
            _Q.c.status,
            # `QuoteRequest.reference`: its number, or the day it arrived.
            sa.func.coalesce(
                rfq_no, sa.func.to_char(_Q.c.received_at.op("AT TIME ZONE")("UTC"), "YYYY-MM-DD")
            ).label("reference"),
            _Q.c.body[("request", "customer_code")].astext.label("customer_code"),
            _Q.c.received_at,
            _Q.c.assigned_to,
            _Q.c.quote_due.label("due"),
            sa.func.coalesce(_entered(CaseKind.QUOTE, _Q), _Q.c.received_at).label("since"),
        ).where(
            sa.or_(
                _Q.c.status.in_(sorted(statuses.get(CaseKind.QUOTE, frozenset()))),
                _Q.c.received_at >= received_since,
            )
        )
        found = [_case(CaseKind.ORDER, r) for r in (await self.session.execute(orders)).mappings()]
        found += [_case(CaseKind.QUOTE, r) for r in (await self.session.execute(quotes)).mappings()]
        return found

    async def already_sent(self, keys: Sequence[FollowupKey]) -> frozenset[FollowupKey]:
        subjects = sorted({key.subject for key in keys})
        if not subjects:
            return frozenset()
        rows = await self.session.execute(
            sa.select(_D.c.followup, _D.c.stage, _D.c.subject, _D.c.since).where(
                _D.c.subject.in_(subjects)
            )
        )
        held = {FollowupKey(r.followup, r.stage, r.subject, r.since) for r in rows}
        return frozenset(key for key in keys if key in held)

    async def record(self, sent: SentFollowup) -> bool:
        key = sent.key
        inserted = await self.session.execute(
            pg_insert(_D)
            .values(
                id=uuid.uuid4(),
                **scope_values(self.scope),
                followup=key.followup,
                stage=key.stage,
                subject=key.subject,
                since=key.since,
                recipients=sent.recipients,
                sent_at=sent.sent_at,
            )
            .on_conflict_do_nothing(constraint="uq_followup_deliveries_key")
            .returning(_D.c.id)
        )
        return inserted.first() is not None

    async def forget_briefs_before(self, day: date) -> int:
        result = await self.session.execute(
            sa.delete(_D).where(_D.c.followup == BRIEF, _D.c.subject < day.isoformat())
        )
        return int(getattr(result, "rowcount", 0) or 0)


@dataclass(frozen=True)
class SqlFollowupScopes:
    """Every workspace with a Sales case, ids only, for the worker's lane."""

    session_factory: async_sessionmaker[AsyncSession]

    async def scopes(self) -> Sequence[SalesScope]:
        async with self.session_factory() as session:
            rows = (await session.execute(_SCOPES)).all()
        return [SalesScope(TenantId(t), WorkspaceId(w)) for t, w in rows]
