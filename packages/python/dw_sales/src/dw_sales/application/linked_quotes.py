"""The quote cases opened from an order (ticket 09), as the order's checks
read them: one narrow question of the case store, outside the unit of work
the order's own step holds, as `OrderCaseLookupPort` is."""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from typing import Protocol

from dw_sales.application.ports import SalesScope
from dw_sales.domain.quotes import QuoteCase


class LinkedQuotesPort(Protocol):
    """The quote cases of ``scope`` with these ids, any status; an id the
    scope does not hold is left out (RLS: another tenant's never reads)."""

    async def quotes(
        self, scope: SalesScope, quote_case_ids: Collection[uuid.UUID]
    ) -> Sequence[QuoteCase]: ...
