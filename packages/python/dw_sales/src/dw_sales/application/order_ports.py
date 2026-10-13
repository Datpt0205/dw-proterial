"""Ports the order flow needs, declared by it; the composition root satisfies them.

Each is as narrow as its one consumer, `OrderIntake`: a reader that turns one
attachment into a PO, the rules a tenant's orders are checked under, and the
cases already opened for a PO number.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from dw_sales.application.ports import SalesScope
from dw_sales.application.threads import ThreadedCase
from dw_sales.domain.catalog import Customer
from dw_sales.domain.layouts import LayoutMapping, PoLayout
from dw_sales.domain.messages import AttachmentContent, InboundMessage
from dw_sales.domain.order_checks import IntakeCaps, OrderRules
from dw_sales.domain.orders import OrderCase, PoDocument, PrintedBuyer, Unreadable

# What a file is by its bytes: read (``pdf``, ``xlsx``), or a document this
# slice does not read (``unsupported``: image, legacy or encrypted Office
# file, archive), which is routed to Sales as unreadable.
FileType = Literal["pdf", "xlsx", "unsupported"]


class PoDocumentReaderPort(Protocol):
    """Reads a PO file into its header and lines, each value with its anchor.

    Parsing only: a reader maps no code and checks nothing. A file it cannot
    read comes back as `Unreadable` with the reason, never as a PO with the
    lines it managed to read. ``caps`` are the policy's (decision 13).
    """

    def sniff(self, data: bytes) -> FileType | None:
        """What the bytes are; None for a file that is no document at all."""
        ...

    async def buyer(self, document: AttachmentContent, caps: IntakeCaps) -> PrintedBuyer | None:
        """The buyer the file names where every PO prints it, or None."""
        ...

    async def read(
        self, document: AttachmentContent, customer_code: str, caps: IntakeCaps
    ) -> PoDocument | Unreadable:
        """``customer_code`` selects the customer's layout: where their PO keeps
        each value. A customer with no layout gets `Unreadable`."""
        ...

    def has_layout(self, customer_code: str, file_type: FileType) -> bool:
        """Whether the platform's layouts read this customer's file of this type."""
        ...

    async def read_with(
        self,
        document: AttachmentContent,
        mapping: LayoutMapping,
        caps: IntakeCaps,
        *,
        layout_ref: str,
    ) -> PoDocument | Unreadable:
        """``document`` read with a layout people mapped and approved (ticket
        30), the PO stamped with ``layout_ref``."""
        ...


# The seller's two quotation forms a file can be: a customer's request in the
# fixed-label layout, or Design's reply to a YCBG.
QuoteForm = Literal["quote_request", "design_reply"]


class QuoteFormPort(Protocol):
    """Which quotation form a file is, recognised by its marker, or None.

    What lets a readable document decide its message's kind before any
    word of the subject is read (ticket 31): recognition only, no value.
    """

    def form(self, content: AttachmentContent) -> QuoteForm | None: ...


class OrderRulesPort(Protocol):
    """The order rules that apply to ``scope``'s tenant.

    By scope from the start: a tenant's own version of a policy is resolved the
    way every versioned artifact is, its own if it has one, the platform's
    otherwise (CLAUDE.md "Per-tenant artifacts").
    """

    async def rules(self, scope: SalesScope) -> OrderRules: ...


class OrderCaseLookupPort(Protocol):
    """The cases already opened for one customer PO number.

    What a duplicate or a revised PO is recognised against. Read-only and this
    narrow on purpose: intake asks one question of the case store.
    """

    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Sequence[OrderCase]:
        """Every case for this customer's PO number: any revision, any status."""
        ...


class ThreadLinkPort(Protocol):
    """The case a reply's thread headers name (ticket 32): one case of the
    sender's own customer whose message the reply answers, or None. Satisfied
    by `ThreadLinks`; deterministic, no model."""

    async def linked_case(
        self, scope: SalesScope, message: InboundMessage, sender: Customer | None
    ) -> ThreadedCase | None: ...


class LayoutLookupPort(Protocol):
    """The PO layouts a tenant approved for its customers (ticket 30), as
    intake reads them: one short read per call, bound to the scope asked about."""

    async def approved(self, scope: SalesScope, customer_code: str) -> Sequence[PoLayout]:
        """The customer's approved layouts, one per kind of file at most."""
        ...

    async def read_count(self, scope: SalesScope, layout_ref: str) -> int:
        """How many order cases were opened from a PO read through it."""
        ...
