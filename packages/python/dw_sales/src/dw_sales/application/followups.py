"""DW1's follow-ups and morning brief: the worker's `sales_followups` lane
(ticket 42).

Every few minutes, per workspace, the lane reads the tenant's resolved
`sales_followups` policy through the rule book (`FollowupPolicyPort`: the
tenant's approved version, else the platform's file), finds the stages owed
(`dw_sales.domain.followups.owed`), and delivers each as an in-app
notification through `NotificationSenderPort`. It informs; it never decides,
and it never writes to a customer or to Design.

**At most once per (case, follow-up, stage, wait).** What was sent is
recorded in `sales.followup_deliveries` (`FollowupStorePort.record`), unique
on that key, and a stage already recorded is not sent again. The delivery
comes first and the record after: a crash in between sends again under the
same ``source_key``, which the inbox ignores per recipient
(`uq_notifications_recipient_user_id_source_key`); two workers at once both
deliver under one key, and only one record is written. The record outlives
the inbox's 90 days and a reassignment, so neither reminds again.

**Quiet hours defer, never drop.** Outside working hours nothing owed is
sent and nothing is recorded, so the first tick inside them sends it.

**Who is told.** ``pic``: the case's assignee, or, while nobody is assigned,
whoever may assign it (the head's `sales.case.assign`). ``head``: the holders
of `sales.case.assign`. Both through `ScopeHoldersPort`, the function that
builds the access context, so who is told and who may act cannot disagree.
Nobody to tell: nothing is recorded, and it is owed again next tick.

**The brief.** Once per working day per workspace, at or after the
configured local time: the head a brief of the workspace, each PIC (a holder
of `sales.order.prepare` or `sales.quote.prepare` who is not also told as a
head) a brief of the cases assigned to them, with nothing in it skipped.
Counts and a link to `/sales`; never an amount, a price or a customer name
(dw_sales ADR 0003; ui-quality §6: a notification is a side door).

**Written by the model, where the step is on** (the AI list, item 10): a
`BriefWriterPort` may open each person's brief with a few sentences of what
to take first, from `brief_facts` (counts and the person's most pressing
cases: reference, customer code, who it waits on, due date, next step; never
an amount or a name). The counts follow either way, and a writer that
declines or fails leaves the brief as it always was.

**Its words are the tenant's copy** (`sales_reminders`, ticket 42 family 6):
read once per tick through the rule book like the timings, the tenant's
approved version else the platform's file. Code picks the template and fills
it; nothing a template says decides anything.

**Paused DW1 reminds nobody.** The pause stops what DW1 does (decided
2026-10-12, extended to rendering by `f4705f9`); a reminder owed meanwhile
is sent when DW1 is resumed, if the case still waits.

**It audits as itself** (ADR 0011-a-background-lane-audits-as-itself): one
`lane_audit_event` per record, in the record's transaction, naming the case,
the follow-up, the stage and how many were told, never who or what.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, Literal, Protocol

from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import lane_audit_event, system_actor
from dw_sales.application.access import SalesScopes
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.overview_ports import BUCKETS, Bucket, FollowupPolicyPort
from dw_sales.application.overview_service import STATUS_BUCKETS, WHOSE_TURN
from dw_sales.application.ports import NotificationSenderPort, SalesScope, ScopeHoldersPort
from dw_sales.application.reminder_copy import (
    BriefWords,
    DueReminder,
    HoursReminder,
    NextSteps,
    PushWords,
    ReminderCopy,
    ReminderCopyPort,
    ReminderWords,
    SinceReminder,
    TurnReminder,
)
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import (
    Audience,
    BriefSlot,
    Due,
    Followup,
    SalesFollowups,
    Stage,
    WaitingCase,
    brief_slot,
    due_soon,
    owed,
    turn_status,
)
from dw_sales.domain.quotes import QuoteStatus

logger = logging.getLogger("dw_sales.followups")

# The lane's worker registry name, and so its audit actor.
SALES_FOLLOWUPS_LANE: Final = "sales_followups"
# The brief's row in the record: its follow-up and its stage.
BRIEF: Final = "morning_brief"
BRIEF_STAGE: Final = "brief"
_RESOURCE_CASE: Final = {CaseKind.ORDER: "sales_order_case", CaseKind.QUOTE: "sales_quote_case"}
_LINK: Final = {CaseKind.ORDER: "/sales/orders/{}", CaseKind.QUOTE: "/sales/quotes/{}"}
_HEADS: Final = frozenset({SalesScopes.CASE_ASSIGN.value})
_PICS: Final = frozenset({SalesScopes.ORDER_PREPARE.value, SalesScopes.QUOTE_PREPARE.value})
# Every status a case waits on someone in: the brief counts them, and every
# status a follow-up watches is one (`test_followups.py` holds the two).
LOADED: Final[Mapping[CaseKind, frozenset[str]]] = {
    kind: frozenset(statuses) for kind, statuses in STATUS_BUCKETS.items()
}
_REFERENCE_LIMIT: Final = 60
# How long a brief's record is kept: only today's is asked for.
BRIEF_RECORDS_KEPT: Final = timedelta(days=35)

Stopped = Literal["paused"]
# What opens a brief whose first sentences the model wrote: the feed (ticket
# 47) splits the brief on it, so the two read one constant.
OPENING_PREFIX: Final = "DW1 viết: "
_KEY_PREFIX: Final = "sales.followup"


@dataclass(frozen=True, slots=True)
class FollowupKey:
    """What one delivery is recorded under: unique in the workspace."""

    followup: str
    stage: str
    # The case id, or the brief's local day.
    subject: str
    # When the wait began, or the brief's slot.
    since: datetime


@dataclass(frozen=True, slots=True)
class SentFollowup:
    key: FollowupKey
    recipients: int
    sent_at: datetime


class FollowupStorePort(Protocol):
    """The follow-ups' reads and their record, in the unit of work's
    workspace (RLS)."""

    async def cases(
        self, statuses: Mapping[CaseKind, frozenset[str]], *, received_since: datetime
    ) -> Sequence[WaitingCase]:
        """Every case in one of ``statuses`` for its kind, and every case
        received since ``received_since`` whatever its status."""
        ...

    async def already_sent(self, keys: Sequence[FollowupKey]) -> frozenset[FollowupKey]:
        """Those of ``keys`` the workspace has a record of."""
        ...

    async def record(self, sent: SentFollowup) -> bool:
        """The record of one delivery; False, writing nothing, when the key
        is recorded already (another worker, a retry)."""
        ...

    async def forget_briefs_before(self, day: date) -> int:
        """Delete the brief records of days before ``day``: only today's is
        ever asked for. How many went."""
        ...


@dataclass(frozen=True, slots=True)
class FollowupTick:
    """What one tick did in one workspace."""

    # The source keys delivered and recorded by this tick.
    sent: tuple[str, ...] = ()
    # Owed, unsent, outside working hours.
    deferred: int = 0
    stopped: Stopped | None = None


def key_of(due: Due) -> FollowupKey:
    return FollowupKey(due.followup.value, due.stage.value, str(due.case.case_id), due.since)


def source_key(key: FollowupKey, scope: SalesScope) -> str:
    """The inbox's idempotency key: the record's key, in its workspace."""
    return (
        f"{source_key_prefix(scope.workspace_id.value)}{key.followup}:{key.stage}:"
        f"{key.subject}:{key.since.isoformat()}"
    )


@dataclass(frozen=True, slots=True)
class SourceKey:
    """A follow-up's inbox key read back (`source_key`'s inverse)."""

    workspace_id: uuid.UUID
    followup: str
    stage: str
    subject: str


def source_key_prefix(workspace_id: uuid.UUID) -> str:
    """What every follow-up delivered in ``workspace_id`` is keyed under."""
    return f"{_KEY_PREFIX}:{workspace_id}:"


def parse_source_key(text: str) -> SourceKey | None:
    """The workspace, follow-up, stage and subject of a key `source_key` made,
    or None for any other key. The wait's instant is last because its ISO
    form holds colons."""
    parts = text.split(":", 5)
    if len(parts) != 6 or parts[0] != _KEY_PREFIX:
        return None
    try:
        workspace = uuid.UUID(parts[1])
    except ValueError:
        return None
    return SourceKey(workspace, parts[2], parts[3], parts[4])


def lane_context(scope: SalesScope) -> AccessContext:
    """The lane delivering in ``scope``: its own actor, no scope at all. The
    inbox's one door delivers inside the bound tenant to its members only."""
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=system_actor(SALES_FOLLOWUPS_LANE).value,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )


class FollowupRulesPort(FollowupPolicyPort, ReminderCopyPort, Protocol):
    """The tenant's follow-up timings and their words, both through the rule
    book (`TenantRuleBook`)."""


class BriefWriterPort(Protocol):
    """The opening of ``person``'s brief, written from ``facts``; None to send
    the brief as it is (`dw_sales.application.brief_writing.BriefWriter`)."""

    async def write(
        self, scope: SalesScope, person: uuid.UUID, facts: Mapping[str, Any]
    ) -> str | None: ...


class PushResult(Protocol):
    """How many of a person's devices took a push, and how many of their
    subscriptions were gone and removed."""

    @property
    def reached(self) -> int: ...

    @property
    def removed(self) -> int: ...


class PushNoticePort(Protocol):
    """A push to every device ``person`` turned notifications on from in the
    workspace (`dw_platform.application.web_push.WebPushService.push`). The
    payload is `PushNotice.payload`'s, nothing else."""

    async def push(
        self,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        person: uuid.UUID,
        payload: Mapping[str, object],
    ) -> PushResult: ...


@dataclass(frozen=True)
class FollowupLane:
    uow: SalesUnitOfWorkFactory
    policies: FollowupRulesPort
    holders: ScopeHoldersPort
    notifications: NotificationSenderPort
    clock: UtcClock
    ids: IdGenerator
    # None where no model is wired: every brief is the counts alone.
    writer: BriefWriterPort | None = None
    # None where web push is off: the inbox alone tells people (ticket 48).
    push: PushNoticePort | None = None

    async def tick(self, scope: SalesScope) -> FollowupTick:
        policy = await self.policies.followups(scope)
        copy = await self.policies.reminder_copy(scope)
        now = self.clock.now()
        slot = brief_slot(policy, now)
        async with self.uow(scope) as work:
            if (await work.worker.state()).paused:
                return FollowupTick(stopped="paused")
            cases = await work.followups.cases(
                LOADED, received_since=slot.since if slot is not None else now
            )
            stages = owed(policy, cases, now, turns=WHOSE_TURN)
            brief_key = None if slot is None else _brief_key(slot)
            asked = [key_of(d) for d in stages] + ([brief_key] if brief_key else [])
            done = await work.followups.already_sent(asked) if asked else frozenset()
        pending = [d for d in stages if key_of(d) not in done]
        sent: list[str] = []
        deferred = 0
        if pending and not policy.working_hours.is_open(now):
            deferred, pending = len(pending), []
        # What each person was told by this tick: one push each, however
        # many (ticket 48: several within a tick's few minutes ring once).
        told: dict[uuid.UUID, list[Due]] = {}
        for due in pending:
            delivered = await self._remind(scope, policy, copy, due, now)
            if delivered is not None:
                key, recipients = delivered
                sent.append(key)
                for person in recipients:
                    told.setdefault(person, []).append(due)
        if told and self.push is not None:
            await self._push(scope, policy, copy.push, told, now)
        if slot is not None and brief_key is not None and brief_key not in done:
            briefed = await self._brief(scope, policy, copy, slot, brief_key, cases, now)
            if briefed is not None:
                sent.append(briefed)
        return FollowupTick(sent=tuple(sent), deferred=deferred)

    # ------------------------------------------------------------- stages --

    async def _remind(
        self,
        scope: SalesScope,
        policy: SalesFollowups,
        copy: ReminderCopy,
        due: Due,
        now: datetime,
    ) -> tuple[str, list[uuid.UUID]] | None:
        """The source key and whom it told, when this tick recorded it; None
        when not delivered, or recorded already by another worker (which
        pushes it, so a person's phone rings once)."""
        recipients = await self._audience(scope, due.notify, due.case.assigned_to)
        if not recipients:
            return None
        key = key_of(due)
        title, body = reminder_text(copy, policy, due, now)
        try:
            await self.notifications.deliver(
                lane_context(scope),
                recipients=recipients,
                source_key=source_key(key, scope),
                title=title,
                body=body,
                link=_LINK[due.case.kind].format(due.case.case_id),
            )
        except Exception:
            # One delivery failing costs the others nothing; unrecorded, it
            # is owed again next tick.
            logger.exception("sales_followups: a reminder was not delivered")
            return None
        details: dict[str, object] = {
            "followup": key.followup,
            "stage": key.stage,
            "since": key.since.isoformat(),
            "recipients": len(recipients),
        }
        recorded = await self._record(
            scope, key, len(recipients), now, _RESOURCE_CASE[due.case.kind], key.subject, details
        )
        return (source_key(key, scope), recipients) if recorded else None

    async def _audience(
        self, scope: SalesScope, notify: Sequence[Audience], assignee: uuid.UUID | None
    ) -> list[uuid.UUID]:
        told: list[uuid.UUID] = []
        heads: list[uuid.UUID] | None = None
        for audience in notify:
            if audience == "pic" and assignee is not None:
                found = [assignee]
            else:
                heads = heads if heads is not None else await self._holding(scope, _HEADS)
                found = heads
            told += [person for person in found if person not in told]
        return told

    async def _holding(self, scope: SalesScope, scopes: frozenset[str]) -> list[uuid.UUID]:
        return await self.holders.holding(scope.tenant_id.value, scope.workspace_id.value, scopes)

    async def _record(
        self,
        scope: SalesScope,
        key: FollowupKey,
        recipients: int,
        now: datetime,
        resource_type: str,
        resource_id: str,
        details: dict[str, object],
        *,
        forget_before: date | None = None,
    ) -> bool:
        async with self.uow(scope) as work:
            if not await work.followups.record(SentFollowup(key, recipients, now)):
                return False
            if forget_before is not None:
                await work.followups.forget_briefs_before(forget_before)
            await work.audit.append(
                lane_audit_event(
                    lane=SALES_FOLLOWUPS_LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=TenantId(scope.tenant_id.value),
                    workspace_id=WorkspaceId(scope.workspace_id.value),
                    action="sales.followup.sent",
                    resource_type=resource_type,
                    resource_id=resource_id,
                    occurred_at=now,
                    details=details,
                )
            )
            await work.commit()
        return True

    # --------------------------------------------------------------- push --

    async def _push(
        self,
        scope: SalesScope,
        policy: SalesFollowups,
        words: PushWords,
        told: Mapping[uuid.UUID, Sequence[Due]],
        now: datetime,
    ) -> None:
        """One push per person told, after the reminders are recorded. A push
        is a nudge towards the feed, which holds the reminder either way, so
        one that fails is logged and not tried again."""
        assert self.push is not None
        for person, dues in told.items():
            notice = push_notice(words, dues, case_number=policy.push.case_number)
            try:
                outcome = await self.push.push(
                    scope.tenant_id.value, scope.workspace_id.value, person, notice.payload()
                )
            except Exception:
                logger.exception("sales_followups: a push was not sent")
                continue
            if not (outcome.reached or outcome.removed):
                # Nobody's phone: nothing happened worth a row.
                continue
            async with self.uow(scope) as work:
                await work.audit.append(
                    lane_audit_event(
                        lane=SALES_FOLLOWUPS_LANE,
                        event_id=self.ids.new_uuid(),
                        tenant_id=TenantId(scope.tenant_id.value),
                        workspace_id=WorkspaceId(scope.workspace_id.value),
                        action="sales.followup.pushed",
                        resource_type="sales_workspace",
                        resource_id=str(scope.workspace_id.value),
                        occurred_at=now,
                        # How many, never who or which case.
                        details={
                            "items": notice.items,
                            "devices": outcome.reached,
                            "removed": outcome.removed,
                        },
                    )
                )
                await work.commit()

    # -------------------------------------------------------------- brief --

    async def _brief(
        self,
        scope: SalesScope,
        policy: SalesFollowups,
        copy: ReminderCopy,
        slot: BriefSlot,
        key: FollowupKey,
        cases: Sequence[WaitingCase],
        now: datetime,
    ) -> str | None:
        notify = policy.morning_brief.notify
        heads = await self._holding(scope, _HEADS) if "head" in notify else []
        pics = (
            [p for p in await self._holding(scope, _PICS) if p not in heads]
            if "pic" in notify
            else []
        )
        briefs = [(person, None) for person in heads] + [(person, person) for person in pics]
        told = 0
        for person, whose in briefs:
            brief = brief_of(cases, slot, policy, whose)
            if brief.empty:
                continue
            title, body = brief_text(copy, brief, slot, workspace=whose is None)
            opening = (
                await self._opening(
                    scope, person, brief_facts(copy, brief, cases, slot, policy, whose)
                )
                if policy.morning_brief.model_opening
                else None
            )
            if opening is not None:
                body = f"{OPENING_PREFIX}{opening}\n\n{body}"
            try:
                await self.notifications.deliver(
                    lane_context(scope),
                    recipients=[person],
                    source_key=source_key(key, scope),
                    title=title,
                    body=body,
                    link="/sales",
                )
            except Exception:
                # Unrecorded: the brief is owed again next tick, and whoever
                # got it already is not told twice (the inbox's key).
                logger.exception("sales_followups: a brief was not delivered")
                return None
            told += 1
        details: dict[str, object] = {"day": key.subject, "recipients": told}
        await self._record(
            scope,
            key,
            told,
            now,
            "sales_workspace",
            str(scope.workspace_id.value),
            details,
            forget_before=slot.day - BRIEF_RECORDS_KEPT,
        )
        # Recorded even with nobody told: a day with nothing in it is done.
        return source_key(key, scope) if told else None

    async def _opening(
        self, scope: SalesScope, person: uuid.UUID, facts: Mapping[str, Any]
    ) -> str | None:
        """The writer's sentences, or None: no writer, or it declined or
        failed, which never holds the brief back."""
        if self.writer is None:
            return None
        try:
            return await self.writer.write(scope, person, facts)
        except Exception:
            logger.exception("sales_followups: the brief's opening was not written")
            return None


def _brief_key(slot: BriefSlot) -> FollowupKey:
    return FollowupKey(BRIEF, BRIEF_STAGE, slot.day.isoformat(), slot.at)


# ------------------------------------------------------------- the words --


def _reference(case: WaitingCase) -> str:
    text = case.reference
    return text if len(text) <= _REFERENCE_LIMIT else text[: _REFERENCE_LIMIT - 1] + "…"


def _local(moment: datetime, policy: SalesFollowups) -> str:
    return moment.astimezone(policy.working_hours.zone).strftime("%H:%M %d/%m/%Y")


def _day(day: date) -> str:
    return day.strftime("%d/%m/%Y")


# What the person does next, where DW1 has done the step before it: said in
# the notice itself, so nobody has to open the case to learn it.
_NEXT_STEP: Final[Mapping[tuple[CaseKind, str], Callable[[NextSteps], str]]] = MappingProxyType(
    {
        (CaseKind.QUOTE, QuoteStatus.YCBG_DRAFTED.value): lambda w: w.ycbg_drafted,
        (CaseKind.QUOTE, QuoteStatus.DESIGN_REPLIED.value): lambda w: w.design_replied,
    }
)


def _next_step(words: NextSteps, case: WaitingCase) -> str | None:
    step = _NEXT_STEP.get((case.kind, case.status))
    return None if step is None else step(words)


type Template = SinceReminder | HoursReminder | DueReminder | TurnReminder


def reminder_text(
    copy: ReminderCopy, policy: SalesFollowups, due: Due, now: datetime
) -> tuple[str, str]:
    """A reminder's title and body, in the tenant's words: the case's number
    and customer code, when the wait began and how long the threshold is.
    Never an amount. Which template, and every value in it, is code's; a
    template names only its own (`reminder_copy`), so the rest go unused."""
    case = due.case
    template, hours = _template(copy.reminders, policy, due, now)
    values: dict[str, object] = {
        "ref": _reference(case),
        "customer": case.customer_code,
        "since": _local(due.since, policy),
        "next_step": _next_step(copy.next_steps, case) or copy.next_steps.other,
        "hours": hours,
        "due": _day(case.due) if case.due is not None else None,
    }
    return template.title.format(**values), template.body.format(**values)


def _template(
    words: ReminderWords, policy: SalesFollowups, due: Due, now: datetime
) -> tuple[Template, int | None]:
    """The template ``due`` is said with, and the threshold it counts in
    hours where it counts one."""
    case = due.case
    order = case.kind is CaseKind.ORDER
    match due.followup, due.stage:
        case Followup.YOUR_TURN, _ if due.notify == ("head",):
            return (words.your_turn_order_head if order else words.your_turn_quote_head), None
        case Followup.YOUR_TURN, _:
            return (words.your_turn_order if order else words.your_turn_quote), None
        case Followup.ORDER_UNCONFIRMED, Stage.REMIND:
            return words.order_unconfirmed_remind, policy.order_unconfirmed.remind.after_hours
        case Followup.ORDER_UNCONFIRMED, _:
            return words.order_unconfirmed_escalate, policy.order_unconfirmed.escalate.after_hours
        case Followup.QUOTE_WAITING_DESIGN, _:
            return words.quote_waiting_design, policy.quote_waiting_design.remind.after_hours
        case Followup.QUOTE_DEADLINE, _:
            assert case.due is not None  # a deadline stage is owed only on a due date
            late = now >= due.since
            return (words.quote_deadline_late if late else words.quote_deadline_soon), None
        case Followup.WAITING_PC, _:
            return words.waiting_pc, policy.waiting_pc.remind.after_hours
        case Followup.IMPLIED_ACCEPTANCE, _:
            return words.implied_acceptance, None
        case Followup.WAITING_DESIGN_CODE, _:
            return words.waiting_design_code, policy.waiting_design_code.remind.after_hours
        case Followup.WAITING_QUOTE, _:
            return words.waiting_quote, policy.waiting_quote.remind.after_hours
        case Followup.WAITING_CUSTOMER, _ if case.customer_asked_at is not None:
            return words.waiting_customer_change, policy.waiting_customer.remind.after_hours
        case Followup.WAITING_CUSTOMER, _ if order:
            return words.waiting_customer_correction, policy.waiting_customer.remind.after_hours
        case _:
            return words.waiting_customer_spec, policy.waiting_customer.remind.after_hours


@dataclass(frozen=True, slots=True)
class Brief:
    """What one person's brief counts. Counts only."""

    new_orders: int
    new_quotes: int
    new_waiting: Mapping[Bucket, int]
    due_soon: Mapping[CaseKind, int]
    overdue: Mapping[CaseKind, int]
    waiting: Mapping[Bucket, int]

    @property
    def empty(self) -> bool:
        return not (self.new_orders or self.new_quotes or any(self.waiting.values()))


def _bucket(case: WaitingCase) -> Bucket | None:
    return STATUS_BUCKETS[case.kind].get(turn_status(case))


def brief_of(
    cases: Sequence[WaitingCase],
    slot: BriefSlot,
    policy: SalesFollowups,
    person: uuid.UUID | None,
) -> Brief:
    """The brief of ``person``'s cases (their assigned ones), or of the
    workspace's for None: what came in since the previous slot, what waits
    on whom, and what is due within the policy's days."""
    mine = [c for c in cases if person is None or c.assigned_to == person]
    new = [c for c in mine if c.received_at >= slot.since]
    open_ = [(c, b) for c in mine if (b := _bucket(c)) is not None]

    def count(rows: Sequence[WaitingCase]) -> dict[Bucket, int]:
        found = [b for c in rows if (b := _bucket(c)) is not None]
        return {bucket: found.count(bucket) for bucket in BUCKETS if bucket in found}

    dated = [c for c, _ in open_ if c.due is not None]
    return Brief(
        new_orders=sum(1 for c in new if c.kind is CaseKind.ORDER),
        new_quotes=sum(1 for c in new if c.kind is CaseKind.QUOTE),
        new_waiting=count(new),
        due_soon={
            kind: sum(
                1
                for c in dated
                if c.kind is kind and c.due is not None and due_soon(c.due, slot.day, policy)
            )
            for kind in CaseKind
        },
        overdue={
            kind: sum(1 for c in dated if c.kind is kind and c.due is not None and c.due < slot.day)
            for kind in CaseKind
        },
        waiting=count([c for c, _ in open_]),
    )


# The most pressing cases a written brief is told of, at most.
BRIEF_CASES: Final = 8
_KIND_WORDS: Final[Mapping[CaseKind, str]] = {
    CaseKind.ORDER: "đơn hàng",
    CaseKind.QUOTE: "báo giá",
}


def brief_facts(
    copy: ReminderCopy,
    brief: Brief,
    cases: Sequence[WaitingCase],
    slot: BriefSlot,
    policy: SalesFollowups,
    person: uuid.UUID | None,
) -> dict[str, Any]:
    """What a writer is told: the brief's counts and the most pressing of
    ``person``'s cases (the workspace's for None), overdue first, then due
    soon, then the longest waiting. References and customer codes, never an
    amount or a name. Whom a case waits on and its next step in the tenant's
    words, as its reminders say them."""
    waits_on = copy.brief.waits_on
    mine = [
        (c, b)
        for c in cases
        if (person is None or c.assigned_to == person) and (b := _bucket(c)) is not None
    ]

    def rank(row: tuple[WaitingCase, Bucket]) -> tuple[int, str, datetime]:
        case = row[0]
        due = case.due
        if due is None:
            return 2, "9999", case.status_since
        tier = 0 if due < slot.day else 1 if due_soon(due, slot.day, policy) else 2
        return tier, due.isoformat(), case.status_since

    shown = sorted(mine, key=rank)[:BRIEF_CASES]
    return {
        # Dates as a Vietnamese reader writes them, so the text copies them.
        "day": _day(slot.day),
        "for": "bộ phận Sales" if person is None else "bạn",
        "new_cases_since": _local(slot.since, policy),
        "new_orders": brief.new_orders,
        "new_quotes": brief.new_quotes,
        "overdue": {_KIND_WORDS[k]: n for k, n in brief.overdue.items()},
        "due_within_days": policy.morning_brief.due_within_days,
        "due_soon": {_KIND_WORDS[k]: n for k, n in brief.due_soon.items()},
        "waiting_on": {waits_on[b]: n for b, n in brief.waiting.items()},
        "cases": [
            {
                "reference": _reference(case),
                "kind": _KIND_WORDS[case.kind],
                "customer_code": case.customer_code,
                "waits_on": waits_on[bucket],
                "due": _day(case.due) if case.due else None,
                "overdue": case.due is not None and case.due < slot.day,
                "next_step": _next_step(copy.next_steps, case),
            }
            for case, bucket in shown
        ],
    }


def _buckets(words: BriefWords, counts: Mapping[Bucket, int]) -> str:
    shown = [f"{words.waits_on[b]} {counts[b]}" for b in BUCKETS if counts.get(b)]
    return " · ".join(shown) if shown else words.nothing


def brief_text(
    copy: ReminderCopy, brief: Brief, slot: BriefSlot, *, workspace: bool
) -> tuple[str, str]:
    """The brief's title and body, in counts, in the tenant's words."""
    words = copy.brief
    new = brief.new_orders + brief.new_quotes
    title = words.title.format(
        day=slot.day.strftime("%d/%m"),
        new=new,
        whose=words.workspace if workspace else words.mine,
    )
    lines = [
        words.new_line.format(
            since=slot.since.strftime("%H:%M %d/%m"),
            new=new,
            new_orders=brief.new_orders,
            new_quotes=brief.new_quotes,
            waiting=_buckets(words, brief.new_waiting),
        ),
        words.due_line.format(
            soon_orders=brief.due_soon[CaseKind.ORDER],
            soon_quotes=brief.due_soon[CaseKind.QUOTE],
            late_orders=brief.overdue[CaseKind.ORDER],
            late_quotes=brief.overdue[CaseKind.QUOTE],
        ),
        words.waiting_line.format(waiting=_buckets(words, brief.waiting)),
    ]
    return title, "\n".join(lines)


# ------------------------------------------------------------- the push --

# What a push says, per follow-up and stage: the kind of work in a few words
# (the tenant's), and of the case nothing but its number (ticket 48).
type _PushWord = Callable[[PushWords], str]
_PUSH_KIND: Final[Mapping[tuple[Followup, Stage], _PushWord]] = MappingProxyType(
    {
        (Followup.YOUR_TURN, Stage.NOTIFY): lambda w: w.your_turn,
        (Followup.ORDER_UNCONFIRMED, Stage.REMIND): lambda w: w.order_unconfirmed_remind,
        (Followup.ORDER_UNCONFIRMED, Stage.ESCALATE): lambda w: w.order_unconfirmed_escalate,
        (Followup.QUOTE_WAITING_DESIGN, Stage.REMIND): lambda w: w.quote_waiting_design,
        (Followup.QUOTE_DEADLINE, Stage.WARN): lambda w: w.quote_deadline,
        (Followup.WAITING_CUSTOMER, Stage.REMIND): lambda w: w.waiting_customer,
        (Followup.WAITING_PC, Stage.REMIND): lambda w: w.waiting_pc,
        (Followup.IMPLIED_ACCEPTANCE, Stage.NOTIFY): lambda w: w.implied_acceptance,
        (Followup.WAITING_DESIGN_CODE, Stage.REMIND): lambda w: w.waiting_design_code,
        (Followup.WAITING_QUOTE, Stage.REMIND): lambda w: w.waiting_quote,
    }
)
_HEAD_TURN: Final[Mapping[CaseKind, _PushWord]] = {
    CaseKind.ORDER: lambda w: w.head_order,
    CaseKind.QUOTE: lambda w: w.head_quote,
}
_PUSH_CASE: Final[Mapping[CaseKind, _PushWord]] = {
    CaseKind.ORDER: lambda w: w.order,
    CaseKind.QUOTE: lambda w: w.quote,
}
# A case number fit for a lock screen: what a PO or quote request number
# looks like. A reference read from a customer's document that is anything
# else (words, spaces, a long string) is left out, never shown: a push never
# carries the customer's text.
_PUSH_NUMBER: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9/._-]{0,39}")
FEED_LINK: Final = "/sales"


@dataclass(frozen=True, slots=True)
class PushNotice:
    """One push: a title and a line, the page it opens, and how many items it
    stands for (the app badge adds them up)."""

    title: str
    body: str
    link: str
    items: int
    tag: str

    def payload(self) -> dict[str, object]:
        """What leaves for the push service, encrypted to the device: these
        five fields and nothing else (`apps/web/public/sw.js` reads them)."""
        return {
            "title": self.title,
            "body": self.body,
            "url": self.link,
            "count": self.items,
            "tag": self.tag,
        }


def item_link(kind: CaseKind, case_id: uuid.UUID) -> str:
    """The feed with one case's item open (ticket 48's deep link)."""
    return f"{FEED_LINK}?item={kind.value}:{case_id}"


def push_notice(words: PushWords, dues: Sequence[Due], *, case_number: bool) -> PushNotice:
    """The push for what one person was told in one tick: one item named by
    its kind and, where the tenant allows it and it looks like one, its
    number; several, counted. Never a price, an amount, a customer or their
    text: ``words`` name no placeholder but the batch's count."""
    if len(dues) > 1:
        return PushNotice(
            title=words.batch_title.format(count=len(dues)),
            body=words.batch_body,
            link=FEED_LINK,
            items=len(dues),
            tag="sales:batch",
        )
    (due,) = dues
    case = due.case
    if due.followup is Followup.YOUR_TURN and due.notify == ("head",):
        title = _HEAD_TURN[case.kind](words)
    else:
        title = _PUSH_KIND[(due.followup, due.stage)](words)
    what = _PUSH_CASE[case.kind](words)
    number = case.reference if _PUSH_NUMBER.fullmatch(case.reference) else None
    return PushNotice(
        title=title,
        body=f"{what} {number}" if case_number and number else what,
        link=item_link(case.kind, case.case_id),
        items=1,
        tag=f"sales:{case.kind.value}:{case.case_id}",
    )
