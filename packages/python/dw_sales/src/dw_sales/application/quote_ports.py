"""The ports the quotation flow needs beyond master data and the mailbox.

A customer's request-for-quotation file and Design's reply are read by
adapters, as a purchase order is: a layout is its author's, and the flow should
not change when a second layout, or a second format, arrives. Cases are found
by the YCBG number Design's reply quotes, and a sent quotation is written to
the master list, through ports the composition root satisfies.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from dw_kernel.errors import DomainError
from dw_sales.application.ports import SalesScope
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import Quotation
from dw_sales.domain.messages import AttachmentContent
from dw_sales.domain.quotes import DesignReplyDocument, QuoteCase, RfqDocument


class QuoteFileUnreadableError(DomainError):
    """A file that presents itself as a request for quotation or a Design
    reply states a value that cannot be read. Names the place, so a person can
    look at it there, and never what is written in it: that is the sender's
    text, and the message reaches logs."""

    def __init__(self, problem: str, *, at: SourceAnchor) -> None:
        super().__init__(
            f"{problem} ({at.cell_ref})",
            details={
                "problem": problem,
                "attachment_id": at.attachment_id,
                "cell_ref": at.cell_ref,
            },
        )
        self.at = at


class RfqReaderPort(Protocol):
    """Reads a customer's request-for-quotation file."""

    def read(self, content: AttachmentContent) -> RfqDocument | None:
        """What the file states, every value anchored to its place in it.

        None when the file is not a request for quotation in a layout this
        reader knows. A quantity or required date the customer left blank is
        read as blank (`rfq_incomplete`); any other value that cannot be read
        raises `QuoteFileUnreadableError`: a request read in part is a request
        misread.
        """
        ...


class DesignReplyReaderPort(Protocol):
    """Reads Design's reply to a YCBG."""

    def read(self, content: AttachmentContent) -> DesignReplyDocument | None:
        """None when the file is not a Design reply this reader knows; raises
        `QuoteFileUnreadableError` when it is one with a value it cannot read."""
        ...


class QuoteCaseLookupPort(Protocol):
    """The quote cases recorded under one YCBG number.

    What a Design reply is matched against, by that number and nothing else.
    Read-only and this narrow on purpose: matching asks one question of the
    case store.
    """

    async def cases_for_ycbg(self, scope: SalesScope, ycbg_no: str) -> Sequence[QuoteCase]:
        """Every case of ``scope`` whose recorded YCBG is ``ycbg_no``, any status."""
        ...


class QuotationLedgerPort(Protocol):
    """The quotation master list (WIV-03-023 step 11), where a sent quotation
    becomes the valid quotation a later PO line is checked against.

    Idempotent by quote number: recording the same rows again changes nothing,
    and different rows under a recorded number are refused. A production
    adapter refuses every write until the customer grants write access to
    their master list; the demo's is `adapters.mock.quotation_ledger`.
    """

    async def record(self, scope: SalesScope, rows: Sequence[Quotation]) -> None: ...
