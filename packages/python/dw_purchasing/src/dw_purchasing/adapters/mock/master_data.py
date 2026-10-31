"""`MasterDataPort` over the fictional master data in `data/master.json`.

Bound to the one demo scope it stands in for: every other tenant and
workspace reads none, so a request there has no reference price, no budget
and goes to the last approval tier. A real adapter reads the tenant's own
lists (the master-data import, once it is the platform's engine: ADR 0013
decision 3).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from dw_platform.application.access_context import AccessContext
from dw_purchasing.adapters.mock.inbox import DATA_DIR
from dw_purchasing.domain.checks import (
    Budget,
    Item,
    MasterData,
    PastPurchase,
    Supplier,
    SupplierQuote,
)


class MockMasterData:
    """Implements `MasterDataPort` for the demo scope (module docstring)."""

    def __init__(self, data: MasterData, *, tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        self._data = data
        self._scope = (tenant_id, workspace_id)

    @classmethod
    def load(cls, *, tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> MockMasterData:
        raw: dict[str, Any] = json.loads((DATA_DIR / "master.json").read_text(encoding="utf-8"))
        items = [Item.model_validate(r) for r in raw["items"]]
        budgets = [Budget.model_validate(r) for r in raw["budgets"]]
        data = MasterData(
            items={i.code: i for i in items},
            quotes=tuple(SupplierQuote.model_validate(r) for r in raw["quotes"]),
            history=tuple(PastPurchase.model_validate(r) for r in raw["history"]),
            budgets={b.code: b for b in budgets},
            suppliers=tuple(Supplier.model_validate(r) for r in raw["suppliers"]),
        )
        return cls(data, tenant_id=tenant_id, workspace_id=workspace_id)

    async def for_context(self, context: AccessContext) -> MasterData:
        if (context.tenant_id, context.workspace_id) != self._scope:
            return MasterData()
        return self._data
