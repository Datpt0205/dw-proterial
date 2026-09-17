#!/usr/bin/env python
"""Create next month's partitions before rows need them.

Both append-only tables are range-partitioned and both ship a DEFAULT partition,
so nothing is ever rejected. That safety net is not a plan: rows that land in
DEFAULT lose the reason partitioning exists — retention stops being
``DROP PARTITION`` and becomes a ``DELETE`` over a table that now holds every
month at once, and moving them out later needs an exclusive lock.

So this runs ahead of time, on a schedule, and creates the months that do not
exist yet. It is idempotent: a month already there is left alone, which is what
makes it safe to run hourly if that is easier than getting the cadence right.

    scripts/roll_partitions.py [--months 3] [--dry-run]

Reads ``DW_DATABASE_URL`` — the migrator connection, because creating a
partition is DDL and the runtime role has no CREATE on the schema.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@dataclass(frozen=True)
class PartitionedTable:
    """One table, and the column its ranges are cut on."""

    schema: str
    name: str
    key: str


# Extend this list in the same change that adds a partitioned table. A table
# missing from here still accepts writes — into DEFAULT — so the failure is
# silent, which is why the check at the end of this script reports what is
# sitting in DEFAULT rather than only what it created.
TABLES = (
    PartitionedTable("platform", "audit_events", "occurred_at"),
    PartitionedTable("platform", "model_usage_ledger", "created_at"),
)


def _month_bounds(year: int, month: int) -> tuple[str, str, str]:
    """Return (suffix, inclusive start, exclusive end) for one month, UTC."""
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year + (month == 12), (month % 12) + 1, 1, tzinfo=UTC)
    return f"{year:04d}_{month:02d}", start.isoformat(), end.isoformat()


def _months_from(now: datetime, count: int) -> list[tuple[int, int]]:
    out = []
    year, month = now.year, now.month
    for _ in range(count):
        out.append((year, month))
        year, month = year + (month == 12), (month % 12) + 1
    return out


async def roll(database_url: str, months: int, dry_run: bool) -> int:
    engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    created = 0
    try:
        async with engine.connect() as conn:
            for table in TABLES:
                for year, month in _months_from(datetime.now(tz=UTC), months):
                    suffix, start, end = _month_bounds(year, month)
                    child = f"{table.name}_{suffix}"
                    exists = await conn.scalar(
                        text(
                            "SELECT 1 FROM pg_class c JOIN pg_namespace n"
                            " ON n.oid = c.relnamespace"
                            " WHERE n.nspname = :schema AND c.relname = :child"
                        ),
                        {"schema": table.schema, "child": child},
                    )
                    if exists:
                        continue
                    statement = (
                        f"CREATE TABLE {table.schema}.{child} PARTITION OF"
                        f" {table.schema}.{table.name}"
                        f" FOR VALUES FROM ('{start}') TO ('{end}')"
                    )
                    if dry_run:
                        print(f"would create {table.schema}.{child}")
                    else:
                        await conn.execute(text(statement))
                        print(f"created {table.schema}.{child}")
                    created += 1

            # What is already in DEFAULT is the number that matters: it says the
            # schedule has been behind, and by how much.
            for table in TABLES:
                stranded = await conn.scalar(
                    text(f"SELECT count(*) FROM {table.schema}.{table.name}_default")
                )
                if stranded:
                    print(
                        f"WARNING: {stranded} rows sit in"
                        f" {table.schema}.{table.name}_default — they were written while"
                        " no month covered them, and retention cannot drop them",
                        file=sys.stderr,
                    )
    finally:
        await engine.dispose()
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months",
        type=int,
        default=3,
        help="how many months ahead to cover (default 3, so a missed run is not an outage)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    url = os.environ.get("DW_DATABASE_URL")
    if not url:
        raise SystemExit("DW_DATABASE_URL is not set (the migrator connection is required)")
    created = asyncio.run(roll(url, args.months, args.dry_run))
    print(f"{created} partition(s) {'would be ' if args.dry_run else ''}created")


if __name__ == "__main__":
    main()
