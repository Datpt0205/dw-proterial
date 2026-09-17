"""Universal ports (clock, id generation) with stdlib default adapters.

Domain and application code depend on these protocols; production and test
composition roots choose the implementation.
"""

from __future__ import annotations

import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


class UtcClock(Protocol):
    """Provides the current UTC time."""

    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    """Generates new unique identifiers."""

    def new_uuid(self) -> uuid.UUID: ...


class SystemClock:
    """Wall-clock implementation of :class:`UtcClock`."""

    def now(self) -> datetime:
        return datetime.now(tz=UTC)


@dataclass
class FixedClock:
    """Deterministic clock for tests; advances only when told to."""

    current: datetime

    def now(self) -> datetime:
        if self.current.tzinfo is None:
            raise ValueError("FixedClock requires an aware datetime")
        return self.current

    def advance_to(self, moment: datetime) -> None:
        self.current = moment


class Uuid4Generator:
    """Random UUID implementation of :class:`IdGenerator`."""

    def new_uuid(self) -> uuid.UUID:
        return uuid.uuid4()


# RFC 9562 UUIDv7 field widths. Named because the shifts below are otherwise
# unreadable, and getting one wrong yields ids that sort almost right.
_UUID7_TIMESTAMP_BITS = 48
_UUID7_COUNTER_BITS = 12  # rand_a, used as a within-millisecond counter
_UUID7_RANDOM_BITS = 62  # rand_b
_UUID7_COUNTER_MAX = (1 << _UUID7_COUNTER_BITS) - 1
_UUID7_TIMESTAMP_MASK = (1 << _UUID7_TIMESTAMP_BITS) - 1


class Uuid7Generator:
    """Time-ordered UUID implementation of :class:`IdGenerator` (RFC 9562).

    Insert-heavy tables (news signals, financial facts, tender contracts, the
    usage ledger) index far better on a key that increases with time: random
    v4 keys scatter writes across the whole B-tree, while v7 keys append to
    one edge of it.

    Python 3.12 has no ``uuid.uuid7``, so this builds the layout directly:
    48-bit millisecond timestamp, version, a 12-bit counter that makes ids
    issued within the same millisecond strictly increasing, then 62 random
    bits. The counter is what makes "time-ordered" true at the resolution
    inserts actually happen at - a bare millisecond timestamp ties thousands
    of rows per second.
    """

    def __init__(self, clock: UtcClock | None = None) -> None:
        self._clock: UtcClock = clock or SystemClock()
        # Concurrent callers must not receive the same id; the worker runs
        # several consumers and this generator is shared.
        self._lock = threading.Lock()
        self._last_ms = 0
        self._counter = 0

    def new_uuid(self) -> uuid.UUID:
        with self._lock:
            timestamp_ms, counter = self._next_slot()
        value = (
            (timestamp_ms << 80)
            | (0x7 << 76)
            | (counter << 64)
            | (0b10 << 62)
            | secrets.randbits(_UUID7_RANDOM_BITS)
        )
        return uuid.UUID(int=value)

    def _next_slot(self) -> tuple[int, int]:
        """Pick the (timestamp, counter) pair, holding the lock."""
        now_ms = int(self._clock.now().timestamp() * 1000) & _UUID7_TIMESTAMP_MASK
        if now_ms > self._last_ms:
            self._last_ms, self._counter = now_ms, 0
        elif self._counter < _UUID7_COUNTER_MAX:
            # Covers a clock that went backwards as well as a fast burst: in
            # both cases keep the previous timestamp so ids stay increasing.
            self._counter += 1
        else:
            # More than 4096 ids in one millisecond. Borrowing from the next
            # millisecond keeps monotonicity; RFC 9562 allows it.
            self._last_ms, self._counter = self._last_ms + 1, 0
        return self._last_ms, self._counter


@dataclass
class SequentialIdGenerator:
    """Deterministic id generator for tests."""

    _counter: int = 0
    issued: list[uuid.UUID] = field(default_factory=list)

    def new_uuid(self) -> uuid.UUID:
        self._counter += 1
        generated = uuid.UUID(int=self._counter)
        self.issued.append(generated)
        return generated
