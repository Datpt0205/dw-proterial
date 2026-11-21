"""What DW holds of Bravo's facts, and how fresh it is (ticket 50).

The `bravo_sync` lane copies Bravo's black list, LME and export control
list into DW (`dw_bravo.sync`); pages read DW's copy, never Bravo, and say
when Bravo was last read: if Bravo is down the copy is stale, never wrong.
This is that "when", per table, for whoever may read cases.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict

from dw_kernel.ports import UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes

# Read every 10-15 minutes in working hours: past this, the copy is stale.
STALE_AFTER: Final = timedelta(hours=1)


@dataclass(frozen=True)
class TableState:
    table: str
    rows: int
    gone: int
    last_read_at: datetime | None
    last_full_at: datetime | None
    last_error: str | None
    last_error_at: datetime | None


class BravoFactsStorePort(Protocol):
    async def state(self, tenant_id: uuid.UUID) -> Sequence[TableState]: ...


class TableStateView(BaseModel):
    model_config = ConfigDict(frozen=True)

    table: str
    rows: int
    gone: int
    last_read_at: AwareDatetime | None
    last_full_at: AwareDatetime | None
    stale: bool
    last_error: str | None


@dataclass(frozen=True)
class BravoFactsService:
    store: BravoFactsStorePort
    gate: Gate
    clock: UtcClock

    async def state(self, context: AccessContext) -> list[TableStateView]:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type="bravo_facts")
        now = self.clock.now()
        return [
            TableStateView(
                table=t.table,
                rows=t.rows,
                gone=t.gone,
                last_read_at=t.last_read_at,
                last_full_at=t.last_full_at,
                stale=t.last_read_at is None or now - t.last_read_at > STALE_AFTER,
                last_error=t.last_error,
            )
            for t in await self.store.state(context.tenant_id)
        ]
