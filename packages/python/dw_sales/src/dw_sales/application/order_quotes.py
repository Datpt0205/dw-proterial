"""A PO for an item with no valid quotation opens a quote case (ticket 09).

- **"Mở báo giá"** (`open`): a person, never a model, opens a quote case for
  the customer and the order's `quotation_missing` lines, its request the
  PO's own lines (`domain.order_quotes.request_from_order`), assigned to the
  order's PIC. The quote case, its link on the order and both cases' events
  and audit rows are written in one transaction: an open refused or lost to
  a concurrent one leaves neither. While one opened from the order is still
  open, opening again is refused naming it, so a double click opens one.
- **The wait**: the order cannot be prepared while a quote case linked to
  it is open (`OrderCommands.prepare`, `settled_quotes`). Whether it is open
  is the quote case's own status, read in the transaction that decides.
- **The resume**: once the quote is approved, the lines it was opened for
  are checked again with its terms as their quotation
  (`OrderIntake.take_quote_check`): by DW1 right after the approval
  (`resume`, on its own transaction, best effort: the approval stands
  whatever the order does), or by a person ("Kiểm tra lại", `recheck`).
  Every later check of those lines reads the approved terms too.

Opening needs `sales.order.prepare` (it is a step of the order) and
`sales.quote.prepare` (it opens a quote case). The audit rows name the cases
and the event, never a price.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict

from dw_kernel.errors import ConflictError, DWError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, order_actor, sales_scope
from dw_sales.application.case_store import (
    CaseOrigin,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
)
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.application.quotation import QuoteRules
from dw_sales.application.support import (
    audit_row,
    decided,
    person_event,
    same_version,
    save_order,
    save_quote,
    seen_by,
    stored_order,
    worker_event,
)
from dw_sales.application.views import CaseChangeView, QuoteLinkView, order_change
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_quotes import approved_rows, is_settled, request_from_order
from dw_sales.domain.orders import OrderCase, OrderStatus
from dw_sales.domain.quotes import FromOrder, QuoteCase

_ORDER: Final = "sales_order_case"
_QUOTE: Final = "sales_quote_case"


class QuoteRulesPort(Protocol):
    """The quote rules in force, which a new quote case is opened under."""

    async def quote_rules(self, scope: SalesScope) -> QuoteRules: ...


class OrderQuoteView(BaseModel):
    """The quote case opened from the order, and the order's next version."""

    model_config = ConfigDict(frozen=True)

    case_version: int
    quote_case_id: uuid.UUID
    lines: list[int]


async def settled_quotes(work: SalesUnitOfWork, case: OrderCase) -> frozenset[uuid.UUID]:
    """The quote cases linked to ``case`` that are approved or declined, as
    stored in ``work``'s transaction. One the store does not hold is not
    among them: the order waits on it (fail closed)."""
    settled: set[uuid.UUID] = set()
    for link in case.quote_links:
        stored = await work.quotes.get(link.quote_case_id)
        if stored is not None and is_settled(stored.case):
            settled.add(link.quote_case_id)
    return frozenset(settled)


async def quote_link_views(
    work: SalesUnitOfWork, viewer: AccessContext, case: OrderCase
) -> list[QuoteLinkView]:
    """The order's links as ``viewer`` sees them: a quote case they may not
    see shows that it exists, not its status."""
    views: list[QuoteLinkView] = []
    for link in case.quote_links:
        stored = await work.quotes.get(link.quote_case_id)
        views.append(
            QuoteLinkView(
                quote_case_id=link.quote_case_id,
                lines=list(link.lines),
                by=link.by,
                at=link.at,
                status=(
                    stored.case.status.value
                    if stored is not None and seen_by(viewer, CaseKind.QUOTE, stored)
                    else None
                ),
                waiting=stored is None or not is_settled(stored.case),
            )
        )
    return views


@dataclass(frozen=True)
class OrderQuotes:
    """`POST /orders/{case_id}/quote` and `POST /orders/{case_id}/quote-check`."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    inbox: InboxPort
    intake: OrderIntake
    rules: QuoteRulesPort
    release_manifest_ref: str | None

    async def open(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> OrderQuoteView:
        """ "Mở báo giá" (module docstring)."""
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE, _ORDER)
        await self.gate.require(context, SalesScopes.QUOTE_PREPARE, resource_type=_QUOTE)
        actor, now, scope = order_actor(context, self.gate), self.clock.now(), sales_scope(context)
        rules = await self.rules.quote_rules(scope)
        async with self.uow(scope) as work:
            stored = await stored_order(work, case_id, viewer=context)
            order = stored.case
            same_version(case_id, order.case_version, case_version)
            quote_id = self.ids.new_uuid()
            settled = await settled_quotes(work, order)
            linked = decided(lambda: order.open_quote(quote_id, actor, now, settled_quotes=settled))
            lines = linked.quote_links[-1].lines
            message = await self.inbox.get_message(scope, order.message_id)
            if message is None:
                raise ConflictError(
                    "the message the order was read from is no longer there",
                    details={"case_id": str(case_id), "rule": "quote_po_not_a_file"},
                )
            quote = QuoteCase.open(
                quote_id,
                request_from_order(order, lines, message),
                rules_version=rules.version,
                # What the order's lines were mapped and checked against.
                catalog_as_of=order.catalog_as_of or now,
                from_order=FromOrder(case_id=order.case_id, po_no=order.effective_header.po_no),
            )
            origin = CaseOrigin(
                assigned_to=stored.origin.assigned_to,
                release_manifest_ref=self.release_manifest_ref,
            )
            event = person_event("quote.opened_from_order", context, now)
            await work.quotes.add(quote, origin, event)
            await work.audit.append(
                audit_row(
                    context,
                    self.ids,
                    case_kind=CaseKind.QUOTE,
                    case_id=quote.case_id,
                    case_version=quote.case_version,
                    from_status=None,
                    to_status=quote.status.value,
                    event=event,
                )
            )
            # A complete request has its YCBG drafted by DW1 at once, as one
            # from the mailbox does (2026-10-28).
            if quote.ready_for_ycbg:
                drafted = quote.draft_ycbg()
                drafting = worker_event("quote.ycbg_drafted", context, now)
                await save_quote(work, context, self.ids, quote, drafted, drafting)
            opened = person_event("order.quote_opened", context, now)
            await save_order(work, context, self.ids, order, linked, opened)
            await work.commit()
        return OrderQuoteView(
            case_version=linked.case_version, quote_case_id=quote_id, lines=list(lines)
        )

    async def recheck(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """ "Kiểm tra lại": the lines of every approved quote opened from the
        order checked again with its terms (module docstring)."""
        await self._require(context, case_id, SalesScopes.ORDER_PREPARE, _ORDER)
        now, scope = self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            order = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, order.case_version, case_version)
            after = await self._checked(work, scope, order)
            event = person_event("order.quote_rechecked", context, now)
            await save_order(work, context, self.ids, order, after, event)
            await work.commit()
        return order_change(after)

    async def resume(self, context: AccessContext, quote: QuoteCase) -> None:
        """Right after ``quote`` was approved: the order it was opened from,
        under review, has the quote's lines checked again by DW1. Best
        effort, on its own transaction: refused (the order moved on, its
        rules no longer load), the order is left as it is, its wait already
        over, and a person checks it again."""
        if quote.from_order is None or not approved_rows(quote):
            return
        now, scope = self.clock.now(), sales_scope(context)
        try:
            async with self.uow(scope) as work:
                stored = await work.orders.get(quote.from_order.case_id)
                if stored is None or stored.case.status is not OrderStatus.IN_REVIEW:
                    return
                order = stored.case
                after = await self._checked(work, scope, order)
                event = worker_event("order.quote_rechecked", context, now)
                await save_order(work, context, self.ids, order, after, event)
                await work.commit()
        except DWError:
            return

    async def _checked(
        self, work: SalesUnitOfWork, scope: SalesScope, order: OrderCase
    ) -> OrderCase:
        """``order`` with the lines of its approved quotes checked again."""
        lines: set[int] = set()
        for link in order.quote_links:
            stored = await work.quotes.get(link.quote_case_id)
            if stored is not None and approved_rows(stored.case):
                lines.update(link.lines)
        return await self.intake.take_quote_check(scope, order, lines)

    async def _require(
        self, context: AccessContext, case_id: uuid.UUID, scope: SalesScopes, kind: str
    ) -> None:
        await self.gate.require(context, scope, resource_type=kind, resource_id=str(case_id))
