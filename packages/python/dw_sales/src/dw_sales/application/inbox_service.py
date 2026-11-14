"""The mailbox through the API: what arrived, and "DW xử lý" on it.

Processing is DW1's work, started by a person (spec decision 5, the stop
control): it needs `sales.inbox.process`, it is refused while DW1 is paused
in the workspace (409 naming who paused and when), and everything it writes
is DW1's event (`actor_kind = worker`) with the person as `initiated_by`.

Every message ends in exactly one disposition (spec decision 10):

- a PO opens an order case, or joins the case of the PO it revises
  (`OrderIntake`), and DW1 hands the case to the PIC's self-check; a mail
  with several POs does so per PO number, every case stored in the one
  transaction that records the message (ticket 19);
- a request for quotation opens a quote case (`QuotationService`);
- Design's reply is attached to the one case awaiting it, by YCBG number;
- anything else, or a file nothing can read, is routed to Sales with the
  reason and an owner.

A new case is assigned to the user its customer's Sales PIC resolves to in
the workspace's directory, stamped then and never looked up again (G22).
The time a message is processed is its ingest, stamped before any reading,
so the overview can tell DW1's time from the people's.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.activity import STEPS_BY_PROMPT
from dw_sales.application.case_store import (
    CaseOrigin,
    LoggedMessage,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
    SentRead,
)
from dw_sales.application.handoffs import HandoffCopy, HandoffCopyPort, render
from dw_sales.application.layouts import keep_learned
from dw_sales.application.model_calls import model_calls, recording_model_calls
from dw_sales.application.order_intake import (
    QUOTATION_KINDS,
    Classification,
    MessageKind,
    OrderIntake,
)
from dw_sales.application.outgoing import outgoing_in
from dw_sales.application.ports import InboxPort, MemberDirectoryPort, SalesCatalogPort, SalesScope
from dw_sales.application.quotation import (
    NotADesignReplyError,
    QuotationService,
    ReplyAttached,
    RequestNotExtractedError,
)
from dw_sales.application.quote_ports import QuoteFileUnreadableError
from dw_sales.application.runs import (
    PendingDecisionsPort,
    withdraw_if_left,
)
from dw_sales.application.support import (
    DW1_WORKER_ID,
    DW1_WORKER_VERSION,
    audit_row,
    save_order,
    save_quote,
    seen_by,
    worker_event,
)
from dw_sales.application.telemetry import SalesSpan, SalesSpans, case_attributes
from dw_sales.application.views import (
    HandoffDraftView,
    InboxMessageView,
    MessageDispositionView,
    inbox_message,
    message_disposition,
)
from dw_sales.application.worker_service import require_running
from dw_sales.domain.activity import outcomes_of, sent_outcomes
from dw_sales.domain.dispositions import (
    SALES_PIC_POOL,
    CaseKind,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
)
from dw_sales.domain.message_intent import IntentReading
from dw_sales.domain.orders import OrderCase, OrderStatus
from dw_sales.domain.quotes import QuoteCase

# A message on a case is not processed again ("DW xử lý lại" is for a routed one).
ON_A_CASE = frozenset({DispositionKind.CASE_CREATED, DispositionKind.ATTACHED_TO_CASE})

# What the audit says of a PO read from a file locked with a password (ticket
# 17): that it was opened, where, with what kind of password, and what that
# means for the scan. Never which password.
OPENED_WITH_MAIL_PASSWORD: Final = (
    "encrypted, its contents not scannable by ClamAV; opened in the reader sandbox"
    " with a password from its own mail"
)

# A message's disposition, and the cases it left as stored: none, one, or one
# per PO of a mail with several (ticket 19), the disposition's first first.
type _Processed = tuple[MessageDisposition, tuple[OrderCase | QuoteCase, ...]]


@dataclass(frozen=True)
class InboxQueries:
    """What arrived, and each message's disposition."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    inbox: InboxPort
    # The words a routed message's hand-off is written with (ticket 33),
    # the tenant's own where it has a version (ticket 36).
    handoffs: HandoffCopyPort
    # Whose address a routed message's owner is, in a tenant that narrows reads.
    directory: MemberDirectoryPort

    async def messages(self, context: AccessContext) -> list[InboxMessageView]:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type="sales_message")
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            logged = {m.disposition.message_id: m for m in await work.messages.list_all()}
            jobs = {job.message_id: job for job in await work.jobs.list_all()}
            # In a tenant that narrows reads, a message is shown as its case
            # is, and one routed to a person as that person's (2026-10-28).
            hidden = (
                set()
                if context.visible_owners is None
                else {
                    *(
                        s.case.case_id
                        for s in await work.orders.list_all()
                        if not seen_by(context, CaseKind.ORDER, s)
                    ),
                    *(
                        s.case.case_id
                        for s in await work.quotes.list_all()
                        if not seen_by(context, CaseKind.QUOTE, s)
                    ),
                }
            )
            numbers = await _offered_numbers(work, logged.values(), hidden)
        copy = (
            await self.handoffs.handoff_copy(scope)
            if any(m.disposition.handoff is not None for m in logged.values())
            else None
        )
        members = (
            {}
            if context.visible_owners is None
            else await members_by_address(self.directory, context)
        )
        outgoing = await outgoing_in(self.directory, context)
        views = []
        for message in await self.inbox.list_messages(scope):
            seen = logged.get(message.message_id)
            if seen is not None and not _shown(context, seen.disposition, hidden, members):
                continue
            # Only a message no flow processed is one Sales sent: one
            # processed before the rule keeps what it became.
            disposition = (
                message_disposition(seen.disposition, seen.processed_at, seen.handled, numbers)
                if seen is not None
                else message_disposition(
                    MessageDisposition.pending(message.message_id),
                    None,
                    outgoing=outgoing(message),
                )
            )
            views.append(
                inbox_message(
                    message, disposition, self._draft(seen, copy), jobs.get(message.message_id)
                )
            )
        return views

    @staticmethod
    def _draft(seen: LoggedMessage | None, copy: HandoffCopy | None) -> HandoffDraftView | None:
        """A routed message's hand-off, written from the template: the
        values code kept, empty where it kept none, for Sales to fill."""
        if seen is None or seen.disposition.handoff is None:
            return None
        disposition = seen.disposition
        assert disposition.handoff is not None and copy is not None  # read above
        written = render(
            disposition.handoff,
            copy,
            customer_code=disposition.customer_code or "",
            message_id=disposition.message_id,
        )
        return HandoffDraftView(
            to=written.to,
            subject=written.subject,
            body=written.body,
            template_ref=written.template_ref,
        )


async def _offered_numbers(
    work: SalesUnitOfWork, logged: Iterable[LoggedMessage], hidden: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """What each case a routed reply still open is offered goes by (ticket
    24), and each case of a mail with several POs (ticket 19): the PO's
    number, or the request's; none for a case the caller does not see."""
    named: list[tuple[CaseKind, uuid.UUID]] = []
    for entry in logged:
        disposition = entry.disposition
        if disposition.more_cases:
            named += [(CaseKind.ORDER, case_id) for case_id in disposition.case_ids]
        if entry.handled is None:
            named += [(c.case_kind, c.case_id) for c in disposition.thread_cases]
    numbers: dict[uuid.UUID, str] = {}
    for kind, case_id in named:
        if case_id in hidden or case_id in numbers:
            continue
        if kind is CaseKind.ORDER:
            order = await work.orders.get(case_id)
            if order is not None:
                numbers[case_id] = order.case.header.po_no
        else:
            quote = await work.quotes.get(case_id)
            if quote is not None:
                numbers[case_id] = quote.case.request.reference
    return numbers


async def members_by_address(
    directory: MemberDirectoryPort, context: AccessContext
) -> dict[str, uuid.UUID]:
    """The workspace's members by mail address, lower-cased: how the Sales PIC
    master data names by address becomes a person, for the case assigned to
    them and for the routed message that is theirs."""
    return {
        member.email.lower(): member.user_id
        for member in await directory.list_members(context)
        if member.email is not None
    }


async def own_address(directory: MemberDirectoryPort, context: AccessContext) -> str | None:
    """The caller's own sign-in address, lower-cased, as the workspace's
    directory holds it: the mailbox a mail they send goes from, and the
    sender of a PO they upload (ticket 18). None when they have none."""
    members = await directory.list_members(context)
    me = next((m for m in members if m.user_id == context.principal_id), None)
    return me.email.lower() if me is not None and me.email else None


def _shown(
    context: AccessContext,
    disposition: MessageDisposition,
    hidden: set[uuid.UUID],
    members: dict[str, uuid.UUID],
) -> bool:
    """A message on a case the caller does not see is not shown, nor one
    routed to a person outside the caller's `visible_owners`; a team's (the
    pool's, `role:<key>`) is everyone's.

    A routed message's owner is the customer's Sales PIC as master data holds
    it, an address (``members`` resolves it). An address no member holds is
    nobody's, so the message is every PIC's to pick up, as a case with such a
    PIC is unassigned (`InboxProcessing._assignee`): hiding it would show it
    to no one."""
    if disposition.case_id is not None:
        # A mail on several cases (ticket 19) is shown to whoever sees one.
        return any(case_id not in hidden for case_id in disposition.case_ids)
    owners, owner = context.visible_owners, disposition.owner
    if owners is None or owner is None or owner.startswith("role:"):
        return True
    person = members.get(owner.lower())
    return person is None or person in owners


logger = logging.getLogger(__name__)


class SourceWarmPort(Protocol):
    """Reads a case's pages and sheets into the source cache as DW1 opens it
    (`SourceService.warm`), so the person who opens the source next waits for
    no file."""

    async def warm(self, scope: SalesScope, case: OrderCase | QuoteCase) -> None: ...


@dataclass(frozen=True)
class InboxProcessing:
    """DW1's processing of the mailbox: the step a DW1 run takes.

    Not mounted on a route: "DW xử lý" starts a run (`Dw1Runs.process`), and
    the run calls this, so every message DW1 processes is counted against the
    tenant's plan where a run begins, whatever door started it.
    """

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    inbox: InboxPort
    catalog: SalesCatalogPort
    intake: OrderIntake
    quotes: QuotationService
    directory: MemberDirectoryPort
    decisions: PendingDecisionsPort
    release_manifest_ref: str | None
    spans: SalesSpans
    sources: SourceWarmPort

    async def process(
        self, context: AccessContext, message_id: str, *, run: RunContext
    ) -> MessageDispositionView:
        """One message processed by DW1, at the caller's request, in ``run``."""
        await self._authorize(context, message_id)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            await require_running(work)
            existing = await work.messages.get(message_id)
        if existing is not None and existing.kind in ON_A_CASE:
            raise ConflictError(
                "the message is already on a case",
                details={"message_id": message_id, "disposition": existing.kind.value},
            )
        outgoing = await outgoing_in(self.directory, context)
        # The message's model calls, timed for its step rows (slice 3).
        with recording_model_calls():
            return await self._process(context, scope, message_id, run, outgoing)

    async def process_all(
        self, context: AccessContext, *, run: RunContext
    ) -> list[MessageDispositionView]:
        """Every message still without a disposition, oldest first."""
        await self._authorize(context, None)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            await require_running(work)
            done = {m.disposition.message_id for m in await work.messages.list_all()}
        outgoing = await outgoing_in(self.directory, context)
        results = []
        for message in await self.inbox.list_messages(scope):
            # A message Sales sent is the mailbox lane's to take up, and only
            # where its thread intents are read (`InboxLane`).
            if message.message_id not in done and not outgoing(message):
                with recording_model_calls():
                    results.append(
                        await self._process(context, scope, message.message_id, run, outgoing)
                    )
        return results

    # ------------------------------------------------------------- helpers --

    async def _authorize(self, context: AccessContext, message_id: str | None) -> None:
        await self.gate.require(
            context,
            SalesScopes.INBOX_PROCESS,
            resource_type="sales_message",
            resource_id=message_id,
        )

    async def _process(
        self,
        context: AccessContext,
        scope: SalesScope,
        message_id: str,
        run: RunContext,
        outgoing: Callable[[InboundMessage], bool],
    ) -> MessageDispositionView:
        started = time.perf_counter()
        message = await self.inbox.get_message(scope, message_id)
        if message is None:
            raise NotFoundError("no such message", details={"message_id": message_id})
        ingest = self.clock.now()
        async with self.uow(scope) as work:
            processed = await work.messages.get(message_id) is not None
        if not processed and outgoing(message):
            # Sales' own mail (ticket 25): never a case, a route or a value.
            await self._sent(context, scope, message, ingest, run)
            return message_disposition(MessageDisposition.pending(message_id), None, outgoing=True)
        classified = await self.intake.classify(scope, message, run=run, now=ingest)
        if classified.retry:
            # The model gave no usable answer and the message is young enough
            # to try again: it stays not yet processed, and nothing is written.
            return message_disposition(MessageDisposition.pending(message_id), None)
        kind, reading = classified.kind, classified.reading
        if kind is MessageKind.QUOTE_REQUEST:
            disposition, cases = await self._quote_request(
                context, scope, message_id, ingest, run, reading
            )
        elif kind is MessageKind.DESIGN_REPLY:
            disposition, cases = await self._design_reply(
                context, scope, message_id, ingest, run, reading
            )
        else:
            assert kind not in QUOTATION_KINDS
            disposition, cases = await self._order(context, scope, message, ingest, run, classified)
        # Ids, codes and counts only (`dw_sales.application.telemetry`).
        self.spans.emit(
            SalesSpan.MESSAGE_PROCESSED,
            {
                "dw.tenant_id": context.tenant_id,
                "dw.workspace_id": context.workspace_id,
                "sales.disposition": disposition.kind,
                "sales.routing_reason": disposition.reason,
                **({} if not cases else case_attributes(cases[0])),
                "sales.cases": len(cases),
                "sales.duration_ms": (time.perf_counter() - started) * 1000,
            },
        )
        for case in cases:
            await self._warm(scope, case)
        return message_disposition(disposition, ingest)

    async def _sent(
        self,
        context: AccessContext,
        scope: SalesScope,
        message: InboundMessage,
        ingest: datetime,
        run: RunContext,
    ) -> None:
        """A message Sales sent, taken up once (`outgoing.py`): what a model
        reads it does where the tenant's rules ask (`OrderIntake.read_sent`),
        kept beside it with its step row and audit row. It has no
        disposition: nothing is opened, routed or changed."""
        async with self.uow(scope) as work:
            if await work.sent.get(message.message_id) is not None:
                raise ConflictError(
                    "DW1 already processed this message Sales sent",
                    details={"message_id": message.message_id, "rule": "sent_message_already_read"},
                )
        reading = await self.intake.read_sent(scope, message, run=run)
        async with self.uow(scope) as work:
            await require_running(work)
            await work.sent.record(SentRead(message.message_id, ingest, reading))
            await work.step_activity.append(
                sent_outcomes(
                    message.message_id,
                    reading,
                    model_calls(),
                    at=self.clock.now(),
                    new_id=self.ids.new_uuid,
                )
            )
            await work.audit.append(
                AuditEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    actor_id=UserId(context.principal_id),
                    action="sales.message.processed",
                    resource_type="sales_message",
                    resource_id=message.message_id,
                    run_id=run.run_id,
                    occurred_at=self.clock.now(),
                    details={
                        "outgoing": True,
                        "reading": "not_read" if reading is None else reading.outcome,
                        "actor_kind": "worker",
                        "worker_id": DW1_WORKER_ID,
                        "worker_version": DW1_WORKER_VERSION,
                    },
                )
            )
            await work.commit()

    async def _warm(self, scope: SalesScope, case: OrderCase | QuoteCase) -> None:
        # A speed-up, never a step: the case is stored and its disposition
        # recorded before this, and a page that cannot be read ahead is read
        # when someone opens it, as before.
        try:
            await self.sources.warm(scope, case)
        except Exception as failed:
            logger.warning(
                "reading case %s's sources ahead failed: %s", case.case_id, type(failed).__name__
            )

    async def _order(
        self,
        context: AccessContext,
        scope: SalesScope,
        message: InboundMessage,
        ingest: datetime,
        run: RunContext,
        classified: Classification,
    ) -> _Processed:
        outcome = await self.intake.process(scope, message, run=run, classified=classified)
        disposition = outcome.disposition
        assert disposition is not None  # quotation kinds are handled above
        stored_cases: list[OrderCase] = []
        revised_from: list[tuple[OrderCase, OrderCase]] = []
        async with self.uow(scope) as work:
            await require_running(work)
            # Every case of the message in this one transaction, with the
            # disposition that is the message's idempotency key: a mail
            # processed twice opens no second set (ticket 19).
            for case in outcome.cases:
                stored = await work.orders.get(case.case_id)
                if stored is None:
                    case = await self._open_order(work, context, case, run)
                else:
                    revised = worker_event("order.revised", context, self.clock.now())
                    await save_order(
                        work, context, self.ids, stored.case, case, revised, run_id=run.run_id
                    )
                    case = await self._start_review(work, context, case, run)
                    revised_from.append((stored.case, case))
                stored_cases.append(case)
            if outcome.learned is not None:
                # The layout the case was read through, in force with it.
                await keep_learned(
                    work, self.ids, self.clock, context, outcome.learned, run_id=run.run_id
                )
            await self._record(work, context, disposition, ingest, run, cases=stored_cases)
            await work.commit()
        for before, case in revised_from:
            # A revision of an order awaiting its cross-check: that check
            # was of the revision it replaced.
            await withdraw_if_left(self.decisions, context, before, case)
        return disposition, tuple(stored_cases)

    async def _open_order(
        self, work: SalesUnitOfWork, context: AccessContext, case: OrderCase, run: RunContext
    ) -> OrderCase:
        origin = CaseOrigin(
            assigned_to=await self._assignee(context, case.customer_code),
            release_manifest_ref=self.release_manifest_ref,
        )
        event = worker_event("order.checked", context, self.clock.now())
        await work.orders.add(case, origin, event)
        await work.audit.append(
            audit_row(
                context,
                self.ids,
                case_kind=CaseKind.ORDER,
                case_id=case.case_id,
                case_version=case.case_version,
                from_status=None,
                to_status=case.status.value,
                event=event,
                run_id=run.run_id,
            )
        )
        return await self._start_review(work, context, case, run)

    async def _start_review(
        self, work: SalesUnitOfWork, context: AccessContext, case: OrderCase, run: RunContext
    ) -> OrderCase:
        """DW1 hands a checked case to the PIC's self-check; the case as stored."""
        if case.status is not OrderStatus.CHECKED:
            return case
        event = worker_event("order.review_started", context, self.clock.now())
        reviewed = case.start_review()
        await save_order(work, context, self.ids, case, reviewed, event, run_id=run.run_id)
        return reviewed

    async def _quote_request(
        self,
        context: AccessContext,
        scope: SalesScope,
        message_id: str,
        ingest: datetime,
        run: RunContext,
        reading: IntentReading | None,
    ) -> _Processed:
        try:
            case = await self.quotes.open_case(scope, message_id, self.ids.new_uuid(), run=run)
        except RequestNotExtractedError as refused:
            reason = (
                RoutingReason.CUSTOMER_UNKNOWN
                if refused.reason == "customer_unknown"
                else RoutingReason.ATTACHMENT_UNREADABLE
            )
            routed = await self._routed(
                context, scope, message_id, reason, refused.reason, ingest, run, reading
            )
            return routed, ()
        except QuoteFileUnreadableError as refused:
            detail = str(refused.details.get("problem", "unreadable"))
            routed = await self._routed(
                context,
                scope,
                message_id,
                RoutingReason.ATTACHMENT_UNREADABLE,
                detail,
                ingest,
                run,
                reading,
            )
            return routed, ()
        disposition = MessageDisposition(
            message_id=message_id,
            kind=DispositionKind.CASE_CREATED,
            case_kind=CaseKind.QUOTE,
            case_id=case.case_id,
            customer_code=case.customer_code,
            reading=reading,
        )
        async with self.uow(scope) as work:
            await require_running(work)
            origin = CaseOrigin(
                assigned_to=await self._assignee(context, case.customer_code),
                release_manifest_ref=self.release_manifest_ref,
            )
            event = worker_event("quote.received", context, self.clock.now())
            await work.quotes.add(case, origin, event)
            await work.audit.append(
                audit_row(
                    context,
                    self.ids,
                    case_kind=CaseKind.QUOTE,
                    case_id=case.case_id,
                    case_version=case.case_version,
                    from_status=None,
                    to_status=case.status.value,
                    event=event,
                    run_id=run.run_id,
                )
            )
            # A complete request has its YCBG drafted by DW1 at once: Sales
            # only enters it in Bravo and records the number (2026-10-28).
            if case.ready_for_ycbg:
                drafted = case.draft_ycbg()
                event = worker_event("quote.ycbg_drafted", context, self.clock.now())
                await save_quote(work, context, self.ids, case, drafted, event, run_id=run.run_id)
                case = drafted
            await self._record(work, context, disposition, ingest, run, cases=(case,))
            await work.commit()
        return disposition, (case,)

    async def _design_reply(
        self,
        context: AccessContext,
        scope: SalesScope,
        message_id: str,
        ingest: datetime,
        run: RunContext,
        reading: IntentReading | None,
    ) -> _Processed:
        try:
            outcome = await self.quotes.take_design_reply(scope, message_id)
        except (NotADesignReplyError, QuoteFileUnreadableError):
            routed = await self._routed(
                context,
                scope,
                message_id,
                RoutingReason.ATTACHMENT_UNREADABLE,
                "no single Design reply could be read",
                ingest,
                run,
                reading,
            )
            return routed, ()
        disposition = outcome.disposition
        if reading is not None:
            disposition = MessageDisposition.model_validate(
                {**disposition.model_dump(), "reading": reading}
            )
        replied: QuoteCase | None = None
        async with self.uow(scope) as work:
            await require_running(work)
            if isinstance(outcome, ReplyAttached):
                stored = await work.quotes.get(outcome.case.case_id)
                if stored is None:
                    raise NotFoundError(
                        "no such quote case", details={"case_id": str(outcome.case.case_id)}
                    )
                event = worker_event("quote.design_replied", context, self.clock.now())
                replied = _replied(stored.case, outcome)
                await save_quote(
                    work, context, self.ids, stored.case, replied, event, run_id=run.run_id
                )
            await self._record(work, context, disposition, ingest, run, cases=_given(replied))
            await work.commit()
        return disposition, _given(replied)

    async def _routed(
        self,
        context: AccessContext,
        scope: SalesScope,
        message_id: str,
        reason: RoutingReason,
        detail: str,
        ingest: datetime,
        run: RunContext,
        reading: IntentReading | None,
    ) -> MessageDisposition:
        disposition = MessageDisposition(
            message_id=message_id,
            kind=DispositionKind.ROUTED_TO_SALES,
            reason=reason,
            detail=detail[:500],
            owner=SALES_PIC_POOL,
            reading=reading,
        )
        async with self.uow(scope) as work:
            await require_running(work)
            await self._record(work, context, disposition, ingest, run)
            await work.commit()
        return disposition

    async def _record(
        self,
        work: SalesUnitOfWork,
        context: AccessContext,
        disposition: MessageDisposition,
        ingest: datetime,
        run: RunContext,
        *,
        cases: Sequence[OrderCase | QuoteCase] = (),
    ) -> None:
        """The disposition and its audit row, which names the DW1 run that
        processed the message, as a decision's row names the run it resumed;
        and what each model step did for the message (``cases``: the cases as
        stored, which hold the stamps of the steps that read into them), so
        the rows commit or roll back with what they describe."""
        await work.messages.record(disposition, ingest)
        await work.step_activity.append(
            outcomes_of(
                disposition,
                cases,
                model_calls(),
                steps_by_prompt=STEPS_BY_PROMPT,
                at=self.clock.now(),
                new_id=self.ids.new_uuid,
            )
        )
        details: dict[str, object] = {
            "disposition": disposition.kind.value,
            "actor_kind": "worker",
            "worker_id": DW1_WORKER_ID,
            "worker_version": DW1_WORKER_VERSION,
        }
        if disposition.reason is not None:
            details["reason"] = disposition.reason.value
        if disposition.reason is RoutingReason.MALWARE_DETECTED:
            # Which attachment and which signature (ticket 25); the detail is
            # built by the intake from ids and signature names, never bytes.
            details["malware"] = disposition.detail
        opened = next(
            (c for c in cases if isinstance(c, OrderCase) and c.document.opened_with_password),
            None,
        )
        if opened is not None:
            # That it was opened, and with what kind of password: never which
            # one (ticket 17). The detail is code's sentence.
            details["encrypted_file"] = (
                f"{opened.document.attachment_id}: {OPENED_WITH_MAIL_PASSWORD}"
            )
        elif disposition.reason is RoutingReason.ATTACHMENT_LOCKED:
            details["encrypted_file"] = disposition.detail
        if disposition.case_id is not None and disposition.case_kind is not None:
            details |= {
                "case_kind": disposition.case_kind.value,
                "case_id": str(disposition.case_id),
            }
            if disposition.more_cases:
                # The mail's other POs' cases (ticket 19): ids only.
                details["more_case_ids"] = [str(c) for c in disposition.more_cases]
        await work.audit.append(
            AuditEvent(
                id=self.ids.new_uuid(),
                tenant_id=TenantId(context.tenant_id),
                workspace_id=WorkspaceId(context.workspace_id),
                actor_id=UserId(context.principal_id),
                action="sales.message.processed",
                resource_type="sales_message",
                resource_id=disposition.message_id,
                run_id=run.run_id,
                occurred_at=self.clock.now(),
                details=details,
            )
        )

    async def _assignee(self, context: AccessContext, customer_code: str) -> uuid.UUID | None:
        """The user the customer's Sales PIC address resolves to in this
        workspace, or None: an unassigned case is every PIC's to pick up."""
        customer = (await self.catalog.customer_by_code(sales_scope(context), customer_code)).data
        if customer is None or customer.sales_pic is None:
            return None
        members = await members_by_address(self.directory, context)
        return members.get(customer.sales_pic.lower())


def _given[T](case: T | None) -> tuple[T, ...]:
    return () if case is None else (case,)


def _replied(stored: QuoteCase, outcome: ReplyAttached) -> QuoteCase:
    """The reply on the case as stored: the matcher read the case through its
    own lookup, so it must be the same version the store holds now."""
    if outcome.case.case_version != stored.case_version + 1:
        raise ConflictError(
            "the case changed while the reply was matched",
            details={"case_id": str(stored.case_id)},
        )
    return outcome.case
