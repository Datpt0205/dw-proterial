"""`MasterDataPort` over the master data in force (`PurchasingRuleBook`).

`RuleMasterData` reads the tenant's own version of `purchasing_master_data`,
else the platform's, which is empty: where deployed, this is the only one.
`DemoMasterData` is the local demo's: the fictional lists stand in for a
tenant that has not loaded its own yet, and give way the moment it has.
"""

from __future__ import annotations

from dataclasses import dataclass

from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import ContextScope
from dw_purchasing.adapters.mock.master_data import MockMasterData
from dw_purchasing.application.rules import PurchasingRuleBook
from dw_purchasing.domain.checks import MasterData


@dataclass(frozen=True)
class RuleMasterData:
    """Implements `MasterDataPort`: the lists in force."""

    book: PurchasingRuleBook

    async def for_context(self, context: AccessContext) -> MasterData:
        lists, _ = await self.book.master_data(ContextScope.of(context))
        return lists.master_data()


@dataclass(frozen=True)
class DemoMasterData:
    """Implements `MasterDataPort` locally: the tenant's own lists once it
    has loaded them, the fictional ones until then."""

    book: PurchasingRuleBook
    mock: MockMasterData

    async def for_context(self, context: AccessContext) -> MasterData:
        lists, layer = await self.book.master_data(ContextScope.of(context))
        if layer == "tenant":
            return lists.master_data()
        return await self.mock.for_context(context)
