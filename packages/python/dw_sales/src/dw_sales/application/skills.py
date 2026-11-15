"""DW1's skills: the platform's words, a tenant's own version of them, and
how a version is proposed and decided (dw_sales ADR 0014, ticket 40).

A skill says in words how DW1 does one kind of work (`SKILL.md`, deepagents'
format): its name and a description the agent chooses it by, then the
instructions. The platform ships each in ``configs/skills/dw1`` with DW1's
conduct (`AGENT.md`), and no customer data: the repository is public. A tenant
holds its own version of a skill in its data.

- **One store, the rules' own.** A skill version is a row of
  `platform.rule_versions` under the key ``sales_skill_<name>`` (hyphens as
  underscores), its description and instructions the document: one row per
  tenant, skill and version, with its status, proposer and decider. The
  platform's rule-version engine holds it as it holds every rule: one
  proposal waiting per skill, never a number the platform ships, decided by
  a holder of the approval's stamp and never by its proposer
  (`RuleDecisionGuard`, `ck_rule_versions_checker_not_maker`), carried out
  by the worker from the approval row. Its scope is the tenant's, as a
  rule's and a prompt's are: a skill reads every workspace's mail alike.
- **Proposed by whoever proposes rules** (`sales.rules.propose`) and
  **decided by the head** (`sales.rules.approve`) on a `sales.skills`
  approval, **never applied directly**, the head's own proposal included:
  a skill changes how every mail is read, so a second person reads it first
  (acceptance 3).
- **Resolved per run** (`SkillBook.skill_set`): each platform skill, the
  tenant's approved version where it has one, else the platform's, never
  another tenant's. The tenant is the run's (`RunContext`, built by the
  runner from a verified context), never a request's.
- **Words, never power**: a version is a description and instructions, held
  to their lengths and nothing else. What a turn may call, whom it reads for
  and what a reading may say stay code's (`thread_tools`, `verified_intents`).

- **Replayed before it is decided.** The worker replays each proposal on
  example mails, with it and with the skills in force
  (`skill_replay.SkillReplayer`), and stores the counts beside it
  (`SkillReplay`); the skills list shows them, and the head may approve only
  a version whose replay is stored (`SkillDecisions`). Rejecting needs none.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.skills import Skill, SkillSet
from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import (
    ContextScope,
    Layer,
    RuleBook,
    RuleDecisionGuard,
    RuleRegistry,
    RuleScope,
    RuleStatus,
    RuleVersion,
    RuleVersionEngine,
    RuleVersionLookupPort,
    RuleVersionSettlement,
    asked_of,
)
from dw_platform.domain.approval import ApprovalRequest, decided_event_type
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.ports import MemberDirectoryPort, SalesScope
from dw_sales.application.rules import ProposerNames, rule_work

__all__ = [
    "READ_SKILL",
    "READ_SKILL_VERSION",
    "SKILLS_APPROVAL",
    "SKILLS_DECIDED",
    "Dw1Skills",
    "SkillBook",
    "SkillDecisions",
    "SkillDocument",
    "SkillReplay",
    "SkillReplayStorePort",
    "SkillSettlement",
    "SkillsService",
    "skill_key",
    "skill_name",
]

# The key a skill's versions are stored under: the prefix, then its name with
# hyphens as underscores (a rule key's alphabet).
SKILL_PREFIX: Final = "sales_skill_"
# The tool a turn loads a skill with (``configs/tools/sales.read_skill@1.0.0.yaml``).
READ_SKILL: Final = "sales.read_skill"
READ_SKILL_VERSION: Final = "1.0.0"
# The most a skill's instructions may hold: the platform's first is about
# 5,000 characters, and every model call of a turn that loaded it carries it.
INSTRUCTIONS_LIMIT: Final = 12_000

_RESOURCE: Final = "sales_skill_version"
SKILLS_APPROVAL: Final = "sales.skills"
SKILLS_DECIDED: Final = decided_event_type(SKILLS_APPROVAL)
REGISTRY: Final = RuleRegistry(
    approval_type=SKILLS_APPROVAL,
    approve_scope=SalesScopes.RULES_APPROVE.value,
    resource_type=_RESOURCE,
    audit_prefix="sales.skills",
    reason=(
        "Phiên bản kỹ năng của DW1 chờ duyệt: Trưởng bộ phận duyệt, không phải người đề xuất"
        " (ticket 40)"
    ),
)

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


def skill_key(name: str) -> str:
    """The rule key a skill named ``name`` is stored under."""
    return SKILL_PREFIX + name.replace("-", "_")


def skill_name(key: str) -> str:
    """The skill a key stores: `skill_key`'s inverse."""
    return key.removeprefix(SKILL_PREFIX).replace("_", "-")


class SkillDocument(BaseModel):
    """One version of a skill, as stored and as resolved: the whole skill,
    never a patch."""

    model_config = _FROZEN

    schema_version: Literal["1.0"] = "1.0"
    policy_id: str = Field(pattern=r"^sales_skill_[a-z0-9]+(_[a-z0-9]+)*$", max_length=64)
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    # What the agent chooses the skill by, in its catalogue.
    description: str = Field(min_length=1, max_length=1024)
    instructions: str = Field(min_length=1, max_length=INSTRUCTIONS_LIMIT)

    @property
    def ref(self) -> str:
        return f"{self.policy_id}@{self.policy_version}"

    @property
    def name(self) -> str:
        return skill_name(self.policy_id)

    def skill(self) -> Skill:
        return Skill(
            name=self.name,
            description=self.description,
            body=self.instructions,
            ref=self.ref,
        )


@dataclass(frozen=True)
class Dw1Skills:
    """The platform layer: DW1's conduct and its skills, as shipped."""

    agent: str
    # ``dw1@<version>``: what the conduct a process serves is pinned as.
    agent_ref: str
    skills: Mapping[str, SkillDocument]


@dataclass(frozen=True)
class SkillBook(RuleBook):
    """The skills in force for a tenant, through the platform's resolution
    (`RuleBook.current`: the tenant's approved version, else the platform's,
    never sideways), and the ones a stamp names (`RuleBook.at`)."""

    async def skill_set(self, run: RunContext) -> SkillSet:
        """Every platform skill as the run's tenant holds it now."""
        scope = ContextScope(TenantId(run.tenant_id), WorkspaceId(run.workspace_id))
        skills = []
        for key in sorted(self.platform):
            document = (await self.current(scope, key)).policy
            assert isinstance(document, SkillDocument)
            skills.append(document.skill())
        return SkillSet(run.tenant_id, run.workspace_id, tuple(skills))

    def knows(self, key: str) -> bool:
        return key in self.platform


def skill_book(skills: Dw1Skills, stored: RuleVersionLookupPort) -> SkillBook:
    """The book over the platform's skills and ``stored``, the tenant's
    versions."""
    return SkillBook(
        platform=dict(skills.skills),
        stored=stored,
        schemas=dict.fromkeys(skills.skills, SkillDocument),
    )


# ------------------------------------------------------------- replays --

ReplaySource = Literal["platform_examples"]
ReplayOutcome = Literal["replayed", "incomplete"]


class SkillReplay(BaseModel):
    """What one replay of a proposed version found, stored beside it
    (`skill_replay`)."""

    model_config = _FROZEN

    version_id: UUID
    replayed_at: datetime
    # Which example mails were read: the platform's, while no tenant's own
    # reply readings are labelled (ticket 43).
    source: ReplaySource
    # ``incomplete``: some reading got no usable answer, so the counts are
    # partial.
    outcome: ReplayOutcome
    # The example mails read (security-only cases excluded), and how many of
    # them were read as exactly their expected intents with the proposal and
    # with the skills in force.
    messages: int = Field(ge=0)
    right_with: int = Field(ge=0)
    right_without: int = Field(ge=0)
    # Readings, of either side, that got no usable answer.
    unanswered: int = Field(ge=0)
    # The security cases the proposal failed, by example id.
    security_failed: tuple[str, ...] = ()


class SkillReplayStorePort(Protocol):
    """The replays stored beside proposals, in one tenant's scope."""

    async def stored(
        self, scope: SalesScope, version_ids: Sequence[UUID]
    ) -> Mapping[UUID, SkillReplay]: ...

    async def store(self, scope: SalesScope, replay: SkillReplay, audit: AuditEvent) -> bool:
        """The replay and its audit row, in one transaction; False, and
        neither written, where the version already has one (another
        workspace's lane got there first)."""
        ...


# Refused: approving a version the worker has not replayed yet.
NOT_REPLAYED: Final = "skill_not_replayed"


# --------------------------------------------------------------- views --


class SkillVersionView(BaseModel):
    """A tenant's version of a skill, as the skills list shows it."""

    model_config = ConfigDict(frozen=True)

    version_id: UUID
    name: str
    ref: str
    status: RuleStatus
    proposed_by: UUID
    decided_by: UUID | None
    description: str
    instructions: str
    # The platform approval it is decided on (`POST /approvals/{id}/decisions`).
    approval_id: UUID | None
    # What the worker's replay found; None until it has run.
    replay: SkillReplay | None = None


class SkillView(BaseModel):
    """A skill as it applies to the tenant now."""

    model_config = ConfigDict(frozen=True)

    name: str
    ref: str
    layer: Layer
    description: str
    instructions: str
    # The ref the platform ships, what a tenant version may not reuse.
    platform_ref: str


class SkillsView(BaseModel):
    model_config = ConfigDict(frozen=True)

    skills: list[SkillView]
    versions: list[SkillVersionView]


class SkillProposal(BaseModel):
    """What a person proposes: the skill's new words and a version number of
    the tenant's own."""

    model_config = _FROZEN

    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(min_length=1, max_length=1024)
    instructions: str = Field(min_length=1, max_length=INSTRUCTIONS_LIMIT)


def _version_view(version: RuleVersion, replay: SkillReplay | None = None) -> SkillVersionView:
    document = SkillDocument.model_validate(dict(version.document))
    return SkillVersionView(
        version_id=version.version_id,
        name=document.name,
        ref=version.ref,
        status=version.status,
        proposed_by=version.proposed_by,
        decided_by=version.decided_by,
        description=document.description,
        instructions=document.instructions,
        approval_id=version.approval_id,
        replay=replay,
    )


# ------------------------------------------------------------- service --


@dataclass(frozen=True)
class SkillsService:
    """List the skills in force and propose a version of one."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    book: SkillBook
    clock: UtcClock
    ids: IdGenerator
    directory: MemberDirectoryPort
    replays: SkillReplayStorePort

    @property
    def _engine(self) -> RuleVersionEngine:
        return RuleVersionEngine(
            REGISTRY,
            rule_work(self.uow),
            self.book,
            self.clock,
            self.ids,
            ProposerNames(self.directory),
        )

    async def list(self, context: AccessContext) -> SkillsView:
        """Each skill as the tenant holds it now, and every version of its."""
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        scope: RuleScope = ContextScope.of(context)
        keys = sorted(self.book.platform)
        skills = []
        for key in keys:
            resolved = await self.book.current(scope, key)
            document = resolved.policy
            assert isinstance(document, SkillDocument)
            skills.append(
                SkillView(
                    name=document.name,
                    ref=document.ref,
                    layer=resolved.layer,
                    description=document.description,
                    instructions=document.instructions,
                    platform_ref=self.book.platform[key].ref,
                )
            )
        versions = await self._engine.list_all(context, keys=keys)
        replays = await self.replays.stored(
            sales_scope(context), [v.version_id for v in versions if v.status == "proposed"]
        )
        return SkillsView(
            skills=skills,
            versions=[_version_view(v, replays.get(v.version_id)) for v in versions],
        )

    async def propose(
        self, context: AccessContext, name: str, proposal: SkillProposal
    ) -> SkillVersionView:
        """A version of the skill named ``name``, waiting on a `sales.skills`
        approval the head decides, never its proposer; never applied
        directly, the head's own included (module docstring). A name the
        platform ships no skill of is not found: a skill of the tenant's own
        is not served yet."""
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        key = skill_key(name)
        if not self.book.knows(key):
            raise NotFoundError("no such skill", details={"skill": name})
        document = SkillDocument(
            policy_id=key,
            policy_version=proposal.version,
            description=proposal.description,
            instructions=proposal.instructions,
        )
        version = await self._engine.propose(
            context, key, document.model_dump(mode="json"), applies_directly=False
        )
        return _version_view(version)


# ----------------------------------------------------------- the decision --


@dataclass(frozen=True)
class SkillDecisions:
    """The platform's `ApprovalDecisionGuard` for `sales.skills`: the
    decider holds the stamp, is not the proposer, and the version still
    waits on this approval (`RuleDecisionGuard` with this registry); and an
    approval only once the worker's replay of the version is stored, so the
    head has seen what it changes (ADR 0014 decision 2). A rejection needs
    no replay."""

    uow: SalesUnitOfWorkFactory
    book: SkillBook
    replays: SkillReplayStorePort

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        await RuleDecisionGuard(REGISTRY, rule_work(self.uow), self.book).check(
            request, decision, context
        )
        if not decision.approve:
            return
        version_id = asked_of(REGISTRY, request).version_id
        if version_id not in await self.replays.stored(sales_scope(context), [version_id]):
            raise ConflictError(
                "Phiên bản kỹ năng chưa được chạy thử trên thư mẫu: chờ kết quả chạy thử"
                " rồi duyệt (vẫn có thể từ chối).",
                details={"version_id": str(version_id), "rule": NOT_REPLAYED},
            )


@dataclass(frozen=True)
class SkillSettlement:
    """Carries out a decided `sales.skills` approval: the worker's handler
    for `SKILLS_DECIDED` calls it with the decider's tenancy and identity."""

    uow: SalesUnitOfWorkFactory
    book: SkillBook
    clock: UtcClock
    ids: IdGenerator

    async def settle(self, approval_id: UUID, decider: AccessContext) -> SkillVersionView:
        settled = await RuleVersionSettlement(
            REGISTRY, rule_work(self.uow), self.book, self.clock, self.ids
        ).settle(approval_id, decider)
        return _version_view(settled)


def platform_skills(skills: Sequence[SkillDocument]) -> dict[str, SkillDocument]:
    """The platform layer by key; two of one name are refused."""
    held: dict[str, SkillDocument] = {}
    for skill in skills:
        if skill.policy_id in held:
            raise ValueError(f"two platform skills named {skill.name}")
        held[skill.policy_id] = skill
    return held
