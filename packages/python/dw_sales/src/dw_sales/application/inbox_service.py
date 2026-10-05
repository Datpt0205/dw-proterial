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

import uuid
from dataclasses import dataclass
from datetime import datetime

from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import CaseOrigin, SalesUnitOfWork, SalesUnitOfWorkFactory
from dw_sales.application.order_intake import QUOTATION_KINDS, MessageKind, OrderIntake
from dw_sales.application.ports import InboxPort, MemberDirectoryPort, SalesCatalogPort, SalesScope
from dw_sales.application.quotation import (
    NotADesignReplyError,
    QuotationService,
    ReplyAttached,
    RequestNotExtractedError,
)
from dw_sales.application.quote_ports import QuoteFileUnreadableError
from dw_sales.application.support import (
    DW1_WORKER_ID,
    DW1_WORKER_VERSION,
    audit_row,
    save_order,
    save_quote,
    worker_event,
)
from dw_sales.application.views import (
    InboxMessageView,
    MessageDispositionView,
    inbox_message,
    message_disposition,
)
from dw_sales.domain.dispositions import (
    SALES_PIC_POOL,
    CaseKind,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
)
from dw_sales.domain.messages import InboundMessage
from dw_sales.domain.orders import OrderCase, OrderStatus
from dw_sales.domain.quotes import QuoteCase

_ON_A_CASE = frozenset({DispositionKind.CASE_CREATED, DispositionKind.ATTACHED_TO_CASE})


@dataclass(frozen=True)
class InboxService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    inbox: InboxPort
    catalog: SalesCatalogPort
    intake: OrderIntake
    quotes: QuotationService
    directory: MemberDirectoryPort
    release_manifest_ref: str | None

    async def messages(self, context: AccessContext) -> list[InboxMessageView]:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type="sales_message")
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            logged = {m.disposition.message_id: m for m in await work.messages.list_all()}
        views = []
        for message in await self.inbox.list_messages(scope):
            seen = logged.get(message.message_id)
            disposition = (
                message_disposition(seen.disposition, seen.processed_at)
                if seen is not None
                else message_disposition(MessageDisposition.pending(message.message_id), None)
            )
            views.append(inbox_message(message, disposition))
        return views

    async def process(self, context: AccessContext, message_id: str) -> MessageDispositionView:
        """One message processed by DW1, at the caller's request."""
        await self._authorize(context, message_id)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            await _running(work)
            existing = await work.messages.get(message_id)
        if existing is not None and existing.kind in _ON_A_CASE:
            raise ConflictError(
                "the message is already on a case",
                details={"message_id": message_id, "disposition": existing.kind.value},
            )
        return await self._process(context, scope, message_id)

    async def process_all(self, context: AccessContext) -> list[MessageDispositionView]:
        """Every message still without a disposition, oldest first."""
        await self._authorize(context, None)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            await _running(work)
            done = {m.disposition.message_id for m in await work.messages.list_all()}
        results = []
        for message in await self.inbox.list_messages(scope):
            if message.message_id not in done:
                results.append(await self._process(context, scope, message.message_id))
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
        self, context: AccessContext, scope: SalesScope, message_id: str
    ) -> MessageDispositionView:
        message = await self.inbox.get_message(scope, message_id)
        if message is None:
            raise NotFoundError("no such message", details={"message_id": message_id})
        ingest = self.clock.now()
        kind = await self.intake.classify(scope, message)
        if kind is MessageKind.QUOTE_REQUEST:
            disposition = await self._quote_request(context, scope, message_id, ingest)
        elif kind is MessageKind.DESIGN_REPLY:
            disposition = await self._design_reply(context, scope, message_id, ingest)
        else:
            assert kind not in QUOTATION_KINDS
            disposition = await self._order(context, scope, message, ingest)
        return message_disposition(disposition, ingest)

    async def _order(
        self, context: AccessContext, scope: SalesScope, message: InboundMessage, ingest: datetime
    ) -> MessageDisposition:
        outcome = await self.intake.process(scope, message)
        disposition = outcome.disposition
        assert disposition is not None  # quotation kinds are handled above
        case = outcome.case
        async with self.uow(scope) as work:
            await _running(work)
            if case is not None:
                stored = await work.orders.get(case.case_id)
                if stored is None:
                    await self._open_order(work, context, case)
                else:
                    revised = worker_event("order.revised", context, self.clock.now())
                    await save_order(work, context, self.ids, stored.case, case, revised)
                    await self._start_review(work, context, case)
            await self._record(work, context, disposition, ingest)
            await work.commit()
        return disposition

    async def _open_order(
        self, work: SalesUnitOfWork, context: AccessContext, case: OrderCase
    ) -> None:
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
            )
        )
        await self._start_review(work, context, case)

    async def _start_review(
        self, work: SalesUnitOfWork, context: AccessContext, case: OrderCase
    ) -> None:
        """DW1 hands a checked case to the PIC's self-check."""
        if case.status is not OrderStatus.CHECKED:
            return
        event = worker_event("order.review_started", context, self.clock.now())
        await save_order(work, context, self.ids, case, case.start_review(), event)

    async def _quote_request(
        self, context: AccessContext, scope: SalesScope, message_id: str, ingest: datetime
    ) -> MessageDisposition:
        try:
            case = await self.quotes.open_case(scope, message_id, self.ids.new_uuid())
        except RequestNotExtractedError as refused:
            reason = (
                RoutingReason.CUSTOMER_UNKNOWN
                if refused.reason == "customer_unknown"
                else RoutingReason.ATTACHMENT_UNREADABLE
            )
            return await self._routed(context, scope, message_id, reason, refused.reason, ingest)
        except QuoteFileUnreadableError as refused:
            detail = str(refused.details.get("problem", "unreadable"))
            return await self._routed(
                context, scope, message_id, RoutingReason.ATTACHMENT_UNREADABLE, detail, ingest
            )
        disposition = MessageDisposition(
            message_id=message_id,
            kind=DispositionKind.CASE_CREATED,
            case_kind=CaseKind.QUOTE,
            case_id=case.case_id,
            customer_code=case.customer_code,
        )
        async with self.uow(scope) as work:
            await _running(work)
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
                )
            )
            await self._record(work, context, disposition, ingest)
            await work.commit()
        return disposition

    async def _design_reply(
        self, context: AccessContext, scope: SalesScope, message_id: str, ingest: datetime
    ) -> MessageDisposition:
        try:
            outcome = await self.quotes.take_design_reply(scope, message_id)
        except (NotADesignReplyError, QuoteFileUnreadableError):
            return await self._routed(
                context,
                scope,
                message_id,
                RoutingReason.ATTACHMENT_UNREADABLE,
                "no single Design reply could be read",
                ingest,
            )
        disposition = outcome.disposition
        async with self.uow(scope) as work:
            await _running(work)
            if isinstance(outcome, ReplyAttached):
                stored = await work.quotes.get(outcome.case.case_id)
                if stored is None:
                    raise NotFoundError(
                        "no such quote case", details={"case_id": str(outcome.case.case_id)}
                    )
                event = worker_event("quote.design_replied", context, self.clock.now())
                await save_quote(
                    work, context, self.ids, stored.case, _replied(stored.case, outcome), event
                )
            await self._record(work, context, disposition, ingest)
            await work.commit()
        return disposition

    async def _routed(
        self,
        context: AccessContext,
        scope: SalesScope,
        message_id: str,
        reason: RoutingReason,
        detail: str,
        ingest: datetime,
    ) -> MessageDisposition:
        disposition = MessageDisposition(
            message_id=message_id,
            kind=DispositionKind.ROUTED_TO_SALES,
            reason=reason,
            detail=detail[:500],
            owner=SALES_PIC_POOL,
        )
        async with self.uow(scope) as work:
            await _running(work)
            await self._record(work, context, disposition, ingest)
            await work.commit()
        return disposition

    async def _record(
        self,
        work: SalesUnitOfWork,
        context: AccessContext,
        disposition: MessageDisposition,
        ingest: datetime,
    ) -> None:
        await work.messages.record(disposition, ingest)
        details: dict[str, object] = {
            "disposition": disposition.kind.value,
            "actor_kind": "worker",
            "worker_id": DW1_WORKER_ID,
            "worker_version": DW1_WORKER_VERSION,
        }
        if disposition.reason is not None:
            details["reason"] = disposition.reason.value
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


async def _running(work: SalesUnitOfWork) -> None:
    """409 while DW1 is paused in the workspace, naming who paused it and when."""
    state = await work.worker.state()
    if state.paused:
        raise ConflictError(
            "DW1 đang tạm dừng: Trưởng bộ phận Sales mở lại trước khi xử lý tiếp",
            details={
                "rule": "worker_paused",
                "paused_by": str(state.changed_by),
                "paused_at": state.changed_at.isoformat() if state.changed_at else "",
            },
        )
