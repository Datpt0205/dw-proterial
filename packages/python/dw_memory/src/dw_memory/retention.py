"""The pass that enforces the retention schedule on `memory.items`.

The schedule itself is `dw_platform.retention_policy` — one contract, because
knowledge expires on the same versioned artifact and two copies of one
commitment drift. What is here is the SQL: which table, which column carries the
class, and how big a bite each pass takes.

`memory.items.retention_policy` has existed since the table did. Every row wrote
`"default"`, nothing ever read it, and nothing ever expired — so the column read
like a data-lifecycle commitment in review and was, in fact, decoration. That is
failure mode 1 in this repository's own list, and it is the one shape of it that
a customer's auditor asks about directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ports import UtcClock
from dw_knowledge import tables as knowledge_tables
from dw_memory import tables
from dw_platform.retention_policy import RetentionPolicy

logger = logging.getLogger("dw_memory.retention")

__all__ = ["SqlMemoryRetention"]

# The cross-tenant scan runs under this rather than `app.tenant_id`, the same way
# the outbox and ingest drains do: a sweep that had to be run once per tenant
# would need a list of tenants, which is itself a cross-tenant read.
_SET_DRAIN = text("SELECT set_config('app.worker_drain', 'on', true)")


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

        `item_evidence` follows through its cascade. The evidence row it pointed
        at does not, and that is what `_delete_orphan_evidence` is for — see its
        docstring for why leaving it is not the safe option it looks like.
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
        orphaned = await self._delete_orphan_evidence(now)
        if orphaned:
            logger.info(
                "retention removed uncited evidence",
                extra={
                    "deleted": orphaned,
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

    async def _delete_orphan_evidence(self, now: datetime) -> int:
        """Delete evidence rows that no memory cites any more.

        Here and not in `dw_knowledge` because the question is a memory one:
        `memory.item_evidence` is what makes an evidence row cited, and knowledge
        may not import memory. Knowledge's own sweep asks only about its own
        tables.

        Why it has to happen at all, rather than leaving the row as a harmless
        remnant: `evidence -> documents` is RESTRICT, so every surviving evidence
        row pins its document in place for good. Without this pass, a document
        that was cited once can never be hard deleted and the document grace
        period in the policy is a promise the schema cannot keep.

        It is not a second citation check — an evidence row is written inside the
        same transaction as the `item_evidence` that links it, so a row with no
        link never had one or lost its last. The grace window is what keeps that
        from being load-bearing.
        """
        cutoff = now - timedelta(days=self.policy.knowledge.orphan_evidence_grace_days)
        async with self.session_factory() as session, session.begin():
            await session.execute(_SET_DRAIN)
            cited = sa.select(tables.item_evidence.c.evidence_id).where(
                tables.item_evidence.c.evidence_id == knowledge_tables.evidence.c.evidence_id
            )
            doomed = (
                sa.select(knowledge_tables.evidence.c.evidence_id)
                .where(
                    knowledge_tables.evidence.c.created_at < cutoff,
                    ~cited.exists(),
                )
                .limit(self.policy.batch_limit)
                .scalar_subquery()
            )
            removed = await session.execute(
                sa.delete(knowledge_tables.evidence)
                .where(knowledge_tables.evidence.c.evidence_id.in_(doomed))
                .returning(knowledge_tables.evidence.c.evidence_id)
            )
            return len(removed.all())
