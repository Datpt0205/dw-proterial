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
  entered that status; and an order whose answer to the customer's change
  was sent (ticket 29's update loop), from the moment Sales recorded it sent
  until a person records the customer's answer.
- ``waiting_pc``: an order whose delivery dates Sales asked PC for (ticket
  07), from the moment Sales recorded asking, until PC's answer is recorded
  for every line asked (the case then names no request, and nothing is owed);
  and an order whose customer's change was asked of PC (ticket 29), until
  PC's answer is recorded for every changed line.
- ``implied_acceptance``: an order whose confirmation left and whose
  customer has days of silence in the order rules (ticket 28, dw_sales ADR
  0011), once those days have passed with no answer recorded: the PIC is told
  once, and records the customer's agreement (or not). DW1 never records it.
- ``waiting_design_code``: an order whose line Sales asked Design to create a
  PRV code for (ticket 06), from the oldest request still open, until the
  line's code is confirmed or the order leaves review (the domain then names
  no request, and nothing is owed).
- ``waiting_quote``: an order waiting on a quote case opened from it (ticket
  09), from the oldest such link whose quote is still open, while the order
  is before its self-check. Whether the quote is open is its own status,
  read when the cases are read, never a copy on the order.
- ``waiting_pcs_price``: a quote case marked pcs without the GM/BC Manager's
  price recorded (ticket 05), from when it was marked, while it is not yet
  sent. Sales may not price it meanwhile; DW1 never mails the GM.
- ``export_control_hold``: an order held on an open `missing_noc_esf` where
  the export-control PIC may acknowledge it (`OrderCase.awaits_export_control`,
  ticket 78), told once to them as the current PO revision's wait (its
  arrival: the finding is raised when a revision is checked). A finding, not
  a status, so "your turn" cannot see it. Who they are is the lane's to
  resolve (``export_control``, never a tenant's to name on another rule).

``quote_waiting_design`` stops once Design's result was read from Bravo's
YCBG export (`QuoteCase.design_check`, ticket 16): the status stays
`sent_to_design`, but Design has answered (`turn_status`), and the morning
brief counts it as Sales' turn, not Design's.

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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from typing import Final, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderStatus, quote_wait_statuses
from dw_sales.domain.quotes import QuoteStatus

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
# `date.weekday()` order: Monday is 0.
WEEKDAYS: Final[tuple[Weekday, ...]] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# Who is told: the case's assigned Sales PIC, or the head of Sales.
Audience = Literal["pic", "head"]
# Whom a due stage tells: a tenant's audience, or the export-control PIC,
# whom only the export-control hold tells (no rule may name them).
Told = Audience | Literal["export_control"]
_CLOCK = r"^([01]\d|2[0-3]):[0-5]\d$"
_HOURS_LIMIT: Final = 24 * 60  # sixty days


class Followup(StrEnum):
    """The follow-ups the proposal promises."""

    ORDER_UNCONFIRMED = "order_unconfirmed"
    QUOTE_WAITING_DESIGN = "quote_waiting_design"
    QUOTE_DEADLINE = "quote_deadline"
    WAITING_CUSTOMER = "waiting_customer"
    # Sales asked PC for delivery dates and waits (ticket 07).
    WAITING_PC = "waiting_pc"
    # The case has come to a person's turn: told at once, not after a wait
    # (2026-10-28: "nếu dừng thì có noti cho họ thấy chưa").
    YOUR_TURN = "your_turn"
    # A customer's days of silence after a confirmation have passed (ticket 28).
    IMPLIED_ACCEPTANCE = "implied_acceptance"
    # Sales asked Design for a new PRV code and waits (ticket 06).
    WAITING_DESIGN_CODE = "waiting_design_code"
    # An order waits on a quote case opened from it (ticket 09).
    WAITING_QUOTE = "waiting_quote"
    # A pcs quote case waits for the GM/BC Manager's price (ticket 05).
    WAITING_PCS_PRICE = "waiting_pcs_price"
    # An order held on an open NOC/ESF finding waits for the export-control
    # PIC (ticket 78).
    EXPORT_CONTROL_HOLD = "export_control_hold"


class Stage(StrEnum):
    """A step of a follow-up: the first reminder, the escalation after it,
    and the warning before a deadline."""

    REMIND = "remind"
    ESCALATE = "escalate"
    WARN = "warn"
    # Told once, as the wait begins.
    NOTIFY = "notify"


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


class WaitingPcRule(BaseModel):
    """An order whose delivery dates Sales asked PC for, with no answer yet.
    DW1 never mails PC: it reminds the person, who chases PC."""

    model_config = _FROZEN

    enabled: bool = Field(description="Bật hoặc tắt nhắc hồ sơ đang chờ PC trả ngày giao.")
    remind: AfterStage = Field(
        description="Nhắc khi đã hỏi PC mà chưa ghi được ngày PC trả lời sau số giờ này."
    )


class WaitingDesignCodeRule(BaseModel):
    """An order line Sales asked Design to create a PRV code for, with no
    code yet. DW1 never mails Design: it reminds the person, who chases."""

    model_config = _FROZEN

    enabled: bool = Field(description="Bật hoặc tắt nhắc đơn hàng đang chờ Design tạo mã.")
    remind: AfterStage = Field(
        description="Nhắc khi đã đề nghị Design tạo mã mà sau số giờ này dòng vẫn chưa có mã."
    )


class WaitingQuoteRule(BaseModel):
    """An order waiting on a quote case opened from it, not yet approved or
    declined: the order cannot be prepared meanwhile."""

    model_config = _FROZEN

    enabled: bool = Field(description="Bật hoặc tắt nhắc đơn hàng đang chờ báo giá mở từ đơn.")
    remind: AfterStage = Field(
        description="Nhắc khi báo giá mở từ đơn chưa được duyệt hoặc từ chối sau số giờ này."
    )


class WaitingPcsPriceRule(BaseModel):
    """A quote case marked pcs whose GM/BC Manager price is not recorded:
    Sales may not price it meanwhile (ticket 05)."""

    model_config = _FROZEN

    enabled: bool = Field(description="Bật hoặc tắt nhắc báo giá hàng pcs đang chờ giá GM.")
    remind: AfterStage = Field(
        description="Nhắc khi báo giá đã đánh dấu pcs mà sau số giờ này chưa ghi giá GM."
    )


class ExportControlHoldRule(BaseModel):
    """An order held on an open NOC/ESF finding: tell the export-control PIC
    at once, the holders of the scope that acknowledges it (ticket 78)."""

    model_config = _FROZEN

    enabled: bool = Field(
        description=(
            "Bật hoặc tắt báo ngay cho người phụ trách kiểm soát xuất khẩu khi đơn hàng thiếu "
            "NOC/ESF chờ họ xác nhận (chưa ai được giao quyền này thì báo Trưởng bộ phận)."
        )
    )


class ImpliedAcceptanceRule(BaseModel):
    """A customer's days of silence after the confirmation have passed (the
    days are the customer's, in the order rules): DW1 records the agreement
    itself and tells the PIC once, who may undo it with one press (ticket 82,
    dw_sales ADR 0011 amendment); with ``record`` off, the PIC records it."""

    model_config = _FROZEN

    enabled: bool = Field(
        description=(
            "Bật hoặc tắt báo cho Sales phụ trách khi khách im lặng quá số ngày được coi là "
            "đồng ý (số ngày của từng khách đặt trong quy tắc kiểm tra PO)."
        )
    )
    # True: DW1 records the silence as agreement (internal, undone by one
    # press); a version written before ticket 82 reads as the platform's.
    record: bool = Field(
        default=True,
        description=(
            "DW1 tự ghi khách đồng ý ngầm khi quá số ngày im lặng, rồi báo Sales phụ trách; "
            "Sales hoàn tác được bằng một nút."
        ),
    )


class YourTurnRule(BaseModel):
    """A case DW1 has done its part on, now waiting on a person: tell them at
    once. The assignee for a step on their own case, the head for one decided
    on the case by someone else (a cross-check, an approval); nobody while
    DW1, Design or the customer holds it (those have their own reminders)."""

    model_config = _FROZEN

    enabled: bool = Field(description="Bật hoặc tắt báo ngay khi hồ sơ đến lượt người xử lý.")


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
    # The AI list, item 10: on where a model is wired, the brief opens with a
    # few sentences the model wrote; the counts follow either way. Defaults
    # on, so a version written before the field reads as on.
    model_opening: bool = Field(
        default=True,
        description=(
            "DW1 viết đoạn mở đầu: vài câu về việc nên làm trước hôm nay, mọi con số "
            "được kiểm với hồ sơ; số đếm luôn có bên dưới."
        ),
    )

    @field_validator("notify")
    @classmethod
    def _once_each(cls, value: tuple[Audience, ...]) -> tuple[Audience, ...]:
        _distinct(value, "notify")
        return value


class PushRule(BaseModel):
    """What a push to a person's phone may show on the lock screen (ticket
    48). A push only ever names the kind of work and, when this allows, the
    case number: never a price, an amount, a customer's name or their text."""

    model_config = _FROZEN

    case_number: bool = Field(
        description=(
            "Thông báo trên điện thoại ghi số PO hoặc số yêu cầu báo giá; tắt thì chỉ ghi "
            "loại việc (màn hình khóa không lộ số hồ sơ)."
        )
    )


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
    waiting_pc: WaitingPcRule = Field(description="Hồ sơ đang chờ PC trả ngày giao.")
    implied_acceptance: ImpliedAcceptanceRule = Field(
        description="Khách im lặng quá số ngày được coi là đồng ý với xác nhận đơn."
    )
    your_turn: YourTurnRule = Field(description="Hồ sơ đến lượt người xử lý.")
    # 1.6.0 (tickets 06 and 09): a version written before them reads both as
    # the platform's current version has them (`read_over`).
    waiting_design_code: WaitingDesignCodeRule = Field(
        description="Đơn hàng đang chờ Design tạo mã PRV."
    )
    waiting_quote: WaitingQuoteRule = Field(description="Đơn hàng đang chờ báo giá mở từ đơn.")
    # 1.7.0 (ticket 05): a version written before it reads it as the
    # platform's current version has it (`read_over`).
    waiting_pcs_price: WaitingPcsPriceRule = Field(
        description="Báo giá hàng pcs đang chờ giá GM/BC Manager."
    )
    # 1.8.0 (ticket 78): a version written before it reads it as the
    # platform's current version has it (`read_over`).
    export_control_hold: ExportControlHoldRule = Field(
        description="Đơn hàng thiếu NOC/ESF chờ người phụ trách kiểm soát xuất khẩu."
    )
    # 1.5.0 (ticket 48): a version written before the field shows the number,
    # as every push before it would have.
    push: PushRule = Field(
        default=PushRule(case_number=True),
        description="Thông báo đẩy đến điện thoại của người xử lý.",
    )

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
    # When Sales recorded asking PC for the dates, while the order waits on
    # PC (`OrderCase.pc_request`, or its update loop's PC step, ticket 29);
    # None otherwise (ticket 07).
    pc_asked_at: datetime | None = None
    # When Sales recorded the answer to a customer's change sent, while the
    # update loop waits on the customer (ticket 29); None otherwise.
    customer_asked_at: datetime | None = None
    # When the customer's silence after the confirmation counts as agreement
    # (`ConfirmationSent.implied_from`), while the order waits on their
    # answer; None for a customer with no days, or any other status.
    implied_from: datetime | None = None
    # When Sales recorded the oldest request to Design still open
    # (`OrderCase.design_requests`); None while no line waits (ticket 06).
    design_asked_at: datetime | None = None
    # When the oldest quote case opened from the order and still open was
    # opened (`OrderCase.quote_links`, the quote's own status); None while
    # every linked quote is settled or none is (ticket 09).
    quote_open_since: datetime | None = None
    # Design's result was read from Bravo's YCBG export onto the quote case
    # (`QuoteCase.design_check`, ticket 16).
    design_checked: bool = False
    # When a quote case was marked pcs, while its GM price is not recorded
    # (`QuoteCase.waits_on_pcs_price`, ticket 05); None otherwise.
    pcs_price_asked_at: datetime | None = None
    # The order awaits the export-control PIC (`OrderCase.awaits_export_control`,
    # ticket 78); its wait is the current revision's, from ``received_at``.
    export_held: bool = False


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


def turn_status(case: WaitingCase) -> str:
    """The status whose turn ``case`` is in: its own, except a quote whose
    Design result was read from Bravo's YCBG export (ticket 16), which is
    Design's answer though the status stays `sent_to_design`, and so is
    `design_replied`'s turn. The chase (`owed`) and the brief's "what waits
    on whom" both read this, so they never disagree on whether Design is
    still awaited."""
    if case.kind is CaseKind.QUOTE and case.status in _WAITING_DESIGN and case.design_checked:
        return QuoteStatus.DESIGN_REPLIED.value
    return case.status


@dataclass(frozen=True, slots=True)
class Due:
    """One stage of one follow-up owed on one case: sent once per wait."""

    case: WaitingCase
    followup: Followup
    stage: Stage
    # When the wait began: the episode the stage is owed for.
    since: datetime
    notify: tuple[Told, ...]


def due_soon(due: date, today: date, policy: SalesFollowups) -> bool:
    """Whether a case due on ``due`` is "sắp đến hạn" on ``today`` (the
    tenant's day): not past, and within `morning_brief.due_within_days`. The
    one meaning of it: the brief counts by it, and the work list and the
    quote page show the flag it gives, holding no threshold of their own
    (hardcode audit, finding 15)."""
    return today <= due and due.toordinal() <= today.toordinal() + (
        policy.morning_brief.due_within_days
    )


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


def pc_reminder_at(policy: SalesFollowups, asked_at: datetime) -> datetime | None:
    """When the reminder of a wait on PC begun at ``asked_at`` falls due, or
    None while the tenant has it off: what the order page shows beside the
    wait, from the same rule `owed` reads (quiet hours may defer it)."""
    pc = policy.waiting_pc
    return asked_at + timedelta(hours=pc.remind.after_hours) if pc.enabled else None


# The follow-ups whose deadline is the customer's own term (the quote due
# date they asked for; their days of silence after a confirmation): a person
# may be reminded of them, never spared them. "Nhắc lại sau" and "Không cần"
# never hide one, however often the person dismissed its like (ticket 47,
# acceptance 1; dw_sales ADR 0015 decision 6: guards stay code).
CUSTOMER_TERM: Final = frozenset({Followup.QUOTE_DEADLINE, Followup.IMPLIED_ACCEPTANCE})


@dataclass(frozen=True, slots=True)
class Sla:
    """When a waiting item is late, and when it starts being about to be.

    Read from the follow-ups the tenant configured, so the countdown a person
    sees and the reminder and escalation the lane sends are one rule: an
    order unconfirmed is warned at its first reminder and late at its
    escalation to the head; a quote request is warned at its deadline warning
    and late at the end of its due day."""

    warn_at: datetime
    due_at: datetime


def sla_of(
    policy: SalesFollowups,
    kind: CaseKind,
    status: str,
    *,
    received_at: datetime,
    due: date | None,
) -> Sla | None:
    """The SLA of a case in ``status``, or None where no follow-up the tenant
    has switched on times it (the case is not late by any rule of theirs)."""
    if kind is CaseKind.ORDER:
        orders = policy.order_unconfirmed
        if not orders.enabled or status not in _ORDER_UNCONFIRMED:
            return None
        return Sla(
            warn_at=received_at + timedelta(hours=orders.remind.after_hours),
            due_at=received_at + timedelta(hours=orders.escalate.after_hours),
        )
    deadline = policy.quote_deadline
    if not deadline.enabled or due is None or status not in _BEFORE_SENT:
        return None
    late = deadline_of(due, policy.working_hours)
    return Sla(warn_at=late - timedelta(hours=deadline.warn.hours_before_due), due_at=late)


def owed(
    policy: SalesFollowups,
    cases: Sequence[WaitingCase],
    now: datetime,
    *,
    turns: Mapping[CaseKind, Mapping[str, Audience]] | None = None,
) -> list[Due]:
    """Every stage whose threshold has passed at ``now``, on every case, for
    every follow-up switched on. Quiet hours are not this function's: what is
    owed stays owed until it is sent or the case stops waiting.

    ``turns``: whom a case waits on in each status, per kind (the overview's
    `whose_turn`); with none, no "your turn" is owed."""
    found: list[Due] = []
    for case in cases:
        audience = (turns or {}).get(case.kind, {}).get(case.status)
        if policy.your_turn.enabled and audience is not None:
            found.append(
                Due(case, Followup.YOUR_TURN, Stage.NOTIFY, case.status_since, (audience,))
            )
    orders = policy.order_unconfirmed
    design = policy.quote_waiting_design
    deadline = policy.quote_deadline
    customer = policy.waiting_customer
    implied = policy.implied_acceptance
    for case in cases:
        order = case.kind is CaseKind.ORDER
        if (
            implied.enabled
            and order
            and case.status == OrderStatus.CONFIRMATION_SENT
            and case.implied_from is not None
            and now >= case.implied_from
        ):
            # Told once, to the PIC, as the days run out: the PIC records it.
            found.append(
                Due(case, Followup.IMPLIED_ACCEPTANCE, Stage.NOTIFY, case.implied_from, ("pic",))
            )
        if policy.export_control_hold.enabled and order and case.export_held:
            # Told once per PO revision: a save rewrites the findings, never
            # the revision's arrival.
            found.append(
                Due(
                    case,
                    Followup.EXPORT_CONTROL_HOLD,
                    Stage.NOTIFY,
                    case.received_at,
                    ("export_control",),
                )
            )
        if orders.enabled and order and case.status in _ORDER_UNCONFIRMED:
            found += _after(
                case,
                Followup.ORDER_UNCONFIRMED,
                ((Stage.REMIND, orders.remind), (Stage.ESCALATE, orders.escalate)),
                case.received_at,
                now,
            )
        # Design answered in Bravo's YCBG (ticket 16): nothing to chase.
        if design.enabled and not order and turn_status(case) in _WAITING_DESIGN:
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
        code = policy.waiting_design_code
        if code.enabled and order and case.design_asked_at is not None:
            found += _after(
                case,
                Followup.WAITING_DESIGN_CODE,
                ((Stage.REMIND, code.remind),),
                case.design_asked_at,
                now,
            )
        quote = policy.waiting_quote
        if (
            quote.enabled
            and order
            and case.status in quote_wait_statuses()
            and case.quote_open_since is not None
        ):
            found += _after(
                case,
                Followup.WAITING_QUOTE,
                ((Stage.REMIND, quote.remind),),
                case.quote_open_since,
                now,
            )
        pcs = policy.waiting_pcs_price
        if (
            pcs.enabled
            and not order
            and case.status in _BEFORE_SENT
            and case.pcs_price_asked_at is not None
        ):
            found += _after(
                case,
                Followup.WAITING_PCS_PRICE,
                ((Stage.REMIND, pcs.remind),),
                case.pcs_price_asked_at,
                now,
            )
        pc = policy.waiting_pc
        if pc.enabled and order and case.pc_asked_at is not None:
            found += _after(
                case, Followup.WAITING_PC, ((Stage.REMIND, pc.remind),), case.pc_asked_at, now
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
        elif customer.enabled and order and case.customer_asked_at is not None:
            found += _after(
                case,
                Followup.WAITING_CUSTOMER,
                ((Stage.REMIND, customer.remind),),
                case.customer_asked_at,
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
