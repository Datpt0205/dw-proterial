"""The `bravo_watch` lane's tick (ticket 65): measure, compare, pause, tell.

The gateway measures (`FingerprintSource`); `dw_bravo.watch` decides; this
module runs one tick and hands the result to its ports: the store keeps the
history and the pauses (`WatchStore`), the announcer tells the people who
hold the watch's read right and audits as the lane (`Announcer`). The ports
are declared here, by the consumer, and satisfied where the worker is wired.

Fail closed throughout: no accepted baseline pauses every kind; Bravo
unread keeps the pauses and, past the age limit, adds them; nothing here
removes a pause, only a person accepting a baseline does.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from dw_bravo.contract import WRITE_KINDS, WriteKind
from dw_bravo.watch import (
    Fingerprint,
    Notice,
    Reaction,
    Replay,
    diff,
    early_warnings,
    react,
    status,
)

Environment = Literal["uat", "production"]
BRAVO_WATCH_LANE = "bravo_watch"


class FingerprintUnavailableError(Exception):
    """Bravo, or the gateway, did not answer: nothing was measured."""


class FingerprintSource(Protocol):
    async def fingerprint(self, environment: Environment) -> Fingerprint: ...

    async def replays(self) -> Mapping[str, Replay]:
        """The replay of recorded saves on today's layouts, by screen."""
        ...


class WatchStore(Protocol):
    async def last_read(self, environment: Environment) -> datetime | None: ...

    async def baseline(self, environment: Environment) -> Fingerprint | None: ...

    async def record(self, fingerprint: Fingerprint, digest: str) -> uuid.UUID:
        """Keep it if it differs from the last of its environment; its id."""
        ...

    async def pause(
        self, paused: Mapping[str, Sequence[str]], fingerprint_id: uuid.UUID | None, at: datetime
    ) -> None:
        """Add these pauses (a kind already paused keeps its row)."""
        ...


class Announcer(Protocol):
    async def tell(self, notices: Sequence[Notice], key: str) -> None:
        """Tell the watch's readers once per `key`, and audit as the lane."""
        ...


def digest_of(fingerprint: Fingerprint) -> str:
    components = sorted(
        (
            {**asdict(c), "screens": sorted(c.screens), "unknown": list(c.unknown)}
            for c in fingerprint.components
        ),
        key=lambda c: (c["kind"], c["name"].lower()),
    )
    text = json.dumps(components, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class BravoWatch:
    source: FingerprintSource
    store: WatchStore
    announcer: Announcer
    write_kinds: Mapping[str, WriteKind] = field(default_factory=lambda: dict(WRITE_KINDS))

    async def tick(self, now: datetime) -> Reaction:
        try:
            current = await self.source.fingerprint("production")
        except FingerprintUnavailableError:
            reaction = status(await self.store.last_read("production"), now, self.write_kinds)
            await self._apply(reaction, None, now, key=f"unread:{now:%Y-%m-%dT%H}")
            return reaction
        digest = digest_of(current)
        fingerprint_id = await self.store.record(current, digest)
        baseline = await self.store.baseline("production")
        if baseline is None:
            reaction = Reaction()
            reaction.pause(self.write_kinds, "no baseline accepted yet")
        else:
            try:
                replays = await self.source.replays()
            except FingerprintUnavailableError:
                replays = {}
            reaction = react(diff(baseline, current), replays, self.write_kinds)
        try:
            uat = await self.source.fingerprint("uat")
        except FingerprintUnavailableError:
            uat = None
        if uat is not None:
            await self.store.record(uat, digest_of(uat))
            reaction.notices.extend(early_warnings(uat, current))
        await self._apply(reaction, fingerprint_id, now, key=digest)
        return reaction

    async def _apply(
        self, reaction: Reaction, fingerprint_id: uuid.UUID | None, now: datetime, *, key: str
    ) -> None:
        if reaction.paused:
            await self.store.pause(reaction.paused, fingerprint_id, now)
        if reaction.notices:
            await self.announcer.tell(reaction.notices, key)
