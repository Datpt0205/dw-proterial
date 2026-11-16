"""The customer codes Sales confirmed in DW1 that Bravo's convert list does
not hold yet (dw_sales ticket 04).

Bravo owns the convert list, and a mapping goes through its approval states
1 → 2 → 3 there (11-10). A code Sales confirms in DW1 on a case stays usable
until Bravo has the row, so the facts do not end up kept in two places only
if someone enters it in Bravo: this lists each confirmed code Bravo's list
does not answer (`not_in_bravo`) or holds only waiting for approval
(`waiting_in_bravo`), and Bravo's own waiting rows, for Sales to enter and
approve there. Once Bravo's approved row is read, it answers first and the
code leaves this list. Read only; nothing here writes Bravo or the list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.ports import SalesScope

GapState = Literal["not_in_bravo", "waiting_in_bravo"]


class ConvertGap(BaseModel):
    """One customer code Bravo does not answer with an approved row."""

    model_config = ConfigDict(frozen=True)

    customer_code: str
    customer_item_code: str
    state: GapState
    # What Sales confirmed in DW1; None for a Bravo row waiting that DW1 has
    # no confirmation of.
    prv_code: str | None = None
    recorded_at: datetime | None = None
    # What Bravo's waiting row names, where it holds one.
    bravo_prv_code: str | None = None


class ConvertGapsView(BaseModel):
    """The gaps, and whether an approved Bravo convert list was read at all:
    without one, nothing can be said to be missing from it."""

    model_config = ConfigDict(frozen=True)

    bravo_read: bool
    as_of: datetime | None
    gaps: list[ConvertGap]


class ConvertGapsPort(Protocol):
    async def convert_gaps(self, scope: SalesScope) -> ConvertGapsView: ...


@dataclass(frozen=True)
class ConvertGapService:
    """The master-data page's side, for whoever reads cases."""

    catalog: ConvertGapsPort
    gate: Gate

    async def list(self, context: AccessContext) -> ConvertGapsView:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type="sales_convert_gaps")
        return await self.catalog.convert_gaps(sales_scope(context))
