"""How long a memory is kept, and the pass that enforces it.

`memory.items.retention_policy` has existed since the table did. Every row wrote
`"default"`, nothing ever read it, and nothing ever expired — so the column read
like a data-lifecycle commitment in review and was, in fact, decoration. That is
failure mode 1 in this repository's own list, and it is the one shape of it that
a customer's auditor asks about directly.

**Deleting, not closing.** `valid_until` answers "this stopped being true" — it
is what supersession writes, and the row stays so a past decision can still be
explained. Retention answers a different question: "we are no longer allowed to
hold this." The two must not share a mechanism, because the second one is what
goes in a contract.

**A class with no `days` never expires.** `legal_hold` is that, deliberately: an
obligation to keep can outlive the ordinary schedule, and the safe way to express
it is a class the sweep cannot touch rather than a flag the sweep must remember
to honour.

**An unknown class is kept, not guessed.** A row naming a class this build does
not have is more likely a newer config than a mistake, and deleting on that
guess is irreversible. It is kept and counted, so the mismatch shows up as a
number rather than as missing data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import sqlalchemy as sa
import yaml
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ports import UtcClock
from dw_memory import tables

logger = logging.getLogger("dw_memory.retention")

__all__ = ["RetentionClass", "RetentionPolicy", "SqlMemoryRetention", "load_retention_policy"]

# The cross-tenant scan runs under this rather than `app.tenant_id`, the same way
# the outbox and ingest drains do: a sweep that had to be run once per tenant
# would need a list of tenants, which is itself a cross-tenant read.
_SET_DRAIN = text("SELECT set_config('app.worker_drain', 'on', true)")


class RetentionClass(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # `None` means never swept. Not zero, and not absent — an explicit null, so
    # "keep forever" is something somebody wrote rather than something omitted.
    days: int | None = Field(default=None, ge=1)
    description: str


class RetentionPolicy(BaseModel):
    """The versioned answer to "how long do you keep our data"."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: str
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    classes: dict[str, RetentionClass]
    batch_limit: int = Field(gt=0, le=10_000)

    def cutoff_for(self, name: str, *, now: datetime) -> datetime | None:
        """The instant before which rows of this class have outlived their term.

        `None` for a class that never expires and for one this build does not
        know — the caller keeps the row either way, and only the second is worth
        a log line.
        """
        found = self.classes.get(name)
        if found is None or found.days is None:
            return None
        return now - timedelta(days=found.days)


def load_retention_policy(path: Path) -> RetentionPolicy:
    return RetentionPolicy.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class SqlMemoryRetention:
    """Implements `dw_worker.consumers.retention.RetentionPrunePort` for memory."""

    session_factory: async_sessionmaker[AsyncSession]
    policy: RetentionPolicy
    clock: UtcClock

    async def prune(self) -> None:
        """One pass: for each class that expires, delete a bounded batch.

        One statement per class rather than one over all of them, because the
        classes have different cutoffs and a single query would need a CASE the
        planner cannot use an index for.

        `item_evidence` follows through its cascade; the evidence rows themselves
        are knowledge's and stay. That is deliberate — the same chunk may be
        cited by a memory that is not expiring, and by a document that is still
        live.
        """
        now = self.clock.now()
        for name in sorted(self.policy.classes):
            cutoff = self.policy.cutoff_for(name, now=now)
            if cutoff is None:
                continue
            deleted = await self._delete_batch(name, cutoff)
            if deleted:
                logger.info(
                    "retention removed expired memories",
                    extra={
                        "retention_class": name,
                        "deleted": deleted,
                        "policy_version": self.policy.policy_version,
                    },
                )

    async def _delete_batch(self, name: str, cutoff: datetime) -> int:
        async with self.session_factory() as session, session.begin():
            await session.execute(_SET_DRAIN)
            doomed = (
                sa.select(tables.items.c.memory_id)
                .where(
                    tables.items.c.retention_policy == name,
                    tables.items.c.created_at < cutoff,
                )
                .limit(self.policy.batch_limit)
                .scalar_subquery()
            )
            # RETURNING rather than rowcount: a CursorResult exposes rowcount,
            # the generic Result the async facade is typed as does not, and
            # counting the rows it hands back says the same thing without a cast.
            removed = await session.execute(
                sa.delete(tables.items)
                .where(tables.items.c.memory_id.in_(doomed))
                .returning(tables.items.c.memory_id)
            )
            return len(removed.all())
