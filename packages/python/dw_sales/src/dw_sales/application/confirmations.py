"""An order's confirmation sent, then the customer's agreement, in words or by
silence, each recorded by a person (ticket 28, dw_sales ADR 0011).

1. **"Ghi đã gửi xác nhận"** (`sent`): the PIC records the confirmation sent,
   with each line's confirmed dates (step 10), and the order waits on the
   customer (`confirmation_sent`). Its clock starts now, or, when the PIC
   records it from a **sent copy** (`confirmation_copy`: a mail Sales sent
   on the case's thread carrying the processed Excel DW1 made at this case
   version, matched by sha256), at that mail's time. The copy only proposes;
   the server finds it again from the thread, whatever the request names.
2. **The customer's term of silence** is read from the rules stamped on the
   case (`OrderIntake.implied_term`): a customer with days there gets the
   instant silence counts as agreement stamped on the confirmation; any
   other never agrees by silence (acceptance 1).
3. **"Khách đã đồng ý"** (`agreed`, `accepted`): from one of the customer's
   replies on the case received after the confirmation left, when the
   person records it from one, with the sentences DW1 located there as
   `accepts`; or with none (a call, a reply DW1 did not read). **"Khách im
   lặng quá hạn → ghi đồng ý ngầm"** (`agreed`, `implied`): only once the
   stamped instant has passed. The follow-up lane tells the PIC when it does
   (`sales_followups.implied_acceptance`); nothing records it but a person.
4. **"Khách từ chối"** (`declined`): the order goes to `change_review`, its
   cross-check and confirmation cleared (ADR 0011: a `rejects` after the
   confirmation), as a person records it.

Every step needs `sales.order.prepare`, names the case version it was
decided on, and writes the case, its event and its audit row in one
transaction; the route takes an `Idempotency-Key`. The audit names ids and
how, never a quote.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.access import Gate, SalesScopes, order_actor, sales_scope
from dw_sales.application.case_store import (
    ArtifactRecord,
    CaseEvent,
    EventActor,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
)
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.outgoing import outgoing_in
from dw_sales.application.ports import MemberDirectoryPort
from dw_sales.application.runs import PendingDecisionsPort, withdraw_if_left
from dw_sales.application.support import (
    DW1_WORKER_ID,
    DW1_WORKER_VERSION,
    decided,
    person_event,
    same_version,
    save_order,
    stored_order,
)
from dw_sales.application.threads import CaseThread, ThreadMembersPort, case_thread
from dw_sales.application.views import CaseChangeView, order_change
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import Actor, AgreementHow, OrderCase

_ORDER: Final = "sales_order_case"
# The processed Excel a confirmation carries beside the customer's own PO
# (spec 11-13): the paste sheet DW1 made from the PO, the one standard file
# the order is entered from. A sent copy carrying it at this case version
# proposes the confirmation sent; the confirmation draft attaches it.
CONFIRMATION_EXCEL: Final = "bravo_upload"


def confirmation_copy(
    case: OrderCase, sent: Sequence[InboundMessage], artifacts: Sequence[ArtifactRecord]
) -> InboundMessage | None:
    """The newest message Sales sent on the case's thread (``sent``, already
    narrowed to the case's customer's writers by `case_thread`) carrying the
    processed Excel DW1 made at the case's current version, matched by
    sha256; None while the confirmation is not what the order waits on, or
    when none does. A file of another version, edited or another case's
    matches nothing."""
    if not case.awaits_confirmation:
        return None
    made = {
        a.sha256
        for a in artifacts
        if (a.case_kind, a.case_id) == (CaseKind.ORDER, case.case_id)
        and a.case_version == case.case_version
        and a.kind == CONFIRMATION_EXCEL
    }
    carrying = [m for m in sent if any(x.sha256 in made for x in m.attachments)]
    return max(carrying, key=lambda m: (m.received_at, m.message_id), default=None)


@dataclass(frozen=True)
class Confirmations:
    """`/orders/{case_id}/confirm`, `.../agreement`, `.../decline` (module
    docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    intake: OrderIntake
    decisions: PendingDecisionsPort
    # The case's thread: Sales' sent copies and the customer's replies.
    threads: ThreadMembersPort
    directory: MemberDirectoryPort

    async def sent(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        delivery_dates: Mapping[int, Sequence[date]],
        sent_message_id: str | None = None,
    ) -> CaseChangeView:
        """Step 10, with the dates Sales confirms for every line (one per
        delivery schedule, ticket 35); from a sent copy when
        ``sent_message_id`` names the one `confirmation_copy` finds now."""
        await self._require(context, case_id)
        actor, now, scope = order_actor(context, self.gate), self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            sent_at, message_id = now, None
            if sent_message_id is not None:
                thread = await self._thread(work, context, case)
                copy = confirmation_copy(
                    case, thread.sent, await work.artifacts.for_case(CaseKind.ORDER, case_id)
                )
                if copy is None or copy.message_id != sent_message_id:
                    raise ConflictError(
                        "thư này không mang tệp Excel DW1 tạo cho phiên bản hồ sơ này",
                        details={"case_id": str(case_id), "rule": "not_the_confirmation"},
                    )
                sent_at, message_id = copy.received_at, copy.message_id
            term, zone = await self.intake.implied_term(scope, case)
            after = decided(
                lambda: case.confirm(
                    actor,
                    now,
                    delivery_dates,
                    case.confirmation_sent(sent_at, term, zone, message_id=message_id),
                )
            )
            event = person_event(
                "order.confirmation_sent",
                context,
                now,
                reason_code="sent_copy" if message_id is not None else None,
            )
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        await withdraw_if_left(self.decisions, context, case, after)
        return order_change(after)

    async def agreed(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        how: AgreementHow,
        message_id: str | None = None,
    ) -> CaseChangeView:
        """The customer agreed (module docstring, step 3). ``message_id``
        names their reply on this case, received after the confirmation
        left; its `accepts` sentences, as DW1 located them, are kept."""
        await self._require(context, case_id)
        actor, now, scope = order_actor(context, self.gate), self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            quotes: tuple[str, ...] = ()
            if message_id is not None:
                if how != "accepted":
                    raise ConflictError(
                        "đồng ý ngầm không có thư của khách",
                        details={"case_id": str(case_id), "rule": "silence_names_no_reply"},
                    )
                quotes = await self._accepting_reply(work, context, case, message_id)
            after = decided(
                lambda: case.agreed(how, actor, now, message_id=message_id, quotes=quotes)
            )
            event = person_event("order.customer_agreed", context, now, reason_code=how)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return order_change(after)

    async def implied_undone(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """ "Hoàn tác đồng ý ngầm": the order waits on the customer again
        (ticket 82), whoever recorded the silence."""
        await self._require(context, case_id)
        now = self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            after = decided(case.implied_undone)
            event = person_event("order.implied_undone", context, now)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return order_change(after)

    async def declined(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """The customer did not agree to the confirmation (step 4)."""
        await self._require(context, case_id)
        now = self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            after = decided(case.declined)
            event = person_event("order.customer_declined", context, now)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return order_change(after)

    # ------------------------------------------------------------- helpers --

    async def _require(self, context: AccessContext, case_id: uuid.UUID) -> None:
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_ORDER, resource_id=str(case_id)
        )

    async def _thread(
        self, work: SalesUnitOfWork, context: AccessContext, case: OrderCase
    ) -> CaseThread:
        logged = await work.messages.list_all()
        return await case_thread(
            self.threads,
            sales_scope(context),
            {m.disposition.message_id: m for m in logged},
            case_kind=CaseKind.ORDER,
            case_id=case.case_id,
            customer_code=case.customer_code,
            outgoing=await outgoing_in(self.directory, context),
        )

    async def _accepting_reply(
        self, work: SalesUnitOfWork, context: AccessContext, case: OrderCase, message_id: str
    ) -> tuple[str, ...]:
        """The `accepts` sentences DW1 located in the customer's reply
        ``message_id``: a reply its thread headers attached to this case, and
        received after the confirmation left. Anything else is not found."""
        logged = await work.messages.logged(message_id)
        reply = None if logged is None else logged.disposition.reply
        if (
            logged is None
            or reply is None
            or not logged.disposition.is_on(CaseKind.ORDER, case.case_id)
        ):
            raise NotFoundError(
                "no such reply on the order",
                details={"case_id": str(case.case_id), "message_id": message_id},
            )
        thread = await self._thread(work, context, case)
        received = thread.received.get(message_id, logged.processed_at)
        sent = case.confirmation
        if sent is not None and received < sent.sent_at:
            raise ConflictError(
                "thư này đến trước khi gửi xác nhận",
                details={"case_id": str(case.case_id), "rule": "reply_before_confirmation"},
            )
        reading = reply.reading
        if reading is None:
            return ()
        return tuple(q.text for i in reading.intents if i.intent == "accepts" for q in i.quotes)


__all__ = ["CONFIRMATION_EXCEL", "Confirmations", "confirmation_copy"]


@dataclass(frozen=True)
class SilenceRecorder:
    """DW1 recording a customer's silence as agreement, for the follow-up
    lane (ticket 82): only the store, the clock and the ids, so the worker
    needs none of the confirmation's other collaborators."""

    uow: SalesUnitOfWorkFactory
    clock: UtcClock
    ids: IdGenerator

    async def record_implied(self, context: AccessContext, case_id: uuid.UUID) -> bool:
        """DW1 records the customer's silence as agreement itself (ticket 82,
        dw_sales ADR 0011 amendment): ``context`` is the follow-up lane's own
        (its system actor, no scope), the case read for the whole workspace.
        The domain's own fences hold: a term stamped on the confirmation and
        run out, nothing running in the update loop. False, and nothing
        written, where the case moved on or the term does not let it."""
        now = self.clock.now()
        actor = Actor(user_id=context.principal_id)
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=None)).case
            try:
                after = case.agreed("implied", actor, now)
            except ConflictError:
                return False
            event = CaseEvent(
                action="order.customer_agreed",
                actor=EventActor.worker(DW1_WORKER_ID, DW1_WORKER_VERSION, initiated_by=None),
                occurred_at=now,
                reason_code="implied",
            )
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return True
