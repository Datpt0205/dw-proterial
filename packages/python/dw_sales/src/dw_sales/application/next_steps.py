"""The next step on an open case, and the scope that takes it.

One owner for three readers: the work list (whose step it is), the
follow-ups' "your turn" (`overview_service.WHOSE_TURN`), and who may see a
case that is not theirs (`visibility.sees_case`: the checker it waits on). A
status not listed waits on someone outside Sales (the customer, Design) or is
done.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from dw_sales.application.access import SalesScopes
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderStatus
from dw_sales.domain.quotes import QuoteStatus

ORDER_NEXT: Final[Mapping[OrderStatus, tuple[str, SalesScopes]]] = {
    OrderStatus.CHECKED: ("self_check", SalesScopes.ORDER_PREPARE),
    OrderStatus.IN_REVIEW: ("self_check", SalesScopes.ORDER_PREPARE),
    OrderStatus.PREPARED: ("bravo_entry", SalesScopes.ORDER_PREPARE),
    OrderStatus.UPLOADED_TO_BRAVO: ("cross_check", SalesScopes.ORDER_CROSS_CHECK),
    OrderStatus.CROSS_CHECKED: ("confirm", SalesScopes.ORDER_PREPARE),
    OrderStatus.CHANGE_REVIEW: ("apply_change", SalesScopes.ORDER_PREPARE),
}
QUOTE_NEXT: Final[Mapping[QuoteStatus, tuple[str, SalesScopes]]] = {
    QuoteStatus.RECEIVED: ("draft_ycbg", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.YCBG_DRAFTED: ("record_ycbg", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.YCBG_RECORDED: ("send_to_design", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.DESIGN_REPLIED: ("price", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.SPEC_DISCUSSION: ("settle_spec", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.PRICED: ("submit", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.PENDING_APPROVAL: ("approve", SalesScopes.QUOTE_APPROVE),
    QuoteStatus.RETURNED: ("reprice", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.APPROVED: ("send", SalesScopes.QUOTE_PREPARE),
    QuoteStatus.SENT: ("record_master_list", SalesScopes.QUOTE_PREPARE),
}
# Steps decided on the whole case by someone other than its assignee.
DECIDED_ON_THE_CASE: Final = frozenset({"cross_check", "approve"})


def next_step(kind: CaseKind, status: str) -> tuple[str, SalesScopes] | None:
    """The step a case in ``status`` waits on, and its scope; None if none."""
    if kind is CaseKind.ORDER:
        return ORDER_NEXT.get(OrderStatus(status)) if status in OrderStatus else None
    return QUOTE_NEXT.get(QuoteStatus(status)) if status in QuoteStatus else None


def checker_scope(kind: CaseKind, status: str) -> SalesScopes | None:
    """The scope of the checker a case in ``status`` waits on (a cross-check,
    a quotation's approval), or None when it waits on its own assignee."""
    step = next_step(kind, status)
    return step[1] if step is not None and step[0] in DECIDED_ON_THE_CASE else None
