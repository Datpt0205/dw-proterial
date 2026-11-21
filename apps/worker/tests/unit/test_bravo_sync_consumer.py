"""The `bravo_sync` lane's schedule (sales ticket 50): every tick by day,
one a night."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dw_worker.consumers.bravo_sync import build_bravo_sync_consumer

pytestmark = pytest.mark.unit

DAY = datetime(2026, 11, 21, 3, tzinfo=UTC)  # 10:00 in Vietnam
NIGHT = datetime(2026, 11, 21, 14, tzinfo=UTC)  # 21:00


class _Sync:
    def __init__(self) -> None:
        self.ticks: list[datetime] = []

    async def tick(self, now: datetime) -> dict[str, str]:
        self.ticks.append(now)
        return {"B20LME": "0 rows"}


async def test_every_tick_by_day_and_one_a_night() -> None:
    sync, clock = _Sync(), [DAY]
    consume = build_bravo_sync_consumer(sync, lambda: clock[0])

    for at in (DAY, DAY + timedelta(minutes=10), NIGHT, NIGHT + timedelta(minutes=10)):
        clock[0] = at
        await consume()

    assert sync.ticks == [DAY, DAY + timedelta(minutes=10), NIGHT]
