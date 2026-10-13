"""`OverviewReadPort` in PostgreSQL: the overview's figures as aggregates, the
work list as a keyset page (ticket 24).

Every statement runs in the unit of work's transaction, so RLS narrows it to
the caller's workspace like any other read; nothing here names a tenant.

What the figures are computed against (whose time each status is, the steps
the survey names, the zone a month is counted in) arrives in `FigureBasis`
and is passed as parameters: this module restates none of it.

The work list is three keyset scans merged: open orders, open quotations and
messages routed to Sales, each through a partial index that leads with the
columns RLS supplies and carries the list's order (migration
`6d0252a87a6c`). The terminal statuses that bound those indexes are the one
thing restated here, written into each statement as literals so that the
planner can match the index's predicate in a generic plan too; no step of
the work list is ever on one (`tests/unit/test_overview_reader.py` holds that).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from dw_kernel.pagination import CursorPosition, Page, PageRequest, build_page
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence.quotes import stored_quote
from dw_sales.adapters.persistence.records import disposition_of
from dw_sales.application.case_store import LoggedMessage
from dw_sales.application.overview_ports import (
    BUCKETS,
    NO_DUE,
    Bucket,
    FigureBasis,
    OpenOrder,
    OverviewFigures,
    Spread,
    WorkEntry,
    WorkFilter,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind, DispositionKind
from dw_sales.domain.orders import DispositionKind as FindingDisposition
from dw_sales.domain.orders import MappingStatus, OrderStatus
from dw_sales.domain.quotes import QuoteStatus

_C = tables.order_cases
_R = tables.order_revisions
_L = tables.order_lines
_F = tables.order_findings
_Q = tables.quote_cases
_M = tables.messages
_E = tables.case_events

# The statuses no work list step is on: the bounds of the partial indexes.
SETTLED_ORDERS: Final = (OrderStatus.CONFIRMED, OrderStatus.CLOSED)
SETTLED_QUOTES: Final = (QuoteStatus.MASTER_LIST_RECORDED, QuoteStatus.DECLINED)
_TEXT_ARRAY = ARRAY(sa.Text)


def _not_in(column: str, values: Sequence[str]) -> sa.TextClause:
    """``column NOT IN (...)`` with the values written in, as the index's
    predicate is: a bound list matches it in a custom plan only."""
    listed = ", ".join(f"'{value}'" for value in values)
    return sa.text(f"{column} NOT IN ({listed})")


# The quotation's due date as the work list sorts it, written as the index is.
_QUOTE_GROUP = sa.literal_column(f"coalesce(quote_cases.quote_due, '{NO_DUE}')", sa.Text)


def _spread(row: sa.Row[Any] | None) -> Spread:
    if row is None or not row.cases:
        return Spread(cases=0, median_seconds=None, max_seconds=None)
    return Spread(cases=row.cases, median_seconds=row.median, max_seconds=row.longest)


def _spread_of(seconds: sa.ColumnElement[Any]) -> tuple[sa.ColumnElement[Any], ...]:
    as_float = sa.cast(seconds, sa.Float)
    return (
        sa.func.count().label("cases"),
        sa.func.percentile_cont(0.5).within_group(as_float).label("median"),
        sa.func.max(as_float).label("longest"),
    )


def _epoch(interval: sa.ColumnElement[Any]) -> sa.ColumnElement[Any]:
    return sa.extract("epoch", interval)


def _current_revisions() -> sa.Subquery:
    return (
        sa.select(_R.c.id, _R.c.case_id, _R.c.document)
        .where(_R.c.superseded_at.is_(None))
        .subquery("current")
    )


@dataclass(frozen=True)
class SqlOverviewReader:
    """Implements `OverviewReadPort` inside a unit of work's transaction."""

    session: AsyncSession
    scope: SalesScope

    # ------------------------------------------------------------ figures --

    async def figures(self, basis: FigureBasis) -> OverviewFigures:
        lines = await self._lines()
        routed, unowned = await self._routed()
        export, months = await self._export(basis)
        return OverviewFigures(
            statuses=await self._statuses(),
            decided_inbox_ids=await self._decided(basis.inbox_ids),
            routed_to_sales=routed,
            routed_without_owner=unowned,
            times=await self._times(basis),
            order_confirmation=await self._order_confirmation(),
            quotation_time=await self._quotation_time(),
            lines_printed=lines["printed"],
            lines_read=lines["read"],
            lines_exact=lines["exact"],
            lines_candidate_confirmed=lines["confirmed"],
            findings_by_code=await self._findings(),
            orders_prepared_without_correction=await self._prepared_without_correction(),
            quotes_sent_as_first_drafted=await self._sent_as_first_drafted(),
            a3_shadow=await self._a3_shadow(),
            export=export,
            months=months,
        )

    async def _statuses(self) -> Mapping[CaseKind, Mapping[str, int]]:
        counted: dict[CaseKind, dict[str, int]] = {CaseKind.ORDER: {}, CaseKind.QUOTE: {}}
        for kind, table in ((CaseKind.ORDER, _C), (CaseKind.QUOTE, _Q)):
            rows = await self.session.execute(
                sa.select(table.c.status, sa.func.count()).group_by(table.c.status)
            )
            counted[kind] = dict(rows.tuples().all())
        return counted

    async def _decided(self, inbox_ids: frozenset[str]) -> frozenset[str]:
        if not inbox_ids:
            return frozenset()
        rows = await self.session.execute(
            sa.select(_M.c.message_id).where(_M.c.message_id.in_(sorted(inbox_ids)))
        )
        return frozenset(rows.scalars())

    async def _routed(self) -> tuple[int, int]:
        routed = _M.c.disposition == DispositionKind.ROUTED_TO_SALES.value
        row = (
            await self.session.execute(
                sa.select(
                    sa.func.count().filter(routed),
                    sa.func.count().filter(routed, sa.func.coalesce(_M.c.owner, "") == ""),
                )
            )
        ).one()
        return int(row[0]), int(row[1])

    async def _times(self, basis: FigureBasis) -> Mapping[Bucket, Spread]:
        """Each case's seconds per bucket, from its consecutive events (the
        bucket of the status the case was in), and DW1's from the message's
        ingest to the case's first draft-ready event (its first event when it
        has none); then per bucket the cases, the median and the longest."""
        pairs = [
            (kind.value, status, bucket)
            for kind, mapping in basis.buckets.items()
            for status, bucket in mapping.items()
            if bucket != "dw"
        ]
        bucket_of = sa.select(
            sa.func.unnest(sa.cast([p[0] for p in pairs], _TEXT_ARRAY)).label("kind"),
            sa.func.unnest(sa.cast([p[1] for p in pairs], _TEXT_ARRAY)).label("status"),
            sa.func.unnest(sa.cast([p[2] for p in pairs], _TEXT_ARRAY)).label("bucket"),
        ).subquery("bucket_of")
        order = (_E.c.occurred_at, _E.c.case_version, _E.c.id)
        stepped = sa.select(
            _E.c.case_kind,
            _E.c.case_id,
            _E.c.to_status,
            _E.c.occurred_at,
            sa.func.lead(_E.c.occurred_at)
            .over(partition_by=_E.c.case_id, order_by=order)
            .label("next_at"),
        ).subquery("stepped")
        spent = (
            sa.select(
                stepped.c.case_id,
                bucket_of.c.bucket,
                sa.func.sum(_epoch(stepped.c.next_at - stepped.c.occurred_at)).label("seconds"),
            )
            .join(
                bucket_of,
                sa.and_(
                    bucket_of.c.kind == stepped.c.case_kind,
                    bucket_of.c.status == stepped.c.to_status,
                ),
            )
            .where(stepped.c.next_at.is_not(None))
            .group_by(stepped.c.case_id, bucket_of.c.bucket)
        )
        case_of_message = sa.func.coalesce(_M.c.order_case_id, _M.c.quote_case_id)
        ingest = (
            sa.select(case_of_message.label("case_id"), sa.func.min(_M.c.processed_at).label("at"))
            .where(
                _M.c.disposition == DispositionKind.CASE_CREATED.value,
                case_of_message.is_not(None),
            )
            .group_by(case_of_message)
            .subquery("ingest")
        )
        draft_kinds = sorted(basis.draft_ready)
        draft = sa.select(
            sa.func.unnest(sa.cast([k.value for k in draft_kinds], _TEXT_ARRAY)).label("kind"),
            sa.func.unnest(sa.cast([basis.draft_ready[k] for k in draft_kinds], _TEXT_ARRAY)).label(
                "status"
            ),
        ).subquery("draft")
        ready = (
            sa.select(_E.c.case_id, _E.c.occurred_at)
            .outerjoin(draft, draft.c.kind == _E.c.case_kind)
            .distinct(_E.c.case_id)
            .order_by(
                _E.c.case_id,
                sa.desc(sa.func.coalesce(_E.c.to_status == draft.c.status, False)),
                *order,
            )
            .subquery("ready")
        )
        dw = sa.select(
            ready.c.case_id,
            sa.literal("dw").label("bucket"),
            sa.func.greatest(_epoch(ready.c.occurred_at - ingest.c.at), 0).label("seconds"),
        ).join(ingest, ingest.c.case_id == ready.c.case_id)
        every = sa.union_all(spent, dw).subquery("every")
        rows = await self.session.execute(
            sa.select(every.c.bucket, *_spread_of(every.c.seconds)).group_by(every.c.bucket)
        )
        found = {row.bucket: _spread(row) for row in rows}
        return {bucket: found.get(bucket, _spread(None)) for bucket in BUCKETS}

    async def _order_confirmation(self) -> Spread:
        seconds = _epoch(_C.c.confirmed_at - _C.c.received_at)
        row = (
            await self.session.execute(
                sa.select(*_spread_of(seconds)).where(_C.c.confirmed_at.is_not(None))
            )
        ).one()
        return _spread(row)

    async def _quotation_time(self) -> Spread:
        sent_at = sa.cast(_Q.c.body[("sent", "at")].astext, sa.TIMESTAMP(timezone=True))
        row = (
            await self.session.execute(
                sa.select(*_spread_of(_epoch(sent_at - _Q.c.received_at))).where(
                    _Q.c.body[("sent", "at")].astext.is_not(None)
                )
            )
        ).one()
        return _spread(row)

    async def _lines(self) -> Mapping[str, int]:
        current = _current_revisions()
        printed = await self.session.scalar(
            sa.select(
                sa.func.coalesce(
                    sa.func.sum(sa.cast(current.c.document["rows_printed"].astext, sa.Integer)), 0
                )
            )
        )
        row = (
            await self.session.execute(
                sa.select(
                    sa.func.count(),
                    sa.func.count().filter(_L.c.mapping_status == MappingStatus.EXACT.value),
                    sa.func.count().filter(
                        _L.c.mapping_status == MappingStatus.CANDIDATE_CONFIRMED.value
                    ),
                ).join(current, current.c.id == _L.c.revision_id)
            )
        ).one()
        return {
            "printed": int(printed or 0),
            "read": int(row[0]),
            "exact": int(row[1]),
            "confirmed": int(row[2]),
        }

    async def _findings(self) -> Mapping[str, int]:
        current = _current_revisions()
        counted: dict[str, int] = defaultdict(int)
        orders = await self.session.execute(
            sa.select(_F.c.code, sa.func.count())
            .join(current, current.c.id == _F.c.revision_id)
            .group_by(_F.c.code)
        )
        for code, count in orders.tuples():
            counted[code] += count
        finding = (
            sa.func.jsonb_array_elements(_Q.c.body["findings"])
            .table_valued("value")
            .render_derived("finding")
        )
        code = finding.c.value.op("->>")(sa.literal_column("'code'"))
        quotes = await self.session.execute(
            sa.select(code, sa.func.count()).select_from(_Q).join(finding, sa.true()).group_by(code)
        )
        for found, count in quotes.tuples():
            counted[str(found)] += count
        return dict(counted)

    async def _prepared_without_correction(self) -> int:
        current = _current_revisions()
        corrected = (
            sa.select(sa.literal(1))
            .select_from(_F)
            .where(
                _F.c.revision_id == current.c.id,
                _F.c.disposition == FindingDisposition.CORRECTED_BY_SALES.value,
            )
            .exists()
        )
        hand_entered = (
            sa.select(sa.literal(1))
            .select_from(_L)
            .where(
                _L.c.revision_id == current.c.id,
                _L.c.mapping_status == MappingStatus.CANDIDATE_CONFIRMED.value,
                sa.func.jsonb_array_length(_L.c.candidates) == 0,
            )
            .exists()
        )
        count = await self.session.scalar(
            sa.select(sa.func.count())
            .select_from(_C)
            .join(current, current.c.case_id == _C.c.id)
            .where(_C.c.prepared_by.is_not(None), ~corrected, ~hand_entered)
        )
        return int(count or 0)

    async def _sent_as_first_drafted(self) -> int:
        count = await self.session.scalar(
            sa.select(sa.func.count()).where(
                _Q.c.body[("sent", "at")].astext.is_not(None),
                sa.func.jsonb_array_length(_Q.c.body["returns"]) == 0,
                sa.func.jsonb_array_length(_Q.c.body["earlier_pricing"]) == 0,
            )
        )
        return int(count or 0)

    async def _a3_shadow(self) -> int:
        """Orders with no finding, every line exact, and no earlier revision."""
        current = _current_revisions()
        found = sa.select(sa.literal(1)).where(_F.c.revision_id == current.c.id).exists()
        inexact = (
            sa.select(sa.literal(1))
            .where(
                _L.c.revision_id == current.c.id,
                _L.c.mapping_status != MappingStatus.EXACT.value,
            )
            .exists()
        )
        revised = (
            sa.select(sa.literal(1))
            .where(_R.c.case_id == current.c.case_id, _R.c.superseded_at.is_not(None))
            .exists()
        )
        count = await self.session.scalar(
            sa.select(sa.func.count()).select_from(current).where(~found, ~inexact, ~revised)
        )
        return int(count or 0)

    async def _export(
        self, basis: FigureBasis
    ) -> tuple[Mapping[tuple[str, str], int], tuple[str, ...]]:
        """Per surveyed step and month, the cases taken through it (each once):
        a case's event passes the status it moved to, and the case's first
        event passed through `received` on the way."""
        listed = [(s.step_id, s.kind.value, state) for s in basis.steps for state in s.states]
        steps = sa.select(
            sa.func.unnest(sa.cast([r[0] for r in listed], _TEXT_ARRAY)).label("step_id"),
            sa.func.unnest(sa.cast([r[1] for r in listed], _TEXT_ARRAY)).label("kind"),
            sa.func.unnest(sa.cast([r[2] for r in listed], _TEXT_ARRAY)).label("state"),
        ).subquery("steps")
        month = sa.func.to_char(sa.func.timezone(basis.zone, _E.c.occurred_at), "YYYY-MM")
        rows = await self.session.execute(
            sa.select(steps.c.step_id, month.label("month"), sa.func.count(_E.c.case_id.distinct()))
            .select_from(_E)
            .join(
                steps,
                sa.and_(
                    steps.c.kind == _E.c.case_kind,
                    sa.or_(
                        steps.c.state == _E.c.to_status,
                        sa.and_(_E.c.from_status.is_(None), steps.c.state == "received"),
                    ),
                ),
            )
            .group_by(steps.c.step_id, month)
        )
        export = {(step_id, at): count for step_id, at, count in rows.tuples()}
        months = await self.session.execute(sa.select(month.distinct()).order_by(month))
        return export, tuple(months.scalars())

    # ---------------------------------------------------------- work list --

    async def work_page(self, wanted: WorkFilter, request: PageRequest) -> Page[WorkEntry]:
        after = request.after
        me = wanted.principal_id
        limit = request.fetch_limit
        # Named although RLS narrows to it too: the policy's workspace test is
        # an OR (the offboarding lane's tenant scope), which no index can seek
        # on, so without this each branch sorted every open row of the tenant
        # (measured on 50,000 cases, ticket 24).
        workspace = self.scope.workspace_id.value
        mine_or_nobody = sa.or_(_C.c.assigned_to.is_(None), _C.c.assigned_to == me)
        orders = (
            sa.select(
                sa.literal("order").label("kind"),
                _C.c.id.label("row_id"),
                sa.literal(NO_DUE, sa.Text).label("grp"),
                _C.c.received_at,
            )
            .where(
                _C.c.workspace_id == workspace,
                _not_in("order_cases.status", [s.value for s in SETTLED_ORDERS]),
                sa.or_(
                    sa.and_(
                        _C.c.status.in_(sorted(s.value for s in wanted.order_statuses)),
                        mine_or_nobody,
                    ),
                    sa.and_(
                        sa.literal(wanted.cross_checks),
                        _C.c.status == OrderStatus.UPLOADED_TO_BRAVO.value,
                    ),
                ),
                *_after_constant_group(NO_DUE, _C.c.received_at, _C.c.id, after),
            )
            .order_by(_C.c.received_at, _C.c.id)
            .limit(limit)
        )
        quotes = (
            sa.select(
                sa.literal("quote").label("kind"),
                _Q.c.id.label("row_id"),
                _QUOTE_GROUP.label("grp"),
                _Q.c.received_at,
            )
            .where(
                _Q.c.workspace_id == workspace,
                _not_in("quote_cases.status", [s.value for s in SETTLED_QUOTES]),
                sa.or_(
                    sa.and_(
                        _Q.c.status.in_(sorted(wanted.quote_statuses)),
                        sa.or_(_Q.c.assigned_to.is_(None), _Q.c.assigned_to == me),
                    ),
                    sa.and_(
                        sa.literal(wanted.approvals),
                        _Q.c.status == QuoteStatus.PENDING_APPROVAL.value,
                        _Q.c.priced_by.is_distinct_from(me),
                    ),
                ),
                *(
                    []
                    if after is None
                    else [
                        sa.tuple_(_QUOTE_GROUP, _Q.c.received_at, _Q.c.id)
                        > sa.tuple_(
                            sa.literal(after.group, sa.Text),
                            sa.literal(after.sort_value, sa.TIMESTAMP(timezone=True)),
                            sa.literal(after.tiebreaker, _Q.c.id.type),
                        )
                    ]
                ),
            )
            .order_by(_QUOTE_GROUP, _Q.c.received_at, _Q.c.id)
            .limit(limit)
        )
        messages = (
            sa.select(
                sa.literal("message").label("kind"),
                _M.c.id.label("row_id"),
                sa.literal(NO_DUE, sa.Text).label("grp"),
                _M.c.processed_at.label("received_at"),
            )
            .where(
                _M.c.workspace_id == workspace,
                sa.text(f"messages.disposition = '{DispositionKind.ROUTED_TO_SALES.value}'"),
                sa.func.lower(sa.func.coalesce(_M.c.owner, "")).in_(sorted(wanted.message_owners)),
                *_after_constant_group(NO_DUE, _M.c.processed_at, _M.c.id, after),
            )
            .order_by(_M.c.processed_at, _M.c.id)
            .limit(limit)
        )
        merged = sa.union_all(
            sa.select(orders.subquery()),
            sa.select(quotes.subquery()),
            sa.select(messages.subquery()),
        ).subquery("work")
        keys = (
            await self.session.execute(
                sa.select(merged)
                .order_by(merged.c.grp, merged.c.received_at, merged.c.row_id)
                .limit(limit)
            )
        ).all()
        rows = await self._rows(keys)
        entries = [
            WorkEntry(
                position=CursorPosition(
                    sort_value=key.received_at, tiebreaker=key.row_id, group=key.grp
                ),
                row=rows[key.row_id],
            )
            for key in keys
            if key.row_id in rows
        ]
        return build_page(entries, request=request, position_of=lambda entry: entry.position)

    async def _rows(self, keys: Sequence[sa.Row[Any]]) -> dict[uuid.UUID, Any]:
        """The rows the keys name, read whole: an order without its document."""
        ids: dict[str, list[uuid.UUID]] = defaultdict(list)
        for key in keys:
            ids[key.kind].append(key.row_id)
        found: dict[uuid.UUID, Any] = {}
        if ids["order"]:
            for row in await self.session.execute(
                sa.select(
                    _C.c.id, _C.c.status, _C.c.customer_code, _C.c.received_at, _C.c.assigned_to
                ).where(_C.c.id.in_(ids["order"]))
            ):
                found[row.id] = OpenOrder(
                    case_id=row.id,
                    status=OrderStatus(row.status),
                    customer_code=row.customer_code,
                    received_at=row.received_at,
                    assigned_to=row.assigned_to,
                )
        if ids["quote"]:
            for quote in (
                await self.session.execute(sa.select(_Q).where(_Q.c.id.in_(ids["quote"])))
            ).mappings():
                found[quote["id"]] = stored_quote(quote)
        if ids["message"]:
            for message in (
                await self.session.execute(sa.select(_M).where(_M.c.id.in_(ids["message"])))
            ).mappings():
                found[message["id"]] = LoggedMessage(
                    disposition_of(message), message["processed_at"]
                )
        return found


def _after_constant_group(
    group: str,
    received_at: sa.ColumnElement[datetime],
    row_id: sa.ColumnElement[uuid.UUID],
    after: CursorPosition | None,
) -> list[sa.ColumnElement[bool]]:
    """The keyset condition for rows that all sort in ``group``: none before
    the first page or after an earlier group, (received, id) past the cursor
    within it, and none at all once the cursor is in a later group."""
    if after is None or after.group < group:
        return []
    if after.group > group:
        return [sa.false()]
    return [
        sa.tuple_(received_at, row_id)
        > sa.tuple_(
            sa.literal(after.sort_value, sa.TIMESTAMP(timezone=True)),
            sa.literal(after.tiebreaker, row_id.type),
        )
    ]
