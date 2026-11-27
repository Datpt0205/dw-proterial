"""The `bravo_ledger_health` lane (Sales ticket 84): the gateway's writes that
wait for a person, as a gauge the operator's alerts read.

Every five minutes it sets `dw_bravo_writes_needing_a_person` from the ledger
itself (`SqlBravoLedgerHealth`), so the number survives a worker restart and
a redelivered settlement counts nothing twice. `DwBravoWriteNeedsAPerson`
fires when it rises; the PIC already sees each one on the case.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final, Protocol

from dw_observability.metrics import DW_BRAVO_WRITES_NEEDING_A_PERSON
from dw_observability.telemetry import TelemetryPort

BRAVO_LEDGER_HEALTH_LANE: Final = "bravo_ledger_health"
INTERVAL_SECONDS: Final = 300.0


class LedgerHealthPort(Protocol):
    async def needing_a_person(self) -> int: ...


def build_bravo_ledger_health_consumer(
    ledger: LedgerHealthPort, telemetry: TelemetryPort
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        telemetry.set_gauge(DW_BRAVO_WRITES_NEEDING_A_PERSON, await ledger.needing_a_person(), {})

    return consume
