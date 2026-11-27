"""Ticket 50's lane: each table read from its cursor in pages, a nightly
full pass that is how a deleted row is seen, and a Bravo that does not
answer said per table without moving any cursor."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from dw_bravo.sync import (
    PAGE_LIMIT,
    BravoSync,
    Cursor,
    SyncAnswer,
    SyncContractError,
    SyncPage,
    SyncQuery,
    SyncRow,
    SyncUnavailableError,
    as_text,
    full_pass_due,
)

pytestmark = pytest.mark.unit

DAY = datetime(2026, 11, 21, 3, tzinfo=UTC)  # 10:00 in Vietnam
NIGHT = datetime(2026, 11, 21, 14, tzinfo=UTC)  # 21:00 in Vietnam


def _rv(n: int) -> str:
    return f"0x{n:016X}"


def _row(n: int) -> SyncRow:
    return SyncRow(n, _rv(n), {"Code": f"C{n}"})


@dataclass
class Source:
    rows: list[SyncRow]
    down: bool = False
    asked: list[SyncQuery] = field(default_factory=list)
    # The Bravo that answers; a list names one per call, in order.
    target: str | list[str] = "uat"

    async def changes(self, query: SyncQuery) -> SyncAnswer:
        self.asked.append(query)
        if self.down:
            raise SyncUnavailableError("timeout")
        after = int(query.after, 16) if query.after else 0
        found = [r for r in self.rows if int(r.row_version, 16) > after]
        target = self.target if isinstance(self.target, str) else self.target.pop(0)
        return SyncAnswer(target, SyncPage(tuple(found[: query.limit])))


@dataclass
class Store:
    cursors: dict[str, Cursor] = field(default_factory=dict)
    rows: dict[tuple[str, int], SyncRow] = field(default_factory=dict)
    gone: set[tuple[str, int]] = field(default_factory=set)
    errors: dict[str, str] = field(default_factory=dict)

    async def cursor(self, table: str) -> Cursor:
        return self.cursors.get(table, Cursor())

    async def keep(self, table: str, rows: Sequence[SyncRow], at: datetime) -> None:
        for r in rows:
            self.rows[(table, r.row_id)] = r
            self.gone.discard((table, r.row_id))

    async def finish(
        self,
        table: str,
        *,
        target: str,
        last_row_version: str | None,
        at: datetime,
        full_pass_seen: frozenset[int] | None,
    ) -> None:
        before = self.cursors.get(table, Cursor())
        self.cursors[table] = Cursor(
            last_row_version, at if full_pass_seen is not None else before.last_full_at, at, target
        )
        if full_pass_seen is not None:
            self.gone |= {k for k in self.rows if k[0] == table and k[1] not in full_pass_seen}
        self.errors.pop(table, None)

    async def restart(self, table: str, at: datetime) -> None:
        self.gone |= {k for k in self.rows if k[0] == table}
        before = self.cursors.get(table, Cursor())
        self.cursors[table] = Cursor(None, None, before.last_read_at, None)

    async def failed(self, table: str, error: str, at: datetime) -> None:
        self.errors[table] = error


async def test_the_first_read_is_a_full_pass_in_pages_and_moves_the_cursor() -> None:
    source, store = Source([_row(n) for n in range(1, PAGE_LIMIT + 6)]), Store()

    said = await BravoSync(source, store, tables=("B20LME",)).tick(DAY)

    assert said["B20LME"] == f"full pass, {PAGE_LIMIT + 5} rows"
    assert [q.after for q in source.asked] == [None, _rv(PAGE_LIMIT)]
    assert store.cursors["B20LME"].last_row_version == _rv(PAGE_LIMIT + 5)


async def test_by_day_only_what_changed_since_the_cursor_is_read() -> None:
    source = Source([_row(1), _row(2)])
    store = Store(cursors={"B20LME": Cursor(_rv(1), DAY, DAY, "uat")})

    await BravoSync(source, store, tables=("B20LME",)).tick(DAY)

    assert [q.after for q in source.asked] == [_rv(1)]
    assert set(store.rows) == {("B20LME", 2)} and store.gone == set()


async def test_a_row_bravo_deleted_is_marked_gone_by_the_nightly_full_pass_only() -> None:
    store = Store()
    await BravoSync(Source([_row(1), _row(2)]), store, tables=("B20LME",)).tick(NIGHT)
    later = Source([_row(2)])  # row 1 deleted in Bravo

    await BravoSync(later, store, tables=("B20LME",)).tick(DAY.replace(day=22))
    assert store.gone == set()  # by day: rowversion shows no deletion
    await BravoSync(later, store, tables=("B20LME",)).tick(NIGHT.replace(day=22))

    assert store.gone == {("B20LME", 1)}


async def test_bravo_not_answering_is_said_and_moves_no_cursor() -> None:
    store = Store(cursors={"B20LME": Cursor(_rv(3), DAY, DAY, "uat")})

    said = await BravoSync(Source([], down=True), store, tables=("B20LME",)).tick(DAY)

    assert said == {"B20LME": "could not read"}
    assert store.cursors["B20LME"].last_row_version == _rv(3)
    assert "did not answer" in store.errors["B20LME"]


# ------------------------------------------ the Bravo that answers (85 review)


async def test_a_cursor_read_from_another_bravo_restarts_the_table_whole() -> None:
    # UAT's cursor is past rowversion 5; production's rows count from 1.
    store = Store(cursors={"B20LME": Cursor(_rv(5), DAY, DAY, "uat")})
    store.rows[("B20LME", 9)] = _row(9)  # a row only UAT holds
    source = Source([_row(1), _row(2)], target="production")

    said = await BravoSync(source, store, tables=("B20LME",)).tick(DAY)

    assert [q.after for q in source.asked] == [_rv(5), None]
    assert said["B20LME"] == "another Bravo answered, read again: full pass, 2 rows"
    assert set(store.rows) == {("B20LME", 1), ("B20LME", 2), ("B20LME", 9)}
    assert store.gone == {("B20LME", 9)}
    assert store.cursors["B20LME"].target == "production"
    assert store.cursors["B20LME"].last_row_version == _rv(2)
    assert store.cursors["B20LME"].last_full_at == DAY


async def test_a_cursor_from_before_the_target_was_kept_restarts_once() -> None:
    store = Store(cursors={"B20LME": Cursor(_rv(1), DAY, DAY)})
    source = Source([_row(1), _row(2)])

    await BravoSync(source, store, tables=("B20LME",)).tick(DAY)
    await BravoSync(source, store, tables=("B20LME",)).tick(DAY)

    assert [q.after for q in source.asked] == [_rv(1), None, _rv(2)]
    assert store.cursors["B20LME"].target == "uat"


async def test_a_bravo_that_changes_between_pages_moves_no_cursor() -> None:
    store = Store(cursors={"B20LME": Cursor(_rv(0), DAY, DAY, "uat")})
    rows = [_row(n) for n in range(1, PAGE_LIMIT + 3)]
    source = Source(rows, target=["uat", "production"])

    said = await BravoSync(source, store, tables=("B20LME",)).tick(DAY)

    assert said == {"B20LME": "could not read"}
    assert store.cursors["B20LME"] == Cursor(_rv(0), DAY, DAY, "uat")


def test_a_full_pass_is_due_at_night_once_and_whenever_never_taken() -> None:
    assert full_pass_due(Cursor(), DAY)
    assert not full_pass_due(Cursor(_rv(1), NIGHT, NIGHT), DAY.replace(day=22))
    assert full_pass_due(Cursor(_rv(1), NIGHT, NIGHT), NIGHT.replace(day=22))
    assert not full_pass_due(Cursor(_rv(1), NIGHT, NIGHT), NIGHT.replace(hour=15))


@pytest.mark.parametrize(
    "build",
    [
        lambda: SyncQuery("B00UserList"),  # type: ignore[arg-type]
        lambda: SyncQuery("B20LME", after="7D1"),
        lambda: SyncQuery("B20LME", limit=PAGE_LIMIT + 1),
    ],
    ids=["table_not_allowed", "not_a_rowversion", "page_too_large"],
)
def test_a_query_outside_the_allowlist_is_refused(build: object) -> None:
    with pytest.raises(SyncContractError):
        build()  # type: ignore[operator]


def test_values_are_kept_exact() -> None:
    assert as_text(Decimal("9123.50")) == "9123.50"
    assert as_text(date(2026, 1, 2)) == "2026-01-02"
    assert as_text(True) == "1" and as_text(None) is None
    with pytest.raises(SyncContractError):
        as_text(0.1)
