"""One place for a person's day (tickets 47 and 48): today's morning brief and
the reminders DW1 sent them, with what they did with each.

The work waiting on the person is the work list (`OverviewService.my_work`,
each item with its SLA); this module serves the two other parts of the same
page, both read back from what the worker already delivered, so the page
asks nothing slow of a model (ticket 47, "latency: built in the worker"):

- **The brief**: today's, as the follow-ups lane delivered it to this person
  (`FollowupLane._brief`), its model-written opening apart from its counts.
  The opening reached the inbox only after `brief_writing`'s figure check;
  what failed it never left the worker, and the counts are code's.
- **The reminders**: the follow-ups delivered to this person in this
  workspace in the last `FEED_DAYS`, but "your turn" (the work list holds
  that work) and the brief. Each can be marked "Đã xử lý" (done),
  "Không cần" (dismissed) or "Nhắc lại sau" (snoozed for some hours),
  stored for that person (`sales.reminder_marks`).

**Learns, never drops a term.** A follow-up kind the person dismissed more
often ranks lower in their list (dw_sales ADR 0015 decision 5: a person's
answer teaches, scoped to them). A reminder whose deadline is the customer's
own term (`CUSTOMER_TERM`) is never hidden by dismissing or snoozing: the
service refuses the mark, the database's CHECK refuses the row, and a mark
that exists anyway is read as nothing (three layers, one rule).

**One person's.** Everything is read with the caller's own context: the
inbox narrows to the verified principal, the marks table to tenant,
workspace and user, and a notification is marked only when it is among the
caller's own follow-up reminders in this workspace.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ports import UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.followups import (
    BRIEF,
    OPENING_PREFIX,
    SourceKey,
    parse_source_key,
    source_key_prefix,
)
from dw_sales.application.local_time import local_day
from dw_sales.application.overview_ports import FollowupPolicyPort
from dw_sales.domain.followups import CUSTOMER_TERM, Followup

# How far back the feed reads the person's reminders. A reminder older than
# a week has been acted on or escalated; the inbox keeps it for 90 days.
FEED_DAYS: Final = 7
# The most notifications one read takes: far above a week of reminders.
_READ_LIMIT: Final = 300
_RESOURCE: Final = "sales_today"
# The follow-ups the feed lists as reminders: every one but "your turn".
REMINDERS: Final = frozenset(Followup) - {Followup.YOUR_TURN}
_VIEW = ConfigDict(frozen=True)


class Mark(StrEnum):
    DONE = "done"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"


class FollowupNotice(Protocol):
    """A notification the follow-ups lane delivered to this person
    (`dw_platform.application.notifications.SourcedNotification`)."""

    @property
    def id(self) -> uuid.UUID: ...

    @property
    def source_key(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def body(self) -> str: ...

    @property
    def link(self) -> str | None: ...

    @property
    def created_at(self) -> datetime: ...


class FollowupNoticesPort(Protocol):
    """The caller's own notifications keyed under ``prefix`` since ``since``,
    newest first (`SqlNotificationRepository.sourced`)."""

    async def sourced(
        self, context: AccessContext, *, prefix: str, since: datetime, limit: int
    ) -> Sequence[FollowupNotice]: ...


@dataclass(frozen=True, slots=True)
class ReminderMark:
    notification_id: uuid.UUID
    followup: Followup
    mark: Mark
    until: datetime | None
    marked_at: datetime


class ReminderMarkStorePort(Protocol):
    """The caller's own marks in their workspace (RLS by tenant, workspace
    and user)."""

    async def marks(self) -> Sequence[ReminderMark]: ...

    async def put(self, mark: ReminderMark) -> None:
        """The person's mark on one notification, replacing theirs before."""
        ...


ReminderMarkStoreFactory = Callable[
    [AccessContext], AbstractAsyncContextManager[ReminderMarkStorePort]
]


class BriefView(BaseModel):
    model_config = _VIEW

    notification_id: uuid.UUID
    title: str
    # What the model wrote to open the brief, checked before it left the
    # worker; None when the brief is the counts alone.
    opening: str | None
    # Code's counts, one line each: the detail behind a click.
    counts: list[str]
    at: datetime


class ReminderView(BaseModel):
    model_config = _VIEW

    notification_id: uuid.UUID
    followup: str
    stage: str
    # The case it is about, for a deep link to open (the subject of every
    # reminder is a case id).
    case_id: uuid.UUID | None
    title: str
    body: str
    link: str | None
    at: datetime
    # The deadline is the customer's own: never hidden, so only "Đã xử lý"
    # is offered (and accepted).
    customer_term: bool


class TodayView(BaseModel):
    model_config = _VIEW

    brief: BriefView | None
    reminders: list[ReminderView]
    # How many the person's own marks hide just now ("Đã xử lý", "Không
    # cần", or snoozed): said, so a short list never reads as everything.
    hidden: int


class MarkIn(BaseModel):
    """What a person did with a reminder."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mark: Literal["done", "dismissed", "snoozed"]
    # "Nhắc lại sau": in how many hours; only with `snoozed`.
    hours: int | None = Field(default=None, ge=1, le=72)

    @model_validator(mode="after")
    def _hours_only_when_snoozed(self) -> MarkIn:
        if (self.mark == "snoozed") != (self.hours is not None):
            raise ValueError("hours are given with a snooze, and only then")
        return self


def _case_id(key: SourceKey) -> uuid.UUID | None:
    try:
        return uuid.UUID(key.subject)
    except ValueError:
        return None


def _reminder(key: SourceKey | None) -> Followup | None:
    if key is None or key.followup not in REMINDERS:
        return None
    return Followup(key.followup)


def hides(mark: ReminderMark | None, followup: Followup, now: datetime) -> bool:
    """Whether the person's mark keeps a reminder off their list now. A
    customer's term is hidden by "Đã xử lý" alone: dismissing or snoozing it
    never hides it (the floor)."""
    if mark is None:
        return False
    if mark.mark is Mark.DONE:
        return True
    if followup in CUSTOMER_TERM:
        return False
    if mark.mark is Mark.DISMISSED:
        return True
    return mark.until is not None and mark.until > now


def rank(
    reminders: Sequence[tuple[FollowupNotice, SourceKey, Followup]],
    marks: Sequence[ReminderMark],
    now: datetime,
) -> tuple[list[tuple[FollowupNotice, SourceKey, Followup]], int]:
    """The reminders the person sees, in order, and how many their marks hide.

    A customer's term first; then the kinds this person dismissed least
    (what they keep answering "Không cần" to sinks, never vanishes); then
    the newest."""
    by_id: Mapping[uuid.UUID, ReminderMark] = {m.notification_id: m for m in marks}
    dismissed = Counter(m.followup for m in marks if m.mark is Mark.DISMISSED)
    shown = [r for r in reminders if not hides(by_id.get(r[0].id), r[2], now)]
    shown.sort(
        key=lambda r: (
            0 if r[2] in CUSTOMER_TERM else 1,
            dismissed[r[2]],
            -r[0].created_at.timestamp(),
        )
    )
    return shown, len(reminders) - len(shown)


def brief_view(notice: FollowupNotice) -> BriefView:
    body = notice.body
    opening: str | None = None
    if body.startswith(OPENING_PREFIX):
        opening, _, body = body[len(OPENING_PREFIX) :].partition("\n\n")
    return BriefView(
        notification_id=notice.id,
        title=notice.title,
        opening=opening or None,
        counts=[line for line in body.splitlines() if line.strip()],
        at=notice.created_at,
    )


@dataclass(frozen=True)
class TodayService:
    gate: Gate
    clock: UtcClock
    notices: FollowupNoticesPort
    marks: ReminderMarkStoreFactory
    # The tenant's time zone, from its follow-up timings: "today" is its day.
    followups: FollowupPolicyPort

    async def _mine(self, context: AccessContext, now: datetime) -> Sequence[FollowupNotice]:
        return await self.notices.sourced(
            context,
            prefix=source_key_prefix(context.workspace_id),
            since=now - timedelta(days=FEED_DAYS),
            limit=_READ_LIMIT,
        )

    async def today(self, context: AccessContext) -> TodayView:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)
        now = self.clock.now()
        policy = await self.followups.followups(sales_scope(context))
        day = local_day(now, policy.working_hours.zone).isoformat()
        notices = await self._mine(context, now)
        async with self.marks(context) as store:
            marks = await store.marks()
        brief: BriefView | None = None
        reminders: list[tuple[FollowupNotice, SourceKey, Followup]] = []
        for notice in notices:
            key = parse_source_key(notice.source_key)
            if key is None or key.workspace_id != context.workspace_id:
                continue
            if key.followup == BRIEF:
                if brief is None and key.subject == day:
                    brief = brief_view(notice)
                continue
            followup = _reminder(key)
            if followup is not None:
                reminders.append((notice, key, followup))
        shown, hidden = rank(reminders, marks, now)
        return TodayView(
            brief=brief,
            reminders=[
                ReminderView(
                    notification_id=notice.id,
                    followup=key.followup,
                    stage=key.stage,
                    case_id=_case_id(key),
                    title=notice.title,
                    body=notice.body,
                    link=notice.link,
                    at=notice.created_at,
                    customer_term=followup in CUSTOMER_TERM,
                )
                for notice, key, followup in shown
            ],
            hidden=hidden,
        )

    async def mark(self, context: AccessContext, notification_id: uuid.UUID, body: MarkIn) -> None:
        """The caller's mark on one of their own reminders. Someone else's,
        or one that is not a reminder in this workspace, is not found."""
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)
        now = self.clock.now()
        found = next((n for n in await self._mine(context, now) if n.id == notification_id), None)
        key = parse_source_key(found.source_key) if found is not None else None
        followup = _reminder(key)
        if key is None or followup is None or key.workspace_id != context.workspace_id:
            raise NotFoundError(
                "no such reminder", details={"notification_id": str(notification_id)}
            )
        mark = Mark(body.mark)
        if followup in CUSTOMER_TERM and mark is not Mark.DONE:
            raise ConflictError(
                "nhắc theo hạn của khách không ẩn được; khi đã xử lý, bấm 'Đã xử lý'",
                details={"reason": "customer_term", "followup": followup.value},
            )
        until = now + timedelta(hours=body.hours) if body.hours is not None else None
        async with self.marks(context) as store:
            await store.put(ReminderMark(notification_id, followup, mark, until, now))
