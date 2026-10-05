"""The overview (counts and times, no amounts) and each person's work list.

**Overview** (`sales.overview.read`, the one Sales URL leadership reaches).
Everything is a count or a duration read from the cases, their events and
the message log, never an amount (spec decision 8):

- cases per surveyed step, the step-to-state mapping read from `WIV_STEPS`;
- messages without a disposition, and how long the oldest has waited;
- DW1's time (ingest to draft ready) and Sales' decision time, apart from
  the waits on Design, the approver and the customer. PC's wait is outside
  the portal and is not measured;
- lines printed against lines read, how lines were mapped, findings by code,
  orders prepared without a corrected value, quotations sent as first
  drafted, and the A3 shadow count;
- an export per surveyed step and month beside the manual baseline, and the
  two targets beside what was measured, from `sales_kpi`, without a verdict.

**My work** (`sales.case.read`): the next step on each open case, for a
caller whose scopes allow that step. The cross-check goes to every holder of
`sales.order.cross_check` who made none of the case, an approval to every
holder of `sales.quote.approve` who did not price it; every other step to
the case's assignee, and an unassigned case to everyone who may take the
step. Messages routed to Sales go to their owner, or to every PIC when the
owner is the pool.

The overview loads every case of the workspace: right for the demo's mock
set, and owed to SQL aggregates before real volume (ticket 12).
"""

from __future__ import annotations

import statistics
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise
from typing import Final, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from dw_kernel.ports import UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import (
    LoggedEvent,
    LoggedMessage,
    SalesUnitOfWorkFactory,
    Stored,
)
from dw_sales.application.ports import InboxPort, MemberDirectoryPort
from dw_sales.application.views import WorkerStateView, worker_state
from dw_sales.domain.dispositions import SALES_PIC_POOL, CaseKind, DispositionKind
from dw_sales.domain.kpi import SalesKpi
from dw_sales.domain.orders import CorrectedBySales, MappingStatus, OrderCase, OrderStatus
from dw_sales.domain.process import WIV_STEPS, Procedure
from dw_sales.domain.quotes import QuoteCase, QuoteStatus

_VIEW = ConfigDict(frozen=True)
_LOCAL = ZoneInfo("Asia/Ho_Chi_Minh")

Bucket = Literal["dw", "sales", "design", "approver", "customer"]

# Whose time a case's interval in each status is: the status it was in.
_ORDER_BUCKETS: Final[Mapping[str, Bucket]] = {
    OrderStatus.RECEIVED: "dw",
    OrderStatus.CHECKED: "dw",
    OrderStatus.IN_REVIEW: "sales",
    OrderStatus.PREPARED: "sales",
    OrderStatus.UPLOADED_TO_BRAVO: "sales",
    OrderStatus.CROSS_CHECKED: "sales",
    OrderStatus.CHANGE_REVIEW: "sales",
    OrderStatus.CORRECTION_REQUESTED: "customer",
}
_QUOTE_BUCKETS: Final[Mapping[str, Bucket]] = {
    QuoteStatus.RECEIVED: "sales",
    QuoteStatus.YCBG_DRAFTED: "sales",
    QuoteStatus.YCBG_RECORDED: "sales",
    QuoteStatus.SENT_TO_DESIGN: "design",
    QuoteStatus.DESIGN_REPLIED: "sales",
    QuoteStatus.SPEC_DISCUSSION: "customer",
    QuoteStatus.PRICED: "sales",
    QuoteStatus.PENDING_APPROVAL: "approver",
    QuoteStatus.RETURNED: "sales",
    QuoteStatus.APPROVED: "sales",
    QuoteStatus.SENT: "sales",
}
# The status a case is "draft ready" in: handed to Sales.
_DRAFT_READY: Final = {CaseKind.ORDER: OrderStatus.IN_REVIEW.value, CaseKind.QUOTE: "received"}
_PROCEDURE_KIND: Final = {
    Procedure.ORDER_ENTRY: CaseKind.ORDER,
    Procedure.QUOTATION: CaseKind.QUOTE,
}


class StepCount(BaseModel):
    model_config = _VIEW

    step_id: str
    procedure: str
    coverage: str
    states: list[str]
    cases: int


class MessagesView(BaseModel):
    model_config = _VIEW

    total: int
    without_disposition: int
    oldest_waiting_seconds: float | None
    routed_to_sales: int
    routed_without_owner: int


class TimeStat(BaseModel):
    model_config = _VIEW

    cases: int
    median_seconds: float | None
    max_seconds: float | None


class TimesView(BaseModel):
    model_config = _VIEW

    dw: TimeStat
    sales: TimeStat
    design: TimeStat
    approver: TimeStat
    customer: TimeStat
    # Agreed with PC outside the portal: nothing here can measure it.
    pc: None = None


class TargetView(BaseModel):
    """A target beside what was measured end to end (waits included)."""

    model_config = _VIEW

    target_seconds: float
    measured: TimeStat


class MappingCounts(BaseModel):
    model_config = _VIEW

    convert_list: int
    confirmed_candidate: int
    unresolved: int


class ExportRow(BaseModel):
    """One surveyed step in one month (giờ Việt Nam): how many times DW1
    took a case through it, beside the minutes it takes by hand."""

    model_config = _VIEW

    step_id: str
    month: str
    times: int
    manual_baseline_minutes: int


class OverviewView(BaseModel):
    model_config = _VIEW

    as_of: datetime
    kpi_policy: str
    worker: WorkerStateView
    steps: list[StepCount]
    messages: MessagesView
    times: TimesView
    order_confirmation: TargetView
    quotation_time: TargetView
    lines_printed: int
    lines_read: int
    mapping: MappingCounts
    findings_by_code: dict[str, int]
    orders_prepared_without_correction: int
    quotes_sent_as_first_drafted: int
    # Orders that would have met the A3 minimum conditions DW1 assumes until
    # the customer defines them: no finding at all, every line exact in the
    # convert list, an original (not a revision).
    a3_shadow: int
    export: list[ExportRow]


class WorkItem(BaseModel):
    model_config = _VIEW

    kind: Literal["order", "quote", "message"]
    id: str
    status: str
    action: str
    customer_code: str | None
    received_at: datetime
    due: date | None
    assigned_to: uuid.UUID | None


# The next step on an open case, and the scope that takes it. A status not
# listed waits on someone outside Sales (the customer, Design) or is done.
_ORDER_NEXT: Final[Mapping[OrderStatus, tuple[str, SalesScopes]]] = {
    OrderStatus.CHECKED: ("self_check", SalesScopes.ORDER_PREPARE),
    OrderStatus.IN_REVIEW: ("self_check", SalesScopes.ORDER_PREPARE),
    OrderStatus.PREPARED: ("bravo_entry", SalesScopes.ORDER_PREPARE),
    OrderStatus.UPLOADED_TO_BRAVO: ("cross_check", SalesScopes.ORDER_CROSS_CHECK),
    OrderStatus.CROSS_CHECKED: ("confirm", SalesScopes.ORDER_PREPARE),
    OrderStatus.CHANGE_REVIEW: ("apply_change", SalesScopes.ORDER_PREPARE),
}
_QUOTE_NEXT: Final[Mapping[QuoteStatus, tuple[str, SalesScopes]]] = {
    QuoteStatus.RECEIVED: ("draft_ycbg", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.YCBG_DRAFTED: ("record_ycbg", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.YCBG_RECORDED: ("send_to_design", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.DESIGN_REPLIED: ("price", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.SPEC_DISCUSSION: ("settle_spec", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.PRICED: ("submit", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.PENDING_APPROVAL: ("approve", SalesScopes.QUOTE_APPROVE),
    QuoteStatus.RETURNED: ("reprice", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.APPROVED: ("send", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.SENT: ("record_master_list", SalesScopes.QUOTE_PREPARE),
}


def _stat(seconds: Sequence[float]) -> TimeStat:
    return TimeStat(
        cases=len(seconds),
        median_seconds=statistics.median(seconds) if seconds else None,
        max_seconds=max(seconds) if seconds else None,
    )


def _month(at: datetime) -> str:
    local = at.astimezone(_LOCAL)
    return f"{local.year:04d}-{local.month:02d}"


@dataclass(frozen=True, slots=True)
class _Durations:
    per_bucket: dict[Bucket, list[float]]


def _durations(events: Iterable[LoggedEvent], ingest: Mapping[uuid.UUID, datetime]) -> _Durations:
    """Each case's time per bucket, from its consecutive events; DW1's time
    also counts from the message's ingest to the case's first event."""
    by_case: dict[uuid.UUID, list[LoggedEvent]] = defaultdict(list)
    for event in events:
        by_case[event.case_id].append(event)
    totals: dict[Bucket, list[float]] = {
        "dw": [],
        "sales": [],
        "design": [],
        "approver": [],
        "customer": [],
    }
    for case_id, timeline in by_case.items():
        timeline.sort(key=lambda e: (e.occurred_at, e.case_version))
        buckets = _ORDER_BUCKETS if timeline[0].case_kind is CaseKind.ORDER else _QUOTE_BUCKETS
        spent: dict[Bucket, float] = defaultdict(float)
        started = ingest.get(case_id)
        if started is not None:
            ready = next(
                (e for e in timeline if e.to_status == _DRAFT_READY[e.case_kind]), timeline[0]
            )
            spent["dw"] += max((ready.occurred_at - started).total_seconds(), 0.0)
        for before, after in pairwise(timeline):
            bucket = buckets.get(before.to_status)
            if bucket is not None and bucket != "dw":
                spent[bucket] += (after.occurred_at - before.occurred_at).total_seconds()
        for bucket, seconds in spent.items():
            totals[bucket].append(seconds)
    return _Durations(totals)


@dataclass(frozen=True)
class OverviewService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    inbox: InboxPort
    kpi: SalesKpi
    directory: MemberDirectoryPort

    async def overview(self, context: AccessContext) -> OverviewView:
        await self.gate.require(context, SalesScopes.OVERVIEW_READ, resource_type="sales_overview")
        scope = sales_scope(context)
        now = self.clock.now()
        async with self.uow(scope) as work:
            orders = [s.case for s in await work.orders.list_all()]
            quotes = [s.case for s in await work.quotes.list_all()]
            messages = list(await work.messages.list_all())
            events = list(await work.events.list_all())
            worker = await work.worker.state()
        inbox = list(await self.inbox.list_messages(scope))
        return OverviewView(
            as_of=now,
            kpi_policy=self.kpi.version,
            worker=worker_state(worker),
            steps=_steps(orders, quotes),
            messages=_messages(
                inbox_ids={m.message_id: m.received_at for m in inbox}, logged=messages, now=now
            ),
            times=_times(events, messages),
            order_confirmation=TargetView(
                target_seconds=self.kpi.order_confirmation_target_hours * 3600.0,
                measured=_stat(
                    [
                        (o.confirmed_at - o.received_at).total_seconds()
                        for o in orders
                        if o.confirmed_at is not None
                    ]
                ),
            ),
            quotation_time=TargetView(
                target_seconds=self.kpi.quotation_target_days * 86400.0,
                measured=_stat(
                    [
                        (q.sent.at - q.request.received_at).total_seconds()
                        for q in quotes
                        if q.sent is not None
                    ]
                ),
            ),
            lines_printed=sum(o.document.rows_printed for o in orders),
            lines_read=sum(len(o.lines) for o in orders),
            mapping=_mapping(orders),
            findings_by_code=dict(
                sorted(
                    Counter(
                        [f.code.value for o in orders for f in o.findings]
                        + [f.code.value for q in quotes for f in q.findings]
                    ).items()
                )
            ),
            orders_prepared_without_correction=sum(
                1 for o in orders if o.prepared_by is not None and not _corrected(o)
            ),
            quotes_sent_as_first_drafted=sum(
                1 for q in quotes if q.sent is not None and not q.returns and not q.earlier_pricing
            ),
            a3_shadow=sum(1 for o in orders if _a3_shadow(o)),
            export=_export(events, self.kpi),
        )

    async def my_work(self, context: AccessContext) -> list[WorkItem]:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type="sales_work")
        scope = sales_scope(context)
        me = context.principal_id
        async with self.uow(scope) as work:
            orders = list(await work.orders.list_all())
            quotes = list(await work.quotes.list_all())
            messages = list(await work.messages.list_all())
        items = [item for s in orders if (item := self._order_item(context, s)) is not None]
        items += [item for s in quotes if (item := self._quote_item(context, s)) is not None]
        if self.gate.allows(context, SalesScopes.INBOX_PROCESS):
            mine = {
                m.email.lower()
                for m in await self.directory.list_members(context)
                if m.user_id == me and m.email
            }
            for logged in messages:
                d = logged.disposition
                if d.kind is DispositionKind.ROUTED_TO_SALES and (
                    d.owner == SALES_PIC_POOL or (d.owner or "").lower() in mine
                ):
                    items.append(
                        WorkItem(
                            kind="message",
                            id=d.message_id,
                            status=d.kind.value,
                            action=f"handle_{d.reason.value if d.reason else 'message'}",
                            customer_code=d.customer_code,
                            received_at=logged.processed_at,
                            due=None,
                            assigned_to=None,
                        )
                    )
        return sorted(items, key=lambda i: (i.due or date.max, i.received_at))

    def _eligible(
        self, context: AccessContext, scope: SalesScopes, assigned_to: uuid.UUID | None
    ) -> bool:
        if not self.gate.allows(context, scope):
            return False
        return assigned_to is None or assigned_to == context.principal_id

    def _order_item(self, context: AccessContext, stored: Stored[OrderCase]) -> WorkItem | None:
        case, assigned = stored.case, stored.origin.assigned_to
        step = _ORDER_NEXT.get(case.status)
        if step is None:
            return None
        action, scope = step
        if action == "cross_check":
            # Anyone who may cross-check and made none of the case.
            if not self.gate.allows(context, scope) or context.principal_id in case.makers:
                return None
        elif not self._eligible(context, scope, assigned):
            return None
        return WorkItem(
            kind="order",
            id=str(case.case_id),
            status=case.status.value,
            action=action,
            customer_code=case.customer_code,
            received_at=case.received_at,
            due=None,
            assigned_to=assigned,
        )

    def _quote_item(self, context: AccessContext, stored: Stored[QuoteCase]) -> WorkItem | None:
        case, assigned = stored.case, stored.origin.assigned_to
        step = _QUOTE_NEXT.get(case.status)
        if step is None:
            return None
        action, scope = step
        if action == "approve":
            pricer = case.pricing.decided_by if case.pricing else None
            if not self.gate.allows(context, scope) or context.principal_id == pricer:
                return None
        elif not self._eligible(context, scope, assigned):
            return None
        due = case.request.document.quote_due
        return WorkItem(
            kind="quote",
            id=str(case.case_id),
            status=case.status.value,
            action=action,
            customer_code=case.customer_code,
            received_at=case.request.received_at,
            due=due.value if due else None,
            assigned_to=assigned,
        )


def _steps(orders: Sequence[OrderCase], quotes: Sequence[QuoteCase]) -> list[StepCount]:
    statuses = {
        CaseKind.ORDER: Counter(o.status.value for o in orders),
        CaseKind.QUOTE: Counter(q.status.value for q in quotes),
    }
    return [
        StepCount(
            step_id=step.step_id,
            procedure=step.procedure.value,
            coverage=step.coverage.value,
            states=list(step.states),
            cases=sum(statuses[_PROCEDURE_KIND[step.procedure]][s] for s in step.states),
        )
        for step in WIV_STEPS
    ]


def _messages(
    *, inbox_ids: Mapping[str, datetime], logged: Sequence[LoggedMessage], now: datetime
) -> MessagesView:
    decided = {m.disposition.message_id for m in logged}
    waiting = [received for message_id, received in inbox_ids.items() if message_id not in decided]
    routed = [m for m in logged if m.disposition.kind is DispositionKind.ROUTED_TO_SALES]
    return MessagesView(
        total=len(inbox_ids),
        without_disposition=len(waiting),
        oldest_waiting_seconds=(now - min(waiting)).total_seconds() if waiting else None,
        routed_to_sales=len(routed),
        routed_without_owner=sum(1 for m in routed if not m.disposition.owner),
    )


def _times(events: Sequence[LoggedEvent], messages: Sequence[LoggedMessage]) -> TimesView:
    ingest = {
        m.disposition.case_id: m.processed_at
        for m in messages
        if m.disposition.case_id is not None and m.disposition.kind is DispositionKind.CASE_CREATED
    }
    spent = _durations(events, ingest).per_bucket
    return TimesView(
        dw=_stat(spent["dw"]),
        sales=_stat(spent["sales"]),
        design=_stat(spent["design"]),
        approver=_stat(spent["approver"]),
        customer=_stat(spent["customer"]),
    )


def _mapping(orders: Sequence[OrderCase]) -> MappingCounts:
    statuses = Counter(line.mapping.status for o in orders for line in o.lines)
    exact = statuses[MappingStatus.EXACT]
    confirmed = statuses[MappingStatus.CANDIDATE_CONFIRMED]
    return MappingCounts(
        convert_list=exact,
        confirmed_candidate=confirmed,
        unresolved=sum(statuses.values()) - exact - confirmed,
    )


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


def _export(events: Sequence[LoggedEvent], kpi: SalesKpi) -> list[ExportRow]:
    """Every surveyed step for every month with activity: the cases DW1 took
    through the step that month (each case once), beside the manual baseline.
    A step DW1 does not do exports with 0, not without a row."""
    cases: dict[tuple[str, str], set[uuid.UUID]] = defaultdict(set)
    for step in WIV_STEPS:
        kind = _PROCEDURE_KIND[step.procedure]
        for event in events:
            # A case is opened already checked: its first event passed
            # through `received` (O1) on the way.
            passed = {event.to_status} | ({"received"} if event.from_status is None else set())
            if event.case_kind is kind and passed & set(step.states):
                cases[(step.step_id, _month(event.occurred_at))].add(event.case_id)
    months = sorted({_month(event.occurred_at) for event in events})
    return [
        ExportRow(
            step_id=step.step_id,
            month=month,
            times=len(cases.get((step.step_id, month), ())),
            manual_baseline_minutes=kpi.manual_baseline_minutes[step.step_id],
        )
        for month in months
        for step in WIV_STEPS
    ]
