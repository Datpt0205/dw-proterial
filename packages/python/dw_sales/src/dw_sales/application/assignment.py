"""The head reassigns a case (ticket 17, G22).

A case's assignee is stamped when it opens, from the customer's Sales PIC
matched against the workspace's members (`InboxProcessing._assignee`), and
until now never changed. The head (`sales.case.assign`) gives it to someone
else, or to nobody (an unassigned case is every PIC's to pick up).

- **Who may be given it** is whoever holds the scope that works the case in
  its workspace (`sales.order.prepare` for an order, `sales.quote.prepare`
  for a quote), answered by `ScopeHoldersPort.holding`, the function the
  access context is built from: the list offered and the check made here are
  one answer. Anyone else is refused (422), another workspace's or tenant's
  member included, without saying whether they exist.
- **The change is the case's**: its version increments (a stale version is
  409, a closed case 409), with one event and one audit row naming the old
  and the new assignee, in one transaction.
- **The new assignee is told** through the platform's inbox, after the commit,
  idempotent by a key naming the case and its version: ids and the case's
  number, never an amount.
- **A support context never reassigns**: it is refused before anything is
  read, whatever scopes its grant stamped (support acts, it does not decide
  whose work a case is).
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from dw_kernel.errors import DomainError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import permission_denied
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWork, SalesUnitOfWorkFactory, Stored
from dw_sales.application.ports import (
    MemberDirectoryPort,
    NotificationSenderPort,
    ScopeHoldersPort,
)
from dw_sales.application.support import (
    audit_row,
    person_event,
    same_version,
    stored_order,
    stored_quote,
)
from dw_sales.application.views import CaseChangeView, order_change, quote_change
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderCase
from dw_sales.domain.quotes import QuoteCase

# The scope that works each kind of case: who may be given it.
_WORKS: dict[CaseKind, SalesScopes] = {
    CaseKind.ORDER: SalesScopes.ORDER_PREPARE,
    CaseKind.QUOTE: SalesScopes.QUOTE_PREPARE,
}


class AssigneeView(BaseModel):
    """A member the case may be given to."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    display_name: str


@dataclass(frozen=True)
class AssignmentService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    holders: ScopeHoldersPort
    directory: MemberDirectoryPort
    notifications: NotificationSenderPort

    async def candidates(
        self, context: AccessContext, kind: CaseKind, case_id: uuid.UUID
    ) -> list[AssigneeView]:
        """Who the case may be given to, by name: the holders of the scope
        that works it in the case's workspace."""
        await self._require(context, kind, case_id)
        async with self.uow(sales_scope(context)) as work:
            await _stored(work, kind, case_id)
        eligible = set(await self._eligible(context, kind))
        members = await self.directory.list_members(context)
        return sorted(
            (
                AssigneeView(user_id=m.user_id, display_name=m.display_name)
                for m in members
                if m.user_id in eligible
            ),
            key=lambda m: m.display_name,
        )

    async def reassign(
        self,
        context: AccessContext,
        kind: CaseKind,
        case_id: uuid.UUID,
        *,
        assignee: uuid.UUID | None,
        case_version: int,
    ) -> CaseChangeView:
        """The case given to ``assignee``, or to nobody when None."""
        await self._require(context, kind, case_id)
        now = self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            stored = await _stored(work, kind, case_id)
            case = stored.case
            same_version(case_id, case.case_version, case_version)
            after = case.reassigned()
            if assignee is not None and assignee not in await self._eligible(context, kind):
                raise DomainError(
                    "the case is given to a member who works this kind of case here",
                    details={"field": "assignee", "rule": "assignee_not_eligible"},
                )
            before = stored.origin.assigned_to
            if assignee == before:
                return _change(case)
            event = person_event(f"{kind.value}.reassigned", context, now, field="assigned_to")
            if isinstance(after, OrderCase):
                await work.orders.save(after, expected_version=case.case_version, event=event)
                await work.orders.assign(case_id, assignee)
            else:
                await work.quotes.save(after, expected_version=case.case_version, event=event)
                await work.quotes.assign(case_id, assignee)
            row = audit_row(
                context,
                self.ids,
                case_kind=kind,
                case_id=case_id,
                case_version=after.case_version,
                from_status=case.status.value,
                to_status=after.status.value,
                event=event,
            )
            await work.audit.append(
                dataclasses.replace(
                    row,
                    details={
                        **row.details,
                        "assigned_from": str(before) if before else None,
                        "assigned_to": str(assignee) if assignee else None,
                    },
                )
            )
            await work.commit()
        if assignee is not None:
            await self._notify(context, after, assignee)
        return _change(after)

    async def _require(self, context: AccessContext, kind: CaseKind, case_id: uuid.UUID) -> None:
        resource = f"sales_{kind.value}_case"
        if context.support is not None:
            raise permission_denied(
                action=SalesScopes.CASE_ASSIGN.value,
                resource_type=resource,
                resource_id=str(case_id),
            )
        await self.gate.require(
            context, SalesScopes.CASE_ASSIGN, resource_type=resource, resource_id=str(case_id)
        )

    async def _eligible(self, context: AccessContext, kind: CaseKind) -> list[uuid.UUID]:
        return await self.holders.holding(
            context.tenant_id, context.workspace_id, frozenset({_WORKS[kind].value})
        )

    async def _notify(
        self, context: AccessContext, case: OrderCase | QuoteCase, assignee: uuid.UUID
    ) -> None:
        names = {m.user_id: m.display_name for m in await self.directory.list_members(context)}
        who = names.get(context.principal_id, "Trưởng bộ phận Sales")
        if isinstance(case, OrderCase):
            what, link = f"đơn hàng PO {case.header.po_no}", f"/sales/orders/{case.case_id}"
        else:
            what, link = (
                f"báo giá RFQ {case.request.document.rfq_no.value}",
                f"/sales/quotes/{case.case_id}",
            )
        await self.notifications.deliver(
            context,
            recipients=[assignee],
            source_key=f"sales.case.assigned:{case.case_id}:{case.case_version}",
            title="Bạn được phân công một hồ sơ Sales",
            body=f"{who} đã phân công cho bạn {what}.",
            link=link,
        )


async def _stored(
    work: SalesUnitOfWork, kind: CaseKind, case_id: uuid.UUID
) -> Stored[OrderCase] | Stored[QuoteCase]:
    if kind is CaseKind.ORDER:
        return await stored_order(work, case_id)
    return await stored_quote(work, case_id)


def _change(case: OrderCase | QuoteCase) -> CaseChangeView:
    return order_change(case) if isinstance(case, OrderCase) else quote_change(case)
