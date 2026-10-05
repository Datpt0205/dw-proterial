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
from datetime import date, datetime
from typing import Protocol

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.domain.catalog import (
    BravoOrder,
    ConvertEntry,
    Customer,
    Item,
    LmeMonth,
    OpenYcbg,
    Quotation,
)
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


@dataclass(frozen=True, slots=True)
class Snapshot[T]:
    """What a master-data read returned, and as of when the source held it.

    ``as_of`` travels with the data rather than through a second call, so it
    always describes the data it came with: a case stamps it as part of its
    check basis (spec decision 11), and a basis that named another moment's
    snapshot would be evidence of something nobody checked against.
    """

    data: T
    as_of: datetime


class SalesSinkPort(Protocol):
    """Where a handled request goes. A real context names its repository here."""

    async def record(self, request: SalesRequest) -> None: ...


class SalesCatalogPort(Protocol):
    """The company's master data, read-only.

    Customers, items, the convert list, quotations, the LME copper price, the
    ERP's sales-order export and its open quote requests (YCBG), all of
    ``scope``'s tenant. Every read returns the snapshot's ``as_of`` beside its
    data. Every lookup is exact: a code or domain that is not there answers
    None, never the nearest match, because a near match is a guess and the
    decision belongs to Sales.
    """

    async def customer_by_code(self, scope: SalesScope, code: str) -> Snapshot[Customer | None]: ...

    async def customer_by_email_domain(
        self, scope: SalesScope, domain: str
    ) -> Snapshot[Customer | None]:
        """The customer a sender's domain belongs to, case-insensitively.

        A subdomain is a different domain: ``mail.velatrix.example`` does not
        match ``velatrix.example`` unless the customer lists it.
        """
        ...

    async def customers(self, scope: SalesScope) -> Snapshot[Sequence[Customer]]: ...

    async def items(self, scope: SalesScope) -> Snapshot[Sequence[Item]]:
        """Every item, for matching a PO description by attributes and for the
        master-data view."""
        ...

    async def item_by_prv_code(self, scope: SalesScope, prv_code: str) -> Snapshot[Item | None]: ...

    async def convert_entry(
        self, scope: SalesScope, customer_code: str, customer_item_code: str
    ) -> Snapshot[ConvertEntry | None]:
        """This customer's row for their code. Codes are per customer: two
        customers may use the same code for different items."""
        ...

    async def convert_list(self, scope: SalesScope) -> Snapshot[Sequence[ConvertEntry]]: ...

    async def quotations_valid_on(
        self, scope: SalesScope, customer_code: str, prv_code: str, day: date
    ) -> Snapshot[Sequence[Quotation]]:
        """The customer's quotations for the item that are valid on ``day``
        (`Quotation.is_valid_on`)."""
        ...

    async def quotations_for_item(
        self, scope: SalesScope, prv_code: str
    ) -> Snapshot[Sequence[Quotation]]:
        """Every customer's quotations for the item, expired ones included.

        Price evidence for Sales. Another customer's price is internal: nothing
        written for a customer may contain it.
        """
        ...

    async def quotations(self, scope: SalesScope) -> Snapshot[Sequence[Quotation]]: ...

    async def lme_for_month(self, scope: SalesScope, month: str) -> Snapshot[LmeMonth | None]:
        """The LME price for ``month`` (``YYYY-MM``, see `month_key`), or None
        when there is none for that month."""
        ...

    async def lme_months(self, scope: SalesScope) -> Snapshot[Sequence[LmeMonth]]:
        """Every month on record, oldest first."""
        ...

    async def orders_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Snapshot[Sequence[BravoOrder]]:
        """The ERP's orders keyed from this customer's PO, every revision,
        oldest revision first. Empty when the PO was never keyed."""
        ...

    async def orders_since(self, scope: SalesScope, since: date) -> Snapshot[Sequence[BravoOrder]]:
        """Every order dated ``since`` or later, oldest first: the order history
        a price is weighed against, and the yearly screening's evidence."""
        ...

    async def open_ycbg(self, scope: SalesScope) -> Snapshot[Sequence[OpenYcbg]]:
        """The quote requests (YCBG) the ERP holds open, oldest first.

        A YCBG closes when its quotation is issued, not when Design replies:
        one whose reply is already in the mailbox is still listed, and that is
        how the reply is matched to its request."""
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
