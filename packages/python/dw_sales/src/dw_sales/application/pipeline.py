"""The pipeline: every case of a workspace laid out by status, and one case's
history (`sales.case.read`).

**Board.** A column per status, in the order a case moves through them (the
status enums' own order), each with whose turn it is (`STATUS_BUCKETS`, the
overview's fact) and the surveyed steps it stands for (`WIV_STEPS`). A card is
a case: its reference, customer, assignee, when it entered its status (the
case's own events, as the follow-ups read it), its due date and the flags its
list row already carries. A case that waits on nobody (confirmed, closed,
recorded, declined) is shown for `DONE_WINDOW` after it got there; older ones
are only counted.

What makes the board differ per person is ``my_action``: the caller's next
step on the case, read from their work list (`OverviewService.my_work`), the
one place that decides who takes a step (the assignee, any cross-checker who
made none of the case, any approver who did not price it). Nothing here
decides it a second time, and an action shown is still refused by the step's
own route when the caller may not take it.

**History.** The case's events, oldest first: what was done, the status move,
a person's id or the worker, the reason code. No document, no amount.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from dw_kernel.ports import UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.overview_ports import Bucket
from dw_sales.application.overview_service import (
    PROCEDURE_KIND,
    STATUS_BUCKETS,
    OverviewService,
)
from dw_sales.application.quotes_service import local_day
from dw_sales.application.support import stored_order, stored_quote
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderStatus
from dw_sales.domain.process import WIV_STEPS
from dw_sales.domain.quotes import QuoteStatus

_VIEW = ConfigDict(frozen=True)
# How long a case that waits on nobody stays on the board.
DONE_WINDOW: Final = timedelta(days=7)
# Each kind's statuses, in the order a board shows them (the enum's).
CASE_STATUSES: Final[Mapping[CaseKind, type[StrEnum]]] = {
    CaseKind.ORDER: OrderStatus,
    CaseKind.QUOTE: QuoteStatus,
}


class PipelineColumn(BaseModel):
    model_config = _VIEW

    kind: Literal["order", "quote"]
    status: str
    # Whose turn a case here is; None when it waits on nobody.
    holder: Bucket | None
    # The surveyed steps (O1..O11, Q1..Q12) this status stands for.
    steps: list[str]
    cases: int
    # Done cases older than `DONE_WINDOW`: counted, not carded.
    hidden: int


class PipelineCard(BaseModel):
    model_config = _VIEW

    kind: Literal["order", "quote"]
    case_id: uuid.UUID
    status: str
    reference: str
    customer_code: str
    assigned_to: uuid.UUID | None
    received_at: datetime
    status_since: datetime
    due: date | None
    overdue: bool
    open_findings: int
    blocking_findings: int
    awaits_cross_check: bool
    # The caller's next step on this case, from their work list; None when
    # the case is not theirs to move now.
    my_action: str | None


class PipelineView(BaseModel):
    model_config = _VIEW

    as_of: datetime
    columns: list[PipelineColumn]
    cards: list[PipelineCard]


class CaseHistoryEntry(BaseModel):
    model_config = _VIEW

    case_version: int
    action: str
    from_status: str | None
    to_status: str
    actor_kind: Literal["worker", "user"]
    # The person, for a user's event; None for a worker's.
    actor_user_id: uuid.UUID | None
    worker_id: str | None
    reason_code: str | None
    occurred_at: datetime


def steps_at(kind: CaseKind, status: str) -> list[str]:
    """The surveyed steps a case of ``kind`` is at while in ``status``."""
    return [
        step.step_id
        for step in WIV_STEPS
        if PROCEDURE_KIND[step.procedure] is kind and status in step.states
    ]


def _actor(
    event_actor: str | None, kind: Literal["worker", "user"]
) -> tuple[uuid.UUID | None, str | None]:
    """A stored actor id as (person, worker): ``svc|<worker>`` or a user id."""
    if event_actor is None:
        return None, None
    if kind == "worker":
        return None, event_actor.removeprefix("svc|")
    try:
        return uuid.UUID(event_actor), None
    except ValueError:
        return None, None


@dataclass(frozen=True)
class PipelineService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    # The work list: the one owner of "whose step is this".
    work: OverviewService

    async def board(self, context: AccessContext) -> PipelineView:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type="sales_pipeline")
        now = self.clock.now()
        today = local_day(now)
        mine = await self._mine(context)
        everything = {
            kind: frozenset(s.value for s in enum) for kind, enum in CASE_STATUSES.items()
        }
        async with self.uow(sales_scope(context)) as work:
            orders = await work.orders.list_all()
            quotes = await work.quotes.list_all()
            waiting = await work.followups.cases(everything, received_since=now)
        found = {(w.kind, w.case_id): w for w in waiting}

        cards: list[PipelineCard] = []
        hidden: dict[tuple[CaseKind, str], int] = {}

        def place(card: PipelineCard, kind: CaseKind) -> None:
            if card.status not in STATUS_BUCKETS[kind] and now - card.status_since > DONE_WINDOW:
                key = (kind, card.status)
                hidden[key] = hidden.get(key, 0) + 1
            else:
                cards.append(card)

        for stored in orders:
            order = stored.case
            w = found.get((CaseKind.ORDER, order.case_id))
            if w is None:  # written after the read above
                continue
            open_findings = [f for f in order.findings if f.is_open]
            due = order.due
            place(
                PipelineCard(
                    kind="order",
                    case_id=order.case_id,
                    status=order.status.value,
                    reference=w.reference,
                    customer_code=w.customer_code,
                    assigned_to=stored.origin.assigned_to,
                    received_at=w.received_at,
                    status_since=w.status_since,
                    due=due,
                    overdue=due is not None
                    and due < today
                    and order.status.value in STATUS_BUCKETS[CaseKind.ORDER],
                    open_findings=len(open_findings),
                    blocking_findings=sum(1 for f in open_findings if f.blocking),
                    awaits_cross_check=order.awaits_cross_check,
                    my_action=mine.get(("order", str(order.case_id))),
                ),
                CaseKind.ORDER,
            )
        for held in quotes:
            quote = held.case
            w = found.get((CaseKind.QUOTE, quote.case_id))
            if w is None:
                continue
            place(
                PipelineCard(
                    kind="quote",
                    case_id=quote.case_id,
                    status=quote.status.value,
                    reference=w.reference,
                    customer_code=w.customer_code,
                    assigned_to=held.origin.assigned_to,
                    received_at=w.received_at,
                    status_since=w.status_since,
                    due=w.due,
                    overdue=quote.is_overdue(today),
                    open_findings=sum(1 for f in quote.findings if f.is_open),
                    blocking_findings=0,
                    awaits_cross_check=False,
                    my_action=mine.get(("quote", str(quote.case_id))),
                ),
                CaseKind.QUOTE,
            )

        # Longest in its status first: what has waited longest is read first.
        cards.sort(key=lambda c: (c.status_since, str(c.case_id)))
        shown: dict[tuple[str, str], int] = {}
        for card in cards:
            shown[(card.kind, card.status)] = shown.get((card.kind, card.status), 0) + 1
        columns = [
            PipelineColumn(
                kind=kind.value,
                status=status.value,
                holder=STATUS_BUCKETS[kind].get(status.value),
                steps=steps_at(kind, status.value),
                cases=shown.get((kind.value, status.value), 0)
                + hidden.get((kind, status.value), 0),
                hidden=hidden.get((kind, status.value), 0),
            )
            for kind, enum in CASE_STATUSES.items()
            for status in enum
        ]
        return PipelineView(as_of=now, columns=columns, cards=cards)

    async def history(
        self, context: AccessContext, kind: CaseKind, case_id: uuid.UUID
    ) -> list[CaseHistoryEntry]:
        await self.gate.require(
            context,
            SalesScopes.CASE_READ,
            resource_type=f"sales_{kind.value}",
            resource_id=str(case_id),
        )
        async with self.uow(sales_scope(context)) as work:
            # A case of another workspace is not found, never an empty history.
            if kind is CaseKind.ORDER:
                await stored_order(work, case_id)
            else:
                await stored_quote(work, case_id)
            events = await work.overview.history(kind, case_id)
        entries: list[CaseHistoryEntry] = []
        for e in events:
            person, worker = _actor(e.actor_id, e.actor_kind)
            entries.append(
                CaseHistoryEntry(
                    case_version=e.case_version,
                    action=e.action,
                    from_status=e.from_status,
                    to_status=e.to_status,
                    actor_kind=e.actor_kind,
                    actor_user_id=person,
                    worker_id=worker,
                    reason_code=e.reason_code,
                    occurred_at=e.occurred_at,
                )
            )
        return entries

    async def _mine(self, context: AccessContext) -> dict[tuple[str, str], str]:
        """The caller's next step per case, every page of their work list."""
        found: dict[tuple[str, str], str] = {}
        cursor: str | None = None
        while True:
            page = await self.work.my_work(context, cursor=cursor)
            for item in page.items:
                if item.kind != "message":
                    found[(item.kind, item.id)] = item.action
            if page.next_cursor is None:
                return found
            cursor = page.next_cursor
