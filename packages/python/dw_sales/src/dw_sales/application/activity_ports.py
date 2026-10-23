"""What DW1's step rows are written to and read from, declared by their
consumers (slice 3), apart from the activity service: the services that read
the rows beside their own, the process page and the case lists, would
otherwise import it, and it imports the process page (it places each model
step where the page places its switch).

- `StepActivityLogPort`: where a message's rows are written, a member of every
  `SalesUnitOfWork`, so the rows commit or roll back with what they describe.
- `StepActivityReadPort`: one workspace's rows, read under its RLS.
- `CaseListActivity` / `StepRowFilter`: the case list a count on the activity
  page stands for (its `ActivityFilter`), narrowed to the cases whose rows
  match, read through `StepActivityReadPort.cases`.
- `automatic_share_last_7_days`: the share the process page shows beside each
  model step.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Final, Literal, Protocol

from dw_kernel.errors import DomainError
from dw_sales.application.ports import SalesScope
from dw_sales.domain.activity import StepOutcome, StepResult, tally
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_checks import SALES_TIME_ZONE, ModelStep

# Who carried an item: DW1 (its row is automatic) or a person.
HandledBy = Literal["dw1", "person"]
# The longest window a summary or a case list filter covers, in days, both
# ends included.
MAX_WINDOW_DAYS: Final = 31
# The rolling window of the process page's share.
WEEK: Final = timedelta(days=7)


class StepActivityLogPort(Protocol):
    """Where a message's step rows are written, in its unit of work."""

    async def append(self, rows: Sequence[StepOutcome]) -> None: ...


@dataclass(frozen=True, slots=True)
class StepRowFilter:
    """The rows a case list narrows to: one step's, on cases of ``lane``,
    from ``start`` (included) to ``end`` (excluded), and of the outcome
    named. ``reason_code`` matches an item's own reason or a value refused
    inside it, as the summary counts both (`StepTally.reasons`)."""

    step: ModelStep
    lane: CaseKind
    start: datetime
    end: datetime
    handled_by: HandledBy | None = None
    result: StepResult | None = None
    reason_code: str | None = None

    def matches(self, row: StepOutcome) -> bool:
        return (
            row.step is self.step
            and row.lane is self.lane
            and row.case_id is not None
            and self.start <= row.occurred_at < self.end
            and (self.handled_by is None or row.automatic == (self.handled_by == "dw1"))
            and (self.result is None or row.result == self.result)
            and (
                self.reason_code is None
                or row.reason_code == self.reason_code
                or self.reason_code in row.refusals
            )
        )


class StepActivityReadPort(Protocol):
    """The step rows of one workspace, read under its RLS."""

    async def for_case(
        self, scope: SalesScope, kind: CaseKind, case_id: uuid.UUID
    ) -> Sequence[StepOutcome]:
        """The rows naming the case, oldest first."""
        ...

    async def between(
        self, scope: SalesScope, start: datetime, end: datetime, lane: CaseKind | None
    ) -> Sequence[StepOutcome]:
        """The rows from ``start`` (included) to ``end`` (excluded), of
        ``lane`` when one is given (a row of no lane is then left out)."""
        ...

    async def cases(self, scope: SalesScope, rows: StepRowFilter) -> frozenset[uuid.UUID]:
        """The cases named by a row ``rows`` matches (`StepRowFilter.matches`)."""
        ...


def day_window(start: date, end: date) -> tuple[datetime, datetime]:
    """Local days ``start`` to ``end``, both included, as the instants from
    the first's midnight (included) to the midnight after the last
    (excluded), Asia/Ho_Chi_Minh. Refuses a window backwards or longer than
    `MAX_WINDOW_DAYS`."""
    if start > end or (end - start).days >= MAX_WINDOW_DAYS:
        raise DomainError(
            "the window is from a day to the same or a later day, at most 31 days",
            details={"from": start.isoformat(), "to": end.isoformat()},
        )
    return (
        datetime.combine(start, time.min, tzinfo=SALES_TIME_ZONE),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=SALES_TIME_ZONE),
    )


@dataclass(frozen=True, slots=True)
class CaseListActivity:
    """A case list's activity filter as the request states it: the fields of
    the summary's `ActivityFilter`, every one optional until checked."""

    step: ModelStep | None = None
    handled_by: HandledBy | None = None
    result: StepResult | None = None
    reason_code: str | None = None
    lane: CaseKind | None = None
    start: date | None = None
    end: date | None = None

    def rows(self, kind: CaseKind) -> StepRowFilter | None:
        """The rows a list of ``kind`` narrows to; None when nothing is
        asked. Refuses (422) a filter that names no step or no window, or
        names the other lane: an unnamed part is not read as "any"."""
        if self == CaseListActivity():
            return None
        if self.step is None or self.start is None or self.end is None:
            raise DomainError(
                "an activity filter names the step and the window (from, to)",
                details={"rule": "activity_filter_incomplete"},
            )
        if self.lane is not None and self.lane is not kind:
            raise DomainError(
                "the activity filter is of the other lane",
                details={"rule": "activity_filter_lane", "lane": self.lane.value},
            )
        start, end = day_window(self.start, self.end)
        return StepRowFilter(
            step=self.step,
            lane=kind,
            start=start,
            end=end,
            handled_by=self.handled_by,
            result=self.result,
            reason_code=self.reason_code,
        )


async def activity_cases(
    reader: StepActivityReadPort,
    scope: SalesScope,
    kind: CaseKind,
    activity: CaseListActivity | None,
) -> frozenset[uuid.UUID] | None:
    """The cases of ``kind`` a list keeps under ``activity``; None: the list
    is not narrowed. The caller has already decided the caller may read the
    list."""
    rows = None if activity is None else activity.rows(kind)
    return None if rows is None else await reader.cases(scope, rows)


@dataclass(frozen=True, slots=True)
class StepShare:
    """A step's automatic share over a window: what the process page shows
    beside the step's bar."""

    handled: int
    automatic: int
    # None when the step handled nothing in the window.
    share: float | None


async def automatic_share_last_7_days(
    reader: StepActivityReadPort, scope: SalesScope, *, now: datetime
) -> dict[ModelStep, StepShare]:
    """Each model step's automatic share over the 168 hours before ``now``,
    in ``scope``'s workspace: every step, one that handled nothing with
    ``share`` None. The caller has already decided the caller may read the
    page it shows on (the process page's own gate)."""
    rows = await reader.between(scope, now - WEEK, now, None)
    return {
        step: StepShare(t.handled, t.automatic, t.automatic_share)
        for step, t in tally(rows).items()
    }
