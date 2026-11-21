"""One `bravo_watch` tick against fakes of its ports (ticket 65)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import pytest

from dw_bravo.watch import Component, Fingerprint, Notice, Replay
from dw_bravo.watch_lane import BravoWatch, Environment, FingerprintUnavailableError, digest_of

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 21, 3, tzinfo=UTC)
ALL = {
    "so.line.set_confirmed_date@1",
    "so.line.set_quantity@1",
    "so.line.cancel@1",
    "so.line.split@1",
    "so.create@1",
}
PROD = Fingerprint(
    "production",
    NOW,
    (
        Component("layout", "EDIT_BizDocSO", "l1"),
        Component("columns", "B30BizDocDetailSO", "c1"),
    ),
)


@dataclass
class Source:
    production: Fingerprint | None = PROD
    uat: Fingerprint | None = None

    async def fingerprint(self, environment: Environment) -> Fingerprint:
        found = self.production if environment == "production" else self.uat
        if found is None:
            raise FingerprintUnavailableError(environment)
        return found

    async def replays(self) -> Mapping[str, Replay]:
        return {}


@dataclass
class Store:
    base: Fingerprint | None = PROD
    read_at: datetime | None = NOW - timedelta(minutes=30)
    recorded: list[str] = field(default_factory=list)
    paused: dict[str, list[str]] = field(default_factory=dict)

    async def last_read(self, environment: Environment) -> datetime | None:
        return self.read_at

    async def baseline(self, environment: Environment) -> Fingerprint | None:
        return self.base

    async def record(self, fingerprint: Fingerprint, digest: str) -> uuid.UUID:
        self.recorded.append(digest)
        return uuid.uuid4()

    async def pause(
        self, paused: Mapping[str, Sequence[str]], fingerprint_id: uuid.UUID | None, at: datetime
    ) -> None:
        for kind, reasons in paused.items():
            self.paused.setdefault(kind, []).extend(reasons)


@dataclass
class Told:
    notices: list[Notice] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)

    async def tell(self, notices: Sequence[Notice], key: str) -> None:
        self.notices.extend(notices)
        self.keys.append(key)


def watch(source: Source, store: Store) -> tuple[BravoWatch, Told]:
    told = Told()
    return BravoWatch(source, store, told), told


def changed_columns() -> Fingerprint:
    return replace(
        PROD,
        components=(PROD.components[0], replace(PROD.components[1], digest="c2")),
    )


async def test_unchanged_pauses_nothing_and_says_nothing() -> None:
    store = Store()
    lane, told = watch(Source(), store)

    await lane.tick(NOW)

    assert store.paused == {} and told.notices == []
    assert store.recorded == [digest_of(PROD)]


async def test_no_accepted_baseline_pauses_every_kind() -> None:
    store = Store(base=None)
    lane, told = watch(Source(), store)

    await lane.tick(NOW)

    assert set(store.paused) == ALL
    assert told.notices[0].level == "pause"


async def test_a_column_changed_pauses_and_is_told_once_per_fingerprint() -> None:
    store = Store()
    lane, told = watch(Source(production=changed_columns()), store)

    await lane.tick(NOW)

    assert set(store.paused) == ALL
    assert told.keys == [digest_of(changed_columns())]


async def test_bravo_unread_recently_says_could_not_check_and_pauses_nothing_new() -> None:
    store = Store()
    lane, told = watch(Source(production=None), store)

    await lane.tick(NOW)

    assert store.paused == {}
    assert [n.level for n in told.notices] == ["could_not_check"]


async def test_bravo_unread_too_long_pauses_every_kind() -> None:
    store = Store(read_at=NOW - timedelta(hours=3))
    lane, _ = watch(Source(production=None), store)

    await lane.tick(NOW)

    assert set(store.paused) == ALL


async def test_uat_ahead_of_production_warns_and_pauses_nothing() -> None:
    store = Store()
    lane, told = watch(Source(uat=replace(changed_columns(), environment="uat")), store)

    await lane.tick(NOW)

    assert store.paused == {}
    assert [n.level for n in told.notices] == ["early_warning"]


async def test_a_tick_never_removes_a_pause() -> None:
    store = Store()
    store.paused = {"so.line.set_quantity@1": ["column changed earlier"]}
    lane, _ = watch(Source(), store)

    await lane.tick(NOW)

    assert store.paused == {"so.line.set_quantity@1": ["column changed earlier"]}


def test_the_digest_ignores_component_order() -> None:
    reordered = replace(PROD, components=tuple(reversed(PROD.components)))

    assert digest_of(reordered) == digest_of(PROD)
    assert digest_of(changed_columns()) != digest_of(PROD)
