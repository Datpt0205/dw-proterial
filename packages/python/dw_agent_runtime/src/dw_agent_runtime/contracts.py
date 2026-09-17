"""Immutable, versioned runtime contracts.

Changing a prompt, tool or graph requires a new version — these models are
frozen and carry explicit version fields that feed the release manifest.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dw_kernel.autonomy import FAIL_CLOSED_LEVEL, AutonomyLevel

_SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"
_SLUG_PATTERN = r"^[a-z][a-z0-9_]*$"

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
    # The most autonomy the tenant allows, carried in from AccessContext by the
    # boundary that builds this context. Narrowest by default, same reasoning as
    # `clearance`: a construction site that forgets it gets a run that asks about
    # everything — loud in the first test — instead of one that quietly ignores
    # the ceiling a customer set.
    autonomy_ceiling: AutonomyLevel = FAIL_CLOSED_LEVEL
    # The level this run actually runs at, and the policy version that turns it
    # into decisions. Set by the runner when the run starts — the lower of the
    # worker's declared level and the ceiling above — stamped on the run row,
    # and replayed from that row on resume. None means the run never went
    # through the runner, and the policy treats that as ask-everything.
    autonomy_level: AutonomyLevel | None = None
    approval_policy_version: str | None = None


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

    def always_requires_approval(self) -> bool:
        """Whether this tool asks for a person at EVERY autonomy level.

        The two floors, and only them: declared `always`, or a `critical` side
        effect. It used to be named `requires_approval` and to be the whole
        decision, which is how a worker's autonomy level came to be read by
        nothing. Whether a given call asks depends on the run — use
        `AutonomyApprovalPolicy.decide`. This answers only what is true of the tool
        regardless of who runs it, which is what an inventory screen can know.
        """
        return self.approval_policy == "always" or self.side_effect_level == "critical"
