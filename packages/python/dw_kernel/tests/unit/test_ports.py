import uuid
from datetime import UTC, datetime

import pytest

from dw_kernel.ports import (
    FixedClock,
    SequentialIdGenerator,
    SystemClock,
    Uuid4Generator,
    Uuid7Generator,
)

pytestmark = pytest.mark.unit


def test_system_clock_returns_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is UTC


def test_fixed_clock_is_deterministic_and_advances() -> None:
    start = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
    clock = FixedClock(start)
    assert clock.now() == start
    later = datetime(2026, 7, 23, 13, 0, tzinfo=UTC)
    clock.advance_to(later)
    assert clock.now() == later


def test_fixed_clock_rejects_naive_datetime() -> None:
    clock = FixedClock(datetime(2026, 7, 23, 12, 0))
    with pytest.raises(ValueError, match="aware"):
        clock.now()


def test_uuid4_generator_returns_unique_ids() -> None:
    gen = Uuid4Generator()
    assert gen.new_uuid() != gen.new_uuid()


def test_uuid7_has_version_and_variant_bits() -> None:
    generated = Uuid7Generator().new_uuid()
    assert generated.version == 7
    assert generated.variant == uuid.RFC_4122


def test_uuid7_encodes_the_clock_time() -> None:
    moment = datetime(2026, 8, 14, 9, 30, tzinfo=UTC)
    generated = Uuid7Generator(FixedClock(moment)).new_uuid()
    encoded_ms = generated.int >> 80
    assert encoded_ms == int(moment.timestamp() * 1000)


def test_uuid7_stays_ordered_inside_one_millisecond() -> None:
    # A frozen clock is the worst case a burst of inserts can produce: without
    # the counter every id in the burst would share a timestamp and sort
    # arbitrarily, which is the property the index relies on.
    generator = Uuid7Generator(FixedClock(datetime(2026, 8, 14, 9, 30, tzinfo=UTC)))
    issued = [generator.new_uuid() for _ in range(500)]
    assert issued == sorted(issued)
    assert len(set(issued)) == len(issued)


def test_uuid7_does_not_go_backwards_when_the_clock_does() -> None:
    clock = FixedClock(datetime(2026, 8, 14, 9, 30, tzinfo=UTC))
    generator = Uuid7Generator(clock)
    before = generator.new_uuid()
    clock.advance_to(datetime(2026, 8, 14, 9, 0, tzinfo=UTC))
    assert generator.new_uuid() > before


def test_uuid7_survives_counter_exhaustion() -> None:
    # 4096 ids share one millisecond; the 4097th must borrow the next one
    # rather than repeat or wrap.
    generator = Uuid7Generator(FixedClock(datetime(2026, 8, 14, 9, 30, tzinfo=UTC)))
    issued = [generator.new_uuid() for _ in range(4098)]
    assert issued == sorted(issued)
    assert len(set(issued)) == len(issued)
    assert (issued[-1].int >> 80) == (issued[0].int >> 80) + 1


def test_sequential_generator_is_deterministic() -> None:
    gen = SequentialIdGenerator()
    first, second = gen.new_uuid(), gen.new_uuid()
    assert first == uuid.UUID(int=1)
    assert second == uuid.UUID(int=2)
    assert gen.issued == [first, second]
