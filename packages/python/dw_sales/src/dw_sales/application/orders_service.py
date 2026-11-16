"""Order cases through the API: reading them, and each Sales decision on one.

Every decision follows one path (`_decide`): the scope it needs, the case in
the caller's workspace, the version the caller decided on, then the case
decides (`OrderCase`), and the next case is stored with its event and audit
row in one transaction; `prepare` reads the served source (`require_served`)
and the quote cases opened from the order (ticket 09) in that transaction. The
case refuses what the process does not allow (409), a scope the caller lacks
is refused before anything is read (403), and a case of another workspace is
not found (404).

The Bravo entry and the cross-check are DW1's run (`dw_sales.application.runs`,
dw_sales ADR 0004): the entry is recorded inside a run that pauses on a
`sales.order.cross_check` approval, decided through the platform's approvals
by someone who made none of the case, and applied by the run (`CaseDecisions`).

Who acted is the verified principal, and when is the server's clock: nothing
in a request names either.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from dw_kernel.errors import DomainError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, order_actor, sales_scope
from dw_sales.application.activity_ports import (
    CaseListActivity,
    StepActivityReadPort,
    activity_cases,
)
from dw_sales.application.autonomy import applied_by
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.confirmations import confirmation_copy
from dw_sales.application.customer_notations import NotationLedgerPort, learn
from dw_sales.application.local_time import LocalZonePort
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.order_ports import ConvertLedgerPort
from dw_sales.application.order_quotes import quote_link_views, settled_quotes
from dw_sales.application.outgoing import outgoing_in
from dw_sales.application.ports import MemberDirectoryPort
from dw_sales.application.runs import (
    PendingDecisionsPort,
    awaited,
    awaiting,
    withdraw_if_left,
)
from dw_sales.application.source import require_served
from dw_sales.application.support import (
    decided,
    person_event,
    same_version,
    save_order,
    seen_by,
    stored_order,
)
from dw_sales.application.threads import ThreadMembersPort, case_thread
from dw_sales.application.views import (
    CaseChangeView,
    OrderCaseView,
    OrderSummaryView,
    PendingDecisionView,
    order_case,
    order_change,
    order_summary,
)
from dw_sales.domain.catalog import ConvertEntry
from dw_sales.domain.customer_notation import order_lesson
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.labelled_cases import mapping_label, po_value_label, undo_label
from dw_sales.domain.orders import (
    AMOUNT_FIELDS,
    Accepted,
    Actor,
    AskCustomer,
    CloseReason,
    CorrectedBySales,
    FindingDisposition,
    Open,
    OrderCase,
)

DispositionChoice = Literal["open", "accepted", "corrected_by_sales", "ask_customer"]

_ORDER = "sales_order_case"


@dataclass(frozen=True)
class OrderQueries:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    decisions: PendingDecisionsPort
    # The step rows a list narrowed by DW1's activity is read through.
    activity: StepActivityReadPort
    # Where the activity filter's days are counted (audit 14).
    zones: LocalZonePort
    # The mailbox's threads, for the talk before the PO (ticket 24) and the
    # messages Sales sent on them (ticket 25).
    threads: ThreadMembersPort
    # Whose sign-in address a message Sales sent is from (ticket 25).
    directory: MemberDirectoryPort

    async def summaries(
        self, context: AccessContext, activity: CaseListActivity | None = None
    ) -> list[OrderSummaryView]:
        """The workspace's orders; with ``activity``, only those a matching
        step row names (the activity page's drill-down), checked after the
        scope."""
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_ORDER)
        scope = sales_scope(context)
        kept = await activity_cases(self.activity, scope, CaseKind.ORDER, activity, self.zones)
        async with self.uow(scope) as work:
            stored = await work.orders.list_all()
        return [
            order_summary(s.case, s.origin.assigned_to)
            for s in stored
            if (kept is None or s.case.case_id in kept) and seen_by(context, CaseKind.ORDER, s)
        ]

    async def get(self, context: AccessContext, case_id: uuid.UUID) -> OrderCaseView:
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type=_ORDER, resource_id=str(case_id)
        )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            stored = await stored_order(work, case_id, viewer=context)
            logged = await work.messages.list_all()
            servings = await work.served.servings(CaseKind.ORDER, case_id)
            sent = {s.message_id: s for s in await work.sent.list_all()}
            requests = await work.change_requests.for_case(case_id)
            artifacts = await work.artifacts.for_case(CaseKind.ORDER, case_id)
            quote_links = await quote_link_views(work, context, stored.case)
        thread = await case_thread(
            self.threads,
            scope,
            {m.disposition.message_id: m for m in logged},
            case_kind=CaseKind.ORDER,
            case_id=case_id,
            customer_code=stored.case.customer_code,
            outgoing=await outgoing_in(self.directory, context),
        )
        wait = await awaited(self.decisions, context, stored.case)
        waits_on = awaiting(stored.case)
        decision = None
        if waits_on is not None and wait is not None and wait.approval_id is not None:
            decision = PendingDecisionView(approval_id=wait.approval_id, approval_type=waits_on)
        return order_case(
            stored.case,
            assigned_to=stored.origin.assigned_to,
            release_manifest_ref=stored.origin.release_manifest_ref,
            prices=self.gate.prices(context),
            decision=decision,
            stalled=wait is not None and wait.stalled,
            replies=logged,
            servings=servings,
            cross_checker=self.gate.allows(context, SalesScopes.ORDER_CROSS_CHECK),
            thread=thread,
            sent=sent,
            change_requests=requests,
            confirmation_copy=confirmation_copy(stored.case, thread.sent, artifacts),
            quote_links=quote_links,
        )


@dataclass(frozen=True)
class OrderCommands:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    intake: OrderIntake
    decisions: PendingDecisionsPort
    # Where a code Sales confirms is kept for the customer's next PO.
    converts: ConvertLedgerPort
    # Where what a typed value teaches of the customer's notation is kept
    # (ticket 37).
    notations: NotationLedgerPort

    async def dispose(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        finding_key: str,
        *,
        case_version: int,
        disposition: DispositionChoice,
        reason: str | None = None,
        value: str | None = None,
        source: str | None = None,
    ) -> CaseChangeView:
        """One finding's decision (steps 7-8). Accepting `missing_noc_esf`
        takes the export-control capability, which the case checks (403)."""

        def step(case: OrderCase, actor: Actor, at: datetime) -> OrderCase:
            return case.dispose(
                finding_key, _disposition(disposition, actor, at, reason, value, source), actor
            )

        return await self._decide(
            context,
            case_id,
            case_version,
            "order.finding_disposed",
            step,
            finding_key=finding_key,
            reason_code=disposition,
        )

    async def confirm_mapping(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        line_no: int,
        *,
        case_version: int,
        prv_code: str,
    ) -> CaseChangeView:
        """Sales confirms the line's PRV code; the line is checked again
        against that item under the case's rules (`OrderIntake.confirm_mapping`)."""
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE)
        actor, now, scope = order_actor(context, self.gate), self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            confirmed = await self.intake.confirm_mapping(
                scope, case, line_no, prv_code, actor, now
            )
            event = person_event("order.mapping_confirmed", context, now, field="prv_code")
            await save_order(work, context, self.ids, case, confirmed, event)
            # What the person kept of a model's reading, if one proposed the
            # candidates (ticket 43), with the decision.
            label = mapping_label(
                case, line_no, prv_code, new_id=self.ids.new_uuid, at=now, by=actor.user_id
            )
            if label is not None:
                await work.labelled_cases.append([label])
            await work.commit()
        # Learned once the case holds it: the customer's next PO with this
        # code maps without asking again (the AI list, item 3).
        code = confirmed.line(line_no).effective.customer_item_code
        if code:
            await self.converts.learn_convert(
                scope,
                ConvertEntry(
                    customer_code=confirmed.customer_code,
                    customer_item_code=code,
                    prv_code=prv_code,
                ),
                by=context.principal_id,
                case_id=case_id,
            )
        return order_change(confirmed)

    async def undo_applied_mapping(
        self, context: AccessContext, case_id: uuid.UUID, line_no: int, *, case_version: int
    ) -> CaseChangeView:
        """Sales undoes the PRV code DW applied by itself (ticket 44): the line
        is a candidate to confirm again, and the undo is a labelled case, the
        applied code rejected, which the step's threshold and audits learn
        from. Taken by whoever may confirm the line (`sales.order.prepare`)."""
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE)
        actor, now, scope = order_actor(context, self.gate), self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            undone = case.undo_applied_mapping(line_no, applied_by=applied_by())
            event = person_event("order.mapping_undone", context, now, field="prv_code")
            await save_order(work, context, self.ids, case, undone, event)
            await work.labelled_cases.append(
                [undo_label(case, line_no, new_id=self.ids.new_uuid, at=now, by=actor.user_id)]
            )
            await work.commit()
        return order_change(undone)

    async def reject_candidates(
        self, context: AccessContext, case_id: uuid.UUID, line_no: int, *, case_version: int
    ) -> CaseChangeView:
        """Sales rejects the candidates a model's reading proposed for a line
        ("Không phải mã này", ticket 44): the line is unmapped, a code for
        Sales to type, and the rejection is a labelled case, nothing kept,
        which the step's threshold and audits learn from. Taken by whoever
        may confirm the line (`sales.order.prepare`)."""
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE)
        actor, now, scope = order_actor(context, self.gate), self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            rejected = await self.intake.reject_candidates(scope, case, line_no)
            event = person_event("order.mapping_rejected", context, now, field="prv_code")
            await save_order(work, context, self.ids, case, rejected, event)
            label = mapping_label(
                case, line_no, None, new_id=self.ids.new_uuid, at=now, by=actor.user_id
            )
            if label is None:
                # The case rejects only a model's candidates; a rejection
                # without its labelled case is not taken.
                raise DomainError(
                    "a rejection names the reading it rejects",
                    details={"case_id": str(case_id), "line": line_no},
                )
            await work.labelled_cases.append([label])
            await work.commit()
        return order_change(rejected)

    async def correct_value(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        finding_key: str,
        *,
        case_version: int,
        field: str,
        value: str,
    ) -> CaseChangeView:
        """One value a `value_uncertain` flagged, typed by Sales (ticket 15),
        with the checks run again on the corrected values
        (`OrderIntake.correct_value`). An amount is typed only by a holder of
        `sales.price.read`, as only they read one (403). The event and the
        audit row name the finding and the field, never the value."""
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE)
        if field in AMOUNT_FIELDS:
            await self._require(context, case_id, SalesScopes.PRICE_READ)
        actor, now, scope = order_actor(context, self.gate), self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            corrected = await self.intake.correct_value(
                scope, case, finding_key, field, value, actor, now
            )
            event = person_event(
                "order.value_corrected", context, now, finding_key=finding_key, field=field
            )
            await save_order(work, context, self.ids, case, corrected, event)
            # The value as a model read it beside the one typed (ticket 43).
            label = po_value_label(case, corrected, finding_key, field, new_id=self.ids.new_uuid)
            if label is not None:
                await work.labelled_cases.append([label])
            await work.commit()
        # Learned once the case holds it: how the customer writes what Sales
        # typed, for the next document that does not say (ticket 37).
        taught = order_lesson(case, corrected, finding_key, field)
        await learn(
            self.notations,
            self.ids,
            scope,
            [] if taught is None else [taught],
            customer_code=corrected.customer_code,
            case_kind="order",
            case_id=case_id,
            by=actor.user_id,
            at=now,
        )
        return order_change(corrected)

    async def record_pc_date(
        self, context: AccessContext, case_id: uuid.UUID, line_no: int, *, case_version: int
    ) -> CaseChangeView:
        """PC agreed the line's short lead time (outside the portal): who
        recorded it and when, without which the line is not confirmed."""
        return await self._decide(
            context,
            case_id,
            case_version,
            "order.pc_date_recorded",
            lambda case, actor, at: case.record_pc_confirmation(line_no, actor, at),
            field="pc_confirmed",
        )

    async def request_correction(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """The findings sent back to the customer go out as one request (step 8)."""
        return await self._decide(
            context,
            case_id,
            case_version,
            "order.correction_requested",
            lambda case, actor, at: case.request_correction(),
        )

    async def resume_review(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """The customer answered the correction request without a corrected
        PO (ticket 32): the review resumes, every finding as it stood."""
        return await self._decide(
            context,
            case_id,
            case_version,
            "order.review_resumed",
            lambda case, actor, at: case.resume_review(),
        )

    async def prepare(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """The PIC's self-check is done (step 7), once they were served the
        source, and while no quote case opened from the order is still open
        (ticket 09): the linked quotes are read in the same transaction, and
        the case refuses one it is not told is settled."""
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE)
        actor, now = order_actor(context, self.gate), self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            await require_served(work, context.principal_id, case)
            settled = await settled_quotes(work, case)
            after = decided(lambda: case.prepare(actor, now, settled_quotes=settled))
            event = person_event("order.prepared", context, now)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        await withdraw_if_left(self.decisions, context, case, after)
        return order_change(after)

    async def close(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        reason: CloseReason,
        superseded_by: uuid.UUID | None,
    ) -> CaseChangeView:
        return await self._decide(
            context,
            case_id,
            case_version,
            "order.closed",
            lambda case, actor, at: case.close(reason, actor, at, superseded_by=superseded_by),
            reason_code=reason.value,
        )

    # ------------------------------------------------------------- helpers --

    async def _require(
        self, context: AccessContext, case_id: uuid.UUID, scope: SalesScopes
    ) -> None:
        await self.gate.require(context, scope, resource_type=_ORDER, resource_id=str(case_id))

    async def _decide(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        case_version: int,
        action: str,
        step: Callable[[OrderCase, Actor, datetime], OrderCase],
        *,
        finding_key: str | None = None,
        field: str | None = None,
        reason_code: str | None = None,
    ) -> CaseChangeView:
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE)
        actor, now = order_actor(context, self.gate), self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            after = decided(lambda: step(case, actor, now))
            event = person_event(
                action,
                context,
                now,
                finding_key=finding_key,
                field=field,
                reason_code=reason_code,
            )
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        await withdraw_if_left(self.decisions, context, case, after)
        return order_change(after)


def _disposition(
    choice: DispositionChoice,
    actor: Actor,
    at: datetime,
    reason: str | None,
    value: str | None,
    source: str | None,
) -> FindingDisposition:
    """The decision as the case records it, stamped with the caller and the
    server's time. A field the choice needs and the request lacks is a 422
    naming the field."""

    def need(name: str, given: str | None) -> str:
        if given is None:
            raise DomainError(f"{choice} needs {name}", details={"field": name})
        return given

    by = actor.user_id
    match choice:
        case "open":
            return Open()
        case "accepted":
            return decided(lambda: Accepted(reason=need("reason", reason), by=by, at=at))
        case "corrected_by_sales":
            return decided(
                lambda: CorrectedBySales(
                    value=need("value", value), source=need("source", source), by=by, at=at
                )
            )
        case "ask_customer":
            return AskCustomer(by=by, at=at)
