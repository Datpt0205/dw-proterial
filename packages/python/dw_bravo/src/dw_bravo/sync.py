"""Bravo's facts copied into DW by rowversion (ticket 50, ADR 0027).

The gateway serves `sync.changes`: the rows of one allowlisted table whose
`timestamp` (SQL Server's rowversion) is past a cursor, the allowlisted
columns only, in rowversion order, a page at a time. The `bravo_sync` lane
(`BravoSync.tick`) keeps one cursor per table: in working hours it reads what
changed since; once a night it reads the whole table again, which is how a
row Bravo deleted is seen (rowversion shows no deletion): a row a full pass
did not see is marked gone, never deleted.

What may be read is this module's `SYNC_TABLES`, each column named by
Bravo's schema (the 11-20 survey, `03-B8_Hitachi_Cable_schema.sql`): the
black list (`B20BlackList`), LME (`B20LME`) and export control
(`B20ExportControlList`). A table or a column not in it is never read.

Nothing here reads Bravo or stores: the gateway reads, the store keeps, and
this decides what to ask for next.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, ClassVar, Final, Literal, Protocol
from zoneinfo import ZoneInfo

VIETNAM: Final = ZoneInfo("Asia/Ho_Chi_Minh")
BRAVO_SYNC_LANE: Final = "bravo_sync"

SyncTable = Literal["B20LME", "B20BlackList", "B20ExportControlList"]

# Per table, the columns DW reads besides `Id` and `timestamp`.
SYNC_TABLES: Final[Mapping[str, tuple[str, ...]]] = {
    "B20LME": (
        "IsGroup", "BranchCode", "Code", "Name", "DocDate", "LMEActual", "LMECenter", "IsActive",
    ),
    "B20BlackList": (
        "IsGroup", "BranchCode", "EffectiveDate", "KeyWord", "Name", "Type", "Description",
        "IsActive",
    ),
    "B20ExportControlList": (
        "IsGroup", "DocDate", "CustomerCode", "IndirectCustomerCode", "CustomerName", "KeyWord",
        "Country", "ProductCode", "Application", "ECPNumber", "EffectiveDate", "TerminatedDate",
        "NoNeed", "IsActive",
    ),
}  # fmt: skip

PAGE_LIMIT: Final = 1000
_ROWVERSION: Final = re.compile(r"^0x[0-9A-F]{16}$")
_STRICT: Final[dict[str, object]] = {"extra": "forbid"}


class SyncContractError(ValueError):
    pass


@dataclass(frozen=True)
class SyncQuery:
    """`sync.changes@1`: rows of ``table`` past ``after`` (None: from the
    start), at most ``limit``, in rowversion order."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "sync.changes"
    version: ClassVar[int] = 1

    table: SyncTable
    after: str | None = None
    limit: int = PAGE_LIMIT

    def __post_init__(self) -> None:
        if self.table not in SYNC_TABLES:
            raise SyncContractError("not a table the sync reads")
        if self.after is not None and not _ROWVERSION.match(self.after):
            raise SyncContractError("after must be a rowversion such as 0x00000000000007D1")
        if not 1 <= self.limit <= PAGE_LIMIT:
            raise SyncContractError(f"limit is 1 to {PAGE_LIMIT}")


@dataclass(frozen=True)
class SyncRow:
    """One Bravo row: its `Id`, its rowversion, and its allowlisted columns
    as text (numbers exact, dates ISO), None where Bravo holds NULL."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT

    row_id: int
    row_version: str
    data: dict[str, str | None]


@dataclass(frozen=True)
class SyncPage:
    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT

    rows: tuple[SyncRow, ...]


# ------------------------------------------------------------------ the lane


class SyncUnavailableError(Exception):
    """The gateway, or Bravo behind it, did not answer."""


class SyncSource(Protocol):
    async def changes(self, query: SyncQuery) -> SyncPage: ...


@dataclass(frozen=True)
class Cursor:
    last_row_version: str | None = None
    last_full_at: datetime | None = None
    last_read_at: datetime | None = None


class MirrorStore(Protocol):
    """DW's copy of one tenant's Bravo tables."""

    async def cursor(self, table: str) -> Cursor: ...

    async def keep(self, table: str, rows: Sequence[SyncRow], at: datetime) -> None:
        """Insert or replace each row, clearing `gone_at` if it reappeared."""
        ...

    async def finish(
        self,
        table: str,
        *,
        last_row_version: str | None,
        at: datetime,
        full_pass_seen: frozenset[int] | None,
    ) -> None:
        """Move the cursor, clear the error, and after a full pass mark every
        row it did not see as gone, in one transaction."""
        ...

    async def failed(self, table: str, error: str, at: datetime) -> None: ...


# The nightly full pass, 19:00-07:00 in Vietnam, once per night.
_NIGHT_STARTS: Final = time(19, 0)
_NIGHT_ENDS: Final = time(7, 0)
FULL_EVERY: Final = timedelta(hours=20)


def full_pass_due(cursor: Cursor, now: datetime) -> bool:
    """Never read whole, or not in the last night, and it is night now."""
    if cursor.last_full_at is None:
        return True
    local = now.astimezone(VIETNAM).time()
    night = local >= _NIGHT_STARTS or local < _NIGHT_ENDS
    return night and now - cursor.last_full_at >= FULL_EVERY


@dataclass
class BravoSync:
    source: SyncSource
    store: MirrorStore
    tables: Sequence[str] = field(default_factory=lambda: tuple(SYNC_TABLES))
    # A bound on the pages one table reads in one tick.
    max_pages: int = 200

    async def tick(self, now: datetime) -> Mapping[str, str]:
        """Each table once: what happened to it, in words, for the lane's log."""
        said: dict[str, str] = {}
        for table in self.tables:
            try:
                said[table] = await self._table(table, now)
            except SyncUnavailableError as down:
                await self.store.failed(table, f"Bravo did not answer: {down}"[:300], now)
                said[table] = "could not read"
        return said

    async def _table(self, table: str, now: datetime) -> str:
        cursor = await self.store.cursor(table)
        full = full_pass_due(cursor, now)
        after = None if full else cursor.last_row_version
        last = after
        seen: set[int] = set()
        read = 0
        for _ in range(self.max_pages):
            page = await self.source.changes(SyncQuery(table, after=last))  # type: ignore[arg-type]
            if page.rows:
                await self.store.keep(table, page.rows, now)
                seen.update(r.row_id for r in page.rows)
                last = page.rows[-1].row_version
                read += len(page.rows)
            if len(page.rows) < PAGE_LIMIT:
                break
        else:
            # Not finished within the bound: the cursor moves to what was
            # read, and a full pass is not taken as complete.
            await self.store.finish(
                table,
                last_row_version=last if not full else cursor.last_row_version,
                at=now,
                full_pass_seen=None,
            )
            return f"{read} rows, more to read"
        await self.store.finish(
            table,
            last_row_version=last if last is not None else cursor.last_row_version,
            at=now,
            full_pass_seen=frozenset(seen) if full else None,
        )
        return f"{'full pass, ' if full else ''}{read} rows"


def as_text(value: Any) -> str | None:
    """A column's value as the copy holds it: exact text, never a float."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, float):
        raise SyncContractError("a float is not an exact value")
    return str(value)
