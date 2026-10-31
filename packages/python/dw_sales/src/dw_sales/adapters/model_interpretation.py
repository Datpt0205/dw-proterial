"""The model DW1's steps run on, as `StepModelPort` asks it. The door to the
model itself, `GatewayInterpretation`, is the runtime's
(`dw_agent_runtime.adapters.model_interpretation`, docs/adr/0013)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from dw_agent_runtime.model.profiles import ModelProfileRegistry


@dataclass(frozen=True)
class ProfileStepModel:
    """Implements `StepModelPort`: the model DW1's profile routes its steps to
    for a tenant, resolved as the gateway resolves it (the tenant's own
    profile where it has one, the platform's otherwise; the structured route
    every step reads on)."""

    profiles: ModelProfileRegistry
    model_profile: str

    def model_for(self, tenant_id: uuid.UUID) -> str:
        profile = self.profiles.resolve(self.model_profile, tenant_id=tenant_id)
        return profile.structured_extraction.model
