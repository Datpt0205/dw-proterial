"""A tenant's version of a model step's prompt: the demonstrations it shows
every reading, proposed by the worker from decided cases, approved by the head
(ticket 43 part 3, dw_sales ADR 0015 decisions 5 and 6).

- **What a version is**: words a model reads, never power. The platform's
  prompt (`configs/prompts/sales/description_attributes@1.2.0.yaml`) stays the
  instructions; a tenant's version adds up to `MAX_DEMONSTRATIONS` decided
  lines (a description and the PRV code a person kept), shown to every
  reading as untrusted input beside the nearest examples
  (`application.examples`). It changes no tool, scope, number or move. The
  replay figures it was proposed on travel with it, counts only.
- **One store, the rules' own**: a row of `platform.rule_versions` under
  `PROMPT_KEY` (migration widening `ck_rule_versions_key`), decided on a
  `sales.prompts` approval through the platform's rule-version engine: one
  proposal waiting at a time, decided by a holder of `sales.rules.approve`
  who is not its proposer (`RuleDecisionGuard`), carried out by the worker
  from the approval row. **Never applied directly**: the proposer is the
  optimiser lane (`application.prompt_optimiser`), which may not decide.
- **Resolved per run** (`PromptBook.demonstrations`): the tenant's approved
  version, else the platform's, which shows none; never another tenant's.
  The tenant is the run's.
- **Read by the head** (`PromptVersionsService`, `/sales/rules/prompts`):
  each version beside the one in force, its replay figures and the decided
  lines it shows, to a holder of `sales.rules.approve` only; the decision
  stays the approval's, on `/approvals`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import (
    Layer,
    RuleBook,
    RuleDecisionGuard,
    RuleRegistry,
    RuleStatus,
    RuleVersion,
    RuleVersionLookupPort,
    RuleVersionSettlement,
)
from dw_platform.domain.approval import ApprovalRequest, decided_event_type
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.model_reading import DESCRIPTION_ATTRIBUTES, Demonstrations
from dw_sales.application.ports import SalesScope
from dw_sales.application.rules import rule_work
from dw_sales.domain.catalog import CustomerCode, PrvCode
from dw_sales.domain.description_reading import SpanRead
from dw_sales.domain.order_checks import ModelStep

__all__ = [
    "MAX_DEMONSTRATIONS",
    "PLATFORM_PROMPT",
    "PROMPTS_APPROVAL",
    "PROMPTS_DECIDED",
    "PROMPT_KEY",
    "REGISTRY",
    "Demonstration",
    "PromptBook",
    "PromptDecisions",
    "PromptDemonstrations",
    "PromptReplay",
    "PromptSettlement",
    "PromptVersionView",
    "PromptVersionsService",
    "PromptsView",
    "StoredDemonstration",
    "prompt_book",
]

# The key a tenant's versions of the description reading's prompt are stored
# under.
PROMPT_KEY: Final = "sales_prompt_description_attributes"
# The most demonstrations a version shows: every reading carries them.
MAX_DEMONSTRATIONS: Final = 6

PROMPTS_APPROVAL: Final = "sales.prompts"
PROMPTS_DECIDED: Final = decided_event_type(PROMPTS_APPROVAL)
REGISTRY: Final = RuleRegistry(
    approval_type=PROMPTS_APPROVAL,
    approve_scope=SalesScopes.RULES_APPROVE.value,
    resource_type="sales_prompt_version",
    audit_prefix="sales.prompts",
    reason=(
        "DW1 đề xuất phiên bản lời nhắc mới, học từ các dòng người đã quyết: đúng hơn trên"
        " mọi dòng đã quyết và qua mọi ca bảo mật. Trưởng bộ phận duyệt, DW không tự áp dụng"
        " (ticket 43)"
    ),
)

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class StoredDemonstration(BaseModel):
    """One decided line a version shows, as its document keeps it: the
    customer's description, the PRV code a person kept and, where code
    accepted one, the line's reading. The head's page lists it as a
    `Demonstration`, without the spans."""

    model_config = _FROZEN

    description: str = Field(min_length=1, max_length=500)
    prv_code: PrvCode
    # The decided line it was taken from, for the head's page: the labelled
    # case, its order case and its customer. Never shown to a reading
    # (`shown_lines` reads the description and the code only); None on a
    # version proposed before they were kept.
    label_id: UUID | None = None
    case_id: UUID | None = None
    customer_code: CustomerCode | None = None
    # The line's reading code accepted, shown as the answer it was where it
    # fits the kept item (ticket 43, 2026-11-22); empty on an older version.
    spans: tuple[SpanRead, ...] = ()


class Demonstration(BaseModel):
    """One decided line a version shows: the customer's description and the
    PRV code a person kept. The reading shows the code's attributes from the
    item master, never the code (`model_reading.shown_lines`)."""

    model_config = _FROZEN

    description: str = Field(min_length=1, max_length=500)
    prv_code: PrvCode
    label_id: UUID | None = None
    case_id: UUID | None = None
    customer_code: CustomerCode | None = None

    @classmethod
    def of(cls, demonstration: StoredDemonstration) -> Demonstration:
        return cls.model_validate(demonstration.model_dump(exclude={"spans"}))


class PromptReplay(BaseModel):
    """What the version was proposed on: the labelled cases replayed, how
    many the platform's (or the version in force) read right and how many
    this one does, and the security cases it passed. Counts only."""

    model_config = _FROZEN

    cases: int = Field(ge=0)
    right_before: int = Field(ge=0)
    right_after: int = Field(ge=0)
    security_cases: int = Field(ge=0)


class PromptDemonstrations(BaseModel):
    """One version of the description reading's prompt for a tenant: the
    whole set, never a patch."""

    model_config = _FROZEN

    schema_version: Literal["1.0"] = "1.0"
    policy_id: Literal["sales_prompt_description_attributes"] = PROMPT_KEY
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    demonstrations: tuple[StoredDemonstration, ...] = Field(
        default=(), max_length=MAX_DEMONSTRATIONS
    )
    replay: PromptReplay | None = None

    @property
    def ref(self) -> str:
        return f"{self.policy_id}@{self.policy_version}"


# The platform's version: the prompt as shipped, no demonstrations. Its
# number is the prompt file's, so a tenant's version never reuses it.
PLATFORM_PROMPT: Final = PromptDemonstrations(policy_version=DESCRIPTION_ATTRIBUTES.version)


@dataclass(frozen=True)
class PromptBook(RuleBook):
    """The prompt version in force for a tenant, through the platform's
    resolution (`RuleBook.current`: the tenant's approved version, else the
    platform's, never sideways). Implements `DemonstrationsPort`."""

    async def in_force(self, scope: SalesScope) -> tuple[PromptDemonstrations, bool]:
        """The version in force and whether it is the tenant's own."""
        resolved = await self.current(scope, PROMPT_KEY)
        document = resolved.policy
        assert isinstance(document, PromptDemonstrations)
        return document, resolved.layer == "tenant"

    async def demonstrations(self, scope: SalesScope) -> Demonstrations:
        document, own = await self.in_force(scope)
        if not own:
            return Demonstrations(None)
        return Demonstrations(document.policy_version, document.demonstrations)


class PromptVersionView(BaseModel):
    """A tenant's version of the prompt, as the head's page shows it."""

    model_config = ConfigDict(frozen=True)

    version_id: UUID
    ref: str
    status: RuleStatus
    proposed_by: UUID
    proposed_at: datetime
    decided_by: UUID | None
    decided_at: datetime | None
    # The decider's reason, as the version keeps it.
    comment: str | None
    # The platform approval it is decided on (`/approvals/{id}`).
    approval_id: UUID | None
    demonstrations: list[Demonstration]
    replay: PromptReplay | None


class PromptsView(BaseModel):
    """The description reading's prompt for the tenant: the platform's
    prompt the versions add to, the version in force and what it shows, and
    every version of the tenant's, newest first."""

    model_config = ConfigDict(frozen=True)

    step: str
    prompt: str
    in_force: str
    layer: Layer
    demonstrations: list[Demonstration]
    versions: list[PromptVersionView]


def _version_view(version: RuleVersion) -> PromptVersionView:
    document = PromptDemonstrations.model_validate(dict(version.document))
    return PromptVersionView(
        version_id=version.version_id,
        ref=version.ref,
        status=version.status,
        proposed_by=version.proposed_by,
        proposed_at=version.proposed_at,
        decided_by=version.decided_by,
        decided_at=version.decided_at,
        comment=version.comment,
        approval_id=version.approval_id,
        demonstrations=[Demonstration.of(d) for d in document.demonstrations],
        replay=document.replay,
    )


@dataclass(frozen=True)
class PromptVersionsService:
    """The head's page of the prompt versions (ticket 43): read only. A
    version is proposed by the optimiser lane alone and decided on its
    `sales.prompts` approval; nothing here proposes or decides."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    book: PromptBook

    async def list(self, context: AccessContext) -> PromptsView:
        """The version in force and every version of the tenant's, to whoever
        decides them (`sales.rules.approve`): the demonstrations carry
        customers' words, which the rules' proposers need not read."""
        await self.gate.require(
            context, SalesScopes.RULES_APPROVE, resource_type=REGISTRY.resource_type
        )
        scope = sales_scope(context)
        document, own = await self.book.in_force(scope)
        async with self.uow(scope) as work:
            versions = await work.rule_versions.list_all(keys=(PROMPT_KEY,))
        return PromptsView(
            step=ModelStep.DESCRIPTION_ATTRIBUTES.value,
            prompt=str(DESCRIPTION_ATTRIBUTES),
            in_force=document.ref,
            layer="tenant" if own else "platform",
            demonstrations=[Demonstration.of(d) for d in document.demonstrations],
            versions=[_version_view(v) for v in versions],
        )


def prompt_book(stored: RuleVersionLookupPort) -> PromptBook:
    """The book over the platform's version and ``stored``, the tenant's."""
    return PromptBook(
        platform={PROMPT_KEY: PLATFORM_PROMPT},
        stored=stored,
        schemas={PROMPT_KEY: PromptDemonstrations},
    )


@dataclass(frozen=True)
class PromptDecisions:
    """The platform's `ApprovalDecisionGuard` for `sales.prompts`: the
    decider holds the stamp, is not the proposer, and the version still
    waits on this approval (`RuleDecisionGuard` with this registry)."""

    uow: SalesUnitOfWorkFactory
    book: PromptBook

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        await RuleDecisionGuard(REGISTRY, rule_work(self.uow), self.book).check(
            request, decision, context
        )


@dataclass(frozen=True)
class PromptSettlement:
    """Carries out a decided `sales.prompts` approval: the worker's handler
    for `PROMPTS_DECIDED` calls it with the decider's tenancy and identity."""

    uow: SalesUnitOfWorkFactory
    book: PromptBook
    clock: UtcClock
    ids: IdGenerator

    async def settle(self, approval_id: UUID, decider: AccessContext) -> RuleVersion:
        return await RuleVersionSettlement(
            REGISTRY, rule_work(self.uow), self.book, self.clock, self.ids
        ).settle(approval_id, decider)
