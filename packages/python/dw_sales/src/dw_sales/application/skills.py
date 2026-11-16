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
- **Taught from a triage card** (ticket 34): a version of the mail kinds may
  be proposed from the card of a mail they did not read (`SkillProposal.
  from_message`). The server finds that mail, with its card, in the
  proposer's own workspace, and the version records it (`SkillTrigger`), so
  its replay reads that mail too, with the version and without it, beside
  the example mails. It is words like any version: what it names is checked
  as every version's is, and it decides nothing.
- **A customer's SalesOrder skill** (ticket 41) is a skill like these,
  ``salesorder-<customer code>`` (`salesorder_skills`), replayed on the
  customer's worked pairs instead: the head may approve a version only where
  every pair came out as the PIC's file (`SkillDecisions`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.skills import Skill, SkillSet
from dw_kernel.errors import ConflictError, DomainError, NotFoundError
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
from dw_sales.domain.document_forms import DOCUMENT_FORMS, document_forms_of
from dw_sales.domain.handoff_kinds import HANDOFFS, handoff_kinds_of
from dw_sales.domain.mail_kinds import MAIL_KINDS, ReadRoute, mail_kinds_of
from dw_sales.domain.reply_kinds import REPLY_DRAFTS, reply_kinds_of

__all__ = [
    "READ_SKILL",
    "READ_SKILL_VERSION",
    "SKILLS_APPROVAL",
    "SKILLS_DECIDED",
    "STEP_SKILLS",
    "WORDS_UNREADABLE",
    "Dw1Skills",
    "SkillBook",
    "SkillDecisions",
    "SkillDocument",
    "SkillReplay",
    "SkillReplayStorePort",
    "SkillSettlement",
    "SkillTrigger",
    "SkillsService",
    "TriggerReplay",
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

# The skills code reads at one fixed step of the classification order (ADR
# 0014's guards: malware, document, upload, headers, then the model), never
# offered to a thread message's skill pick: the mail kinds (ticket 42); and
# the hand-offs and reply drafts, each read at its own fixed step (family 5).
STEP_SKILLS: Final = frozenset({MAIL_KINDS, HANDOFFS, REPLY_DRAFTS}) | {
    # A customer's file no fixed reader reads (family 3).
    DOCUMENT_FORMS
}
# What code checks of a version's words before it is proposed, per skill: the
# mail kinds' routes are the platform's legal ones (ticket 42).
_WORDS_CHECKED: Final[Mapping[str, Callable[[str], object]]] = {
    MAIL_KINDS: mail_kinds_of,
    # The hand-offs' fields and teams, and the reply drafts' drafts, are the
    # platform's closed sets (ticket 42 family 5).
    HANDOFFS: handoff_kinds_of,
    REPLY_DRAFTS: reply_kinds_of,
    # The document forms' routes and customers (ticket 42 family 3).
    DOCUMENT_FORMS: document_forms_of,
}

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


# A customer's SalesOrder skill (ticket 41, `salesorder_skills`): the generic
# skill's key, then the customer's code in lower case.
SALESORDER_PREFIX: Final = SKILL_PREFIX + "salesorder_"


def salesorder_key(customer_code: str) -> str:
    """The key a customer's SalesOrder skill is stored under."""
    return SALESORDER_PREFIX + customer_code.lower()


def is_salesorder_key(key: str) -> bool:
    """Whether ``key`` is a customer's SalesOrder skill's: the prefix, then a
    customer code (`domain.catalog.CustomerCode`) in lower case."""
    code = key.removeprefix(SALESORDER_PREFIX)
    return (
        key.startswith(SALESORDER_PREFIX)
        and 2 <= len(code) <= 16
        and code.isascii()
        and code.isalnum()
        and code[0].isalpha()
        and code == code.lower()
    )


class SkillTrigger(BaseModel):
    """The mail a version was proposed from (a triage card, ticket 34), in
    the proposer's workspace as the server resolved it: its replay reads it
    with the version and without it."""

    model_config = _FROZEN

    workspace_id: UUID
    message_id: str = Field(pattern=r"^[!-~]{1,512}$")


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
    # The mail it was proposed from, where a triage card proposed it; read
    # by its replay only, never served.
    trigger: SkillTrigger | None = None

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
        """Every platform skill a thread message's reading may pick, as the
        run's tenant holds it now: not one a fixed step reads (`STEP_SKILLS`)."""
        skills = []
        for key in sorted(self.platform):
            if skill_name(key) not in STEP_SKILLS:
                skills.append(await self.skill(run, skill_name(key)))
        return SkillSet(run.tenant_id, run.workspace_id, tuple(skills))

    async def skill(self, run: RunContext, name: str) -> Skill:
        """The skill named ``name`` as the run's tenant holds it now."""
        scope = ContextScope(TenantId(run.tenant_id), WorkspaceId(run.workspace_id))
        document = (await self.current(scope, skill_key(name))).policy
        assert isinstance(document, SkillDocument)
        return document.skill()

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

# ``customer_pairs``: a customer's SalesOrder skill replayed on its worked
# pairs (ticket 41): ``messages`` counts the pairs, ``right_*`` the pairs
# whose fill came out as the PIC's file.
ReplaySource = Literal["platform_examples", "customer_pairs"]
ReplayOutcome = Literal["replayed", "incomplete"]


class TriggerReplay(BaseModel):
    """The mail a version was proposed from (`SkillTrigger`), read with the
    version and with the one in force: the kind each named (None: no usable
    answer, or no kind read), its label where the skill gives one, and the
    route it took (``none``: no kind read; None: no usable answer)."""

    model_config = _FROZEN

    message_id: str = Field(pattern=r"^[!-~]{1,512}$")
    # False: the lane did not find the mail any more (its retention, or a
    # workspace that left); nothing was read.
    found: bool
    with_kind: str | None = Field(default=None, max_length=40)
    with_label: str | None = Field(default=None, max_length=60)
    with_route: ReadRoute | None = None
    without_kind: str | None = Field(default=None, max_length=40)
    without_label: str | None = Field(default=None, max_length=60)
    without_route: ReadRoute | None = None


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
    # The mail the version was proposed from, read both ways (ticket 34).
    trigger: TriggerReplay | None = None


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


# Refused: proposing a version whose words code cannot read (an unknown
# route, a kind named twice).
WORDS_UNREADABLE: Final = "skill_words_unreadable"


def _first_error(exc: ValueError) -> str:
    """What is wrong, in one sentence: pydantic's first message, or the
    reader's own."""
    if isinstance(exc, ValidationError):
        return str(exc.errors()[0]["msg"])
    return str(exc)


# Refused: a version taught from a triage card of a skill other than the
# mail kinds (ticket 34).
TRIGGER_REFUSED: Final = "skill_trigger_refused"


# Refused: approving a version the worker has not replayed yet.
NOT_REPLAYED: Final = "skill_not_replayed"
# Refused: approving a customer's SalesOrder skill that did not reproduce
# every worked pair of the customer, or that no pair proved (ticket 41).
PAIRS_BROKEN: Final = "skill_pairs_broken"


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
    # The mail it was proposed from, where a triage card proposed it.
    trigger: str | None = None


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
    # The mail whose triage card it is proposed from (ticket 34): the
    # server finds it, with its card, in the proposer's own workspace.
    from_message: str | None = Field(default=None, pattern=r"^[!-~]{1,512}$")


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
        trigger=None if document.trigger is None else document.trigger.message_id,
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
            trigger=await self._trigger(context, name, proposal.from_message),
        )
        if (check := _WORDS_CHECKED.get(name)) is not None:
            try:
                check(document.instructions)
            except ValueError as exc:
                raise DomainError(
                    f"Kỹ năng {name} chưa đọc được: {_first_error(exc)}",
                    details={"skill": name, "rule": WORDS_UNREADABLE},
                ) from exc
        version = await self._engine.propose(
            context, key, document.model_dump(mode="json"), applies_directly=False
        )
        return _version_view(version)

    async def _trigger(
        self, context: AccessContext, name: str, message_id: str | None
    ) -> SkillTrigger | None:
        """The mail a version is proposed from (module docstring): only the
        mail kinds are taught from a card, and only from a card on a mail of
        the proposer's own workspace (RLS reads no other; one not found, or
        carrying no card, is not found)."""
        if message_id is None:
            return None
        if name != MAIL_KINDS:
            raise DomainError(
                "Chỉ kỹ năng phân loại thư được dạy từ thẻ gợi ý của một thư.",
                details={"skill": name, "rule": TRIGGER_REFUSED},
            )
        async with self.uow(sales_scope(context)) as work:
            logged = await work.messages.logged(message_id)
        if logged is None or logged.disposition.triage is None:
            raise NotFoundError("no such card", details={"message_id": message_id})
        return SkillTrigger(workspace_id=context.workspace_id, message_id=message_id)


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
        asked = asked_of(REGISTRY, request)
        version_id = asked.version_id
        stored = await self.replays.stored(sales_scope(context), [version_id])
        if version_id not in stored:
            raise ConflictError(
                "Phiên bản kỹ năng chưa được chạy thử trên thư mẫu: chờ kết quả chạy thử"
                " rồi duyệt (vẫn có thể từ chối).",
                details={"version_id": str(version_id), "rule": NOT_REPLAYED},
            )
        replay = stored[version_id]
        if is_salesorder_key(asked.key) and not every_pair(replay):
            raise ConflictError(
                "Kỹ năng SalesOrder của khách chưa điền đúng mọi cặp ví dụ của khách: sửa kỹ"
                " năng hoặc thêm cặp ví dụ rồi đề xuất lại (vẫn có thể từ chối).",
                details={
                    "version_id": str(version_id),
                    "rule": PAIRS_BROKEN,
                    "pairs": replay.messages,
                    "reproduced": replay.right_with,
                },
            )


def every_pair(replay: SkillReplay) -> bool:
    """A customer's SalesOrder skill replayed on its pairs, every one of
    which came out as the PIC's file: at least one, each answered."""
    return (
        replay.source == "customer_pairs"
        and replay.outcome == "replayed"
        and replay.messages > 0
        and replay.right_with == replay.messages
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
