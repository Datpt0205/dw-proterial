"""What the overview and the work list read, declared by them (ticket 24).

The overview is counts and durations over every case of a workspace, and the
work list is the open cases someone may act on. Both used to load every case,
message and event and count in Python, so a page view read the whole history.
`OverviewReadPort` asks the store for the figures and for one page of work
instead; the PostgreSQL adapter answers with aggregates and a keyset page, and
the facts they are computed against (whose time each status is, which steps
the survey names, which steps the caller may take) are handed down by the
service that owns them, never restated in SQL.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal, Protocol

from dw_kernel.pagination import CursorPosition, Page, PageRequest
from dw_sales.application.case_store import LoggedMessage, Stored
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderStatus
from dw_sales.domain.quotes import QuoteCase

Bucket = Literal["dw", "sales", "design", "approver", "customer"]
BUCKETS: Final[tuple[Bucket, ...]] = ("dw", "sales", "design", "approver", "customer")

# The work list's first sort key for an item without a due date: `date.max`,
# as text that sorts the way the dates do.
NO_DUE: Final = date.max.isoformat()


@dataclass(frozen=True, slots=True)
class SurveyStep:
    """A surveyed step as the export counts it: the case kind and the states
    a case passes through while the step is done."""

    step_id: str
    kind: CaseKind
    states: frozenset[str]


@dataclass(frozen=True, slots=True)
class FigureBasis:
    """What the overview's figures are computed against, from their owners."""

    # Whose time a case's interval in each status is, per case kind.
    buckets: Mapping[CaseKind, Mapping[str, Bucket]]
    # The status a case is "draft ready" (handed to Sales) in, per kind.
    draft_ready: Mapping[CaseKind, str]
    steps: Sequence[SurveyStep]
    # The zone a month is counted in.
    zone: str
    # The mailbox's messages: which of them have a disposition is asked.
    inbox_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class Spread:
    """How many cases, and the median and longest of their seconds."""

    cases: int
    median_seconds: float | None
    max_seconds: float | None


@dataclass(frozen=True, slots=True)
class OverviewFigures:
    """Every number the overview shows, computed by the store."""

    statuses: Mapping[CaseKind, Mapping[str, int]]
    decided_inbox_ids: frozenset[str]
    routed_to_sales: int
    routed_without_owner: int
    times: Mapping[Bucket, Spread]
    order_confirmation: Spread
    quotation_time: Spread
    lines_printed: int
    lines_read: int
    lines_exact: int
    lines_candidate_confirmed: int
    findings_by_code: Mapping[str, int]
    orders_prepared_without_correction: int
    quotes_sent_as_first_drafted: int
    a3_shadow: int
    # Cases taken through each surveyed step, per month, and every month with
    # an event (a step with none that month exports 0).
    export: Mapping[tuple[str, str], int]
    months: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkFilter:
    """Which open cases and messages may be the caller's work: the narrowing
    the store applies, from the rules the service owns. The service decides
    each row again; this only keeps the store from reading the rest."""

    principal_id: uuid.UUID
    # Steps taken by the case's assignee, or anyone eligible while unassigned.
    order_statuses: frozenset[OrderStatus]
    quote_statuses: frozenset[str]
    # Orders awaiting their cross-check, for the service to decide on the case.
    cross_checks: bool
    # Quotations pending approval that the caller did not price.
    approvals: bool
    # Owners whose routed messages are the caller's (the pool included);
    # empty: no message is.
    message_owners: frozenset[str]


@dataclass(frozen=True, slots=True)
class OpenOrder:
    """An open order as the work list reads it, without its document."""

    case_id: uuid.UUID
    status: OrderStatus
    customer_code: str
    received_at: datetime
    assigned_to: uuid.UUID | None


type WorkRow = OpenOrder | Stored[QuoteCase] | LoggedMessage


@dataclass(frozen=True, slots=True)
class WorkEntry:
    """One row of the work list, with where it sorts: (due, received, row id)."""

    position: CursorPosition
    row: WorkRow


class OverviewReadPort(Protocol):
    async def figures(self, basis: FigureBasis) -> OverviewFigures: ...

    async def work_page(self, wanted: WorkFilter, request: PageRequest) -> Page[WorkEntry]:
        """One page of the rows ``wanted`` admits, by (due date or `NO_DUE`,
        received, row id), resuming after ``request.after``."""
        ...
