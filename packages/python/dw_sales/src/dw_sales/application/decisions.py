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
  decider, linked to the run.

The decide scope is not asked for here: the platform requires
`approvals.decide` and the scope the approval was stamped with in its
`required_scope` column (`DECIDE_SCOPES`), and the guard refuses an approval
stamped with any other. That is what lets `apply` hand the approver the
approve capability without their access context: nobody reaches `apply` but
through `ApproveAndResumeService.decide`, which checked it.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import ConflictError, DomainError, PermissionDeniedError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.approval import ApprovalRequest
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.inbox_service import InboxProcessing
from dw_sales.application.orders_service import order_actor
from dw_sales.application.quotation import QuotationService
from dw_sales.application.quotes_service import local_day, parse_finding_key
from dw_sales.application.runs import (
    DECIDE_SCOPES,
    DecisionAsked,
    DecisionGiven,
    DecisionType,
    awaiting,
)
from dw_sales.application.source import require_served
from dw_sales.application.support import (
    decided,
    person_event,
    same_version,
    save_order,
    save_quote,
    stored_order,
    stored_quote,
)
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import Actor, OrderCase, OrderStatus
from dw_sales.domain.quotes import QuoteActor, QuoteCapability, QuoteCase

_QUOTE = "sales_quote_case"
_ORDER = "sales_order_case"


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


@dataclass(frozen=True)
class CaseDecisions:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    quotation: QuotationService
    inbox: InboxProcessing

    # ------------------------------------------------------- DW xử lý --

    async def process(
        self, context: AccessContext, message_id: str | None
    ) -> list[dict[str, str | None]]:
        """One message, or every one still without a disposition. What the
        run keeps of it: the disposition and the case, by id."""
        views = (
            [await self.inbox.process(context, message_id)]
            if message_id is not None
            else await self.inbox.process_all(context)
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
            case = (await stored_quote(work, case_id)).case
            same_version(case_id, case.case_version, case_version)
            submitted = await self.quotation.submit(
                scope,
                case,
                quote_no=quote_no,
                issued_on=local_day(now),
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
        """The sales-order number and the statement that the Bravo entry was
        compared with the PO; on a revised order in Bravo, the change applied.
        The cross-check the run then waits on, unless the case's rules need
        none."""
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_ORDER, resource_id=str(case_id)
        )
        actor, now = order_actor(context, self.gate), self.clock.now()

        def step(case: OrderCase) -> OrderCase:
            if case.status is OrderStatus.CHANGE_REVIEW:
                return case.apply_change(actor, now, entry_compared=entry_compared)
            if so_no is None:
                raise DomainError(
                    "a Bravo entry names its sales-order number",
                    details={"case_id": str(case.case_id), "field": "so_no"},
                )
            return case.record_bravo_entry(so_no, actor, now, entry_compared=entry_compared)

        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id)).case
            same_version(case_id, case.case_version, case_version)
            after = decided(lambda: step(case))
            event = person_event("order.bravo_recorded", context, now, field="bravo_so_no")
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
        async with self.uow(sales_scope(decider)) as work:
            if asked.case_kind is CaseKind.QUOTE:
                quote = (await stored_quote(work, asked.case_id)).case
                _still_waiting(quote, asked, decision.subject_version)
                quoted, action = self._on_quote(quote, asked, decision, now)
                if write:
                    event = person_event(action, decider, now)
                    await save_quote(work, decider, self.ids, quote, quoted, event, run_id=run_id)
            else:
                order = (await stored_order(work, asked.case_id)).case
                _still_waiting(order, asked, decision.subject_version)
                # The cross-checker opened the original at this version
                # (spec decision 12), whichever way they decide.
                await require_served(work, decider.principal_id, order)
                ordered, action = _on_order(order, decision, now)
                if write:
                    event = person_event(action, decider, now)
                    await save_order(work, decider, self.ids, order, ordered, event, run_id=run_id)
            if write:
                await work.commit()
        return action

    @staticmethod
    def _on_quote(
        case: QuoteCase, asked: DecisionAsked, decision: _Decision, at: datetime
    ) -> tuple[QuoteCase, str]:
        actor = QuoteActor(
            user_id=decision.decider.principal_id,
            capabilities=(
                frozenset({QuoteCapability.APPROVE}) if decision.approves_quotes else frozenset()
            ),
        )
        if not decision.approve:
            comment = decision.comment
            returned = decided(lambda: case.return_to_pricer(actor, at=at, reason=comment))
            return returned, "quote.returned"
        # A quote approval names its document: the hash the approver approves.
        sha = asked.document_sha256 or ""
        given = {parse_finding_key(key): reason for key, reason in decision.reasons.items()}
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
