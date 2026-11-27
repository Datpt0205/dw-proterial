"""Which Bravo a read or a write reaches: the tenant's target now (ticket 85).

The gateway holds a credential set per target (`settings`), and the tenant's
approved `sales_bravo_writes` version names the one in use (`Switches.target`).
Every read and write is routed by it, read at that moment: a target the
gateway holds no logins for refuses (`target_unconfigured`), and nothing
falls back to the other. The write pipeline checks the target again itself,
so a switch made between the routing and the write refuses the write.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from dw_bravo.contract import BRAVO_TARGETS, BravoTarget, WriteCommand
from dw_bravo.watch import Fingerprint
from dw_bravo_gateway.pipeline import Preview, WritePipeline, WriteResult
from dw_bravo_gateway.ports import Directory, SalesOrders, Switches, SyncTables


class FingerprintSource(Protocol):
    async def fingerprint(self, environment: Literal["uat", "production"]) -> Fingerprint: ...


class TargetRefusedError(Exception):
    """The tenant's target cannot be reached: nothing is read or written."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class TargetBravo:
    """One configured Bravo: the write pipeline over it, and its reads."""

    pipeline: WritePipeline
    orders: SalesOrders | None = None
    directory: Directory | None = None
    sync: SyncTables | None = None
    fingerprints: FingerprintSource | None = None


@dataclass(frozen=True)
class Targets:
    tenant_id: uuid.UUID
    switches: Switches
    reach: Mapping[BravoTarget, TargetBravo]

    async def now(self) -> tuple[BravoTarget, TargetBravo]:
        target = await self.switches.target(self.tenant_id)
        if target is None:
            raise TargetRefusedError("target_unreadable")
        bravo = self.reach.get(target)
        if bravo is None:
            raise TargetRefusedError("target_unconfigured")
        return target, bravo

    def configured(self) -> dict[BravoTarget, bool]:
        return {t: t in self.reach for t in BRAVO_TARGETS}

    async def execute(self, command: WriteCommand, token: str) -> WriteResult:
        try:
            _, bravo = await self.now()
        except TargetRefusedError as refused:
            return WriteResult("refused", "target", refused.reason)
        return await bravo.pipeline.execute(command, token)

    async def preview(self, command: WriteCommand, token: str) -> Preview:
        try:
            _, bravo = await self.now()
        except TargetRefusedError as refused:
            return Preview(None, "target", refused.reason)
        return await bravo.pipeline.preview(command, token)
