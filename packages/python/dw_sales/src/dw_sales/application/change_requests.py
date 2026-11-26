"""A change a customer asks for by mail, recorded on the order and confirmed
line by line (ticket 27; dw_sales ADR 0010 decisions 2 and 4, ADR 0005 as
amended: the body changes no value a person has not confirmed).

The rules of what a line is and what blocks it are the domain's
(`domain.change_requests`); this module is the door a person uses:

- **Open** ("Ghi yêu cầu thay đổi"): from a customer's reply the thread
  headers attached to this order (ticket 32), never another mail, so the
  sender is the order's own customer by code's link. Code splits a table in
  the mail; a model reads the free text where the tenant's step is on and
  measured (`model_assist.change_request`, gated by `ModelStepGatePort` as
  every model step is; the one-call door, as the asker); the person may add
  lines typed by hand, so a mail Sales reads by eye is never stuck while the
  model is off. A request with no line at all is refused (`nothing_read`):
  the person types the lines. One mail makes one request per order; one
  opened while another is open or queued waits behind it.
- **Confirm** one line: the value the case holds must still be the one the
  request read (else `held_changed`: the order moved on, a person rejects
  it); the change is applied with the checks run again
  (`OrderIntake.take_change`), the case takes its next version, and the
  request line, the case, its event and the audit row are written in one
  transaction. There is no confirming in bulk (`ui-quality.md` §7). On an
  order already in Bravo the change is not applied: it joins the update
  loop (`OrderCase.loop_change`, `update_loop.py`, ticket 29), and the order
  changes only once the customer accepts PC's answer.
- **Reject** one line, with the person's reason, kept on the request.

Every decision needs `sales.order.prepare`, as the PIC's other decisions on
the order do; reading needs `sales.case.read`. The audit rows name ids,
fields and counts, never a value or a reason (spec decision 8).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import ConflictError, DomainError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.mail_parts import newest_part, newest_tables
from dw_sales.application.access import Gate, SalesScopes, order_actor, sales_scope
from dw_sales.application.case_store import SalesUnitOfWork, SalesUnitOfWorkFactory
from dw_sales.application.change_reading import ChangeReader
from dw_sales.application.local_time import LocalZonePort, local_day
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.order_ports import ModelStepGatePort, OrderRulesPort
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.application.support import (
    decided,
    person_event,
    same_version,
    save_order,
    stored_order,
)
from dw_sales.application.views import ChangeRequestView, change_request_view
from dw_sales.domain.anchors import MessageText
from dw_sales.domain.change_requests import (
    ChangeField,
    ChangeLine,
    ChangeRequest,
    first_state,
    held_value,
    merged,
    next_to_open,
    person_line,
    table_changes,
)
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.labelled_cases import change_line_label
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import IN_BRAVO, AppliedChange, OrderCase, OrderStatus
from dw_sales.domain.rfq_reading import normalised, text_digest

_ORDER: Final = "sales_order_case"


class TypedChange(BaseModel):
    """A line a person types: the line, the field, the value in its one form
    (an ISO date from the date picker, a number from the number box)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    line_no: int = Field(ge=1, le=99_999)
    field: ChangeField
    value: str = Field(min_length=1, max_length=40)


class ChangeRequestResult(BaseModel):
    """What a change-request decision returns: the request as it now stands
    and the case's version after it (the next decision names it)."""

    model_config = ConfigDict(frozen=True)

    case_version: int
    request: ChangeRequestView


@dataclass(frozen=True)
class ChangeRequests:
    """The order's change requests through the API (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    intake: OrderIntake
    inbox: InboxPort
    rules: OrderRulesPort
    zones: LocalZonePort
    # Whether the model step may run for the tenant now; None: never.
    model_steps: ModelStepGatePort | None
    # The one-call door's reader; None where no model is wired.
    reader: ChangeReader | None
    worker_id: str
    worker_version: str

    async def open(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        message_id: str,
        typed: Sequence[TypedChange] = (),
    ) -> ChangeRequestResult:
        """A change request from one of the order's replies (module docstring)."""
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            await _require_reply(work, case_id, message_id)
        message = await self.inbox.get_message(scope, message_id)
        if message is None:
            raise NotFoundError("no such reply on this order", details={"message_id": message_id})
        if case.status is OrderStatus.CLOSED:
            raise ConflictError(
                "a closed order takes no change request",
                details={"case_id": str(case_id), "rule": "case_closed"},
            )
        text = normalised(newest_part(message).text)
        received_on = local_day(message.received_at, await self.zones.time_zone(scope))
        read = table_changes(case, text, newest_tables(message), received_on)
        reading = None
        if await self._reads_text(scope):
            rules = await self.rules.rules(scope)
            assert self.reader is not None
            by_model, reading = await self.reader.read(
                case,
                text,
                received_on=received_on,
                rules_version=rules.version,
                run_for=context,
                run_id=self.ids.new_uuid(),
                worker=(self.worker_id, self.worker_version),
            )
            read = merged(read, by_model)
        now = self.clock.now()
        request = ChangeRequest(
            request_id=self.ids.new_uuid(),
            case_id=case_id,
            number=1,
            message_id=message_id,
            text=_message_text(text),
            opened_by=context.principal_id,
            opened_at=now,
            state="open",
            lines=read.lines,
            unread=min(read.unread, 999),
            reading=reading,
        )
        for line in typed:
            request = request.with_line(_person_line(case, line))
        if not request.lines:
            raise ConflictError(
                "DW1 không đọc được thay đổi nào trong thư này: hãy nhập từng dòng",
                details={
                    "case_id": str(case_id),
                    "message_id": message_id,
                    "unread": read.unread,
                    "rule": "nothing_read",
                },
            )
        async with self.uow(scope) as work:
            current = (await stored_order(work, case_id, viewer=context)).case
            # The lines were read against the version the person saw.
            same_version(case_id, current.case_version, case_version)
            earlier = await work.change_requests.for_case(case_id)
            request = ChangeRequest.model_validate(
                {**dict(request), "state": first_state(earlier), "number": len(earlier) + 1}
            )
            await work.change_requests.add(request)
            await work.audit.append(
                self._audit(
                    context,
                    "order.change_request_opened",
                    current,
                    request,
                    lines=len(request.lines),
                    unread=request.unread,
                    state=request.state,
                    reading=None if reading is None else reading.outcome,
                )
            )
            await work.commit()
        return ChangeRequestResult(
            case_version=current.case_version,
            request=change_request_view(request, prices=self.gate.prices(context)),
        )

    async def add_line(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        request_id: uuid.UUID,
        typed: TypedChange,
        *,
        case_version: int,
    ) -> ChangeRequestResult:
        """One line typed by a person on a request not yet closed."""
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE)
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            request = await _request(work, case_id, request_id)
            after = request.with_line(_person_line(case, typed))
            await work.change_requests.save(after, expected_version=request.version)
            await work.audit.append(
                self._audit(
                    context,
                    "order.change_line_added",
                    case,
                    after,
                    line=after.lines[-1].seq,
                    field=typed.field,
                )
            )
            await work.commit()
        return ChangeRequestResult(
            case_version=case.case_version,
            request=change_request_view(after, prices=self.gate.prices(context)),
        )

    async def confirm(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        request_id: uuid.UUID,
        seq: int,
        *,
        case_version: int,
    ) -> ChangeRequestResult:
        """One line confirmed and applied to the case (module docstring)."""
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE)
        actor, now, scope = order_actor(context, self.gate), self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            requests = await work.change_requests.for_case(case_id)
            request = _one(requests, case_id, request_id)
            after = request.confirmed(seq, context.principal_id, now)
            line = request.line(seq)
            if held_value(case, line.line_no, line.field)[0] != line.held:
                raise ConflictError(
                    "giá trị trên đơn đã khác lúc đọc thư: hãy từ chối dòng này và ghi lại",
                    details={
                        "case_id": str(case_id),
                        "request_id": str(request_id),
                        "line": seq,
                        "rule": "held_changed",
                    },
                )
            change = AppliedChange(
                field=line.field,
                value=line.asked,
                request_id=request_id,
                by=actor.user_id,
                at=now,
            )
            if case.status in IN_BRAVO:
                # In Bravo the change joins the update loop and the order
                # waits on PC and the customer before it changes (ticket 29).
                changed = decided(lambda: case.loop_change(line.line_no, change, actor))
                action = "order.update_change_confirmed"
            else:
                changed = await self.intake.take_change(scope, case, line.line_no, change, actor)
                action = "order.change_confirmed"
            event = person_event(action, context, now, field=line.field)
            await save_order(work, context, self.ids, case, changed, event)
            await self._settle(work, requests, request, after)
            await work.audit.append(
                self._audit(
                    context,
                    "order.change_line_confirmed",
                    changed,
                    after,
                    line=seq,
                    field=line.field,
                )
            )
            await self._label(work, case, after, seq)
            await work.commit()
        return ChangeRequestResult(
            case_version=changed.case_version,
            request=change_request_view(after, prices=self.gate.prices(context)),
        )

    async def reject(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        request_id: uuid.UUID,
        seq: int,
        *,
        case_version: int,
        reason: str,
    ) -> ChangeRequestResult:
        """One line rejected with why; the case does not change."""
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE)
        now = self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            requests = await work.change_requests.for_case(case_id)
            request = _one(requests, case_id, request_id)
            after = decided(lambda: request.rejected(seq, reason, context.principal_id, now))
            await self._settle(work, requests, request, after)
            line = after.line(seq)
            await work.audit.append(
                self._audit(
                    context,
                    "order.change_line_rejected",
                    case,
                    after,
                    line=seq,
                    field=line.field,
                )
            )
            await self._label(work, case, after, seq)
            await work.commit()
        return ChangeRequestResult(
            case_version=case.case_version,
            request=change_request_view(after, prices=self.gate.prices(context)),
        )

    async def for_case(self, context: AccessContext, case_id: uuid.UUID) -> list[ChangeRequestView]:
        """The order's requests, oldest first, for whoever reads the order."""
        await self._require(context, case_id, SalesScopes.CASE_READ)
        async with self.uow(sales_scope(context)) as work:
            await stored_order(work, case_id, viewer=context, export_control=True)
            requests = await work.change_requests.for_case(case_id)
        return [change_request_view(r, prices=self.gate.prices(context)) for r in requests]

    # ------------------------------------------------------------ helpers --

    async def _reads_text(self, scope: SalesScope) -> bool:
        """A model wired, and the step on in the tenant's rules in force and
        measured at its bar; never without the gate."""
        if self.reader is None or self.model_steps is None:
            return False
        rules = await self.rules.rules(scope)
        return await self.model_steps.allows(scope, rules, ModelStep.CHANGE_REQUEST)

    async def _settle(
        self,
        work: SalesUnitOfWork,
        requests: Sequence[ChangeRequest],
        before: ChangeRequest,
        after: ChangeRequest,
    ) -> None:
        """``after`` stored; once it is closed, the next queued request opens."""
        await work.change_requests.save(after, expected_version=before.version)
        if after.state != "closed":
            return
        others = [after if r.request_id == after.request_id else r for r in requests]
        nxt = next_to_open(others)
        if nxt is not None:
            await work.change_requests.save(nxt.opened(), expected_version=nxt.version)

    async def _label(
        self, work: SalesUnitOfWork, case: OrderCase, after: ChangeRequest, seq: int
    ) -> None:
        """The line as the model read it beside what the person decided
        (ticket 43), written with the decision; nothing for a line a table
        or a person gave."""
        label = change_line_label(case, after, after.line(seq), new_id=self.ids.new_uuid)
        if label is not None:
            await work.labelled_cases.append([label])

    async def _require(
        self, context: AccessContext, case_id: uuid.UUID, scope: SalesScopes
    ) -> None:
        await self.gate.require(context, scope, resource_type=_ORDER, resource_id=str(case_id))

    def _audit(
        self,
        context: AccessContext,
        action: str,
        case: OrderCase,
        request: ChangeRequest,
        **facts: str | int | None,
    ) -> AuditEvent:
        """The audit row of one request decision: ids, the line and field,
        counts; never a value or the person's reason (spec decision 8)."""
        return AuditEvent(
            id=self.ids.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            actor_id=UserId(context.principal_id),
            action=f"sales.{action}",
            resource_type=_ORDER,
            resource_id=str(case.case_id),
            occurred_at=self.clock.now(),
            details={
                "case_kind": CaseKind.ORDER.value,
                "case_version": case.case_version,
                "request_id": str(request.request_id),
                "message_id": request.message_id,
                "request_state": request.state,
                **{k: v for k, v in facts.items() if v is not None},
            },
        )


def _person_line(case: OrderCase, typed: TypedChange) -> ChangeLine:
    return decided(lambda: person_line(case, typed.line_no, typed.field, typed.value))


def _message_text(text: str) -> MessageText:
    if not text.strip():
        raise DomainError("the mail has no text to read", details={"rule": "nothing_read"})
    return MessageText(text=text[:50_000], sha256=text_digest(text[:50_000]))


async def _require_reply(work: SalesUnitOfWork, case_id: uuid.UUID, message_id: str) -> None:
    """The message is a customer's reply its thread attached to this order
    (ticket 32): any other, another order's or another customer's, is not
    found here."""
    logged = await work.messages.get(message_id)
    if (
        logged is None
        or logged.reply is None
        or logged.case_kind is not CaseKind.ORDER
        or logged.case_id != case_id
    ):
        raise NotFoundError("no such reply on this order", details={"message_id": message_id})


async def _request(
    work: SalesUnitOfWork, case_id: uuid.UUID, request_id: uuid.UUID
) -> ChangeRequest:
    return _one(await work.change_requests.for_case(case_id), case_id, request_id)


def _one(
    requests: Sequence[ChangeRequest], case_id: uuid.UUID, request_id: uuid.UUID
) -> ChangeRequest:
    found = next((r for r in requests if r.request_id == request_id), None)
    if found is None:
        raise NotFoundError(
            "no such change request on this order",
            details={"case_id": str(case_id), "request_id": str(request_id)},
        )
    return found


__all__ = [
    "ChangeRequestResult",
    "ChangeRequests",
    "TypedChange",
]
