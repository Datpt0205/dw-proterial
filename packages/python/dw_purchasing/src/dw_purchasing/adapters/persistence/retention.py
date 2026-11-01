"""DW2's rows past their term (`retention@1.10.0`, `tables`), deleted by the
worker's `purchasing_retention` lane through `purchasing.prune_expired`
(migration 6cbb8581e01e): a purchase case received before its cutoff, a mail
outcome settled before its own. A table the policy gives no term reaches the
function as NULL, which deletes nothing of it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ports import UtcClock
from dw_platform.retention_policy import RetentionPolicy

_LOG = logging.getLogger("dw_purchasing.retention")
CASES: Final = "purchasing.cases"
MAIL_OUTCOMES: Final = "purchasing.mail_outcomes"
_PRUNE = sa.text("SELECT cases, outcomes FROM purchasing.prune_expired(:cases, :outcomes)")


@dataclass(frozen=True)
class SqlPurchasingRetention:
    """Implements the worker's `RetentionPrunePort`."""

    session_factory: async_sessionmaker[AsyncSession]
    policy: RetentionPolicy
    clock: UtcClock

    async def prune(self) -> None:
        now = self.clock.now()
        cutoffs = {
            "cases": self.policy.row_cutoff_for(CASES, now=now),
            "outcomes": self.policy.row_cutoff_for(MAIL_OUTCOMES, now=now),
        }
        async with self.session_factory() as session, session.begin():
            row = (await session.execute(_PRUNE, cutoffs)).one()
        if row.cases or row.outcomes:
            _LOG.info(
                "deleted purchasing rows past their term",
                extra={
                    "cases": row.cases,
                    "outcomes": row.outcomes,
                    "policy_version": self.policy.policy_version,
                },
            )
