"""The reaper, and the cadence the registry now lets a consumer ask for.

The property worth a test is not that reaping happens - it is that one broken
queue does not stop the other four. Each table has different blocked accounts
behind it, and a sweep that gave up on the first error would leave them blocked
for the sake of tidy control flow.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from dw_worker.consumers import ConsumerRegistry
from dw_worker.consumers.reaper import ReapTarget, build_reaper_consumer

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


@dataclass
class FakeClock:
    def now(self) -> datetime:
        return NOW


@dataclass
class FakeQueue:
    reaped: list[uuid.UUID] = field(default_factory=list)
    boom: Exception | None = None
    asked: list[datetime] = field(default_factory=list)

    async def reap_stale(self, *, older_than: datetime) -> list[Any]:
        self.asked.append(older_than)
        if self.boom is not None:
            raise self.boom
        return list(self.reaped)


async def test_every_queue_gets_its_own_window() -> None:
    fast, slow = FakeQueue(), FakeQueue()
    consume = build_reaper_consumer(
        [
            ReapTarget("preference match", fast, timedelta(minutes=5)),
            ReapTarget("portal compile", slow, timedelta(minutes=20)),
        ],
        FakeClock(),
    )

    await consume()

    assert fast.asked == [NOW - timedelta(minutes=5)]
    assert slow.asked == [NOW - timedelta(minutes=20)]


async def test_one_broken_queue_does_not_block_the_others() -> None:
    """A blocked account behind table four is not table one's fault."""
    broken = FakeQueue(boom=RuntimeError("connection reset"))
    healthy = FakeQueue(reaped=[uuid.uuid4()])
    consume = build_reaper_consumer(
        [
            ReapTarget("research run", broken, timedelta(minutes=15)),
            ReapTarget("signal scan", healthy, timedelta(minutes=20)),
        ],
        FakeClock(),
    )

    await consume()

    assert healthy.asked, "the second queue was still swept"


async def test_a_sweep_that_finds_nothing_is_not_an_error() -> None:
    quiet = FakeQueue()
    consume = build_reaper_consumer(
        [ReapTarget("bidder crawl", quiet, timedelta(minutes=5))], FakeClock()
    )
    await consume()
    assert quiet.asked


# ------------------------------------------------------------- registry ----


async def _noop() -> None:
    return None


def test_a_consumer_without_a_cadence_gets_the_poll_interval() -> None:
    registry = ConsumerRegistry()
    registry.register("sales_research", _noop)
    assert registry.interval_for("sales_research", 5.0) == 5.0


def test_a_periodic_consumer_keeps_the_cadence_it_asked_for() -> None:
    registry = ConsumerRegistry()
    registry.register("retention_prune", _noop, interval_seconds=3600.0)
    assert registry.interval_for("retention_prune", 5.0) == 3600.0


def test_a_cadence_that_would_spin_is_refused() -> None:
    registry = ConsumerRegistry()
    with pytest.raises(ValueError, match="interval must be positive"):
        registry.register("bad", _noop, interval_seconds=0)
