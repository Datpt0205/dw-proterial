"""`OverviewReadPort` over cases held in memory: the in-memory store's, and
the reference the SQL reader is held to (ticket 24).

This is the computation the overview service made before ticket 24, when it
loaded every case, message and event and counted in Python. It stays here, out
of the service, for two readers: the in-memory store the evals and the unit
tests run on, and the API's `test_sales_overview_sql.py`, which runs it and
the SQL reader over the same stored cases and asserts the same figures and
the same work.
"""

from __future__ import annotations

import statistics
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from zoneinfo import ZoneInfo

from dw_kernel.pagination import CursorPosition, Page, PageRequest, build_page
from dw_sales.application.case_store import LoggedEvent, LoggedMessage, Stored
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
from dw_sales.domain.dispositions import CaseKind, DispositionKind
from dw_sales.domain.orders import CorrectedBySales, MappingStatus, OrderCase, OrderStatus
from dw_sales.domain.quotes import QuoteCase, QuoteStatus


def message_row_id(message_id: str) -> uuid.UUID:
    """A message's stable row id in memory, where no table mints one."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"sales-message:{message_id}")


@dataclass(frozen=True)
class PythonOverviewReader:
    """Implements `OverviewReadPort` over the workspace's stored records."""

    orders: Sequence[Stored[OrderCase]]
    quotes: Sequence[Stored[QuoteCase]]
    messages: Sequence[LoggedMessage]
    events: Sequence[LoggedEvent]

    async def figures(self, basis: FigureBasis) -> OverviewFigures:
        orders = [s.case for s in self.orders]
        quotes = [s.case for s in self.quotes]
        lines = Counter(line.mapping.status for o in orders for line in o.lines)
        export, months = _export(self.events, basis)
        routed = [m for m in self.messages if m.disposition.kind is DispositionKind.ROUTED_TO_SALES]
        return OverviewFigures(
            statuses={
                CaseKind.ORDER: dict(Counter(o.status.value for o in orders)),
                CaseKind.QUOTE: dict(Counter(q.status.value for q in quotes)),
            },
            decided_inbox_ids=frozenset(
                m.disposition.message_id
                for m in self.messages
                if m.disposition.message_id in basis.inbox_ids
            ),
            routed_to_sales=len(routed),
            routed_without_owner=sum(1 for m in routed if not m.disposition.owner),
            times=_times(self.events, self.messages, basis),
            order_confirmation=_spread(
                [
                    (o.confirmed_at - o.received_at).total_seconds()
                    for o in orders
                    if o.confirmed_at is not None
                ]
            ),
            quotation_time=_spread(
                [
                    (q.sent.at - q.request.received_at).total_seconds()
                    for q in quotes
                    if q.sent is not None
                ]
            ),
            lines_printed=sum(o.document.rows_printed for o in orders),
            lines_read=sum(len(o.lines) for o in orders),
            lines_exact=lines[MappingStatus.EXACT],
            lines_candidate_confirmed=lines[MappingStatus.CANDIDATE_CONFIRMED],
            findings_by_code=dict(
                Counter(
                    [f.code.value for o in orders for f in o.findings]
                    + [f.code.value for q in quotes for f in q.findings]
                )
            ),
            orders_prepared_without_correction=sum(
                1 for o in orders if o.prepared_by is not None and not _corrected(o)
            ),
            quotes_sent_as_first_drafted=sum(
                1 for q in quotes if q.sent is not None and not q.returns and not q.earlier_pricing
            ),
            a3_shadow=sum(1 for o in orders if _a3_shadow(o)),
            export=export,
            months=months,
        )

    async def work_page(self, wanted: WorkFilter, request: PageRequest) -> Page[WorkEntry]:
        me = wanted.principal_id
        entries: list[WorkEntry] = []
        for stored in self.orders:
            case, assigned = stored.case, stored.origin.assigned_to
            mine = case.status in wanted.order_statuses and assigned in (None, me)
            check = wanted.cross_checks and case.status is OrderStatus.UPLOADED_TO_BRAVO
            if mine or check:
                row = OpenOrder(
                    case_id=case.case_id,
                    status=case.status,
                    customer_code=case.customer_code,
                    received_at=case.received_at,
                    due=case.due,
                    assigned_to=assigned,
                )
                group = case.due.isoformat() if case.due else NO_DUE
                entries.append(_entry(group, case.received_at, case.case_id, row))
        for quoted in self.quotes:
            quote, assigned = quoted.case, quoted.origin.assigned_to
            pricer = quote.pricing.decided_by if quote.pricing else None
            mine = quote.status.value in wanted.quote_statuses and assigned in (None, me)
            approve = (
                wanted.approvals and quote.status is QuoteStatus.PENDING_APPROVAL and pricer != me
            )
            if mine or approve:
                due = quote.request.document.quote_due
                group = due.value.isoformat() if due else NO_DUE
                entries.append(_entry(group, quote.request.received_at, quote.case_id, quoted))
        for logged in self.messages:
            d = logged.disposition
            if (
                d.kind is DispositionKind.ROUTED_TO_SALES
                and (d.owner or "").lower() in wanted.message_owners
            ):
                row_id = message_row_id(d.message_id)
                entries.append(_entry(NO_DUE, logged.processed_at, row_id, logged))
        entries.sort(key=_key)
        after = request.after
        if after is not None:
            entries = [
                e for e in entries if _key(e) > (after.group, after.sort_value, after.tiebreaker)
            ]
        return build_page(
            entries[: request.fetch_limit], request=request, position_of=lambda e: e.position
        )


def _entry(group: str, at: datetime, row_id: uuid.UUID, row: object) -> WorkEntry:
    position = CursorPosition(sort_value=at, tiebreaker=row_id, group=group)
    return WorkEntry(position=position, row=row)  # type: ignore[arg-type]


def _key(entry: WorkEntry) -> tuple[str, datetime, uuid.UUID]:
    p = entry.position
    return p.group, p.sort_value, p.tiebreaker


def _spread(seconds: Sequence[float]) -> Spread:
    return Spread(
        cases=len(seconds),
        median_seconds=statistics.median(seconds) if seconds else None,
        max_seconds=max(seconds) if seconds else None,
    )


def _times(
    events: Iterable[LoggedEvent], messages: Sequence[LoggedMessage], basis: FigureBasis
) -> Mapping[Bucket, Spread]:
    """Each case's time per bucket, from its consecutive events; DW1's time
    also counts from the message's ingest to the case's first draft-ready
    event (its first event when it has none)."""
    ingest: dict[uuid.UUID, datetime] = {}
    for m in messages:
        d = m.disposition
        if d.case_id is not None and d.kind is DispositionKind.CASE_CREATED:
            earlier = ingest.get(d.case_id)
            ingest[d.case_id] = m.processed_at if earlier is None else min(earlier, m.processed_at)
    by_case: dict[uuid.UUID, list[LoggedEvent]] = defaultdict(list)
    for event in events:
        by_case[event.case_id].append(event)
    totals: dict[Bucket, list[float]] = {bucket: [] for bucket in BUCKETS}
    for case_id, timeline in by_case.items():
        timeline.sort(key=lambda e: (e.occurred_at, e.case_version))
        buckets = basis.buckets[timeline[0].case_kind]
        spent: dict[Bucket, float] = defaultdict(float)
        started = ingest.get(case_id)
        if started is not None:
            ready = next(
                (e for e in timeline if e.to_status == basis.draft_ready[e.case_kind]),
                timeline[0],
            )
            spent["dw"] += max((ready.occurred_at - started).total_seconds(), 0.0)
        for before, after in pairwise(timeline):
            bucket = buckets.get(before.to_status)
            if bucket is not None and bucket != "dw":
                spent[bucket] += (after.occurred_at - before.occurred_at).total_seconds()
        for bucket, seconds in spent.items():
            totals[bucket].append(seconds)
    return {bucket: _spread(seconds) for bucket, seconds in totals.items()}


def _corrected(case: OrderCase) -> bool:
    return any(isinstance(f.disposition, CorrectedBySales) for f in case.findings) or any(
        line.mapping.hand_entered for line in case.lines
    )


def _a3_shadow(case: OrderCase) -> bool:
    return (
        not case.findings
        and not case.superseded
        and all(line.mapping.status is MappingStatus.EXACT for line in case.lines)
    )


def _export(
    events: Sequence[LoggedEvent], basis: FigureBasis
) -> tuple[Mapping[tuple[str, str], int], tuple[str, ...]]:
    """The cases taken through each surveyed step per month (each case once)."""
    zone = ZoneInfo(basis.zone)

    def month(at: datetime) -> str:
        local = at.astimezone(zone)
        return f"{local.year:04d}-{local.month:02d}"

    cases: dict[tuple[str, str], set[uuid.UUID]] = defaultdict(set)
    for step in basis.steps:
        for event in events:
            # A case is opened already checked: its first event passed
            # through `received` (O1) on the way.
            passed = {event.to_status} | ({"received"} if event.from_status is None else set())
            if event.case_kind is step.kind and passed & step.states:
                cases[(step.step_id, month(event.occurred_at))].add(event.case_id)
    months = tuple(sorted({month(event.occurred_at) for event in events}))
    return {key: len(ids) for key, ids in cases.items()}, months
