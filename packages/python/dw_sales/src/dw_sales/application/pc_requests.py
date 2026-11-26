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
- **PC's mail read by DW1** (ticket 77, `pc_replies`): its dates proposed on
  the lines asked. "Đúng" on one line (`accept_reply`) records them as the
  person's answer, with the line's own deliveries, once that person opened
  the mail at this version (`reply_mail`, which records it served;
  ui-quality §7); one line per press, never several. "Sửa" is the answer
  form. Either records a labelled case beside what DW1 proposed.

Every step needs `sales.order.prepare`, as the PIC's other decisions do. The
audit rows name the case, its version and the event, never a quantity or a
date (spec decision 8).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict

from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.mail_parts import newest_part
from dw_sales.application.access import Gate, SalesScopes, order_actor, sales_scope
from dw_sales.application.case_store import (
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
    ServedSource,
    SourceRegion,
)
from dw_sales.application.handoffs import HandoffCopyPort, pc_asked_lines, render_pc_request
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.overview_ports import FollowupPolicyPort
from dw_sales.application.ports import InboxPort
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
from dw_sales.domain.labelled_cases import pc_reply_label
from dw_sales.domain.orders import OrderCase

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


class PcReplyMailView(BaseModel):
    """PC's mail a proposal was read from, as the PIC opens it: its newest
    part, the words DW1 read (ticket 77)."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    sender: str
    subject: str
    received_at: datetime
    text: str


def pc_mail_region(message_id: str) -> SourceRegion:
    """PC's mail served for its proposal, recorded as a one-page source of
    its own (`ServedSource`): ``pcmail.`` and its id's sha256, so any message
    id fits the record's shape."""
    digest = hashlib.sha256(message_id.encode()).hexdigest()[:40]
    return SourceRegion(f"pcmail.{digest}", 1, None)


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
    # The stored mailbox PC's mail is opened from (ticket 77); None where no
    # mailbox is wired: no mail is served, and no line can be confirmed.
    inbox: InboxPort | None = None

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
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            return await self._recorded(work, context, case, line_no, deliveries)

    async def accept_reply(
        self, context: AccessContext, case_id: uuid.UUID, line_no: int, *, case_version: int
    ) -> CaseChangeView:
        """ "Đúng" on one line DW1 read from PC's mail (module docstring)."""
        await self._require(context, case_id)
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            proposed = case.pc_reply.of(line_no) if case.pc_reply is not None else ()
            if not proposed:
                raise NotFoundError(
                    "DW1 không đề xuất ngày PC nào cho dòng này",
                    details={"line": line_no, "rule": "pc_reply_none"},
                )
            quantities = case.line(line_no).delivery_quantities
            if [d.delivery for d in proposed] != list(range(1, len(quantities) + 1)):
                raise ConflictError(
                    "thư PC không nêu ngày cho mọi đợt của dòng: ghi ngày PC bằng tay",
                    details={"line": line_no, "rule": "pc_reply_incomplete"},
                )
            await self._require_opened(work, context, case, {d.message_id for d in proposed})
            deliveries = [(q, d.date) for q, d in zip(quantities, proposed, strict=True)]
            return await self._recorded(work, context, case, line_no, deliveries)

    async def reply_mail(
        self, context: AccessContext, case_id: uuid.UUID, message_id: str
    ) -> PcReplyMailView:
        """PC's mail a proposal on the case was read from, opened by the
        caller: recorded served to them at the case's version, which "Đúng"
        asks for. Any other mail is not found."""
        await self._require(context, case_id)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            named = {d.message_id for d in case.pc_reply.dates} if case.pc_reply else set()
            message = (
                await self.inbox.get_message(scope, message_id)
                if self.inbox is not None and message_id in named
                else None
            )
            if message is None:
                raise NotFoundError(
                    "không có thư PC này trong đề xuất của đơn",
                    details={"message_id": message_id},
                )
            text = newest_part(message).text
            region = pc_mail_region(message_id)
            await work.served.record(
                ServedSource(
                    principal_id=context.principal_id,
                    case_kind=CaseKind.ORDER,
                    case_id=case_id,
                    case_version=case.case_version,
                    attachment_id=region.attachment_id,
                    attachment_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    page=region.page,
                    served_at=self.clock.now(),
                )
            )
            await work.commit()
        return PcReplyMailView(
            message_id=message.message_id,
            sender=message.sender.address,
            subject=message.subject,
            received_at=message.received_at,
            text=text,
        )

    async def _require_opened(
        self, work: SalesUnitOfWork, context: AccessContext, case: OrderCase, mails: set[str]
    ) -> None:
        """409 "chưa mở nguồn" until the caller opened every mail the line's
        dates were read from, at the case's current version."""
        served = await work.served.served(
            context.principal_id, CaseKind.ORDER, case.case_id, case.case_version
        )
        if not all(pc_mail_region(m) in served for m in mails):
            raise ConflictError(
                "chưa mở nguồn: mở thư PC ở phiên bản hồ sơ này trước khi bấm Đúng",
                details={
                    "case_id": str(case.case_id),
                    "case_version": case.case_version,
                    "rule": "source_not_served",
                },
            )

    async def _recorded(
        self,
        work: SalesUnitOfWork,
        context: AccessContext,
        case: OrderCase,
        line_no: int,
        deliveries: Sequence[tuple[Decimal, date]],
    ) -> CaseChangeView:
        """PC's answer for one line, saved with its event and audit row, and,
        where DW1 had proposed dates for the line, the labelled case beside."""
        actor, now, scope = order_actor(context, self.gate), self.clock.now(), sales_scope(context)
        after = await self.intake.take_pc_answer(scope, case, line_no, deliveries, actor, now)
        event = person_event("order.pc_answer_recorded", context, now)
        await save_order(work, context, self.ids, case, after, event)
        label = pc_reply_label(
            case, after, line_no, new_id=self.ids.new_uuid, at=now, by=context.principal_id
        )
        if label is not None:
            await work.labelled_cases.append([label])
        await work.commit()
        return order_change(after)

    async def _require(self, context: AccessContext, case_id: uuid.UUID) -> None:
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_ORDER, resource_id=str(case_id)
        )
