"""Model step measurements in memory, for unit tests and evals (dw_sales ADR
0005, addendum of 2026-10-23).

Holds the SQL store's contract, not only the happy path: each tenant's rows
are its own, whichever workspace wrote them (what RLS narrowed by tenant gives
`sales.model_step_measurements`), the latest is the newest on that step,
model and prompt, a row is never changed or removed, and the audit event is
kept beside the row it records. A test that turns a model step on seeds a
passing measurement here, through `ModelAttestation` like the live lane,
rather than going around the gate.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from dw_agent_runtime.model.readiness import MeasuredScope
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.domain.audit import AuditEvent, system_actor_label
from dw_sales.application.model_readiness import (
    ATTEST_LANE,
    BARS,
    ModelAttestation,
    ModelMeasurement,
    ModelReadiness,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.order_checks import ModelStep


@dataclass
class MemoryModelMeasurements:
    """Implements `ModelMeasurementsPort` and `MeasurementLogPort`.
    ``unreadable`` makes every read fail, as a store that cannot be reached."""

    rows: dict[uuid.UUID, list[ModelMeasurement]] = field(default_factory=dict)
    events: list[AuditEvent] = field(default_factory=list)
    unreadable: bool = False

    async def latest(
        self, scope: MeasuredScope, step: str, *, model: str, prompt: str
    ) -> ModelMeasurement | None:
        if self.unreadable:
            raise ConnectionError("measurements unreadable")
        found = [
            m
            for m in self.rows.get(scope.tenant_id.value, [])
            if m.step == step and m.model == model and m.prompt == prompt
        ]
        return max(found, key=lambda m: (m.measured_at, m.measurement_id), default=None)

    async def record(
        self, scope: MeasuredScope, measurement: ModelMeasurement, event: AuditEvent
    ) -> None:
        if event.tenant_id != scope.tenant_id:
            raise ValueError("the audit event is the measurement's tenant's")
        self.rows.setdefault(scope.tenant_id.value, []).append(measurement)
        self.events.append(event)

    def seed(self, scope: SalesScope, *measurements: ModelMeasurement) -> None:
        """Rows as the lane would have written them, for a world built
        outside an event loop; read back through `latest` like any other."""
        self.rows.setdefault(scope.tenant_id.value, []).extend(measurements)


@dataclass(frozen=True)
class FixedStepModel:
    """Implements `StepModelPort` with one model for every tenant."""

    model: str

    def model_for(self, tenant_id: uuid.UUID) -> str:
        return self.model


async def measure(
    log: MemoryModelMeasurements,
    scope: SalesScope,
    model: str,
    clock: UtcClock,
    ids: IdGenerator,
    *,
    steps: Sequence[ModelStep] = tuple(ModelStep),
    value: float | None = None,
) -> list[ModelMeasurement]:
    """One measurement per step for ``scope``'s tenant on ``model``, through
    the lane's own `ModelAttestation`: at the step's bar (passing) unless
    ``value`` says otherwise."""
    attest = ModelAttestation(log, clock, ids)
    return [
        await attest.attest(
            scope,
            step,
            model=model,
            value=BARS[step].bar if value is None else value,
            held=True,
            dataset=f"{BARS[step].dataset}@1.0.0",
        )
        for step in steps
    ]


def passing(step: ModelStep, model: str, at: datetime, ids: IdGenerator) -> ModelMeasurement:
    """A measurement of ``step`` on ``model`` at its bar, as the lane writes one."""
    owner = BARS[step]
    return ModelMeasurement(
        measurement_id=ids.new_uuid(),
        step=step,
        model=model,
        prompt=str(owner.prompt),
        metric=owner.metric,
        value=owner.bar,
        bar=owner.bar,
        passed=True,
        dataset=f"{owner.dataset}@1.0.0",
        measured_at=at,
        recorded_by=system_actor_label(ATTEST_LANE),
    )


def readiness(log: MemoryModelMeasurements, model: str) -> ModelReadiness:
    """The gate over ``log``, every tenant's steps on ``model``."""
    return ModelReadiness(log, FixedStepModel(model))
