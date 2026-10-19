"""`sales_followups`: when DW1 reminds a person, and whom (ticket 42).

The proposal promises four follow-ups and a morning brief. Every timing in
them is the customer's to change, so none is a constant here: each is a field
of `SalesFollowups`, versioned in ``configs/policies/sales_followups@<v>.yaml``
and overridable per tenant like every Sales rule (`RuleKey.FOLLOWUPS`).

**A reminder informs, it never decides.** It is an in-app notification to a
member of the workspace: DW1 never mails the customer or Design, and nothing
on a case changes because a reminder went out. The person decides.

**What each follow-up watches** (the case statuses are `OrderStatus` and
`QuoteStatus`; the clock each one reads is named):

- ``order_unconfirmed``: an order Sales has not confirmed yet, from the moment
  its PO (its current revision) arrived. Not while it waits on the customer:
  that is ``waiting_customer``'s.
- ``quote_waiting_design``: a quote request sent to Design (BP code, spec),
  from the moment it entered that status.
- ``quote_deadline``: a quote request not yet sent to the customer whose
  quote due date is near, counted to the end of the due day, local time.
- ``waiting_customer``: an order whose correction was asked of the customer,
  or a quote whose spec is being discussed with them, from the moment it
  entered that status.

**One wait, one reminder per stage.** A stage is due when its threshold has
passed; it is sent once per (case, follow-up, stage, wait), the wait being
the instant its clock started (`Due.since`): a case that comes back to the
same wait later is a new wait.

**Quiet hours defer, never drop.** Outside the working days and hours a due
stage is not sent; it stays due, and the first tick inside working hours
sends it, unless the case stopped waiting in between (then nothing is owed).
The morning brief is sent at its own local time on a working day, which may
be before working hours start.

Validated narrowly (failure-modes #7): no field has a default, a time is
``HH:MM`` text (a bare ``07:30`` in YAML is a number), a time zone must load,
and a later stage must come after an earlier one.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from typing import Final, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderStatus
from dw_sales.domain.quotes import QuoteStatus

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
# `date.weekday()` order: Monday is 0.
WEEKDAYS: Final[tuple[Weekday, ...]] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# Who is told: the case's assigned Sales PIC, or the head of Sales.
Audience = Literal["pic", "head"]
_CLOCK = r"^([01]\d|2[0-3]):[0-5]\d$"
_HOURS_LIMIT: Final = 24 * 60  # sixty days


class Followup(StrEnum):
    """The follow-ups the proposal promises."""

    ORDER_UNCONFIRMED = "order_unconfirmed"
    QUOTE_WAITING_DESIGN = "quote_waiting_design"
    QUOTE_DEADLINE = "quote_deadline"
    WAITING_CUSTOMER = "waiting_customer"


class Stage(StrEnum):
    """A step of a follow-up: the first reminder, the escalation after it,
    and the warning before a deadline."""

    REMIND = "remind"
    ESCALATE = "escalate"
    WARN = "warn"


def _distinct(values: tuple[str, ...], what: str) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError(f"{what} lists a value twice")
    return values


def clock_time(text: str) -> time:
    """``HH:MM`` as a time of day (validated by the field's pattern)."""
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))


class AfterStage(BaseModel):
    """A stage that is due once a wait has lasted a number of hours."""

    model_config = _FROZEN

    after_hours: int = Field(
        gt=0,
        le=_HOURS_LIMIT,
        description=(
            "Sau bao nhiêu giờ chờ thì gửi nhắc (giờ đồng hồ, tính cả ngoài giờ làm việc; "
            "ngoài giờ làm việc thì nhắc được hoãn đến đầu giờ làm việc tiếp theo)."
        ),
    )
    notify: tuple[Audience, ...] = Field(
        min_length=1,
        max_length=2,
        description=(
            "Ai được nhắc: 'pic' là Sales phụ trách hồ sơ (hồ sơ chưa phân công thì nhắc "
            "Trưởng bộ phận), 'head' là Trưởng bộ phận Sales."
        ),
    )

    @field_validator("notify")
    @classmethod
    def _once_each(cls, value: tuple[Audience, ...]) -> tuple[Audience, ...]:
        _distinct(value, "notify")
        return value


class BeforeStage(BaseModel):
    """A stage that is due a number of hours before a deadline."""

    model_config = _FROZEN

    hours_before_due: int = Field(
        gt=0,
        le=_HOURS_LIMIT,
        description=(
            "Báo trước hạn báo giá bao nhiêu giờ (hạn tính đến hết ngày hạn, giờ địa phương)."
        ),
    )
    notify: tuple[Audience, ...] = Field(
        min_length=1,
        max_length=2,
        description="Ai được báo: 'pic' là Sales phụ trách hồ sơ, 'head' là Trưởng bộ phận Sales.",
    )

    @field_validator("notify")
    @classmethod
    def _once_each(cls, value: tuple[Audience, ...]) -> tuple[Audience, ...]:
        _distinct(value, "notify")
        return value


class OrderUnconfirmedRule(BaseModel):
    """A PO not yet confirmed: remind the PIC, then tell the head."""

    model_config = _FROZEN

    enabled: bool = Field(description="Bật hoặc tắt nhắc PO chưa xác nhận.")
    remind: AfterStage = Field(
        description="Nhắc lần đầu, tính từ lúc PO (bản sửa đổi hiện tại) đến."
    )
    escalate: AfterStage = Field(
        description=(
            "Báo lên khi PO vẫn chưa được xác nhận, tính từ lúc PO đến; phải sau lần nhắc đầu."
        )
    )

    @model_validator(mode="after")
    def _escalation_comes_later(self) -> Self:
        if self.escalate.after_hours <= self.remind.after_hours:
            raise ValueError("the escalation comes after the first reminder")
        return self


class QuoteWaitingDesignRule(BaseModel):
    """A quote request waiting on Design's BP code and spec."""

    model_config = _FROZEN

    enabled: bool = Field(description="Bật hoặc tắt nhắc yêu cầu báo giá đang chờ Design.")
    remind: AfterStage = Field(description="Nhắc khi hồ sơ chờ Design quá số giờ này.")


class QuoteDeadlineRule(BaseModel):
    """A quote request whose due date is near and that is not yet sent."""

    model_config = _FROZEN

    enabled: bool = Field(description="Bật hoặc tắt báo hạn báo giá sắp đến.")
    warn: BeforeStage = Field(description="Báo khi còn ít hơn số giờ này đến hạn báo giá.")


class WaitingCustomerRule(BaseModel):
    """A case waiting on the customer (a correction or a spec asked of them).
    DW1 never mails the customer: it reminds the person, who decides."""

    model_config = _FROZEN

    enabled: bool = Field(description="Bật hoặc tắt nhắc hồ sơ đang chờ khách hàng.")
    remind: AfterStage = Field(
        description="Nhắc khi hồ sơ chờ khách (sửa PO, thống nhất spec) quá số giờ này."
    )


class WorkingHours(BaseModel):
    """When a reminder may be delivered; outside them it waits."""

    model_config = _FROZEN

    time_zone: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z_]+(/[A-Za-z0-9_+-]+)*$",
        description="Múi giờ của công ty (tên IANA, ví dụ Asia/Ho_Chi_Minh).",
    )
    days: tuple[Weekday, ...] = Field(
        min_length=1,
        max_length=7,
        description="Ngày làm việc: mon, tue, wed, thu, fri, sat, sun.",
    )
    start: str = Field(pattern=_CLOCK, description="Giờ bắt đầu làm việc, HH:MM, giờ địa phương.")
    end: str = Field(
        pattern=_CLOCK,
        description="Giờ kết thúc làm việc, HH:MM, giờ địa phương; sau giờ bắt đầu.",
    )

    @field_validator("time_zone")
    @classmethod
    def _zone_loads(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("not a time zone this host knows") from None
        return value

    @field_validator("days")
    @classmethod
    def _each_day_once(cls, value: tuple[Weekday, ...]) -> tuple[Weekday, ...]:
        _distinct(value, "days")
        return value

    @model_validator(mode="after")
    def _start_before_end(self) -> Self:
        if clock_time(self.start) >= clock_time(self.end):
            raise ValueError("working hours start before they end")
        return self

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.time_zone)

    def is_working_day(self, day: date) -> bool:
        return WEEKDAYS[day.weekday()] in self.days

    def is_open(self, now: datetime) -> bool:
        """Whether ``now`` is inside working hours: a working day, from
        ``start`` (included) to ``end`` (excluded), local time."""
        local = now.astimezone(self.zone)
        return self.is_working_day(local.date()) and clock_time(
            self.start
        ) <= local.time() < clock_time(self.end)


class MorningBrief(BaseModel):
    """One notification per person each working morning: what came in since
    the last brief and its state, what is due soon, what waits on whom."""

    model_config = _FROZEN

    enabled: bool = Field(description="Bật hoặc tắt bản tóm tắt buổi sáng.")
    at: str = Field(
        pattern=_CLOCK,
        description=(
            "Giờ gửi tóm tắt, HH:MM, giờ địa phương, vào ngày làm việc (có thể trước giờ "
            "bắt đầu làm việc)."
        ),
    )
    notify: tuple[Audience, ...] = Field(
        min_length=1,
        max_length=2,
        description=(
            "Ai nhận: 'pic' là mỗi Sales phụ trách (tóm tắt hồ sơ của mình), 'head' là "
            "Trưởng bộ phận (tóm tắt cả bộ phận)."
        ),
    )
    due_within_days: int = Field(
        gt=0,
        le=30,
        description="Hồ sơ có hạn trong số ngày tới này được tính là 'sắp đến hạn'.",
    )

    @field_validator("notify")
    @classmethod
    def _once_each(cls, value: tuple[Audience, ...]) -> tuple[Audience, ...]:
        _distinct(value, "notify")
        return value


class SalesFollowups(BaseModel):
    """Every timing and switch of DW1's follow-ups and its morning brief."""

    model_config = _FROZEN

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: Literal["sales_followups"]
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    working_hours: WorkingHours = Field(
        description="Giờ làm việc: ngoài giờ này không gửi nhắc, nhắc được hoãn chứ không bỏ."
    )
    morning_brief: MorningBrief = Field(description="Bản tóm tắt buổi sáng.")
    order_unconfirmed: OrderUnconfirmedRule = Field(description="PO chưa được xác nhận.")
    quote_waiting_design: QuoteWaitingDesignRule = Field(
        description="Yêu cầu báo giá đang chờ Design (mã BP, spec)."
    )
    quote_deadline: QuoteDeadlineRule = Field(description="Hạn báo giá sắp đến.")
    waiting_customer: WaitingCustomerRule = Field(description="Hồ sơ đang chờ khách hàng.")

    @property
    def version(self) -> str:
        return f"{self.policy_id}@{self.policy_version}"

    @property
    def ref(self) -> str:
        """``key@x.y.z``, as a tenant's version of it is named."""
        return self.version


# ------------------------------------------------------------ the cases --


@dataclass(frozen=True, slots=True)
class WaitingCase:
    """A case as the follow-ups read it: no document, no line, no amount.

    ``status_since``: when it entered its current status (the case's own
    event log), its arrival when no event says. ``due``: an order's due date
    (`OrderCase.due`) or a quote's due date, when it has one."""

    kind: CaseKind
    case_id: uuid.UUID
    status: str
    reference: str
    customer_code: str
    received_at: datetime
    status_since: datetime
    assigned_to: uuid.UUID | None
    due: date | None


# The statuses each follow-up watches.
_ORDER_UNCONFIRMED: Final = frozenset(
    {
        OrderStatus.RECEIVED,
        OrderStatus.CHECKED,
        OrderStatus.IN_REVIEW,
        OrderStatus.PREPARED,
        OrderStatus.UPLOADED_TO_BRAVO,
        OrderStatus.CROSS_CHECKED,
        OrderStatus.CHANGE_REVIEW,
    }
)
_WAITING_DESIGN: Final = frozenset({QuoteStatus.SENT_TO_DESIGN})
# Not yet sent to the customer.
_BEFORE_SENT: Final = frozenset(
    {
        QuoteStatus.RECEIVED,
        QuoteStatus.YCBG_DRAFTED,
        QuoteStatus.YCBG_RECORDED,
        QuoteStatus.SENT_TO_DESIGN,
        QuoteStatus.DESIGN_REPLIED,
        QuoteStatus.SPEC_DISCUSSION,
        QuoteStatus.PRICED,
        QuoteStatus.PENDING_APPROVAL,
        QuoteStatus.RETURNED,
        QuoteStatus.APPROVED,
    }
)
_ORDER_WAITING_CUSTOMER: Final = frozenset({OrderStatus.CORRECTION_REQUESTED})
_QUOTE_WAITING_CUSTOMER: Final = frozenset({QuoteStatus.SPEC_DISCUSSION})

# Every status a follow-up watches, per kind: what a reader must load.
WATCHED: Final[dict[CaseKind, frozenset[str]]] = {
    CaseKind.ORDER: frozenset(str(s) for s in _ORDER_UNCONFIRMED | _ORDER_WAITING_CUSTOMER),
    CaseKind.QUOTE: frozenset(str(s) for s in _BEFORE_SENT),
}


@dataclass(frozen=True, slots=True)
class Due:
    """One stage of one follow-up owed on one case: sent once per wait."""

    case: WaitingCase
    followup: Followup
    stage: Stage
    # When the wait began: the episode the stage is owed for.
    since: datetime
    notify: tuple[Audience, ...]


def deadline_of(due: date, hours: WorkingHours) -> datetime:
    """The end of the due day, local time: the instant a quote is late."""
    return datetime.combine(due + timedelta(days=1), time(0), tzinfo=hours.zone)


def _after(
    case: WaitingCase,
    followup: Followup,
    stages: Iterable[tuple[Stage, AfterStage]],
    since: datetime,
    now: datetime,
) -> list[Due]:
    return [
        Due(case, followup, stage, since, rule.notify)
        for stage, rule in stages
        if now >= since + timedelta(hours=rule.after_hours)
    ]


def owed(policy: SalesFollowups, cases: Sequence[WaitingCase], now: datetime) -> list[Due]:
    """Every stage whose threshold has passed at ``now``, on every case, for
    every follow-up switched on. Quiet hours are not this function's: what is
    owed stays owed until it is sent or the case stops waiting."""
    found: list[Due] = []
    orders = policy.order_unconfirmed
    design = policy.quote_waiting_design
    deadline = policy.quote_deadline
    customer = policy.waiting_customer
    for case in cases:
        order = case.kind is CaseKind.ORDER
        if orders.enabled and order and case.status in _ORDER_UNCONFIRMED:
            found += _after(
                case,
                Followup.ORDER_UNCONFIRMED,
                ((Stage.REMIND, orders.remind), (Stage.ESCALATE, orders.escalate)),
                case.received_at,
                now,
            )
        if design.enabled and not order and case.status in _WAITING_DESIGN:
            found += _after(
                case,
                Followup.QUOTE_WAITING_DESIGN,
                ((Stage.REMIND, design.remind),),
                case.status_since,
                now,
            )
        if deadline.enabled and not order and case.status in _BEFORE_SENT and case.due is not None:
            late = deadline_of(case.due, policy.working_hours)
            if now >= late - timedelta(hours=deadline.warn.hours_before_due):
                found.append(
                    Due(case, Followup.QUOTE_DEADLINE, Stage.WARN, late, deadline.warn.notify)
                )
        waits = _ORDER_WAITING_CUSTOMER if order else _QUOTE_WAITING_CUSTOMER
        if customer.enabled and case.status in waits:
            found += _after(
                case,
                Followup.WAITING_CUSTOMER,
                ((Stage.REMIND, customer.remind),),
                case.status_since,
                now,
            )
    return found


# ---------------------------------------------------------- the brief --


@dataclass(frozen=True, slots=True)
class BriefSlot:
    """Today's brief: its local day, the instant it is due, and the previous
    working day's slot, from which "what came in" is counted."""

    day: date
    at: datetime
    since: datetime


def brief_slot(policy: SalesFollowups, now: datetime) -> BriefSlot | None:
    """Today's brief if it is due at ``now``: switched on, a working day,
    and its local time has come. Late is still today's (a worker that was
    down sends it when it is back); tomorrow it is tomorrow's."""
    brief, hours = policy.morning_brief, policy.working_hours
    if not brief.enabled:
        return None
    zone = hours.zone
    today = now.astimezone(zone).date()
    if not hours.is_working_day(today):
        return None
    at = datetime.combine(today, clock_time(brief.at), tzinfo=zone)
    if now < at:
        return None
    previous = today - timedelta(days=1)
    for _ in range(6):
        if hours.is_working_day(previous):
            break
        previous -= timedelta(days=1)
    return BriefSlot(today, at, datetime.combine(previous, clock_time(brief.at), tzinfo=zone))
