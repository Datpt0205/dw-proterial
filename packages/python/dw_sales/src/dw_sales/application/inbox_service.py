"""The mailbox through the API: what arrived, and "DW xử lý" on it.

Processing is DW1's work, started by a person (spec decision 5, the stop
control): it needs `sales.inbox.process`, it is refused while DW1 is paused
in the workspace (409 naming who paused and when), and everything it writes
is DW1's event (`actor_kind = worker`) with the person as `initiated_by`.

Every message ends in exactly one disposition (spec decision 10):

- a PO opens an order case, or joins the case of the PO it revises
  (`OrderIntake`), and DW1 hands the case to the PIC's self-check;
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

import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import (
    CaseOrigin,
    LoggedMessage,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
)
from dw_sales.application.handoffs import HandoffCopy, HandoffCopyPort, render
from dw_sales.application.order_intake import (
    QUOTATION_KINDS,
    Classification,
    MessageKind,
    OrderIntake,
)
from dw_sales.application.ports import InboxPort, MemberDirectoryPort, SalesCatalogPort, SalesScope
from dw_sales.application.quotation import (
    NotADesignReplyError,
    QuotationService,
    ReplyAttached,
    RequestNotExtractedError,
)
from dw_sales.application.quote_ports import QuoteFileUnreadableError
from dw_sales.application.runs import PendingDecisionsPort, withdraw_if_left
from dw_sales.application.support import (
    DW1_WORKER_ID,
    DW1_WORKER_VERSION,
    audit_row,
    save_order,
    save_quote,
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
from dw_sales.domain.dispositions import (
    SALES_PIC_POOL,
    CaseKind,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
)
from dw_sales.domain.message_intent import IntentReading
from dw_sales.domain.messages import InboundMessage
from dw_sales.domain.orders import OrderCase, OrderStatus
from dw_sales.domain.quotes import QuoteCase

# A message on a case is not processed again ("DW xử lý lại" is for a routed one).
ON_A_CASE = frozenset({DispositionKind.CASE_CREATED, DispositionKind.ATTACHED_TO_CASE})

# A message's disposition, and the case it left as stored, if it is on one.
type _Processed = tuple[MessageDisposition, OrderCase | QuoteCase | None]


@dataclass(frozen=True)
class InboxQueries:
    """What arrived, and each message's disposition."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    inbox: InboxPort
    # The words a routed message's hand-off is written with (ticket 33),
    # the tenant's own where it has a version (ticket 36).
    handoffs: HandoffCopyPort

    async def messages(self, context: AccessContext) -> list[InboxMessageView]:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type="sales_message")
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            logged = {m.disposition.message_id: m for m in await work.messages.list_all()}
            jobs = {job.message_id: job for job in await work.jobs.list_all()}
        copy = (
            await self.handoffs.handoff_copy(scope)
            if any(m.disposition.handoff is not None for m in logged.values())
            else None
        )
        views = []
        for message in await self.inbox.list_messages(scope):
            seen = logged.get(message.message_id)
            disposition = (
                message_disposition(seen.disposition, seen.processed_at)
                if seen is not None
                else message_disposition(MessageDisposition.pending(message.message_id), None)
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
        return await self._process(context, scope, message_id, run)

    async def process_all(
        self, context: AccessContext, *, run: RunContext
    ) -> list[MessageDispositionView]:
        """Every message still without a disposition, oldest first."""
        await self._authorize(context, None)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            await require_running(work)
            done = {m.disposition.message_id for m in await work.messages.list_all()}
        results = []
        for message in await self.inbox.list_messages(scope):
            if message.message_id not in done:
                results.append(await self._process(context, scope, message.message_id, run))
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
        self, context: AccessContext, scope: SalesScope, message_id: str, run: RunContext
    ) -> MessageDispositionView:
        started = time.perf_counter()
        message = await self.inbox.get_message(scope, message_id)
        if message is None:
            raise NotFoundError("no such message", details={"message_id": message_id})
        ingest = self.clock.now()
        classified = await self.intake.classify(scope, message, run=run, now=ingest)
        if classified.retry:
            # The model gave no usable answer and the message is young enough
            # to try again: it stays not yet processed, and nothing is written.
            return message_disposition(MessageDisposition.pending(message_id), None)
        kind, reading = classified.kind, classified.reading
        if kind is MessageKind.QUOTE_REQUEST:
            disposition, case = await self._quote_request(
                context, scope, message_id, ingest, run, reading
            )
        elif kind is MessageKind.DESIGN_REPLY:
            disposition, case = await self._design_reply(
                context, scope, message_id, ingest, run, reading
            )
        else:
            assert kind not in QUOTATION_KINDS
            disposition, case = await self._order(context, scope, message, ingest, run, classified)
        # Ids, codes and counts only (`dw_sales.application.telemetry`).
        self.spans.emit(
            SalesSpan.MESSAGE_PROCESSED,
            {
                "dw.tenant_id": context.tenant_id,
                "dw.workspace_id": context.workspace_id,
                "sales.disposition": disposition.kind,
                "sales.routing_reason": disposition.reason,
                **({} if case is None else case_attributes(case)),
                "sales.duration_ms": (time.perf_counter() - started) * 1000,
            },
        )
        return message_disposition(disposition, ingest)

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
        case = outcome.case
        before: OrderCase | None = None
        async with self.uow(scope) as work:
            await require_running(work)
            if case is not None:
                stored = await work.orders.get(case.case_id)
                if stored is None:
                    case = await self._open_order(work, context, case, run)
                else:
                    before = stored.case
                    revised = worker_event("order.revised", context, self.clock.now())
                    await save_order(
                        work, context, self.ids, stored.case, case, revised, run_id=run.run_id
                    )
                    case = await self._start_review(work, context, case, run)
            await self._record(work, context, disposition, ingest, run)
            await work.commit()
        if before is not None and case is not None:
            # A revision of an order awaiting its cross-check: that check
            # was of the revision it replaced.
            await withdraw_if_left(self.decisions, context, before, case)
        return disposition, case

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
            return routed, None
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
            return routed, None
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
            await self._record(work, context, disposition, ingest, run)
            await work.commit()
        return disposition, case

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
            return routed, None
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
            await self._record(work, context, disposition, ingest, run)
            await work.commit()
        return disposition, replied

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
    ) -> None:
        """The disposition and its audit row, which names the DW1 run that
        processed the message, as a decision's row names the run it resumed."""
        await work.messages.record(disposition, ingest)
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
        if disposition.case_id is not None and disposition.case_kind is not None:
            details |= {
                "case_kind": disposition.case_kind.value,
                "case_id": str(disposition.case_id),
            }
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
        wanted = customer.sales_pic.lower()
        for member in await self.directory.list_members(context):
            if member.email is not None and member.email.lower() == wanted:
                return member.user_id
        return None


def _replied(stored: QuoteCase, outcome: ReplyAttached) -> QuoteCase:
    """The reply on the case as stored: the matcher read the case through its
    own lookup, so it must be the same version the store holds now."""
    if outcome.case.case_version != stored.case_version + 1:
        raise ConflictError(
            "the case changed while the reply was matched",
            details={"case_id": str(stored.case_id)},
        )
    return outcome.case
