"""Shadow mode shared by every model step (ticket 67, dw_sales ADR 0015
decision 4; the reading is `domain.shadow.ShadowReading`).

- **When a step reads in shadow** (`ShadowReadings.shadows`): the tenant's
  rules list it in `model_assist.shadow`, it is not on and passing (the
  caller asks its gate first: on and passing, the step runs as itself), and
  a model is configured for it (`ShadowGatePort`). The tenant decides what
  is spent: a step in shadow costs its model calls and applies nothing.
- **Kept** (`ShadowReadings.keep`) in a transaction of its own while the
  step's caller still holds the mail: a reading of a mail no case comes of
  is dropped with the term, never shown.
- **Taken** (`ShadowReadingRepositoryPort.take`, a member of every
  `SalesUnitOfWork`) in the transaction of the person's decision, deleted
  as it is labelled: one reading labels one decision, never two.
- **Dropped** past `SHADOW_KEPT_FOR` by the `sales_shadow_retention` lane
  (`ShadowRetention`), per workspace in its own scope, audited as the lane
  with the count in the drop's transaction.

The log carries ids and counts, never a value.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.domain.audit import lane_audit_event
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.domain.order_checks import ModelStep, OrderRules
from dw_sales.domain.shadow import ShadowReading

__all__ = [
    "SHADOW_KEPT_FOR",
    "SHADOW_RETENTION_LANE",
    "ShadowGatePort",
    "ShadowReadingRepositoryPort",
    "ShadowReadings",
    "ShadowRetention",
]

_LOG = logging.getLogger("dw_sales.shadow")

SHADOW_RETENTION_LANE: Final = "sales_shadow_retention"
# How long a reading waits on a person's decision: a PO line is settled in
# days; one still open after this labels a decision too late to say much.
SHADOW_KEPT_FOR: Final = timedelta(days=60)


class ShadowReadingRepositoryPort(Protocol):
    """The workspace's shadow readings, in a unit of work, under its RLS."""

    async def keep(self, readings: Sequence[ShadowReading]) -> int:
        """Keeps each reading whose item holds none yet for its step (the
        first reading of an item stands: a mail processed again reads it
        again); the number kept."""
        ...

    async def take(self, step: ModelStep, item_key: str) -> ShadowReading | None:
        """``step``'s reading of the item, deleted as it is returned."""
        ...

    async def prune(self, before: datetime) -> int:
        """Drops the readings read before ``before``; the number."""
        ...


class ShadowGatePort(Protocol):
    """Whether a model is configured for a step now (`ModelReadiness`)."""

    async def configured(self, scope: SalesScope, step: ModelStep) -> bool: ...


@dataclass(frozen=True)
class ShadowReadings:
    """A step's side: whether it reads in shadow now, and where it keeps
    what it read."""

    gate: ShadowGatePort
    uow: SalesUnitOfWorkFactory
    # When a reading is read: what its term is counted from.
    clock: UtcClock

    async def shadows(self, scope: SalesScope, rules: OrderRules, step: ModelStep) -> bool:
        """Whether ``step`` reads in shadow for the tenant now; asked only
        where the step is not on and passing (module docstring)."""
        if step not in rules.model_assist.shadow:
            return False
        return await self.gate.configured(scope, step)

    async def keep(self, scope: SalesScope, readings: Sequence[ShadowReading]) -> None:
        if not readings:
            return
        async with self.uow(scope) as work:
            kept = await work.shadow_readings.keep(readings)
            await work.commit()
        _LOG.info(
            "kept %s of %s shadow readings of %s for tenant %s",
            kept,
            len(readings),
            sorted({r.step.value for r in readings}),
            scope.tenant_id.value,
        )


@dataclass(frozen=True)
class ShadowRetention:
    """The `sales_shadow_retention` lane's work for one scope."""

    uow: SalesUnitOfWorkFactory
    clock: UtcClock
    ids: IdGenerator

    async def tick(self, scope: SalesScope) -> int:
        """Drops ``scope``'s readings past the term; how many."""
        now = self.clock.now()
        async with self.uow(scope) as work:
            dropped = await work.shadow_readings.prune(now - SHADOW_KEPT_FOR)
            if dropped:
                await work.audit.append(
                    lane_audit_event(
                        lane=SHADOW_RETENTION_LANE,
                        event_id=self.ids.new_uuid(),
                        tenant_id=scope.tenant_id,
                        workspace_id=scope.workspace_id,
                        action="sales.shadow_readings.pruned",
                        resource_type="sales_shadow_reading",
                        resource_id=str(scope.workspace_id.value),
                        occurred_at=now,
                        details={"readings": dropped, "kept_days": SHADOW_KEPT_FOR.days},
                    )
                )
            await work.commit()
        return dropped
