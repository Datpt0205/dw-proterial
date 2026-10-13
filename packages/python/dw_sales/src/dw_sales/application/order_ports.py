"""Ports the order flow needs, declared by it; the composition root satisfies them.

Each is as narrow as its one consumer, `OrderIntake`: a reader that turns one
attachment into a PO, the rules a tenant's orders are checked under, and the
cases already opened for a PO number.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from dw_sales.application.ports import SalesScope
from dw_sales.domain.messages import AttachmentContent
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
