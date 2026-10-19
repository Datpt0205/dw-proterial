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

**Paused DW1 reminds nobody.** The pause stops what DW1 does (decided
2026-10-12, extended to rendering by `f4705f9`); a reminder owed meanwhile
is sent when DW1 is resumed, if the case still waits.

**It audits as itself** (ADR 0011-a-background-lane-audits-as-itself): one
`lane_audit_event` per record, in the record's transaction, naming the case,
the follow-up, the stage and how many were told, never who or what.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final, Literal, Protocol

from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import lane_audit_event, system_actor
from dw_sales.application.access import SalesScopes
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.overview_ports import BUCKETS, Bucket
from dw_sales.application.overview_service import STATUS_BUCKETS
from dw_sales.application.ports import NotificationSenderPort, SalesScope, ScopeHoldersPort
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
    owed,
)

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
_BUCKET_WORDS: Final[Mapping[Bucket, str]] = {
    "dw": "DW1",
    "sales": "Sales",
    "design": "Design",
    "approver": "Người duyệt",
    "customer": "Khách",
}
_REFERENCE_LIMIT: Final = 60
# How long a brief's record is kept: only today's is asked for.
BRIEF_RECORDS_KEPT: Final = timedelta(days=35)

Stopped = Literal["paused"]


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


class FollowupPolicyPort(Protocol):
    """The tenant's follow-up policy in force (`TenantRuleBook.followups`)."""

    async def followups(self, scope: SalesScope) -> SalesFollowups: ...


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
        f"sales.followup:{scope.workspace_id.value}:{key.followup}:{key.stage}:"
        f"{key.subject}:{key.since.isoformat()}"
    )


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


@dataclass(frozen=True)
class FollowupLane:
    uow: SalesUnitOfWorkFactory
    policies: FollowupPolicyPort
    holders: ScopeHoldersPort
    notifications: NotificationSenderPort
    clock: UtcClock
    ids: IdGenerator

    async def tick(self, scope: SalesScope) -> FollowupTick:
        policy = await self.policies.followups(scope)
        now = self.clock.now()
        slot = brief_slot(policy, now)
        async with self.uow(scope) as work:
            if (await work.worker.state()).paused:
                return FollowupTick(stopped="paused")
            cases = await work.followups.cases(
                LOADED, received_since=slot.since if slot is not None else now
            )
            stages = owed(policy, cases, now)
            brief_key = None if slot is None else _brief_key(slot)
            asked = [key_of(d) for d in stages] + ([brief_key] if brief_key else [])
            done = await work.followups.already_sent(asked) if asked else frozenset()
        pending = [d for d in stages if key_of(d) not in done]
        sent: list[str] = []
        deferred = 0
        if pending and not policy.working_hours.is_open(now):
            deferred, pending = len(pending), []
        for due in pending:
            delivered = await self._remind(scope, policy, due, now)
            if delivered is not None:
                sent.append(delivered)
        if slot is not None and brief_key is not None and brief_key not in done:
            delivered = await self._brief(scope, policy, slot, brief_key, cases, now)
            if delivered is not None:
                sent.append(delivered)
        return FollowupTick(sent=tuple(sent), deferred=deferred)

    # ------------------------------------------------------------- stages --

    async def _remind(
        self, scope: SalesScope, policy: SalesFollowups, due: Due, now: datetime
    ) -> str | None:
        recipients = await self._audience(scope, due.notify, due.case.assigned_to)
        if not recipients:
            return None
        key = key_of(due)
        title, body = reminder_text(policy, due, now)
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
        await self._record(
            scope, key, len(recipients), now, _RESOURCE_CASE[due.case.kind], key.subject, details
        )
        return source_key(key, scope)

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
    ) -> None:
        async with self.uow(scope) as work:
            if not await work.followups.record(SentFollowup(key, recipients, now)):
                return
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

    # -------------------------------------------------------------- brief --

    async def _brief(
        self,
        scope: SalesScope,
        policy: SalesFollowups,
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
        briefs = [(person, brief_of(cases, slot, policy, None)) for person in heads] + [
            (person, brief_of(cases, slot, policy, person)) for person in pics
        ]
        told = 0
        for person, brief in briefs:
            if brief.empty:
                continue
            title, body = brief_text(brief, slot, workspace=person in heads)
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


def reminder_text(policy: SalesFollowups, due: Due, now: datetime) -> tuple[str, str]:
    """A reminder's title and body: the case's number and customer code, when
    the wait began and how long the threshold is. Never an amount."""
    case = due.case
    ref, customer = _reference(case), case.customer_code
    since = _local(due.since, policy)
    match due.followup, due.stage:
        case Followup.ORDER_UNCONFIRMED, Stage.REMIND:
            hours = policy.order_unconfirmed.remind.after_hours
            return (
                f"Nhắc: PO {ref} chưa xác nhận",
                f"PO {ref} của khách {customer} đến lúc {since}, đã hơn {hours} giờ mà "
                "chưa xác nhận. Mở hồ sơ để xử lý.",
            )
        case Followup.ORDER_UNCONFIRMED, _:
            hours = policy.order_unconfirmed.escalate.after_hours
            return (
                f"PO {ref} quá {hours} giờ chưa xác nhận",
                f"PO {ref} của khách {customer} đến lúc {since}, đã hơn {hours} giờ mà "
                "Sales chưa xác nhận.",
            )
        case Followup.QUOTE_WAITING_DESIGN, _:
            hours = policy.quote_waiting_design.remind.after_hours
            return (
                f"Nhắc: báo giá {ref} đang chờ Design",
                f"Yêu cầu báo giá {ref} của khách {customer} chờ Design (mã BP, spec) từ "
                f"{since}, đã hơn {hours} giờ. DW1 không gửi thư cho Design: bạn quyết "
                "định có nhắc Design hay không.",
            )
        case Followup.QUOTE_DEADLINE, _:
            assert case.due is not None  # a deadline stage is owed only on a due date
            late = now >= due.since
            return (
                f"{'Quá hạn' if late else 'Sắp đến hạn'} báo giá {ref}: {_day(case.due)}",
                f"Báo giá {ref} của khách {customer} "
                f"{'đã quá hạn' if late else 'đến hạn'} ngày {_day(case.due)} mà chưa gửi khách.",
            )
        case Followup.WAITING_CUSTOMER, _ if case.kind is CaseKind.ORDER:
            hours = policy.waiting_customer.remind.after_hours
            return (
                f"Nhắc: PO {ref} đang chờ khách sửa",
                f"Đã yêu cầu khách {customer} sửa PO {ref} từ {since}, hơn {hours} giờ "
                "chưa có PO sửa. DW1 không gửi thư cho khách: bạn quyết định có nhắc "
                "khách hay không.",
            )
        case _:
            hours = policy.waiting_customer.remind.after_hours
            return (
                f"Nhắc: báo giá {ref} đang chờ khách thống nhất spec",
                f"Báo giá {ref} của khách {customer} chờ khách thống nhất spec từ {since}, "
                f"hơn {hours} giờ. DW1 không gửi thư cho khách: bạn quyết định có nhắc "
                "khách hay không.",
            )


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
    return STATUS_BUCKETS[case.kind].get(case.status)


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
    horizon = slot.day.toordinal() + policy.morning_brief.due_within_days

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
                if c.kind is kind
                and c.due is not None
                and slot.day <= c.due
                and c.due.toordinal() <= horizon
            )
            for kind in CaseKind
        },
        overdue={
            kind: sum(1 for c in dated if c.kind is kind and c.due is not None and c.due < slot.day)
            for kind in CaseKind
        },
        waiting=count([c for c, _ in open_]),
    )


def _buckets(counts: Mapping[Bucket, int]) -> str:
    shown = [f"{_BUCKET_WORDS[b]} {counts[b]}" for b in BUCKETS if counts.get(b)]
    return " · ".join(shown) if shown else "không có"


def brief_text(brief: Brief, slot: BriefSlot, *, workspace: bool) -> tuple[str, str]:
    """The brief's title and body, in counts."""
    new = brief.new_orders + brief.new_quotes
    whose = "bộ phận Sales" if workspace else "hồ sơ của bạn"
    title = f"Tóm tắt sáng {slot.day.strftime('%d/%m')}: {new} hồ sơ mới ({whose})"
    since = slot.since.strftime("%H:%M %d/%m")
    lines = [
        f"Từ {since}: {new} hồ sơ mới ({brief.new_orders} đơn hàng, "
        f"{brief.new_quotes} báo giá); đang chờ: {_buckets(brief.new_waiting)}.",
        f"Sắp đến hạn: {brief.due_soon[CaseKind.ORDER]} đơn hàng, "
        f"{brief.due_soon[CaseKind.QUOTE]} báo giá; quá hạn: "
        f"{brief.overdue[CaseKind.ORDER]} đơn hàng, {brief.overdue[CaseKind.QUOTE]} báo giá.",
        f"Đang chờ: {_buckets(brief.waiting)}.",
    ]
    return title, "\n".join(lines)
