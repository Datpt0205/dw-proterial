"""Immutable, versioned runtime contracts.

Changing a prompt, tool or graph requires a new version — these models are
frozen and carry explicit version fields that feed the release manifest.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"
_SLUG_PATTERN = r"^[a-z][a-z0-9_]*$"

AutonomyLevel = Literal["A0", "A1", "A2", "A3", "A4"]
SideEffectLevel = Literal["none", "internal", "external", "critical"]
ApprovalPolicy = Literal["never", "conditional", "always"]


class WorkerDefinition(BaseModel):
    """Immutable description of a deployable Digital Worker."""

    model_config = ConfigDict(frozen=True)

    worker_id: str
    worker_version: str = Field(pattern=_SEMVER_PATTERN)
    domain: str = Field(pattern=_SLUG_PATTERN)
    graph_version: str = Field(pattern=_SEMVER_PATTERN)
    prompt_bundle_version: str = Field(pattern=_SEMVER_PATTERN)
    toolset_version: str = Field(pattern=_SEMVER_PATTERN)
    policy_version: str = Field(pattern=_SEMVER_PATTERN)
    memory_policy_version: str = Field(pattern=_SEMVER_PATTERN)
    default_model_profile: str
    supported_channels: frozenset[str]
    autonomy_level: AutonomyLevel
    # deepagents compiles with recursion_limit=9999; a runaway turn would burn
    # that whole budget before LangGraph stopped it.
    recursion_limit: int = Field(default=50, gt=0, le=500)

    @field_validator("worker_id", "default_model_profile")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class RunContext(BaseModel):
    """Per-run trusted context, created at the boundary and passed explicitly."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    # Unset means the run is its own thread; conversations pass a shared one.
    thread_id: UUID | None = None
    tenant_id: UUID
    workspace_id: UUID
    actor_id: UUID
    worker_id: str
    worker_version: str = Field(pattern=_SEMVER_PATTERN)
    channel: str
    plan_id: str
    roles: frozenset[str]
    scopes: frozenset[str]
    # How far up the classification ladder this run may read. Retrieval derives
    # its allowed classifications from it, so a run that does not carry it reads
    # nothing above "internal" - the default is the narrowest value on purpose,
    # so a construction site that forgets it under-retrieves instead of leaking.
    clearance: str = "internal"
    # The record-visibility roll-up (ADR-003), carried through so a run's CRM
    # reads narrow to the same owner subtree the REST endpoints do. Dropping
    # these silently defaulted every run to "open"/no-limit, so a chat run in a
    # restricted tenant read the whole workspace's records — the roll-up the
    # direct API enforces for the same user. Narrowest-safe defaults: an "open"
    # run with no visible set behaves as before for system/background runs.
    record_visibility: str = "open"
    visible_owners: frozenset[UUID] | None = None
    trace_id: str
    locale: str = "vi-VN"
    # The record this run is about, for surfaces that watch one of them. A page
    # showing a lead has to learn that a run touching THAT lead started or
    # finished, and it cannot learn it from a run id it has never seen. Left
    # unset by runs that are not about a single record - a conversation turn is
    # its own subject and needs no second name.
    subject_ref: str | None = None


class ToolDefinition(BaseModel):
    """Versioned tool contract enforced by the tool executor."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str = Field(pattern=_SEMVER_PATTERN)
    description: str
    input_schema_ref: str
    output_schema_ref: str
    required_scopes: frozenset[str]
    side_effect_level: SideEffectLevel
    approval_policy: ApprovalPolicy
    timeout_seconds: int = Field(gt=0, le=600)
    max_retries: int = Field(ge=0, le=10)
    idempotent: bool
    data_classification: frozenset[str]

    @field_validator("name")
    @classmethod
    def _tool_name_is_namespaced(cls, value: str) -> str:
        if "." not in value or value.startswith(".") or value.endswith("."):
            raise ValueError("tool name must be namespaced like 'task.prepare'")
        return value

    def requires_approval(self) -> bool:
        """Critical side effects always require approval regardless of policy."""
        return self.approval_policy == "always" or self.side_effect_level == "critical"
