"""Model-step measurements in memory, for DW2's tests and evals: each
tenant's rows its own, the latest the newest on that step, model and prompt,
a row never changed (what `platform.model_step_measurements` holds)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from dw_agent_runtime.model.readiness import MeasuredScope, ModelMeasurement
from dw_platform.domain.audit import AuditEvent


@dataclass
class MemoryMeasurements:
    """Implements `ModelMeasurementsPort` and `MeasurementLogPort`."""

    rows: dict[uuid.UUID, list[ModelMeasurement]] = field(default_factory=dict)
    events: list[AuditEvent] = field(default_factory=list)

    async def latest(
        self, scope: MeasuredScope, step: str, *, model: str, prompt: str
    ) -> ModelMeasurement | None:
        found = [
            m
            for m in self.rows.get(scope.tenant_id.value, [])
            if m.step == step and m.model == model and m.prompt == prompt
        ]
        return max(found, key=lambda m: (m.measured_at, m.measurement_id), default=None)

    async def record(
        self, scope: MeasuredScope, measurement: ModelMeasurement, event: AuditEvent
    ) -> None:
        self.rows.setdefault(scope.tenant_id.value, []).append(measurement)
        self.events.append(event)


@dataclass(frozen=True)
class FixedModel:
    """Implements `StepModelPort` with one model for every tenant."""

    model: str = "qwen3.5:9b"

    def model_for(self, tenant_id: uuid.UUID) -> str:
        return self.model
