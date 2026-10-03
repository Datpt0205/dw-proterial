"""Ports this context needs, declared BY the consumer.

The composition root satisfies them. Declaring them here rather than importing a
concrete adapter is what keeps the handler testable without infrastructure.

Master data and the mailbox are read through ports and never copied into this
context's tables (spec decision 2): the mock adapters over fixture files are
replaced by ERP, SharePoint or Microsoft 365 adapters without the flow changing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.domain.catalog import ConvertEntry, Customer, Item, LmeMonth, Quotation
from dw_sales.domain.entities import SalesRequest
from dw_sales.domain.messages import AttachmentContent, InboundMessage


@dataclass(frozen=True, slots=True)
class SalesScope:
    """Whose master data and whose mailbox a call reads.

    Built from the verified access context, or from the run that started the
    work, and never from anything a request carries: a caller who could name
    the tenant would read another company's customers and prices.
    """

    tenant_id: TenantId
    workspace_id: WorkspaceId


class SalesSinkPort(Protocol):
    """Where a handled request goes. A real context names its repository here."""

    async def record(self, request: SalesRequest) -> None: ...


class SalesCatalogPort(Protocol):
    """The company's master data, read-only.

    Customers, items, the convert list, quotations and the LME copper price of
    ``scope``'s tenant. Every lookup is exact: a code or domain that is not
    there answers None, never the nearest match, because a near match is a
    guess and the decision belongs to Sales.
    """

    async def customer_by_code(self, scope: SalesScope, code: str) -> Customer | None: ...

    async def customer_by_email_domain(self, scope: SalesScope, domain: str) -> Customer | None:
        """The customer a sender's domain belongs to, case-insensitively.

        A subdomain is a different domain: ``mail.velatrix.example`` does not
        match ``velatrix.example`` unless the customer lists it.
        """
        ...

    async def customers(self, scope: SalesScope) -> Sequence[Customer]: ...

    async def items(self, scope: SalesScope) -> Sequence[Item]:
        """Every item, for matching a PO description by attributes and for the
        master-data view."""
        ...

    async def item_by_prv_code(self, scope: SalesScope, prv_code: str) -> Item | None: ...

    async def convert_entry(
        self, scope: SalesScope, customer_code: str, customer_item_code: str
    ) -> ConvertEntry | None:
        """This customer's row for their code. Codes are per customer: two
        customers may use the same code for different items."""
        ...

    async def convert_list(self, scope: SalesScope) -> Sequence[ConvertEntry]: ...

    async def quotations_valid_on(
        self, scope: SalesScope, customer_code: str, prv_code: str, day: date
    ) -> Sequence[Quotation]:
        """The customer's quotations for the item that are valid on ``day``
        (`Quotation.is_valid_on`)."""
        ...

    async def quotations_for_item(self, scope: SalesScope, prv_code: str) -> Sequence[Quotation]:
        """Every customer's quotations for the item, expired ones included.

        Price evidence for Sales. Another customer's price is internal: nothing
        written for a customer may contain it.
        """
        ...

    async def quotations(self, scope: SalesScope) -> Sequence[Quotation]: ...

    async def lme_for_month(self, scope: SalesScope, month: str) -> LmeMonth | None:
        """The LME price for ``month`` (``YYYY-MM``, see `month_key`), or None
        when there is none for that month."""
        ...

    async def lme_months(self, scope: SalesScope) -> Sequence[LmeMonth]:
        """Every month on record, oldest first."""
        ...


class InboxPort(Protocol):
    """The mailbox DW1 reads: the messages it has been given, and their files."""

    async def list_messages(self, scope: SalesScope) -> Sequence[InboundMessage]:
        """Oldest first by ``received_at``: the order a duplicate or a revised
        PO is recognised in."""
        ...

    async def get_message(self, scope: SalesScope, message_id: str) -> InboundMessage | None: ...

    async def read_attachment(
        self, scope: SalesScope, message_id: str, attachment_id: str
    ) -> AttachmentContent | None:
        """The bytes of one attachment, or None when that message has no such
        attachment."""
        ...
