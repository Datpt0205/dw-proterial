"""The `bravo_ledger_health` lane sets the gauge `DwBravoWriteNeedsAPerson`
reads, from the ledger's own count each tick (Sales ticket 84)."""

from __future__ import annotations

import pytest

from dw_observability.metrics import DW_BRAVO_WRITES_NEEDING_A_PERSON
from dw_observability.telemetry import RecordingTelemetry
from dw_worker.consumers.bravo_ledger_health import build_bravo_ledger_health_consumer

pytestmark = pytest.mark.unit


class _Ledger:
    def __init__(self, *counts: int) -> None:
        self.counts = list(counts)

    async def needing_a_person(self) -> int:
        return self.counts.pop(0)


async def test_each_tick_sets_the_gauge_to_what_the_ledger_counts_now() -> None:
    telemetry = RecordingTelemetry()
    lane = build_bravo_ledger_health_consumer(_Ledger(0, 2), telemetry)

    await lane()
    await lane()

    assert telemetry.gauges == [
        (DW_BRAVO_WRITES_NEEDING_A_PERSON, 0, {}),
        (DW_BRAVO_WRITES_NEEDING_A_PERSON, 2, {}),
    ]
