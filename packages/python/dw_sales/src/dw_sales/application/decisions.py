"""What a DW1 run does, step by step, and the check of a decision before it counts.

The graph (`dw_sales.workflows.graph`) calls these and nothing else does:
they are not on the routes' bundle (`SalesServices`), so the only door to
processing the mailbox, submitting a quotation and recording a Bravo entry
is a run, which the runner counts against the tenant's plan where it begins.

A decision (approve or return a quotation, cross-check or return an order) is
made through the platform's approvals and reaches the case twice, through the
same code (`_decide`):

- **before it is recorded**, as this context's `ApprovalDecisionGuard`
  (`check`): with the decider's own verified context, without writing. A
  decision the case would refuse (a stale version, a source not opened, a
  blocking price finding without its reason, a maker) is refused while the
  approval is still undecided;
- **when the run resumes** (`apply`): the same transition, written, as the
  decider, linked to the run. A decision the case refuses here (it changed
  in the instant between, say) is still recorded on the platform; the order
  then says it was not applied and why, the audit names the run, the
  approval and the reason, and its cross-check can be raised again
  (ticket 14).

The decide scope is not asked for here: the platform requires
`approvals.decide` and the scope the approval was stamped with in its
`required_scope` column (`DECIDE_SCOPES`), and the guard refuses an approval
stamped with any other. That is what lets `apply` hand the approver the
approve capability without their access context: nobody reaches `apply` but
through `ApproveAndResumeService.decide`, which checked it.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from pydantic import ValidationError

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import (
    ConflictError,
    DomainError,
    DWError,
    NotFoundError,
    PermissionDeniedError,
)
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.domain.approval import ApprovalRequest, ApprovalStatus, decided_event_type
from dw_sales.application.access import Gate, SalesScopes, order_actor, sales_scope
from dw_sales.application.bravo_sales_orders import (
    BravoReadBack,
    ReadBackUnitOfWorkFactory,
    require_bravo_agrees,
)
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.inbox_service import InboxProcessing
from dw_sales.application.order_quotes import OrderQuotes
from dw_sales.application.ports import NotificationSenderPort
from dw_sales.application.quotation import QuotationService
from dw_sales.application.quotes_service import parse_finding_key
from dw_sales.application.runs import (
    DECIDE_SCOPES,
    DecisionAsked,
    DecisionGiven,
    DecisionType,
    awaiting,
)
from dw_sales.application.source import require_served
from dw_sales.application.support import (
    audit_row,
    decided,
    person_event,
    same_version,
    save_order,
    save_quote,
    stored_order,
    stored_quote,
    worker_event,
)
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import Actor, OrderCase, OrderStatus, UnappliedDecision
from dw_sales.domain.quotes import QuoteActor, QuoteCapability, QuoteCase, QuoteStatus

_QUOTE = "sales_quote_case"
_ORDER = "sales_order_case"
# The shape a case event's reason code takes (`CaseEvent.reason_code`).
_REASON_CODE = re.compile(r"[a-z_]{1,40}")


@dataclass(frozen=True, slots=True)
class _Decision:
    """A decision as `_decide` takes it, from the guard or from the run."""

    decider: AccessContext
    approve: bool
    comment: str
    reasons: Mapping[str, str]
    subject_version: int | None
    # Whether the decider may approve a quotation (`sales.quote.approve`).
    approves_quotes: bool
    # Whether the decider may approve one with an order as its Manager
    # (`sales.quote.manager_approve`, ticket 39).
    manages_quotes: bool = False


@dataclass(frozen=True)
class CaseDecisions:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    quotation: QuotationService
    inbox: InboxProcessing
    # The pricer is told when their quotation is approved (2026-10-28).
    notifications: NotificationSenderPort
    # Bravo's sales order read back (ticket 03): one that differs at the
    # version being cross-checked refuses "Kiểm chéo đạt".
    read_backs: ReadBackUnitOfWorkFactory
    # The order a quote was opened from has its lines checked again once the
    # quote is approved (ticket 09). None: nothing is checked here, and the
    # order waits for a person's "Kiểm tra lại".
    order_quotes: OrderQuotes | None = None

    # ------------------------------------------------------- DW xử lý --

    async def process(
        self, context: AccessContext, message_id: str | None, *, run: RunContext
    ) -> list[dict[str, str | None]]:
        """One message, or every one still without a disposition. What the
        run keeps of it: the disposition and the case, by id. A model call
        the processing makes is attributed to ``run`` (dw_sales ADR 0005)."""
        views = (
            [await self.inbox.process(context, message_id, run=run)]
            if message_id is not None
            else await self.inbox.process_all(context, run=run)
        )
        return [
            {
                "kind": view.kind,
                "case_kind": view.case_kind.value if view.case_kind else None,
                "case_id": str(view.case_id) if view.case_id else None,
            }
            for view in views
        ]

    # ---------------------------------------------- raised for decision --

    async def submit_quote(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        quote_no: str,
        run_id: uuid.UUID,
    ) -> DecisionAsked:
        """Step 8: the quotation document written from the decided terms,
        stamped with its hash, issued today. What the run then waits on."""
        await self.gate.require(
            context, SalesScopes.QUOTE_PREPARE, resource_type=_QUOTE, resource_id=str(case_id)
        )
        now, scope = self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_quote(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            submitted = await self.quotation.submit(
                scope,
                case,
                quote_no=quote_no,
                issued_on=await self.quotation.today(scope, now),
                by=context.principal_id,
                at=now,
            )
            event = person_event("quote.submitted", context, now)
            await save_quote(work, context, self.ids, case, submitted, event, run_id=run_id)
            await work.commit()
        return DecisionAsked.of_quote(submitted)

    async def record_bravo_entry(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        so_no: str | None,
        entry_compared: bool,
        run_id: uuid.UUID,
    ) -> DecisionAsked | None:
        """What brings the order to its cross-check, by the state it is in:
        the sales-order number and the statement that the Bravo entry was
        compared with the PO; on a revised order in Bravo, the change applied;
        on an order already in Bravo, its cross-check raised again ("Gửi kiểm
        chéo lại", ticket 14, which the case allows only its Bravo recorder or
        the head). The cross-check the run then waits on, unless the case's
        rules need none."""
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_ORDER, resource_id=str(case_id)
        )
        actor, now = order_actor(context, self.gate), self.clock.now()

        def step(case: OrderCase) -> tuple[OrderCase, str]:
            if case.status is OrderStatus.UPLOADED_TO_BRAVO:
                return case.resend_cross_check(actor), "order.cross_check_resent"
            if case.status is OrderStatus.CHANGE_REVIEW:
                applied = case.apply_change(actor, now, entry_compared=entry_compared)
                return applied, "order.bravo_recorded"
            if so_no is None:
                raise DomainError(
                    "a Bravo entry names its sales-order number",
                    details={"case_id": str(case.case_id), "field": "so_no"},
                )
            recorded = case.record_bravo_entry(so_no, actor, now, entry_compared=entry_compared)
            return recorded, "order.bravo_recorded"

        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            after, action = decided(lambda: step(case))
            field = "bravo_so_no" if action == "order.bravo_recorded" else None
            event = person_event(action, context, now, field=field)
            await save_order(work, context, self.ids, case, after, event, run_id=run_id)
            await work.commit()
        return DecisionAsked.of_order(after) if awaiting(after) is not None else None

    # ------------------------------------------------------- the decision --

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        """The decision as the case would take it, refused or not, unwritten.

        `ApprovalDecisionGuard` for every `sales.` approval: called by the
        platform after the decider's scope and the separation of duties,
        before the decision is recorded.
        """
        asked = _asked(request)
        await self._decide(
            asked,
            _Decision(
                decider=context,
                approve=decision.approve,
                comment=decision.comment,
                reasons=decision.reasons,
                subject_version=decision.subject_version,
                approves_quotes=self.gate.allows(context, SalesScopes.QUOTE_APPROVE),
                manages_quotes=self.gate.allows(context, SalesScopes.QUOTE_MANAGER_APPROVE),
            ),
            write=False,
        )

    async def apply(
        self,
        context: AccessContext,
        asked: DecisionAsked,
        given: DecisionGiven,
        *,
        run_id: uuid.UUID,
    ) -> str:
        """The decision on the case, as its decider, when the run resumes.

        ``context`` is the run's (its tenant and workspace); the decider is
        who the platform recorded, with no scope of their own here: the one
        this decision needed was required of them when they decided.
        """
        decider = context.model_copy(
            update={"principal_id": given.decided_by, "roles": frozenset(), "scopes": frozenset()}
        )
        try:
            return await self._decide(
                asked,
                _Decision(
                    decider=decider,
                    approve=given.approved,
                    comment=given.comment,
                    reasons=given.reasons,
                    subject_version=given.subject_version,
                    approves_quotes=asked.approval_type is DecisionType.QUOTE_APPROVAL,
                ),
                write=True,
                run_id=run_id,
            )
        except DWError as refused:
            # The platform has recorded the decision; the run ends failed.
            if asked.case_kind is CaseKind.ORDER:
                await self._not_applied(decider, asked, given, refused, run_id=run_id)
            raise

    async def _not_applied(
        self,
        decider: AccessContext,
        asked: DecisionAsked,
        given: DecisionGiven,
        refused: DWError,
        *,
        run_id: uuid.UUID,
    ) -> None:
        """The trace of a cross-check decision the case refused when the run
        applied it (ticket 14): the order says so while it still awaits its
        cross-check, and the audit row names the run, the approval and the
        reason code. Ids and codes only: the comment stays on the platform's
        decision record. Written by DW1, at the decider's decision."""
        rule = refused.details.get("rule")
        reason = rule if isinstance(rule, str) and _REASON_CODE.fullmatch(rule) else None
        reason = reason or refused.code.value
        now = self.clock.now()
        event = worker_event("order.decision_not_applied", decider, now, reason_code=reason)
        async with self.uow(sales_scope(decider)) as work:
            stored = await work.orders.get(asked.case_id)
            if stored is None:
                return
            case = stored.case
            if awaiting(case) is DecisionType.ORDER_CROSS_CHECK:
                after = case.decision_not_applied(
                    UnappliedDecision(
                        approval_id=given.approval_id,
                        run_id=run_id,
                        decided_by=given.decided_by,
                        approved=given.approved,
                        decided_on=given.subject_version,
                        reason_code=reason,
                        at=now,
                    )
                )
                await save_order(
                    work,
                    decider,
                    self.ids,
                    case,
                    after,
                    event,
                    run_id=run_id,
                    approval_id=given.approval_id,
                )
            else:
                # The case moved on (revised, say): nothing to say on it.
                await work.audit.append(
                    audit_row(
                        decider,
                        self.ids,
                        case_kind=CaseKind.ORDER,
                        case_id=case.case_id,
                        case_version=case.case_version,
                        from_status=case.status.value,
                        to_status=case.status.value,
                        event=event,
                        run_id=run_id,
                        approval_id=given.approval_id,
                    )
                )
            await work.commit()

    async def _decide(
        self,
        asked: DecisionAsked,
        decision: _Decision,
        *,
        write: bool,
        run_id: uuid.UUID | None = None,
    ) -> str:
        """One decision on the case the approval names; the event it writes."""
        if decision.subject_version is None:
            raise DomainError(
                "quyết định trên hồ sơ Sales nêu phiên bản hồ sơ đã xem: mở hồ sơ để quyết định",
                details={"field": "subject_version"},
            )
        decider, now = decision.decider, self.clock.now()
        # The guard reads as the decider, who must see the case; carrying out
        # a decision already taken acts for the workspace.
        seer = None if write else decider
        quoted: QuoteCase | None = None
        read_back: BravoReadBack | None = None
        if asked.case_kind is CaseKind.ORDER and decision.approve:
            async with self.read_backs(sales_scope(decider)) as backs:
                read_back = await backs.read_backs.get(asked.case_id)
        async with self.uow(sales_scope(decider)) as work:
            if asked.case_kind is CaseKind.QUOTE:
                quote = (await stored_quote(work, asked.case_id, viewer=seer)).case
                _still_waiting(quote, asked, decision.subject_version)
                quoted, action = self._on_quote(quote, asked, decision, now)
                if write:
                    event = person_event(action, decider, now)
                    await save_quote(work, decider, self.ids, quote, quoted, event, run_id=run_id)
                    if action == "quote.checked":
                        await work.approvals.add(manager_request(self.ids, decider, quoted))
            else:
                order = (await stored_order(work, asked.case_id, viewer=seer)).case
                _still_waiting(order, asked, decision.subject_version)
                # The cross-checker opened the original at this version
                # (spec decision 12), whichever way they decide.
                await require_served(work, decider.principal_id, order)
                if decision.approve:
                    require_bravo_agrees(read_back, order)
                ordered, action = _on_order(order, decision, now)
                if write:
                    event = person_event(action, decider, now)
                    await save_order(work, decider, self.ids, order, ordered, event, run_id=run_id)
            if write:
                await work.commit()
        if write and quoted is not None and action == "quote.approved":
            await tell_approved(self.notifications, decider, quoted)
            if self.order_quotes is not None:
                await self.order_quotes.resume(decider, quoted)
        return action

    @staticmethod
    def _on_quote(
        case: QuoteCase, asked: DecisionAsked, decision: _Decision, at: datetime
    ) -> tuple[QuoteCase, str]:
        held = {
            QuoteCapability.APPROVE: decision.approves_quotes,
            QuoteCapability.MANAGER_APPROVE: decision.manages_quotes,
        }
        actor = QuoteActor(
            user_id=decision.decider.principal_id,
            capabilities=frozenset(capability for capability, has in held.items() if has),
        )
        if not decision.approve:
            comment = decision.comment
            returned = decided(lambda: case.return_to_pricer(actor, at=at, reason=comment))
            return returned, "quote.returned"
        # A quote approval names its document: the hash the approver approves.
        sha = asked.document_sha256 or ""
        given = {parse_finding_key(key): reason for key, reason in decision.reasons.items()}
        if asked.approval_type is DecisionType.QUOTE_APPROVAL and case.needs_manager:
            # WIV-03-023 §4: with an order, the first level checks it and a
            # Manager approves it (ticket 39).
            checked = decided(
                lambda: case.check_for_manager(actor, at=at, document_sha256=sha, reasons=given)
            )
            return checked, "quote.checked"
        approved = decided(lambda: case.approve(actor, at=at, document_sha256=sha, reasons=given))
        return approved, "quote.approved"


def _on_order(case: OrderCase, decision: _Decision, at: datetime) -> tuple[OrderCase, str]:
    if decision.reasons:
        raise DomainError("a cross-check names no finding reasons", details={"field": "reasons"})
    actor = Actor(user_id=decision.decider.principal_id)
    if decision.approve:
        return case.cross_check(actor, at), "order.cross_checked"
    comment = decision.comment
    returned = decided(lambda: case.return_from_cross_check(comment, actor, at))
    return returned, "order.returned"


def _asked(request: ApprovalRequest) -> DecisionAsked:
    """The approval as this context raised it, or a refusal.

    Fails closed on a request this context would not have raised: its payload
    unreadable, its type not the one it says, or its decide scope not the one
    `DECIDE_SCOPES` names. A `sales.` request stamped with no scope at all
    would have been let through by `approvals.decide`; it stops here.
    """
    try:
        asked = DecisionAsked.model_validate(request.payload)
    except ValidationError:
        raise ConflictError(
            "the approval is not one DW1 raised", details={"approval_id": str(request.id)}
        ) from None
    if asked.approval_type.value != request.approval_type:
        raise ConflictError(
            "the approval is not one DW1 raised", details={"approval_id": str(request.id)}
        )
    # The column, not the payload: the column is what the platform's decision
    # enforced, and the two must name the same scope.
    if request.required_scope != DECIDE_SCOPES[asked.approval_type].value:
        raise PermissionDeniedError(
            "this approval is decided with the scope DW1 names for it",
            details={"approval_type": request.approval_type},
        )
    return asked


def _still_waiting(case: OrderCase | QuoteCase, asked: DecisionAsked, decided_on: int) -> None:
    """The case still waits on this decision, at the version the decider saw.

    A case that left the state (priced again, declined, revised) waits on
    nothing; a quotation re-submitted waits on another document. Either way
    this approval no longer applies. The version is the decider's, as on
    every Sales decision: what they were shown.
    """
    stale = awaiting(case) is not asked.approval_type or case.case_version < asked.case_version
    if isinstance(case, QuoteCase) and not stale:
        stale = case.submission is None or (
            case.submission.document_sha256 != asked.document_sha256
        )
    if stale:
        raise ConflictError(
            "hồ sơ không còn chờ quyết định này: yêu cầu duyệt đã hết hiệu lực",
            details={
                "case_id": str(case.case_id),
                "status": case.status.value,
                "rule": "decision_stale",
            },
        )
    same_version(case.case_id, case.case_version, decided_on)


# ----------------------------------------- the Manager's level (ticket 39) --

# The event a decided Manager's approval writes; the worker carries it out.
QUOTE_MANAGER_DECIDED: Final = decided_event_type(DecisionType.QUOTE_MANAGER.value)


def manager_request(ids: IdGenerator, checker: AccessContext, quote: QuoteCase) -> ApprovalRequest:
    """The Manager's run-less approval of a quotation the first level checked:
    raised by the checker in the check's own transaction, decided with
    `sales.quote.manager_approve`, its makers the pricer, the submitter and
    the checker (strict: none of them decides it)."""
    asked = DecisionAsked.of_manager(quote)
    return ApprovalRequest(
        id=ids.new_uuid(),
        tenant_id=TenantId(checker.tenant_id),
        workspace_id=WorkspaceId(checker.workspace_id),
        approval_type=asked.approval_type.value,
        requested_by=UserId(checker.principal_id),
        reason=asked.reason,
        payload=asked.payload(),
        required_scope=asked.required_scope,
    )


async def tell_approved(
    notifications: NotificationSenderPort, decider: AccessContext, quote: QuoteCase
) -> None:
    """Tell who priced and submitted it: print it to sign, or send it. No
    electronic signature: the signed copy comes back as an upload."""
    submission = quote.submission
    if submission is None:
        return
    recipients = sorted(
        {submission.priced_by, submission.submitted_by} - {decider.principal_id}, key=str
    )
    if not recipients:
        return
    await notifications.deliver(
        decider,
        recipients=recipients,
        source_key=f"sales.quote.approved:{quote.case_id}:{quote.case_version}",
        title=f"Báo giá {quote.request.reference} đã được duyệt",
        body=(
            "Tải tài liệu báo giá để in trình ký hoặc gửi khách. "
            "Bản đã ký có thể tải lên lại hồ sơ để gửi kèm."
        ),
        link=f"/sales/quotes/{quote.case_id}",
    )


# Words for a Manager's return when the decision's own comment is not on the
# event (the outbox carries ids only); the comment stays on the platform's
# decision record, which the approvals page shows.
_MANAGER_RETURNED = "Manager trả lại báo giá: xem ý kiến trên yêu cầu duyệt"


@dataclass(frozen=True)
class QuoteManagerSettlement:
    """Carries out a decided `sales.quote.manager` approval, for the worker's
    handler of its decided event, with the decider's tenancy and identity
    from the event's envelope. What was decided is read from the approval
    row, as every run-less Sales approval is."""

    uow: SalesUnitOfWorkFactory
    clock: UtcClock
    ids: IdGenerator
    notifications: NotificationSenderPort

    async def settle(self, approval_id: uuid.UUID, decider: AccessContext) -> str:
        """The Manager's decision on the quotation. Idempotent: a redelivery
        finds it decided by this person on this document and writes nothing.
        Raises the refusals the quotation makes (409, 404)."""
        audience = ApprovalAudience(
            context=decider.model_copy(
                update={"scopes": frozenset({SalesScopes.QUOTE_MANAGER_APPROVE.value})}
            ),
            holds_decide=True,
        )
        now = self.clock.now()
        async with self.uow(sales_scope(decider)) as work:
            request = await work.approvals.get(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            if request is None:
                raise NotFoundError(
                    "quote approval not found", details={"approval_id": str(approval_id)}
                )
            asked = _asked(request)
            if asked.approval_type is not DecisionType.QUOTE_MANAGER:
                raise ConflictError(
                    "the approval is not a Manager's", details={"approval_id": str(approval_id)}
                )
            if request.status is ApprovalStatus.PENDING:
                raise ConflictError(
                    "the Manager's approval is not decided yet",
                    details={"approval_id": str(approval_id)},
                )
            quote = (await stored_quote(work, asked.case_id, viewer=None)).case
            done = _manager_applied(quote, asked, decider.principal_id)
            if done is not None:
                return done
            _still_waiting(quote, asked, asked.case_version)
            approve = request.status is ApprovalStatus.APPROVED
            quoted, action = CaseDecisions._on_quote(
                quote,
                asked,
                _Decision(
                    decider=decider,
                    approve=approve,
                    comment="" if approve else _MANAGER_RETURNED,
                    reasons={},
                    subject_version=asked.case_version,
                    approves_quotes=False,
                    manages_quotes=True,
                ),
                now,
            )
            event = person_event(action, decider, now)
            await save_quote(work, decider, self.ids, quote, quoted, event)
            await work.commit()
        if action == "quote.approved":
            await tell_approved(self.notifications, decider, quoted)
        return action


def _manager_applied(quote: QuoteCase, asked: DecisionAsked, by: uuid.UUID) -> str | None:
    """The action an earlier delivery of the same decision already took."""
    approval = quote.approval
    if (
        quote.status is not QuoteStatus.PENDING_APPROVAL
        and approval is not None
        and approval.approved_by == by
        and approval.document_sha256 == asked.document_sha256
    ):
        return "quote.approved"
    returned = quote.returns[-1] if quote.returns else None
    if (
        quote.status is QuoteStatus.RETURNED
        and returned is not None
        and returned.returned_by == by
        and returned.case_version >= asked.case_version
    ):
        return "quote.returned"
    return None
