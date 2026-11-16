"""A PO for an item with no valid quotation opens a quote case (ticket 09;
drawio 2a: a PO can arrive before any quotation, and Sales then quotes first).

From the order's `quotation_missing` lines a person opens a quote case
("Mở báo giá"). Its request is the PO's own lines, every value anchored where
the PO prints it, so the quote case serves the same file the order does; the
customer is the order's. Nothing is read by a model.

The two cases name each other (`OrderCase.quote_links`, `QuoteCase.from_order`).
Whether the order still waits is the quote case's own status, read where it
matters, never a copy on the order: a quotation approved, then priced again,
is open again, and the order waits again. Once approved, its terms are the
quotation the order's lines are checked against at the order's next check: a
quotation made for this PO applies from the PO's date, which its issue date
follows by construction.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from typing import Final

from pydantic import TypeAdapter, ValidationError

from dw_kernel.errors import ConflictError
from dw_platform.domain.messages import InboundMessage
from dw_sales.domain.catalog import CustomerItemCode, Quotation
from dw_sales.domain.orders import OrderCase, OrderLine
from dw_sales.domain.quotes import (
    QuoteCase,
    QuoteRequest,
    QuoteStatus,
    RequestedItem,
    RfqDocument,
    Sourced,
    quoted_rows,
)

# The quote case is approved, and its approved document stands.
APPROVED_ON: Final = frozenset(
    {QuoteStatus.APPROVED, QuoteStatus.SENT, QuoteStatus.MASTER_LIST_RECORDED}
)
# The order no longer waits on it: approved, or declined.
SETTLED: Final = APPROVED_ON | {QuoteStatus.DECLINED}

_ITEM_CODE: Final = TypeAdapter(CustomerItemCode)


def is_settled(quote: QuoteCase) -> bool:
    """Approved or declined: the order it was opened from waits no more."""
    return quote.status in SETTLED


def approved_rows(quote: QuoteCase) -> tuple[Quotation, ...]:
    """The quotation an approved quote case states (`quoted_rows`): the
    document the approval is bound to, by its hash; none otherwise."""
    submission, approval = quote.submission, quote.approval
    if (
        quote.status not in APPROVED_ON
        or submission is None
        or approval is None
        or approval.document_sha256 != submission.document_sha256
    ):
        return ()
    return quoted_rows(submission.document)


def quoted_for_po(
    quotes: Iterable[QuoteCase], *, customer_code: str, prv_code: str, po_date: date
) -> Quotation | None:
    """The quotation approved for this PO's item among ``quotes`` (those
    opened from the order for the line), as it applies to the PO: from the
    PO's date to the last day its prices hold. Another customer's is never
    one; of two, the later issue applies (`order_checks.current_quotation`).
    None where none is approved, or its prices ended before the PO's date."""
    rows = [
        row
        for quote in quotes
        if quote.customer_code == customer_code
        for row in approved_rows(quote)
        if row.customer_code == customer_code and row.prv_code == prv_code
    ]
    latest = max(rows, key=lambda r: (r.valid_from, r.quote_no), default=None)
    if latest is None or latest.valid_to < po_date:
        return None
    return latest.model_copy(update={"valid_from": min(latest.valid_from, po_date)})


def request_from_order(
    order: OrderCase, lines: Sequence[int], message: InboundMessage
) -> QuoteRequest:
    """The request a quote opened from ``order`` asks: ``lines`` as the order
    holds them (Sales' corrections included), each value anchored where the
    PO prints it, in the PO's currency; the PO's price as the customer's
    target. Refused, naming why, for a PO read from the mail's text (no file
    to serve) and for values the request's types do not take."""
    document = order.document
    details: dict[str, object] = {"case_id": str(order.case_id)}
    attachment = next(
        (a for a in message.attachments if a.attachment_id == document.attachment_id), None
    )
    if document.attachment_id is None or attachment is None:
        raise ConflictError(
            "a quote is opened from a PO read from a file",
            details={**details, "rule": "quote_po_not_a_file"},
        )
    header = order.effective_header
    try:
        rfq = RfqDocument(
            parser_version=document.parser_version,
            rfq_no=None,
            rfq_date=None,
            currency=Sourced(value=header.currency, source=header.anchors.currency),
            items=tuple(_item(order.line(no)) for no in lines),
        )
        return QuoteRequest(
            message_id=order.message_id,
            received_at=order.received_at,
            sender=message.sender,
            attachment=attachment,
            customer_code=order.customer_code,
            customer_from="sender_domain",
            document=rfq,
        )
    except (ValidationError, ValueError):
        raise ConflictError(
            "the PO's lines do not make a request for quotation",
            details={**details, "rule": "quote_request_unreadable"},
        ) from None


def _item(line: OrderLine) -> RequestedItem:
    po, anchors, item = line.effective, line.effective.anchors, line.basis.item
    if item is None or item.uom is None:
        raise ValueError(f"line {line.line_no} names no item with a unit")
    code = po.customer_item_code
    described = po.description.strip()
    item_code: Sourced[CustomerItemCode] | None
    try:
        item_code = Sourced(
            value=_ITEM_CODE.validate_python(code), source=anchors.customer_item_code
        )
    except ValidationError:
        item_code = None
    return RequestedItem(
        line_no=line.line_no,
        customer_item_code=item_code,
        description=Sourced(
            value=described or code,
            source=anchors.description if described else anchors.customer_item_code,
        ),
        quantity=Sourced(value=po.quantity, source=anchors.quantity),
        uom=Sourced(value=item.uom, source=anchors.uom),
        target_price=(
            Sourced(value=po.unit_price, source=anchors.unit_price) if po.unit_price > 0 else None
        ),
        needed_by=Sourced(value=po.requested_date, source=anchors.requested_date),
        candidates=(item.prv_code,),
    )
