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
`sales.order.cross_check` who made none of the case, while its approval is
pending; an order whose cross-check nothing is on the way to (ticket 14)
goes to whoever recorded its Bravo entry, to raise it again. An approval
goes to every holder of `sales.quote.approve` who did not price it; every
other step to the case's assignee, and an unassigned case to everyone who
may take the step. Messages routed to Sales go to their owner, or to every
PIC when the owner is the pool.

Neither reads the whole history: the store computes the figures and pages
the work list (`OverviewReadPort`, ticket 24), against the facts this module
owns (whose time each status is, the next step on each status and the scope
that takes it), which it hands down rather than the store restating them.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from dw_kernel.pagination import Page, PageQuery, page_request
from dw_kernel.ports import UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import LoggedMessage, SalesUnitOfWorkFactory, Stored
from dw_sales.application.overview_ports import (
    Bucket,
    FigureBasis,
    OpenOrder,
    OverviewFigures,
    Spread,
    SurveyStep,
    WorkFilter,
)
from dw_sales.application.ports import InboxPort, MemberDirectoryPort, SalesScope
from dw_sales.application.runs import PendingDecisionsPort, awaited
from dw_sales.application.views import WorkerStateView, worker_state
from dw_sales.domain.dispositions import SALES_PIC_POOL, CaseKind, DispositionKind
from dw_sales.domain.kpi import SalesKpi
from dw_sales.domain.orders import OrderCase, OrderStatus
from dw_sales.domain.process import WIV_STEPS, Procedure
from dw_sales.domain.quotes import QuoteCase, QuoteStatus

_VIEW = ConfigDict(frozen=True)
# The zone a month is counted in (giờ Việt Nam).
_LOCAL_ZONE: Final = "Asia/Ho_Chi_Minh"

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


def _stat(spread: Spread) -> TimeStat:
    return TimeStat(
        cases=spread.cases, median_seconds=spread.median_seconds, max_seconds=spread.max_seconds
    )


_BASIS_BUCKETS: Final[Mapping[CaseKind, Mapping[str, Bucket]]] = {
    CaseKind.ORDER: {str(status): bucket for status, bucket in _ORDER_BUCKETS.items()},
    CaseKind.QUOTE: {str(status): bucket for status, bucket in _QUOTE_BUCKETS.items()},
}
_SURVEY: Final = tuple(
    SurveyStep(step.step_id, _PROCEDURE_KIND[step.procedure], frozenset(step.states))
    for step in WIV_STEPS
)


def figure_basis(inbox_ids: frozenset[str]) -> FigureBasis:
    """What the store computes the figures against, from this module's facts."""
    return FigureBasis(
        buckets=_BASIS_BUCKETS,
        draft_ready={kind: str(status) for kind, status in _DRAFT_READY.items()},
        steps=_SURVEY,
        zone=_LOCAL_ZONE,
        inbox_ids=inbox_ids,
    )


# Steps decided on the whole case rather than on its assignee.
_DECIDED_ON_THE_CASE: Final = frozenset({"cross_check", "approve"})
# The page a work list is cut into when the caller names none.
WORK_PAGE: Final = 50


class KpiPort(Protocol):
    """The KPI policy that applies to ``scope``'s tenant."""

    async def kpi(self, scope: SalesScope) -> SalesKpi: ...


@dataclass(frozen=True)
class OverviewService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    inbox: InboxPort
    # The KPI policy in force for the caller's tenant (its own approved
    # version, or the platform's: ticket 19).
    kpi: KpiPort
    directory: MemberDirectoryPort
    decisions: PendingDecisionsPort

    async def overview(self, context: AccessContext) -> OverviewView:
        await self.gate.require(context, SalesScopes.OVERVIEW_READ, resource_type="sales_overview")
        scope = sales_scope(context)
        now = self.clock.now()
        inbox = {m.message_id: m.received_at for m in await self.inbox.list_messages(scope)}
        kpi = await self.kpi.kpi(scope)
        async with self.uow(scope) as work:
            figures = await work.overview.figures(figure_basis(frozenset(inbox)))
            worker = await work.worker.state()
        return OverviewView(
            as_of=now,
            kpi_policy=kpi.version,
            worker=worker_state(worker),
            steps=_steps(figures),
            messages=_messages(inbox, figures, now=now),
            times=TimesView(
                dw=_stat(figures.times["dw"]),
                sales=_stat(figures.times["sales"]),
                design=_stat(figures.times["design"]),
                approver=_stat(figures.times["approver"]),
                customer=_stat(figures.times["customer"]),
            ),
            order_confirmation=TargetView(
                target_seconds=kpi.order_confirmation_target_hours * 3600.0,
                measured=_stat(figures.order_confirmation),
            ),
            quotation_time=TargetView(
                target_seconds=kpi.quotation_target_days * 86400.0,
                measured=_stat(figures.quotation_time),
            ),
            lines_printed=figures.lines_printed,
            lines_read=figures.lines_read,
            mapping=MappingCounts(
                convert_list=figures.lines_exact,
                confirmed_candidate=figures.lines_candidate_confirmed,
                unresolved=figures.lines_read
                - figures.lines_exact
                - figures.lines_candidate_confirmed,
            ),
            findings_by_code=dict(sorted(figures.findings_by_code.items())),
            orders_prepared_without_correction=figures.orders_prepared_without_correction,
            quotes_sent_as_first_drafted=figures.quotes_sent_as_first_drafted,
            a3_shadow=figures.a3_shadow,
            export=[
                ExportRow(
                    step_id=step.step_id,
                    month=month,
                    times=figures.export.get((step.step_id, month), 0),
                    manual_baseline_minutes=kpi.manual_baseline_minutes[step.step_id],
                )
                for month in figures.months
                for step in WIV_STEPS
            ],
        )

    async def my_work(
        self, context: AccessContext, *, limit: int = WORK_PAGE, cursor: str | None = None
    ) -> Page[WorkItem]:
        """One page of the caller's work, by due date then by when it came in.

        The store narrows to the rows these rules could admit and pages them;
        each row is then decided here, so a page can hold fewer items than
        ``limit`` (a cross-check a run is still on its way to raising), and
        ``next_cursor`` alone says whether more follow."""
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type="sales_work")
        scope = sales_scope(context)
        request = page_request(
            limit=limit,
            cursor=cursor,
            query=PageQuery(
                key="sales.my_work",
                filters={
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "principal": context.principal_id,
                },
            ),
        )
        wanted = await self._wanted(context)
        async with self.uow(scope) as work:
            page = await work.overview.work_page(wanted, request)
            # A cross-check is decided on the case itself (who made it, what
            # the run is waiting on): only those are read whole.
            checks: dict[uuid.UUID, Stored[OrderCase] | None] = {}
            for entry in page.items:
                row = entry.row
                if isinstance(row, OpenOrder) and row.status is OrderStatus.UPLOADED_TO_BRAVO:
                    checks[row.case_id] = await work.orders.get(row.case_id)
        items: list[WorkItem] = []
        for entry in page.items:
            row = entry.row
            if isinstance(row, OpenOrder):
                item = await self._order_item(context, row, checks.get(row.case_id))
            elif isinstance(row, LoggedMessage):
                item = _message_item(row, wanted)
            else:
                item = self._quote_item(context, row)
            if item is not None:
                items.append(item)
        return Page(items=tuple(items), next_cursor=page.next_cursor)

    async def _wanted(self, context: AccessContext) -> WorkFilter:
        """The narrowing the store applies, read from the same tables the
        rows are decided by below."""
        owners: frozenset[str] = frozenset()
        if self.gate.allows(context, SalesScopes.INBOX_PROCESS):
            mine = {
                m.email.lower()
                for m in await self.directory.list_members(context)
                if m.user_id == context.principal_id and m.email
            }
            owners = frozenset({SALES_PIC_POOL, *mine})
        return WorkFilter(
            principal_id=context.principal_id,
            order_statuses=frozenset(
                status
                for status, (action, scope) in _ORDER_NEXT.items()
                if action not in _DECIDED_ON_THE_CASE and self.gate.allows(context, scope)
            ),
            quote_statuses=frozenset(
                status.value
                for status, (action, scope) in _QUOTE_NEXT.items()
                if action not in _DECIDED_ON_THE_CASE and self.gate.allows(context, scope)
            ),
            cross_checks=self.gate.allows(context, SalesScopes.ORDER_CROSS_CHECK)
            or self.gate.allows(context, SalesScopes.ORDER_PREPARE),
            approvals=self.gate.allows(context, SalesScopes.QUOTE_APPROVE),
            message_owners=owners,
        )

    def _eligible(
        self, context: AccessContext, scope: SalesScopes, assigned_to: uuid.UUID | None
    ) -> bool:
        if not self.gate.allows(context, scope):
            return False
        return assigned_to is None or assigned_to == context.principal_id

    async def _order_item(
        self, context: AccessContext, row: OpenOrder, stored: Stored[OrderCase] | None
    ) -> WorkItem | None:
        step = _ORDER_NEXT.get(row.status)
        if step is None:
            return None
        action, scope = step
        if action == "cross_check":
            if stored is None:  # gone since the page was read
                return None
            case = stored.case
            wait = await awaited(self.decisions, context, case)
            if wait is not None and wait.stalled:
                # Nothing is on the way to the cross-check: its Bravo recorder
                # raises it again (the head may too, from the order's page).
                if context.principal_id != case.bravo_recorded_by or not self.gate.allows(
                    context, SalesScopes.ORDER_PREPARE
                ):
                    return None
                action = "resend_cross_check"
            elif wait is not None and wait.approval_id is None:
                # A run is on its way to raising it: nothing to decide yet.
                return None
            # Anyone who may cross-check and made none of the case.
            elif not self.gate.allows(context, scope) or context.principal_id in case.makers:
                return None
        elif not self._eligible(context, scope, row.assigned_to):
            return None
        return WorkItem(
            kind="order",
            id=str(row.case_id),
            status=row.status.value,
            action=action,
            customer_code=row.customer_code,
            received_at=row.received_at,
            due=None,
            assigned_to=row.assigned_to,
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


def _message_item(logged: LoggedMessage, wanted: WorkFilter) -> WorkItem | None:
    """A message routed to Sales: its owner's, or every PIC's when the owner
    is the pool."""
    d = logged.disposition
    if d.kind is not DispositionKind.ROUTED_TO_SALES or (
        (d.owner or "").lower() not in wanted.message_owners
    ):
        return None
    return WorkItem(
        kind="message",
        id=d.message_id,
        status=d.kind.value,
        action=f"handle_{d.reason.value if d.reason else 'message'}",
        customer_code=d.customer_code,
        received_at=logged.processed_at,
        due=None,
        assigned_to=None,
    )


def _steps(figures: OverviewFigures) -> list[StepCount]:
    return [
        StepCount(
            step_id=step.step_id,
            procedure=step.procedure.value,
            coverage=step.coverage.value,
            states=list(step.states),
            cases=sum(
                figures.statuses.get(_PROCEDURE_KIND[step.procedure], {}).get(s, 0)
                for s in step.states
            ),
        )
        for step in WIV_STEPS
    ]


def _messages(
    inbox: Mapping[str, datetime], figures: OverviewFigures, *, now: datetime
) -> MessagesView:
    waiting = [
        received
        for message_id, received in inbox.items()
        if message_id not in figures.decided_inbox_ids
    ]
    return MessagesView(
        total=len(inbox),
        without_disposition=len(waiting),
        oldest_waiting_seconds=(now - min(waiting)).total_seconds() if waiting else None,
        routed_to_sales=figures.routed_to_sales,
        routed_without_owner=figures.routed_without_owner,
    )
