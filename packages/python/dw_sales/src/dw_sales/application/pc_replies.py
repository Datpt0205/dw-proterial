"""PC's mail read by DW1 while an order waits on PC, and proposed to the PIC
(ticket 77; the worker's `sales_pc_replies` lane).

Where the tenant turns `model_assist.pc_reply` on, its live eval met the bar
(`ModelStepGatePort`), and its order rules name PC's mailboxes
(`pc_mailboxes`), each tick reads, per workspace:

- **which mail** is PC's answer, by code alone: a verified mail from one of
  PC's mailboxes, received since the case asked PC, naming the PO number or
  the Bravo sales order of exactly one order waiting on PC (a mail naming
  two is left to the person's own list, `pc_dates.mails`: line numbers repeat
  across orders, so its dates could land on the wrong one), not read already
  for this wait. Oldest first, so a later mail's dates stand per line.
- **what it says**: its newest part (history cut by structure, so DW1's own
  request quoted below is not read) through `pc_dates.reading`, the reading
  Sales' own uses, every date checked by code.
- **what is kept**: `OrderCase.read_pc_reply`, a proposal per line asked;
  nothing of the case's values changes. A mail read to no date is kept as
  read too, so it costs one call. A mail that could not be read (the
  model down, its answer not valid) is read again each tick for
  `RETRY_FOR` after it arrived, then kept as read with no date and the PIC
  told to read it; one too long to read at all (`pc_dates.fits`) is that
  at once. Never read for ever, on the GPU interactive steps share, and
  never dropped silently.

The PIC is told when a mail gave dates, or could not be read (no PO number in the words, as every
push is), and confirms or corrects each line on the case (`PcRequests`). Off,
not ready, no mailbox named, or DW1 paused: nothing is read. The lane audits
as itself (ADR 0011), counts only.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Final, Protocol

from dw_agent_runtime.model.interpretation import InterpretationPort
from dw_kernel.errors import ConflictError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import lane_audit_event, system_actor
from dw_platform.domain.mail_parts import newest_part
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.case_store import CaseEvent, EventActor, SalesUnitOfWorkFactory, Stored
from dw_sales.application.order_ports import ModelStepGatePort, OrderRulesPort
from dw_sales.application.pc_dates import fits, reading, written_in
from dw_sales.application.ports import InboxPort, NotificationSenderPort, SalesScope
from dw_sales.application.salesorder_pairs import lane_run
from dw_sales.application.support import DW1_WORKER_ID, DW1_WORKER_VERSION
from dw_sales.application.worker_service import require_running
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import OrderCase

logger = logging.getLogger("dw_sales.pc_replies")

SALES_PC_REPLIES_LANE: Final = "sales_pc_replies"
_ORDER: Final = "sales_order_case"
# Said to the PIC when PC's mail gave dates: no PO number, no date.
_TOLD: Final = (
    "PC đã trả lời ngày giao",
    "DW1 đọc thư PC và đề xuất ngày cho {lines} dòng. Mở đơn để bấm Đúng hoặc Sửa từng dòng.",
)
# Said when PC's mail could not be read: the PIC reads it.
_UNREAD: Final = (
    "DW1 không đọc được thư PC",
    "Có thư PC trả lời về một đơn đang chờ PC mà DW1 không đọc được. "
    "Mở đơn, xem thư PC và ghi ngày bằng tay.",
)
# How long after it arrived a mail DW1 could not read is tried again, one
# call a tick (module docstring).
RETRY_FOR: Final = timedelta(hours=1)


class PcReplyScopesPort(Protocol):
    async def scopes(self) -> Sequence[SalesScope]: ...


@dataclass(frozen=True)
class PcReplyTick:
    read: int = 0
    proposed: int = 0


def _names(case: OrderCase) -> list[str]:
    """What PC's answer names the order by: its PO number, its Bravo SO."""
    return [case.document.header.po_no, *([case.bravo_so_no] if case.bravo_so_no else [])]


def _lane_context(scope: SalesScope) -> AccessContext:
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=system_actor(SALES_PC_REPLIES_LANE).value,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )


def answered_by(
    message: InboundMessage, waiting: Sequence[OrderCase], pc: frozenset[str]
) -> OrderCase | None:
    """The one waiting order ``message`` answers for PC, or None (module
    docstring, "which mail")."""
    if not message.authentication.verified or message.sender.address.lower() not in pc:
        return None
    text = f"{message.subject}\n{newest_part(message).text}"
    named = [case for case in waiting if any(written_in(n, text) for n in _names(case))]
    if len(named) != 1:
        return None
    (case,) = named
    request, held = case.pc_request, case.pc_reply
    if request is None or message.received_at < request.at:
        return None
    if held is not None and message.message_id in held.messages:
        return None
    return case


@dataclass(frozen=True)
class PcReplyLane:
    """The worker's `sales_pc_replies` lane (module docstring)."""

    uow: SalesUnitOfWorkFactory
    scopes: PcReplyScopesPort
    inbox: InboxPort
    rules: OrderRulesPort
    steps: ModelStepGatePort
    model: InterpretationPort
    notifications: NotificationSenderPort
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def tick(self) -> PcReplyTick:
        read = proposed = 0
        for scope in await self.scopes.scopes():
            try:
                done = await self._scope(scope)
            except Exception:
                logger.exception("sales_pc_replies: a workspace was not read")
                continue
            read, proposed = read + done.read, proposed + done.proposed
        return PcReplyTick(read=read, proposed=proposed)

    async def _scope(self, scope: SalesScope) -> PcReplyTick:
        rules = await self.rules.rules(scope)
        pc = frozenset(a.lower() for a in rules.pc_mailboxes)
        if not pc or not await self.steps.allows(scope, rules, ModelStep.PC_REPLY):
            return PcReplyTick()
        async with self.uow(scope) as work:
            waiting = {s.case.case_id: s for s in await work.orders.waiting_on_pc()}
        if not waiting:
            return PcReplyTick()
        read = proposed = 0
        for message in await self.inbox.list_messages(scope):
            case = answered_by(message, [s.case for s in waiting.values()], pc)
            if case is None:
                continue
            kept = await self._read(scope, waiting[case.case_id], message)
            if kept is None:
                continue
            stored, unread = kept
            read += 1
            waiting[case.case_id] = stored
            if unread:
                await self._tell(scope, stored, message, _UNREAD)
                continue
            before = case.pc_reply.dates if case.pc_reply else ()
            after = stored.case.pc_reply.dates if stored.case.pc_reply else ()
            fresh = {d.line_no for d in after if d.message_id == message.message_id}
            if fresh and set(after) != set(before):
                proposed += 1
                title, body = _TOLD
                await self._tell(scope, stored, message, (title, body.format(lines=len(fresh))))
        return PcReplyTick(read=read, proposed=proposed)

    async def _read(
        self, scope: SalesScope, stored: Stored[OrderCase], message: InboundMessage
    ) -> tuple[Stored[OrderCase], bool] | None:
        """``message`` read for the case, kept with its event and audit row in
        one transaction, and whether it was kept unread (module docstring);
        None when nothing was kept (to be read again, or the case moved on
        while it was read)."""
        case = stored.case
        run_id = self.ids.new_uuid()
        run = lane_run(SALES_PC_REPLIES_LANE, scope, run_id, self.worker_id, self.worker_version)
        text = newest_part(message).text
        view = await reading(self.model, case, text, run)
        now = self.clock.now()
        unread = view.status == "unavailable"
        if unread and fits(self.model, text) and now - message.received_at < RETRY_FOR:
            return None
        try:
            after = case.read_pc_reply(
                message.message_id,
                message.received_at,
                [(d.line_no, d.delivery, d.date, d.quote) for d in view.dates],
                at=now,
                prompt_ref=view.prompt_ref or "",
                model_profile=view.model_profile or "",
            )
        except ConflictError as refused:
            logger.info("sales_pc_replies: a mail was not kept: %s", refused.details.get("rule"))
            return None
        async with self.uow(scope) as work:
            try:
                await require_running(work)
            except ConflictError:
                return None
            current = await work.orders.get(case.case_id)
            if current is None or current.case.case_version != case.case_version:
                return None  # moved on while it was read: read again next tick
            await work.orders.save(
                after,
                expected_version=case.case_version,
                event=CaseEvent(
                    action="order.pc_reply_read",
                    actor=EventActor.worker(DW1_WORKER_ID, DW1_WORKER_VERSION, initiated_by=None),
                    occurred_at=now,
                ),
            )
            await work.audit.append(
                lane_audit_event(
                    lane=SALES_PC_REPLIES_LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=scope.tenant_id,
                    workspace_id=scope.workspace_id,
                    action="sales.order.pc_reply_read",
                    resource_type=_ORDER,
                    resource_id=str(case.case_id),
                    occurred_at=now,
                    run_id=run_id,
                    details={
                        "case_version": after.case_version,
                        "dates": len(view.dates),
                        "unread": unread,
                        "dropped": view.dropped,
                        "step": ModelStep.PC_REPLY.value,
                        "prompt": view.prompt_ref,
                    },
                )
            )
            await work.commit()
        return Stored(after, stored.origin), unread

    async def _tell(
        self,
        scope: SalesScope,
        stored: Stored[OrderCase],
        message: InboundMessage,
        words: tuple[str, str],
    ) -> None:
        """The case's assignee, else who asked PC, told once per mail."""
        request = stored.case.pc_request
        who = stored.origin.assigned_to or (request.by if request is not None else None)
        if who is None:
            return
        title, body = words
        mail = hashlib.sha256(message.message_id.encode()).hexdigest()[:16]
        try:
            await self.notifications.deliver(
                _lane_context(scope),
                recipients=[who],
                source_key=f"{SALES_PC_REPLIES_LANE}:{stored.case.case_id}:{mail}",
                title=title,
                body=body,
                link=f"/sales/orders/{stored.case.case_id}",
            )
        except Exception:
            logger.exception("sales_pc_replies: the PIC was not told")


__all__ = ["RETRY_FOR", "SALES_PC_REPLIES_LANE", "PcReplyLane", "PcReplyTick", "answered_by"]
