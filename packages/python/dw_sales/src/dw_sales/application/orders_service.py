"""Order cases through the API: reading them, and each Sales decision on one.

Every decision follows one path (`_decide`): the scope it needs, the case in
the caller's workspace, the version the caller decided on, for `prepare` the
served source (`require_served`), then the case decides (`OrderCase`), and
the next case is stored with its event and audit row in one transaction. The
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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from dw_kernel.errors import DomainError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.runs import (
    PendingDecisionsPort,
    awaiting,
    subject_of,
    withdraw_if_left,
)
from dw_sales.application.source import require_served
from dw_sales.application.support import (
    decided,
    person_event,
    same_version,
    save_order,
    stored_order,
)
from dw_sales.application.views import (
    CaseChangeView,
    OrderCaseView,
    OrderSummaryView,
    PendingDecisionView,
    order_case,
    order_change,
    order_summary,
)
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import (
    Accepted,
    Actor,
    AskCustomer,
    Capability,
    CloseReason,
    CorrectedBySales,
    FindingDisposition,
    Open,
    OrderCase,
)

DispositionChoice = Literal["open", "accepted", "corrected_by_sales", "ask_customer"]

_ORDER = "sales_order_case"


def order_actor(context: AccessContext, gate: Gate) -> Actor:
    """The caller as the case knows them: their principal id, and the export
    -control capability when their scopes include `sales.compliance.ack`."""
    capabilities = (
        frozenset({Capability.ACKNOWLEDGE_EXPORT_CONTROL})
        if gate.allows(context, SalesScopes.COMPLIANCE_ACK)
        else frozenset()
    )
    return Actor(user_id=context.principal_id, capabilities=capabilities)


@dataclass(frozen=True)
class OrderQueries:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    decisions: PendingDecisionsPort

    async def summaries(self, context: AccessContext) -> list[OrderSummaryView]:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_ORDER)
        async with self.uow(sales_scope(context)) as work:
            stored = await work.orders.list_all()
        return [order_summary(s.case, s.origin.assigned_to) for s in stored]

    async def get(self, context: AccessContext, case_id: uuid.UUID) -> OrderCaseView:
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type=_ORDER, resource_id=str(case_id)
        )
        async with self.uow(sales_scope(context)) as work:
            stored = await stored_order(work, case_id)
        decision = None
        if (waits_on := awaiting(stored.case)) is not None:
            approval_id = await self.decisions.pending(context, subject_of(CaseKind.ORDER, case_id))
            if approval_id is not None:
                decision = PendingDecisionView(approval_id=approval_id, approval_type=waits_on)
        return order_case(
            stored.case,
            assigned_to=stored.origin.assigned_to,
            release_manifest_ref=stored.origin.release_manifest_ref,
            prices=self.gate.prices(context),
            decision=decision,
        )


@dataclass(frozen=True)
class OrderCommands:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    intake: OrderIntake
    decisions: PendingDecisionsPort

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
            case = (await stored_order(work, case_id)).case
            same_version(case_id, case.case_version, case_version)
            confirmed = await self.intake.confirm_mapping(
                scope, case, line_no, prv_code, actor, now
            )
            event = person_event("order.mapping_confirmed", context, now, field="prv_code")
            await save_order(work, context, self.ids, case, confirmed, event)
            await work.commit()
        return order_change(confirmed)

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

    async def prepare(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """The PIC's self-check is done (step 7), once they were served the source."""
        return await self._decide(
            context,
            case_id,
            case_version,
            "order.prepared",
            lambda case, actor, at: case.prepare(actor, at),
            served_gate=True,
        )

    async def confirm(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        delivery_dates: Mapping[int, date],
    ) -> CaseChangeView:
        """Step 10, with the date Sales confirms for every line."""
        return await self._decide(
            context,
            case_id,
            case_version,
            "order.confirmed",
            lambda case, actor, at: case.confirm(actor, at, delivery_dates),
        )

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
        served_gate: bool = False,
        finding_key: str | None = None,
        field: str | None = None,
        reason_code: str | None = None,
    ) -> CaseChangeView:
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE)
        actor, now = order_actor(context, self.gate), self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id)).case
            same_version(case_id, case.case_version, case_version)
            if served_gate:
                await require_served(work, context.principal_id, case)
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
