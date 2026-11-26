"""Asking PC for an order's delivery dates, and PC's answer recorded line by
line (ticket 07; drawio 2a, WIV-03-012 step O4).

- **"Hỏi PC"** (`draft`): the request Sales sends PC, written by code from the
  order case (each line asked as it is entered: its number, PRV code, the
  customer's code, quantity and requested date) in the tenant's hand-off copy
  (`sales_handoffs`, `pc_request`). The person copies it into Teams or a mail
  from their own account, or sends the same words as the order's
  `pc_request_draft` from their mailbox through the outbox (ticket 77), to
  the tenant's `pc_mailboxes` only.
- **"Ghi đã hỏi PC"** (`ask`): the case waits on PC from now
  (`OrderCase.ask_pc`), and the `sales_followups` lane reminds the PIC once
  the tenant's `waiting_pc` hours have passed with no answer. A mail sent
  through the outbox records it on its receipt, as the person who pressed,
  from when they pressed (`sales_outbound`).
- **PC's answer** (`answer`), one line at a time: each delivery's quantity and
  PC's date, typed by the person (or filled from PC's mail by the reader of
  item 7, `pc_dates`, and checked by the person). A split whose quantities do
  not add up to the line's is refused, never adjusted; a re-confirmation keeps
  the date PC confirmed first. The line's checks run again through the path a
  change the customer asked takes (`OrderIntake.take_pc_answer`), the case
  takes its next version, and the case, its event and the audit row are
  written in one transaction. The wait ends with the last line's answer, and
  with it the reminder.

Every step needs `sales.order.prepare`, as the PIC's other decisions do. The
audit rows name the case, its version and the event, never a quantity or a
date (spec decision 8).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict

from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, order_actor, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.handoffs import HandoffCopyPort, pc_asked_lines, render_pc_request
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.overview_ports import FollowupPolicyPort
from dw_sales.application.support import (
    decided,
    person_event,
    same_version,
    save_order,
    stored_order,
)
from dw_sales.application.views import CaseChangeView, order_change
from dw_sales.domain.followups import pc_reminder_at

_ORDER: Final = "sales_order_case"


class PcRequestView(BaseModel):
    """The request to PC, drafted from the case for a person to copy, and
    when DW1 reminds while the case waits on PC (who asked, and when, is the
    order's own `pc_request`)."""

    model_config = ConfigDict(frozen=True)

    case_version: int
    # The lines the request asks about (`OrderCase.pc_lines`).
    lines: list[int]
    subject: str
    body: str
    template_ref: str
    # When the PIC is reminded if PC has not answered: the tenant's
    # `waiting_pc` hours after asking; None while there is no wait, or the
    # reminder is off.
    reminder_at: datetime | None = None


@dataclass(frozen=True)
class PcRequests:
    """`/orders/{case_id}/pc-request` and `/orders/{case_id}/lines/{line_no}/pc-answer`."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    intake: OrderIntake
    copy: HandoffCopyPort
    followups: FollowupPolicyPort

    async def draft(self, context: AccessContext, case_id: uuid.UUID) -> PcRequestView:
        """The request as it would be sent now, and the wait (module docstring)."""
        await self._require(context, case_id)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
        asked = pc_asked_lines(case)
        rendered = render_pc_request(
            await self.copy.handoff_copy(scope),
            customer_code=case.customer_code,
            po_no=case.effective_header.po_no,
            lines=asked,
        )
        request = case.pc_request
        reminder = None
        if request is not None:
            reminder = pc_reminder_at(await self.followups.followups(scope), request.at)
        return PcRequestView(
            case_version=case.case_version,
            lines=sorted(line.line_no for line in asked),
            subject=rendered.subject,
            body=rendered.body,
            template_ref=rendered.template_ref,
            reminder_at=reminder,
        )

    async def ask(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        sent_at: datetime | None = None,
    ) -> CaseChangeView:
        """ "Ghi đã hỏi PC": the case waits on PC from the server's now, or,
        recorded from an outbox receipt, from ``sent_at``, when the server
        queued the mail at the person's press (never a value a request
        carries: the route does not take it)."""
        await self._require(context, case_id)
        actor, now = order_actor(context, self.gate), self.clock.now()
        asked_at = now if sent_at is None else sent_at
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            after = decided(lambda: case.ask_pc(actor, asked_at))
            await save_order(
                work, context, self.ids, case, after, person_event("order.pc_asked", context, now)
            )
            await work.commit()
        return order_change(after)

    async def answer(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        line_no: int,
        *,
        case_version: int,
        deliveries: Sequence[tuple[Decimal, date]],
    ) -> CaseChangeView:
        """PC's answer for one line (module docstring)."""
        await self._require(context, case_id)
        actor, now, scope = order_actor(context, self.gate), self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            after = await self.intake.take_pc_answer(scope, case, line_no, deliveries, actor, now)
            event = person_event("order.pc_answer_recorded", context, now)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return order_change(after)

    async def _require(self, context: AccessContext, case_id: uuid.UUID) -> None:
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_ORDER, resource_id=str(case_id)
        )
