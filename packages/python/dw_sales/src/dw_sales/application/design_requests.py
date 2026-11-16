"""Asking Design to create a PRV code for a line no item fits, and the code
Design names (ticket 06; drawio 1a, "code unknown: asks Design").

- **"Đề nghị Design tạo mã"** (`draft`): for a line left `unmapped`, the
  request Sales sends Design, written by code from the order case (the line
  as the PO prints it: its number, the customer's code, the description,
  quantity and requested date) and the `NEAREST` codes of the tenant's item
  master that hold the most of what the description states
  (`descriptions.nearest`, over the attributes ticket 28's reading stamped on
  the line), each with its words (`descriptions.described`), in the tenant's
  hand-off copy (`sales_handoffs`, `design_request`). Every code the draft
  names is one the scope's item master holds: nothing a model, the mail or
  the convert list names is written. It is addressed to the tenant's Design
  mailboxes (`QuoteRules.design_mailboxes`, the one setting that names
  Design, which the quotation lane already trusts for Design's replies),
  never an address a skill, a model or a mail names. The person copies it
  into a mail from their own account: DW1 sends nothing.
- **"Ghi đã gửi Design"** (`ask`): the case waits on Design for that line
  from now (`OrderCase.ask_design`), until the line's code is confirmed.
- **The code Design names** (`DesignRequestView.named`): while the line
  waits, the verified mails from those Design mailboxes received since the
  request that name the order's PO number are read by code, not a model:
  each code their newest part writes, as a whole token, that the item master
  holds is listed with the mail it came from. A code the item master does not
  hold (Design wrote it before creating it, or mistyped it) is not listed.
  Nothing maps on Design's reply: Sales confirms the code on the line
  (`OrderCommands.confirm_mapping`, which looks it up in the item master
  again and checks the line against it), and the confirmation teaches the
  customer's code (the AI list, item 3), as for any confirmed code.

Every step needs `sales.order.prepare`, as the PIC's other decisions do. The
audit row names the case, its version and the event, never the mail's text.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict

from dw_kernel.errors import ConflictError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.mail_parts import newest_part
from dw_sales.application.access import Gate, SalesScopes, order_actor, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.handoffs import (
    DesignAskedLine,
    HandoffCopyPort,
    NearestCode,
    render_design_request,
)
from dw_sales.application.pc_dates import written_in
from dw_sales.application.ports import InboxPort, SalesCatalogPort, SalesScope
from dw_sales.application.quotation import QuoteRules
from dw_sales.application.support import (
    decided,
    person_event,
    same_version,
    save_order,
    stored_order,
)
from dw_sales.application.views import CaseChangeView, order_change
from dw_sales.domain.catalog import Item
from dw_sales.domain.descriptions import described, nearest
from dw_sales.domain.orders import MappingStatus, OrderCase

_ORDER: Final = "sales_order_case"
# How many of the item master's codes the request shows Design (the ticket's
# three): enough to compare against, few enough to read in a mail.
NEAREST: Final = 3
# A PRV code's shape (`catalog.PrvCode`), as a whole token: what Design's mail
# is searched for, each one then looked up in the item master.
_CODE: Final = re.compile(r"(?<![A-Za-z0-9-])[A-Z0-9][A-Z0-9-]{1,31}(?![A-Za-z0-9-])")


class DesignMailboxesPort(Protocol):
    """Where Design is reached: the tenant's quote rules in force, whose
    ``design_mailboxes`` name the addresses Design writes from."""

    async def quote_rules(self, scope: SalesScope) -> QuoteRules: ...


class NearestCodeView(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    description: str


class NamedCodeView(BaseModel):
    """A code a Design mail names that the item master holds, and the mail."""

    model_config = ConfigDict(frozen=True)

    code: str
    description: str
    message_id: str
    sender: str
    subject: str
    received_at: datetime


class DesignRequestView(BaseModel):
    """The request to Design for one line, drafted from the case for a person
    to send, and the codes Design named since it was recorded sent (who
    recorded it, and when, is the order's own `design_requests`)."""

    model_config = ConfigDict(frozen=True)

    case_version: int
    line_no: int
    # The tenant's Design mailboxes; empty where its quote rules name none.
    to: list[str]
    subject: str
    body: str
    template_ref: str
    nearest: list[NearestCodeView]
    named: list[NamedCodeView] = []


@dataclass(frozen=True)
class DesignRequests:
    """`/orders/{case_id}/lines/{line_no}/design-request` (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    catalog: SalesCatalogPort
    copy: HandoffCopyPort
    mailboxes: DesignMailboxesPort
    # The stored mailbox; None where none is wired: no reply is listed.
    inbox: InboxPort | None = None

    async def draft(
        self, context: AccessContext, case_id: uuid.UUID, line_no: int
    ) -> DesignRequestView:
        """The request as it would be sent now, and what Design named (module docstring)."""
        await self._require(context, case_id)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
        line = case.line(line_no)
        if line.mapping.status is not MappingStatus.UNMAPPED:
            raise ConflictError(
                "only a line no item fits is a code for Design to create",
                details={"case_id": str(case_id), "line": line_no, "rule": "design_line_has_code"},
            )
        items = (await self.catalog.items(scope)).data
        stated = line.basis.stated_attributes
        near = () if stated is None else nearest(stated, items, NEAREST)
        po = line.effective
        rendered = render_design_request(
            await self.copy.handoff_copy(scope),
            customer_code=case.customer_code,
            po_no=case.effective_header.po_no,
            line=DesignAskedLine(
                line_no=line_no,
                customer_item_code=po.customer_item_code,
                description=po.description,
                quantity=po.quantity,
                uom=po.uom,
                requested_date=po.requested_date,
            ),
            nearest=[NearestCode(item.prv_code, described(item)) for item in near],
        )
        mailboxes = (await self.mailboxes.quote_rules(scope)).design_mailboxes
        return DesignRequestView(
            case_version=case.case_version,
            line_no=line_no,
            to=list(mailboxes),
            subject=rendered.subject,
            body=rendered.body,
            template_ref=rendered.template_ref,
            nearest=[
                NearestCodeView(code=item.prv_code, description=described(item)) for item in near
            ],
            named=await self._named(scope, case, line_no, mailboxes, items),
        )

    async def ask(
        self, context: AccessContext, case_id: uuid.UUID, line_no: int, *, case_version: int
    ) -> CaseChangeView:
        """ "Ghi đã gửi Design": the case waits on Design for the line from
        the server's now."""
        await self._require(context, case_id)
        actor, now = order_actor(context, self.gate), self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            after = decided(lambda: case.ask_design(line_no, actor, now))
            event = person_event("order.design_asked", context, now)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return order_change(after)

    async def _named(
        self,
        scope: SalesScope,
        case: OrderCase,
        line_no: int,
        mailboxes: Sequence[str],
        items: Sequence[Item],
    ) -> list[NamedCodeView]:
        """The codes Design's mails name for the line since it was asked
        (module docstring), newest mail first."""
        request = next((r for r in case.design_requests if r.line_no == line_no), None)
        if request is None or self.inbox is None or not mailboxes:
            return []
        design = {address.lower() for address in mailboxes}
        held = {item.prv_code: item for item in items}
        po_no = case.effective_header.po_no
        found: list[NamedCodeView] = []
        for message in await self.inbox.list_messages(scope):
            if (
                message.sender.address.lower() not in design
                or not message.authentication.verified
                or message.received_at < request.at
            ):
                continue
            part = newest_part(message)
            if not written_in(po_no, part.text):
                continue
            body = unicodedata.normalize("NFKC", part.body)
            codes = dict.fromkeys(m.group(0) for m in _CODE.finditer(body) if m.group(0) in held)
            found.extend(
                NamedCodeView(
                    code=code,
                    description=described(held[code]),
                    message_id=message.message_id,
                    sender=message.sender.address,
                    subject=message.subject,
                    received_at=message.received_at,
                )
                for code in codes
            )
        return sorted(found, key=lambda n: n.received_at, reverse=True)

    async def _require(self, context: AccessContext, case_id: uuid.UUID) -> None:
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_ORDER, resource_id=str(case_id)
        )
