"""Shadow mode shared by every model step (ticket 67, dw_sales ADR 0015
decision 4; the reading is `domain.shadow.ShadowReading`).

- **When a step reads in shadow** (`ShadowReadings.shadows`): the tenant's
  `model_assist.shadow` is on (it is unless a version turns it off), the
  step has a shadow consumer (`SHADOW_STEPS`), it is not on and passing (the
  caller asks its gate first: on and passing, the step runs as itself), a
  model is configured for it (`ShadowGatePort`), and the tenant's hour still
  has calls left (`ShadowBudget`, `model_assist.shadow_calls_per_hour`): a
  reading in shadow never takes the model from work that is on.
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
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final, Protocol

from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import lane_audit_event
from dw_sales.application.case_store import SalesUnitOfWork, SalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_checks import SHADOW_STEPS, ModelStep, OrderRules
from dw_sales.domain.shadow import REPLY_MOVES, REPLY_SHADOW_STEPS, ShadowReading, shadow_label

__all__ = [
    "SHADOW_KEPT_FOR",
    "SHADOW_RETENTION_LANE",
    "ShadowBudget",
    "ShadowGatePort",
    "ShadowReadingRepositoryPort",
    "ShadowReadings",
    "ShadowRetention",
    "label_reply_move",
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

    async def take_for_case(
        self, steps: Sequence[ModelStep], case_id: uuid.UUID
    ) -> Sequence[ShadowReading]:
        """``steps``' readings of the case's items, deleted as they are
        returned: a move on the case labels the newest and ends the rest."""
        ...

    async def prune(self, before: datetime) -> int:
        """Drops the readings read before ``before``; the number."""
        ...


class ShadowGatePort(Protocol):
    """Whether a model is configured for a step now (`ModelReadiness`)."""

    async def configured(self, scope: SalesScope, step: ModelStep) -> bool: ...


@dataclass
class ShadowBudget:
    """The calls shadow readings made per tenant in the current hour, in this
    process (the worker reads mail in one). One entry per tenant, replaced
    when its hour turns: bounded by the tenants the process serves."""

    used: dict[uuid.UUID, tuple[datetime, int]] = field(default_factory=dict)

    def take(self, tenant_id: uuid.UUID, limit: int, now: datetime) -> bool:
        """One call taken from the tenant's hour, or False with none left."""
        hour = now.replace(minute=0, second=0, microsecond=0)
        start, count = self.used.get(tenant_id, (hour, 0))
        if start != hour:
            count = 0
        if count >= limit:
            return False
        self.used[tenant_id] = (hour, count + 1)
        return True


@dataclass(frozen=True)
class ShadowReadings:
    """A step's side: whether it reads in shadow now, and where it keeps
    what it read."""

    gate: ShadowGatePort
    uow: SalesUnitOfWorkFactory
    # When a reading is read: what its term and the hour's budget count from.
    clock: UtcClock
    budget: ShadowBudget = field(default_factory=ShadowBudget)

    async def shadows(self, scope: SalesScope, rules: OrderRules, step: ModelStep) -> bool:
        """Whether ``step`` reads in shadow for the tenant now, a call taken
        from its hour when it does; asked only where the step is not on and
        passing (module docstring)."""
        assist = rules.model_assist
        if not assist.shadow or step not in SHADOW_STEPS:
            return False
        if not await self.gate.configured(scope, step):
            return False
        if self.budget.take(scope.tenant_id.value, assist.shadow_calls_per_hour, self.clock.now()):
            return True
        _LOG.info(
            "shadow reading of %s skipped for tenant %s: %s calls this hour",
            step.value,
            scope.tenant_id.value,
            assist.shadow_calls_per_hour,
        )
        return False

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


async def label_reply_move(
    work: SalesUnitOfWork,
    context: AccessContext,
    ids: IdGenerator,
    *,
    case_kind: CaseKind,
    case_id: uuid.UUID,
    customer_code: str,
    from_status: str,
    to_status: str,
    at: datetime,
) -> None:
    """A person's move on a case, labelling what each reply reader read in
    shadow (ticket 67): the move a reading proposed beside the move taken,
    the newest reading per reader. A move no reply proposes (`REPLY_MOVES`)
    labels nothing and leaves the readings; a lane's move (no scope: the
    silence that implies an agreement) labels nothing either: only a person
    decides what a reply meant."""
    if not context.scopes:
        return
    move = REPLY_MOVES.get((case_kind, from_status, to_status))
    if move is None:
        return
    taken = await work.shadow_readings.take_for_case(REPLY_SHADOW_STEPS, case_id)
    newest: dict[ModelStep, ShadowReading] = {}
    for reading in taken:
        held = newest.get(reading.step)
        if held is None or reading.read_at > held.read_at:
            newest[reading.step] = reading
    labels = [
        shadow_label(
            reading,
            move,
            lane=case_kind,
            case_id=case_id,
            customer_code=customer_code,
            at=at,
            by=context.principal_id,
            new_id=ids.new_uuid,
        )
        for _, reading in sorted(newest.items())
    ]
    if labels:
        await work.labelled_cases.append(labels)
