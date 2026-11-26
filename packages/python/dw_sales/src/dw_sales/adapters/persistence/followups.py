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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.application.followups import BRIEF, FollowupKey, SentFollowup
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import WaitingCase
from dw_sales.domain.order_quotes import SETTLED
from dw_sales.domain.orders import FindingCode, OrderStatus, export_acknowledgeable_statuses

_D = tables.followup_deliveries
_O = tables.order_cases
_Q = tables.quote_cases
_E = tables.case_events
_R = tables.order_revisions
_F = tables.order_findings
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


def _at(text: sa.ColumnElement[str]) -> sa.ColumnElement[datetime]:
    return sa.cast(text, sa.DateTime(timezone=True))


def _loop_since(step: str) -> sa.ColumnElement[datetime]:
    """When the order's update loop began waiting at ``step``; NULL at any
    other step, or with no loop (ticket 29)."""
    loop = _O.c.update_loop
    return sa.case((loop["step"].astext == step, _at(loop["since"].astext)), else_=sa.null())


def _implied_from() -> sa.ColumnElement[datetime]:
    """When the customer's silence counts as agreement, while the order waits
    on their answer to its confirmation; NULL for a customer with no days,
    or once the order is anywhere else (ticket 28)."""
    return sa.case(
        (
            _O.c.status == OrderStatus.CONFIRMATION_SENT.value,
            _at(_O.c.confirmation["implied_from"].astext),
        ),
        else_=sa.null(),
    )


def _elements(column: sa.ColumnElement[object], name: str) -> sa.TableValuedAlias:
    """A jsonb array column's elements, as rows of one jsonb ``value``."""
    return sa.func.jsonb_array_elements(column).table_valued(sa.column("value", JSONB)).alias(name)


def _design_asked_at() -> sa.ScalarSelect[datetime]:
    """When Sales recorded the oldest request to Design the order still names
    (ticket 06); NULL while none. The domain drops a request as its wait
    ends, so a request named is a wait that holds."""
    asked = _elements(_O.c.design_requests, "asked")
    return sa.select(sa.func.min(_at(asked.c.value["at"].astext))).scalar_subquery()


def _quote_open_since() -> sa.ScalarSelect[datetime]:
    """When the oldest quote case opened from the order and still open was
    opened (ticket 09): its own status, read now, not approved or declined
    (`order_quotes.SETTLED`); NULL while none is. Read under the same row
    security as the order, in its tenant and workspace."""
    link = _elements(_O.c.quote_links, "link")
    return (
        sa.select(sa.func.min(_at(link.c.value["at"].astext)))
        .select_from(link)
        .join(
            _Q,
            sa.and_(
                _Q.c.tenant_id == _O.c.tenant_id,
                _Q.c.workspace_id == _O.c.workspace_id,
                _Q.c.id == sa.cast(link.c.value["quote_case_id"].astext, sa.Uuid),
            ),
        )
        .where(_Q.c.status.notin_(sorted(status.value for status in SETTLED)))
        .scalar_subquery()
    )


def _pcs_price_asked_at() -> sa.ColumnElement[datetime]:
    """When a quote case was marked pcs, while no GM price is recorded on it
    (`QuoteCase.waits_on_pcs_price`, ticket 05); NULL otherwise."""
    body = _Q.c.body
    waits = sa.and_(body["production_type"].astext == "pcs", body["pcs_price"].astext.is_(None))
    return sa.case((waits, _at(body[("production_type_set", "at")].astext)), else_=sa.null())


def export_held() -> sa.ColumnElement[bool]:
    """`OrderCase.awaits_export_control`, read without the case: a status
    where the export-control PIC may decide it, and an open `missing_noc_esf`
    on the current revision (ticket 78). The follow-ups and the work list
    (`overview.SqlOverviewReader.work_page`) both read it. Never the finding's own time: every
    save rewrites the findings (`_replace_findings`), so the wait is the
    revision's arrival, `received_at`, and owed once per revision."""
    held = (
        sa.select(_F.c.id)
        .join(
            _R,
            sa.and_(
                _R.c.id == _F.c.revision_id,
                _R.c.tenant_id == _F.c.tenant_id,
                _R.c.workspace_id == _F.c.workspace_id,
            ),
        )
        .where(
            _R.c.tenant_id == _O.c.tenant_id,
            _R.c.workspace_id == _O.c.workspace_id,
            _R.c.case_id == _O.c.id,
            _R.c.superseded_at.is_(None),
            _F.c.code == FindingCode.MISSING_NOC_ESF.value,
            _F.c.disposition == "open",
        )
        .exists()
    )
    statuses = sorted(s.value for s in export_acknowledgeable_statuses())
    return sa.and_(_O.c.status.in_(statuses), held)


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
        pc_asked_at=row["pc_asked_at"],
        pc_proposed=bool(row["pc_proposed"]),
        customer_asked_at=row["customer_asked_at"],
        implied_from=row["implied_from"],
        design_asked_at=row["design_asked_at"],
        quote_open_since=row["quote_open_since"],
        design_checked=bool(row["design_checked"]),
        pcs_price_asked_at=row["pcs_price_asked_at"],
        export_held=bool(row["export_held"]),
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
            # The start of the wait on PC (ticket 07), or of the update loop's
            # (ticket 29); NULL while none.
            sa.func.coalesce(_at(_O.c.pc_request["at"].astext), _loop_since("waiting_pc")).label(
                "pc_asked_at"
            ),
            # Dates read from PC's mail for the wait (ticket 77).
            (sa.func.coalesce(sa.func.jsonb_array_length(_O.c.pc_reply["dates"]), 0) > 0).label(
                "pc_proposed"
            ),
            # The start of the update loop's wait on the customer (ticket 29).
            _loop_since("waiting_customer").label("customer_asked_at"),
            # When the customer's silence counts as agreement (ticket 28).
            _implied_from().label("implied_from"),
            # The waits on Design's new code (06) and on a quote opened from
            # the order (09).
            _design_asked_at().label("design_asked_at"),
            _quote_open_since().label("quote_open_since"),
            sa.false().label("design_checked"),
            sa.null().label("pcs_price_asked_at"),
            # An NOC/ESF hold waiting on the export-control PIC (ticket 78).
            # Its statuses are all loaded already (`LOADED`), so no filter.
            export_held().label("export_held"),
        ).where(
            sa.or_(
                _O.c.status.in_(sorted(statuses.get(CaseKind.ORDER, frozenset()))),
                _O.c.received_at >= received_since,
                # An update loop runs on an order whose confirmation left
                # (ticket 29).
                _O.c.update_loop.isnot(None),
                # A confirmation whose customer agrees by silence (ticket 28).
                _implied_from().isnot(None),
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
            sa.null().label("pc_asked_at"),
            sa.false().label("pc_proposed"),
            sa.null().label("customer_asked_at"),
            sa.null().label("implied_from"),
            sa.null().label("design_asked_at"),
            sa.null().label("quote_open_since"),
            # Design's result read from Bravo's YCBG export (ticket 16).
            _Q.c.body["design_check"].astext.isnot(None).label("design_checked"),
            # A pcs case waiting for the GM's price (ticket 05).
            _pcs_price_asked_at().label("pcs_price_asked_at"),
            sa.false().label("export_held"),
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
