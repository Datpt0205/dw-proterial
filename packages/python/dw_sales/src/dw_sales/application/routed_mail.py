"""A message routed to Sales, marked handled (2026-10-27).

DW1 routes a message it does not turn into a case to Sales, with a reason and
an owner: the customer's PIC by address, or the PICs' pool. Until now nothing
closed one, so every routed message stayed on Việc cần làm for good. A person
marks it handled once they have dealt with it outside DW1 (replied, passed it
to PC or QA, decided it needs nothing):

- **Who may** is whoever Việc cần làm shows it to (`message_owners`, the one
  answer both read: the PIC it is addressed to, any PIC for the pool's), and
  the head (`sales.case.assign`), who decides whose work a message is.
- **What changes** is the message's mark, never its disposition: what DW1
  decided stays as it was. It leaves Việc cần làm and the overview's waiting
  count, and stays in the inbox, saying who handled it and when.
- **Undo** is a reopen, by the same people. Processing the message again
  ("DW xử lý lại") clears the mark too: it is a new disposition.
- Each change is one audit row in the change's transaction. The note is the
  person's words, so it stays on the message and the audit row says only
  whether one was left.

**A reply Sales picks the case for** ("Chọn hồ sơ", ticket 24): a reply whose
mail thread holds several cases of its customer and names none of them is
routed `reply_to_case` with those cases (`MessageDisposition.thread_cases`).
Whoever may process the mailbox (`sales.inbox.process`, as "DW xử lý" asks)
picks one, and only one of those: the message is then attached to it as a
reply on it, saying who picked it, and leaves Việc cần làm. A case not
offered is refused (409), whatever the caller sends: the offer is the allowed
list. The time DW1 processed the message stays as it was.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import permission_denied
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import (
    HANDLED_NOTE_MAX,
    MessageHandled,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
)
from dw_sales.application.ports import MemberDirectoryPort
from dw_sales.application.views import MessageDispositionView, message_disposition
from dw_sales.domain.dispositions import (
    SALES_PIC_POOL,
    CaseKind,
    DispositionKind,
    MessageDisposition,
)
from dw_sales.domain.reply_intent import CaseReply

_RESOURCE = "sales_message"


async def message_owners(
    gate: Gate, directory: MemberDirectoryPort, context: AccessContext
) -> frozenset[str]:
    """The owners whose routed messages are the caller's work: the pool and
    the caller's own address, for someone who handles the mailbox; nothing
    for anyone else. Việc cần làm lists by it and a mark is allowed by it."""
    if not gate.allows(context, SalesScopes.INBOX_PROCESS):
        return frozenset()
    mine = {
        m.email.lower()
        for m in await directory.list_members(context)
        if m.user_id == context.principal_id and m.email
    }
    return frozenset({SALES_PIC_POOL, *mine})


class HandledRequest(BaseModel):
    """The note a person may leave when they mark a message handled."""

    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=HANDLED_NOTE_MAX)


class HandledView(BaseModel):
    """Where a routed message stands after a mark or a reopen."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    handled_at: datetime | None
    handled_by: uuid.UUID | None
    handled_note: str | None


@dataclass(frozen=True)
class RoutedMailService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    directory: MemberDirectoryPort
    clock: UtcClock
    ids: IdGenerator

    async def handle(
        self, context: AccessContext, message_id: str, note: str | None
    ) -> HandledView:
        """The message marked handled by the caller, now. Marking one already
        handled keeps the first mark: a second press changes nothing."""
        text = (note or "").strip() or None
        async with self.uow(sales_scope(context)) as work:
            logged = await self._routed(context, work, message_id)
            if logged is not None:
                return _view(message_id, logged)
            mark = MessageHandled(by=context.principal_id, at=self.clock.now(), note=text)
            await self._write(context, work, message_id, mark, "sales.message.handled")
            await work.commit()
        return _view(message_id, mark)

    async def reopen(self, context: AccessContext, message_id: str) -> HandledView:
        """The message open again, back on its owner's Việc cần làm."""
        async with self.uow(sales_scope(context)) as work:
            logged = await self._routed(context, work, message_id)
            if logged is None:
                return _view(message_id, None)
            await self._write(context, work, message_id, None, "sales.message.reopened")
            await work.commit()
        return _view(message_id, None)

    async def pick_case(
        self, context: AccessContext, message_id: str, case_id: uuid.UUID
    ) -> MessageDispositionView:
        """The reply attached to ``case_id``, one of the cases its thread
        holds that it was routed with (module docstring): 404 for a message
        the workspace does not hold, 409 for a case it was not offered."""
        await self.gate.require(
            context, SalesScopes.INBOX_PROCESS, resource_type=_RESOURCE, resource_id=message_id
        )
        async with self.uow(sales_scope(context)) as work:
            logged = await work.messages.logged(message_id)
            if logged is None:
                raise NotFoundError("no such message", details={"message_id": message_id})
            routed = logged.disposition
            offered = routed.thread_case(case_id)
            if routed.kind is not DispositionKind.ROUTED_TO_SALES or offered is None:
                raise ConflictError(
                    "only a case the reply's thread holds is picked for it",
                    details={"message_id": message_id, "rule": "case_not_offered"},
                )
            stored = await (
                work.orders.get(case_id)
                if offered.case_kind is CaseKind.ORDER
                else work.quotes.get(case_id)
            )
            if stored is None or stored.case.customer_code != routed.customer_code:
                raise NotFoundError("no such case", details={"case_id": str(case_id)})
            picked = MessageDisposition(
                message_id=message_id,
                kind=DispositionKind.ATTACHED_TO_CASE,
                case_kind=offered.case_kind,
                case_id=offered.case_id,
                customer_code=routed.customer_code,
                reading=routed.reading,
                reply=CaseReply(linked_to=offered.linked_to, picked_by=context.principal_id),
            )
            # Refused here when it was processed onto a case meanwhile.
            await work.messages.record(picked, logged.processed_at)
            await work.audit.append(
                AuditEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    actor_id=UserId(context.principal_id),
                    action="sales.message.case_picked",
                    resource_type=_RESOURCE,
                    resource_id=message_id,
                    occurred_at=self.clock.now(),
                    details={"case_kind": offered.case_kind.value, "case_id": str(case_id)},
                )
            )
            await work.commit()
        return message_disposition(picked, logged.processed_at)

    async def _routed(
        self, context: AccessContext, work: SalesUnitOfWork, message_id: str
    ) -> MessageHandled | None:
        """The message's current mark, after checking the caller may change
        it: 404 for a message the workspace does not hold, 409 for one that is
        not routed to Sales, 403 for someone else's."""
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type=_RESOURCE, resource_id=message_id
        )
        logged = await work.messages.logged(message_id)
        if logged is None:
            raise NotFoundError("no such message", details={"message_id": message_id})
        disposition = logged.disposition
        if disposition.kind is not DispositionKind.ROUTED_TO_SALES:
            raise ConflictError(
                "only a message routed to Sales is marked handled",
                details={"message_id": message_id, "rule": "message_not_routed"},
            )
        owner = (disposition.owner or "").lower()
        if owner not in await message_owners(self.gate, self.directory, context) and not (
            self.gate.allows(context, SalesScopes.CASE_ASSIGN)
        ):
            raise permission_denied(
                action=SalesScopes.INBOX_PROCESS.value,
                resource_type=_RESOURCE,
                resource_id=message_id,
            )
        return logged.handled

    async def _write(
        self,
        context: AccessContext,
        work: SalesUnitOfWork,
        message_id: str,
        mark: MessageHandled | None,
        action: str,
    ) -> None:
        if not await work.messages.set_handled(message_id, mark):
            raise ConflictError(  # processed onto a case since it was read
                "only a message routed to Sales is marked handled",
                details={"message_id": message_id, "rule": "message_not_routed"},
            )
        await work.audit.append(
            AuditEvent(
                id=self.ids.new_uuid(),
                tenant_id=TenantId(context.tenant_id),
                workspace_id=WorkspaceId(context.workspace_id),
                actor_id=UserId(context.principal_id),
                action=action,
                resource_type=_RESOURCE,
                resource_id=message_id,
                occurred_at=self.clock.now(),
                details={"note": mark is not None and mark.note is not None},
            )
        )


def _view(message_id: str, mark: MessageHandled | None) -> HandledView:
    return HandledView(
        message_id=message_id,
        handled_at=mark.at if mark else None,
        handled_by=mark.by if mark else None,
        handled_note=mark.note if mark else None,
    )
