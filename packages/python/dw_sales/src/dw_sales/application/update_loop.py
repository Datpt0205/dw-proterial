"""A customer's change on an order already in Bravo, from the PIC's
confirmation to the order confirmed again: the BA's step 6 (ticket 29,
dw_sales ADR 0010 decision 3; ADR 0026 as amended 2026-11-13).

The steps are the case's (`OrderCase.update_loop`, its `UpdateStep`); this
module is the door a person uses at each one. DW1 sends nothing and writes
nothing to Bravo: every draft is copied and sent by a person, who records it
sent, and the Bravo update is the file a person approved.

1. **The change** (6-DW1): the PIC confirms a change line of a customer's
   change request (`change_requests.py`); on an order Sales has confirmed,
   it joins the loop instead of the order (`OrderCase.loop_change`).
2. **"Hỏi PC"** (6-DW2, `pc_request`): the request to PC, drafted by ticket
   07's code and copy (`render_pc_request`) with the values the customer
   asks; "Ghi đã hỏi PC" (`ask_pc`) once every line of the request is
   decided. The case waits on PC; `sales_followups.waiting_pc` reminds.
3. **PC's answer** (6-PC, `pc_answer`), line by line as in ticket 07, its
   quantities adding up to the quantity asked. With the last line, code
   compares PC's dates with the dates asked: the drafted answer to the
   customer is 6-DW4 (PC can) or 6-DW3 (PC proposes otherwise), the
   artifacts `change_can_do_draft` or `change_options_draft`, from the
   versioned copy. "Ghi đã gửi khách" (`answer_sent`): the case waits on the
   customer; `sales_followups.waiting_customer` reminds.
4. **The customer's answer** ("Khách quyết định?", `customer_answer`), as a
   person records it: keep the PO (the loop ends and the order is exactly as
   it was), ask PC again, or accept, which applies the change with its
   checks run again (`OrderIntake.take_update`) and opens the Bravo update.
   No model decides it: the thread-intent step may propose, a person records.
5. **The Bravo update** (6.2-SP, `approve`): the PIC approves the exact file
   (`bravo_update`, the paste-sheet rows of the changed lines, drawn at the
   case's version) by its id and hash; it is then entered and recorded as a
   Bravo entry is (`CaseDecisions.record_bravo_entry`, which refuses an
   unapproved update), cross-checked as the case's rules say by someone who
   made none of it, and confirmed again (6.3: `confirmation_draft`), which
   ends the loop.

Every step needs `sales.order.prepare` (the PIC's, as every 🔒 step of the
BA's flow, ADR 0010 decision 5), names the case version it was decided on,
and writes the case, its event and its audit row in one transaction. The
audit names ids, the step and code's verdict, never a quantity or a date.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, order_actor, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.handoffs import HandoffCopyPort, PcAskedLine, render_pc_request
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.overview_ports import FollowupPolicyPort
from dw_sales.application.pc_requests import PcRequestView
from dw_sales.application.support import (
    decided,
    person_event,
    same_version,
    save_order,
    stored_order,
)
from dw_sales.application.views import CaseChangeView, order_change
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import pc_reminder_at
from dw_sales.domain.orders import CustomerAnswer

_ORDER: Final = "sales_order_case"
# The artifact kind of the Bravo update file (`artifacts_service.ORDER_GATES`).
BRAVO_UPDATE: Final = "bravo_update"


@dataclass(frozen=True)
class UpdateLoops:
    """`/orders/{case_id}/update/...` (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    intake: OrderIntake
    copy: HandoffCopyPort
    followups: FollowupPolicyPort

    async def pc_request(self, context: AccessContext, case_id: uuid.UUID) -> PcRequestView:
        """6-DW2 as it would be sent now: ticket 07's request with the values
        the customer asks, and when DW1 reminds while the case waits on PC."""
        await self._require(context, case_id)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
        loop = case.update_loop
        if loop is None or loop.step not in ("ask_pc", "waiting_pc"):
            raise ConflictError(
                "đơn không chờ hỏi PC về thay đổi của khách",
                details={"case_id": str(case_id), "rule": "update_step"},
            )
        asked = []
        for loop_line in loop.lines:
            line, target = case.line(loop_line.line_no), case.loop_target(loop_line)
            asked.append(
                PcAskedLine(
                    line_no=line.line_no,
                    prv_code=line.mapping.prv_code,
                    customer_item_code=target.customer_item_code,
                    quantity=target.quantity,
                    uom=target.uom,
                    requested_date=target.requested_date,
                )
            )
        rendered = render_pc_request(
            await self.copy.handoff_copy(scope),
            customer_code=case.customer_code,
            po_no=case.effective_header.po_no,
            lines=asked,
        )
        reminder = None
        if loop.step == "waiting_pc":
            reminder = pc_reminder_at(await self.followups.followups(scope), loop.since)
        return PcRequestView(
            case_version=case.case_version,
            lines=[x.line_no for x in loop.lines],
            subject=rendered.subject,
            body=rendered.body,
            template_ref=rendered.template_ref,
            reminder_at=reminder,
        )

    async def ask_pc(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """ "Ghi đã hỏi PC": refused while a line of the change request is
        still undecided, so PC is asked about the whole change once."""
        await self._require(context, case_id)
        now = self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            loop = case.update_loop
            if loop is not None:
                requests = await work.change_requests.for_case(case_id)
                request = next((r for r in requests if r.request_id == loop.request_id), None)
                if request is not None and request.state != "closed":
                    raise ConflictError(
                        "còn dòng thay đổi chưa xác nhận hoặc từ chối: quyết định hết rồi hỏi PC",
                        details={"case_id": str(case_id), "rule": "change_request_open"},
                    )
            after = decided(lambda: case.loop_ask_pc(now))
            event = person_event("order.update_pc_asked", context, now)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return order_change(after)

    async def pc_answer(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        line_no: int,
        *,
        case_version: int,
        deliveries: Sequence[tuple[Decimal, date]],
    ) -> CaseChangeView:
        """PC's answer for one changed line (module docstring, step 3)."""
        await self._require(context, case_id)
        actor, now = order_actor(context, self.gate), self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            after = decided(lambda: case.loop_pc_answer(line_no, deliveries, actor, now))
            loop = after.update_loop
            verdict = None if loop is None else loop.verdict
            event = person_event("order.update_pc_answered", context, now, reason_code=verdict)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return order_change(after)

    async def answer_sent(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """ "Ghi đã gửi khách": the drafted answer left from the person's own
        mailbox; the case waits on the customer from now."""
        await self._require(context, case_id)
        now = self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            after = decided(lambda: case.loop_answer_sent(now))
            loop = after.update_loop
            verdict = None if loop is None else loop.verdict
            event = person_event("order.update_answer_sent", context, now, reason_code=verdict)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return order_change(after)

    async def customer_answer(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        answer: CustomerAnswer,
    ) -> CaseChangeView:
        """What the customer answered, recorded by a person (step 4)."""
        await self._require(context, case_id)
        now, scope = self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            if answer == "accept":
                after = await self.intake.take_update(scope, case, now)
            else:
                after = decided(lambda: case.loop_answered(answer, now))
            event = person_event("order.update_customer_answered", context, now, reason_code=answer)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return order_change(after)

    async def approve(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        artifact_id: uuid.UUID,
    ) -> CaseChangeView:
        """6.2-SP: the PIC approves the Bravo update file drawn at this
        version, by its id; the approval stamps its hash (module docstring)."""
        await self._require(context, case_id)
        actor, now = order_actor(context, self.gate), self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            record = await work.artifacts.get(artifact_id)
            if (
                record is None
                or (record.case_kind, record.case_id) != (CaseKind.ORDER, case_id)
                or record.kind != BRAVO_UPDATE
            ):
                raise NotFoundError(
                    "the order has no such Bravo update file",
                    details={"case_id": str(case_id), "artifact_id": str(artifact_id)},
                )
            after = decided(
                lambda: case.approve_update(
                    record.artifact_id, record.sha256, record.case_version, actor, now
                )
            )
            event = person_event("order.update_approved", context, now)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return order_change(after)

    async def _require(self, context: AccessContext, case_id: uuid.UUID) -> None:
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_ORDER, resource_id=str(case_id)
        )


__all__ = ["BRAVO_UPDATE", "UpdateLoops"]
