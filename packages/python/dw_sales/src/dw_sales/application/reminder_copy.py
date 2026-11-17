"""The words of DW1's reminders, morning brief and pushes to Sales staff
(`configs/copy/sales_reminders@<version>.yaml`, ticket 42 family 6).

The follow-ups lane (`dw_sales.application.followups`) decides what is owed,
to whom and when; this copy only says it. Code fills every placeholder from
the case as the lane read it: its number, its customer code, when the wait
began, the tenant's threshold, the due date, counts. Never an amount. The
words reach a member of the workspace only (DW1 never mails a customer or
Design), and a push's words never carry a placeholder at all: a lock screen
shows the kind of work and, where the follow-ups policy allows, the number,
which the lane adds itself (ticket 48).

A tenant's own wording is its version of this copy, proposed and approved
on /sales/rules like every rule version (`RuleKey.REMINDERS`), never an edit
here. A version written before a template existed reads that template as
the platform's current copy has it (`read_over`), so a new kind of reminder
is said in the platform's words until the tenant words it.

Each template names only the placeholders its own reminder fills,
`{name}` and nothing else (`handoffs._plain_placeholders`, the one check of
a template's placeholders): a template naming another is refused when it is
proposed, so nothing reads as a blank or a brace at run time.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Final, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dw_sales.application.handoffs import _named, _plain_placeholders
from dw_sales.application.overview_ports import BUCKETS, Bucket
from dw_sales.application.ports import SalesScope

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# What a reminder's template may name, by what its reminder knows.
_SINCE: Final = frozenset({"ref", "customer", "since"})
_HOURS: Final = _SINCE | {"hours"}
_DUE: Final = frozenset({"ref", "customer", "due"})
_TURN: Final = _SINCE | {"next_step"}
_TITLE_MAX: Final = 200
_BODY_MAX: Final = 1000


class _Reminder(BaseModel):
    """A reminder's title and body; each subclass says what they may name."""

    model_config = _FROZEN
    NAMES: ClassVar[frozenset[str]]

    title: str
    body: str

    @field_validator("title", "body")
    @classmethod
    def _placeholders(cls, value: str) -> str:
        return _plain_placeholders(value, cls.NAMES)


class SinceReminder(_Reminder):
    """``{ref}`` the case's number, ``{customer}`` its customer code,
    ``{since}`` when the wait began (local time)."""

    NAMES: ClassVar[frozenset[str]] = _SINCE
    title: str = Field(min_length=1, max_length=_TITLE_MAX, json_schema_extra=_named(_SINCE))
    body: str = Field(min_length=1, max_length=_BODY_MAX, json_schema_extra=_named(_SINCE))


class HoursReminder(_Reminder):
    """As `SinceReminder`, and ``{hours}``: the tenant's threshold in hours."""

    NAMES: ClassVar[frozenset[str]] = _HOURS
    title: str = Field(min_length=1, max_length=_TITLE_MAX, json_schema_extra=_named(_HOURS))
    body: str = Field(min_length=1, max_length=_BODY_MAX, json_schema_extra=_named(_HOURS))


class DueReminder(_Reminder):
    """``{ref}``, ``{customer}`` and ``{due}``: the quote's due date."""

    NAMES: ClassVar[frozenset[str]] = _DUE
    title: str = Field(min_length=1, max_length=_TITLE_MAX, json_schema_extra=_named(_DUE))
    body: str = Field(min_length=1, max_length=_BODY_MAX, json_schema_extra=_named(_DUE))


class TurnReminder(_Reminder):
    """As `SinceReminder`, and ``{next_step}``: one of `NextSteps`."""

    NAMES: ClassVar[frozenset[str]] = _TURN
    title: str = Field(min_length=1, max_length=_TITLE_MAX, json_schema_extra=_named(_TURN))
    body: str = Field(min_length=1, max_length=_BODY_MAX, json_schema_extra=_named(_TURN))


class ReminderWords(BaseModel):
    """One reminder per follow-up, and per way it reads (`followups.Followup`;
    which one a case gets is code's, `followups.reminder_text`)."""

    model_config = _FROZEN

    # A case come to the head's turn: an order's cross-check, a quote's approval.
    your_turn_order_head: SinceReminder
    your_turn_quote_head: SinceReminder
    # A case come to the PIC's turn.
    your_turn_order: TurnReminder
    your_turn_quote: TurnReminder
    order_unconfirmed_remind: HoursReminder
    order_unconfirmed_escalate: HoursReminder
    quote_waiting_design: HoursReminder
    quote_deadline_soon: DueReminder
    quote_deadline_late: DueReminder
    waiting_pc: HoursReminder
    implied_acceptance: SinceReminder
    # The customer's answer to their change (ticket 29), a PO's correction,
    # a quote's spec.
    waiting_customer_change: HoursReminder
    waiting_customer_correction: HoursReminder
    waiting_customer_spec: HoursReminder
    waiting_design_code: HoursReminder
    waiting_quote: HoursReminder
    # A pcs quote waiting for the GM's price (ticket 05).
    waiting_pcs_price: HoursReminder


def _plain(max_length: int) -> Any:
    """A text with no placeholder (checked by each model's validator)."""
    return Field(min_length=1, max_length=max_length)


class NextSteps(BaseModel):
    """What the person does next on their turn, where DW1 did the step before
    it: said in the reminder (and told to the brief's writer), so nobody has
    to open the case to learn it. No placeholder."""

    model_config = _FROZEN

    ycbg_drafted: str = _plain(300)
    design_replied: str = _plain(300)
    # Any other turn.
    other: str = _plain(300)

    @field_validator("ycbg_drafted", "design_replied", "other")
    @classmethod
    def _no_placeholders(cls, value: str) -> str:
        return _plain_placeholders(value, frozenset())


_BRIEF_TITLE: Final = frozenset({"day", "new", "whose"})
_BRIEF_NEW: Final = frozenset({"since", "new", "new_orders", "new_quotes", "waiting"})
_BRIEF_DUE: Final = frozenset({"soon_orders", "soon_quotes", "late_orders", "late_quotes"})
_BRIEF_WAITING: Final = frozenset({"waiting"})


class BriefWords(BaseModel):
    """The morning brief's counts, a title and three lines. ``{day}`` the
    brief's day, ``{since}`` the previous brief's slot, ``{whose}`` the
    `workspace` or `mine` words, ``{waiting}`` the counts per whom the cases
    wait on (`waits_on`, else `nothing`); every other placeholder a count."""

    model_config = _FROZEN

    title: str = Field(min_length=1, max_length=200, json_schema_extra=_named(_BRIEF_TITLE))
    new_line: str = Field(min_length=1, max_length=300, json_schema_extra=_named(_BRIEF_NEW))
    due_line: str = Field(min_length=1, max_length=300, json_schema_extra=_named(_BRIEF_DUE))
    waiting_line: str = Field(
        min_length=1, max_length=300, json_schema_extra=_named(_BRIEF_WAITING)
    )
    # Whose brief: the head's (the whole of Sales), a PIC's (their cases).
    workspace: str = _plain(60)
    mine: str = _plain(60)
    # No case waits on anyone.
    nothing: str = _plain(60)
    # Whom a case waits on (the overview's buckets).
    waits_on: Mapping[Bucket, str]

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _plain_placeholders(value, _BRIEF_TITLE)

    @field_validator("new_line")
    @classmethod
    def _new(cls, value: str) -> str:
        return _plain_placeholders(value, _BRIEF_NEW)

    @field_validator("due_line")
    @classmethod
    def _due(cls, value: str) -> str:
        return _plain_placeholders(value, _BRIEF_DUE)

    @field_validator("waiting_line")
    @classmethod
    def _waiting(cls, value: str) -> str:
        return _plain_placeholders(value, _BRIEF_WAITING)

    @field_validator("workspace", "mine", "nothing")
    @classmethod
    def _words(cls, value: str) -> str:
        return _plain_placeholders(value, frozenset())

    @field_validator("waits_on")
    @classmethod
    def _every_bucket(cls, value: Mapping[Bucket, str]) -> Mapping[Bucket, str]:
        if set(value) != set(BUCKETS) or not all(0 < len(w) <= 40 for w in value.values()):
            raise ValueError(f"waits_on words each of {list(BUCKETS)}, 1 to 40 characters")
        for words in value.values():
            _plain_placeholders(words, frozenset())
        return value


_BATCH: Final = frozenset({"count"})


class PushWords(BaseModel):
    """What a push says (ticket 48): the kind of work, never a customer, a
    price or their text. No placeholder but the batch's ``{count}``; the
    case's number follows `order` or `quote` where the tenant allows it."""

    model_config = _FROZEN

    your_turn: str = _plain(60)
    head_order: str = _plain(60)
    head_quote: str = _plain(60)
    order_unconfirmed_remind: str = _plain(60)
    order_unconfirmed_escalate: str = _plain(60)
    quote_waiting_design: str = _plain(60)
    quote_deadline: str = _plain(60)
    waiting_customer: str = _plain(60)
    waiting_pc: str = _plain(60)
    implied_acceptance: str = _plain(60)
    waiting_design_code: str = _plain(60)
    waiting_quote: str = _plain(60)
    waiting_pcs_price: str = _plain(60)
    batch_title: str = Field(min_length=1, max_length=60, json_schema_extra=_named(_BATCH))
    batch_body: str = _plain(120)
    # The case's kind, before its number.
    order: str = _plain(20)
    quote: str = _plain(20)

    @field_validator("batch_title")
    @classmethod
    def _batch(cls, value: str) -> str:
        return _plain_placeholders(value, _BATCH)

    @field_validator(
        "your_turn",
        "head_order",
        "head_quote",
        "order_unconfirmed_remind",
        "order_unconfirmed_escalate",
        "quote_waiting_design",
        "quote_deadline",
        "waiting_customer",
        "waiting_pc",
        "implied_acceptance",
        "waiting_design_code",
        "waiting_quote",
        "waiting_pcs_price",
        "batch_body",
        "order",
        "quote",
    )
    @classmethod
    def _no_placeholders(cls, value: str) -> str:
        return _plain_placeholders(value, frozenset())


class ReminderCopy(BaseModel):
    """`configs/copy/sales_reminders@<version>.yaml`: the follow-ups' words."""

    model_config = _FROZEN

    schema_version: str = Field(pattern=r"^1\.0$")
    copy_id: str = Field(pattern=r"^sales_reminders$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    reminders: ReminderWords
    next_steps: NextSteps
    brief: BriefWords
    push: PushWords

    @property
    def ref(self) -> str:
        return f"{self.copy_id}@{self.version}"


class ReminderCopyPort(Protocol):
    """The reminder copy a scope's tenant speaks with."""

    async def reminder_copy(self, scope: SalesScope) -> ReminderCopy: ...
