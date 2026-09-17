"""Integrations API: the registered tool/connector surface of this release.

Read-only reflection of the ToolRegistry — the same definitions the executor
enforces, so the page can never drift from reality.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from dw_api.dependencies.auth import RequireAccessContext
from dw_api.dependencies.services import RequireContainer
from dw_kernel.errors import InfrastructureError


class IntegrationView(BaseModel):
    tool: str
    version: str
    description: str
    side_effect_level: str
    approval_policy: str
    # Whether the tool asks for a person at EVERY autonomy level — its two
    # floors, declared `always` or a `critical` side effect. False does not mean
    # a call never pauses: that depends on the run's autonomy, which an
    # inventory has no run to read. Name kept to avoid breaking the contract.
    requires_approval: bool = Field(
        description=(
            "True if this tool always requires approval, at every autonomy level. "
            "False does not mean it never pauses: whether a given call does "
            "depends on the run."
        ),
    )
    idempotent: bool
    timeout_seconds: int
    required_scopes: list[str]


router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationView])
async def list_integrations(
    context: RequireAccessContext,
    container: RequireContainer,
) -> list[IntegrationView]:
    if container.tool_registry is None:
        raise InfrastructureError("tool registry is not configured")
    await container.authorization.require(
        context=context, action="integrations.read", resource_type="integration"
    )
    return [
        IntegrationView(
            tool=definition.name,
            version=definition.version,
            description=definition.description,
            side_effect_level=str(definition.side_effect_level),
            approval_policy=str(definition.approval_policy),
            requires_approval=definition.always_requires_approval(),
            idempotent=definition.idempotent,
            timeout_seconds=definition.timeout_seconds,
            required_scopes=sorted(definition.required_scopes),
        )
        for definition in container.tool_registry.all_definitions()
    ]
