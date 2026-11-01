"""A tenant's own versions of the Sales rules: proposed, approved, resolved
(ticket 19, G15, spec decision 14).

One deployment serves customers whose rules differ (a lead-time table, an LME
rule, a KPI target), and a customer's value arrives as a version of its own at
runtime, never as an edit to the checkout (`CLAUDE.md`, "Per-tenant
artifacts"). The platform layer is the file in ``configs/policies``; a
tenant's layer is a version a person proposed and a second person approved.

- **Proposed** by a holder of `sales.rules.propose`: the Sales head, or the
  admin through the set `sales_rules_editor` (2026-10-28: a PIC works to the
  settings and proposes nothing), validated by the key's own schema; a
  key that holds prices or price policy (`PRICE_BEARING`) also asks for
  `sales.price.read`. The proposal opens a run-less platform approval,
  `sales.rules`, in its transaction, stamped with `sales.rules.approve` and
  naming the proposer as its maker (dw_sales ADR 0004, ticket 38).
- **One waiting per key** (Đạt, 2026-10-22): a version is the whole
  document and approving one supersedes what is in force, so two proposals
  waiting side by side, started from one version, would each undo the other
  when both are approved. While one waits, another on the same key, from any
  workspace of the tenant, is refused (409, `ONE_OPEN_PROPOSAL`) naming the
  waiting version, who proposed it and when; `uq_rule_versions_one_proposed`
  holds it whatever writes the row. A decision frees the key, and so does a
  settlement that cannot apply an approved number (`RuleSettlement`). What
  it does not refuse is a proposal started from a version superseded since:
  a proposal records no base, and the head reads its diff against the
  version in force (`rule-approval.tsx`).
- **Applied directly** when the proposer is the head (holds
  `sales.rules.approve`; Đạt, 2026-10-28): no approval is opened, the version
  is in force at once, decided by its proposer, `applied_directly`, audited
  `sales.rules.applied`. A proposal waiting on the key is decided first.
- **Approved or rejected** on that approval by a holder of the stamp (the
  head), never by its proposer: `sales.` is strict, `RuleDecisions.check` (the
  decision guard) refuses what the version would refuse before it is
  recorded, and `ck_rule_versions_checker_not_maker` holds it whatever writes
  the row. The worker carries out `sales.rules.decided` through
  `RuleSettlement.settle`. Each step is audited in its transaction.
- **Resolved** through `TenantOverlay`: the tenant's approved version where it
  has one, the platform's otherwise, never another tenant's. The tenant is the
  scope's, from the run or the verified access context; no request names it.
- **Stamped**: a case stamps ``id@version`` when it is checked, and a later
  check reads that version (`TenantRuleBook.at`), not whatever is in force.
  A tenant version takes a number the platform layer does not ship, so a
  stamp names one document, and the rules list says which layer it is.
- **Still read after a deploy**: every platform version the checkout ever
  released stays loadable (`released`), and a version written before a field
  of its schema existed reads that field as the platform's current version
  has it (`read_over`), so a case keeps its rules across a release.

A key a tenant may override is one whose readers resolve it per tenant
(`OVERRIDABLE`): order rules (intake, checks, layouts) and the KPI policy (the
overview), since ticket 19; the quote rules and the pricing policy (the
quotation flow), the e-mail and document copy and the Bravo upload template
(every artifact), and the hand-off copy (the inbox), since ticket 36; the
follow-ups and the morning brief (the worker's `sales_followups` lane), since
ticket 42.
Proposing any other key is refused (422): a stored version nothing reads would
look like a safeguard and be none (failure-modes #1).

The engine itself (one waiting per key, never a shipped number, the
decision guard, the settlement, resolution through `TenantOverlay`) is the
platform's since ADR 0013's lift (`dw_platform.application.rule_versions`),
and so is the table (`platform.rule_versions`); what stays here is what is
Sales': the keys and their schemas, who may read a price-bearing key, the
model-step refusal, the typed reads and the views.

Where a case stamps the version it used, a later read takes the stamp: the
order rules a case was checked under, the quote rules a quotation was opened
under (`quote_rules_at`), and the copy the files of one case version were
drawn with (`artifact_copy`), so a file drawn again is the file drawn before.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import (
    ONE_OPEN_PROPOSAL,
    Layer,
    Resolved,
    RuleBook,
    RuleDecisionGuard,
    RuleRegistry,
    RuleScope,
    RuleStatus,
    RuleVersion,
    RuleVersionEngine,
    RuleVersionLookupPort,
    RuleVersionSettlement,
    RuleVersionStorePort,
    RuleWork,
    Unready,
    read_over,
)
from dw_platform.domain.approval import ApprovalRequest, decided_event_type
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.artifact_content import (
    BravoUploadLayout,
    SalesDocumentCopy,
    SalesEmailCopy,
)
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.drafting import ArtifactCopy
from dw_sales.application.handoffs import HandoffCopy
from dw_sales.application.model_readiness import (
    MODEL_BAR_UNMET,
    ModelReadiness,
    StepReadiness,
    refusal,
)
from dw_sales.application.ports import MemberDirectoryPort, SalesScope
from dw_sales.application.quotation import QuoteRules
from dw_sales.domain.followups import SalesFollowups
from dw_sales.domain.kpi import SalesKpi
from dw_sales.domain.order_checks import OrderRules
from dw_sales.domain.pricing import SalesPricing

# What other Sales modules read from here, as the platform names them.
__all__ = [
    "ONE_OPEN_PROPOSAL",
    "Layer",
    "Resolved",
    "RuleStatus",
    "RuleVersion",
    "RuleVersionLookupPort",
    "RuleVersionStorePort",
    "read_over",
]

_RESOURCE: Final = "sales_rule_version"

# The platform approval a version's proposal opens, and the event its decision
# is announced by. Under `sales.`, so the strict rule (a second person who is
# not the maker, and a written comment) holds for it as for every Sales one.
RULES_APPROVAL: Final = "sales.rules"
RULES_DECIDED: Final = decided_event_type(RULES_APPROVAL)
_RULES_REASON: Final = (
    "Phiên bản quy tắc chờ duyệt: Trưởng bộ phận duyệt, không phải người đề xuất (ticket 38)"
)
# What Sales registers with the platform's rule-version engine.
REGISTRY: Final = RuleRegistry(
    approval_type=RULES_APPROVAL,
    approve_scope=SalesScopes.RULES_APPROVE.value,
    resource_type=_RESOURCE,
    audit_prefix="sales.rules",
    reason=_RULES_REASON,
)


class RuleKey(StrEnum):
    """The Sales policies and copy a tenant may hold its own version of."""

    ORDER_RULES = "sales_order_rules"
    KPI = "sales_kpi"
    QUOTE_RULES = "sales_quote_rules"
    PRICING = "sales_pricing"
    EMAILS = "sales_emails"
    DOCUMENTS = "sales_documents"
    BRAVO_UPLOAD = "sales_bravo_upload"
    HANDOFFS = "sales_handoffs"
    FOLLOWUPS = "sales_followups"


type Policy = (
    OrderRules
    | SalesKpi
    | QuoteRules
    | SalesPricing
    | SalesEmailCopy
    | SalesDocumentCopy
    | BravoUploadLayout
    | HandoffCopy
    | SalesFollowups
)

# Each key's schema: what a proposal is validated by and what is resolved.
OVERRIDABLE: Final[Mapping[RuleKey, type[Policy]]] = MappingProxyType(
    {
        RuleKey.ORDER_RULES: OrderRules,
        RuleKey.KPI: SalesKpi,
        RuleKey.QUOTE_RULES: QuoteRules,
        RuleKey.PRICING: SalesPricing,
        RuleKey.EMAILS: SalesEmailCopy,
        RuleKey.DOCUMENTS: SalesDocumentCopy,
        RuleKey.BRAVO_UPLOAD: BravoUploadLayout,
        RuleKey.HANDOFFS: HandoffCopy,
        RuleKey.FOLLOWUPS: SalesFollowups,
    }
)
# The keys a version may be drafted for from the company's own file ("Tạo từ
# tệp mẫu", `rule_drafts`): the Bravo upload template now, the copy in phase 2.
DRAFTABLE: Final = frozenset({RuleKey.BRAVO_UPLOAD})
# The keys whose documents hold prices or price policy: the pricing inputs
# (copper adders, the floor, freight), the quote rules (the reference price
# band, the copper basis) and the order rules (`price.relative_tolerance`, the
# LME rule, which ADR 0003 names confidential). Reading, starting from or
# proposing one also asks for `sales.price.read` (dw_sales ADR 0003 §2), so a
# proposer without it (tenant IT, whom `sod_sales_price_vs_member_admin` keeps
# from it) is not shown them at all. A key added to `RuleKey` fails
# `test_rules.py` until someone decides whether it belongs here.
PRICE_BEARING: Final = frozenset({RuleKey.ORDER_RULES, RuleKey.QUOTE_RULES, RuleKey.PRICING})
# The copy an artifact is drawn with, in the order `ArtifactCopy` takes it.
_ARTIFACT_COPY: Final = (RuleKey.EMAILS, RuleKey.DOCUMENTS, RuleKey.BRAVO_UPLOAD)


def _sales_schemas() -> dict[Any, type[BaseModel]]:
    return dict(OVERRIDABLE)


@dataclass(frozen=True)
class TenantRuleBook(RuleBook):
    """The rules in force for a scope's tenant, and the ones a stamp names.

    Each reader asks through its own port, which a typed method here
    satisfies: `KpiPort`, `QuotePoliciesPort`, `ArtifactCopyPort` and
    `HandoffCopyPort` and `FollowupPolicyPort`; `OrderRulesPort` through
    `RuleBookOrderRules`."""

    schemas: Mapping[Any, type[BaseModel]] = field(default_factory=_sales_schemas)

    async def order_rules(self, scope: SalesScope) -> OrderRules:
        policy = (await self.current(scope, RuleKey.ORDER_RULES)).policy
        assert isinstance(policy, OrderRules)
        return policy

    async def kpi(self, scope: SalesScope) -> SalesKpi:
        policy = (await self.current(scope, RuleKey.KPI)).policy
        assert isinstance(policy, SalesKpi)
        return policy

    async def quote_rules(self, scope: SalesScope) -> QuoteRules:
        policy = (await self.current(scope, RuleKey.QUOTE_RULES)).policy
        assert isinstance(policy, QuoteRules)
        return policy

    async def quote_rules_at(self, scope: SalesScope, ref: str) -> QuoteRules | None:
        policy = await self.at(scope, RuleKey.QUOTE_RULES, ref)
        return policy if isinstance(policy, QuoteRules) else None

    async def pricing(self, scope: SalesScope) -> SalesPricing:
        policy = (await self.current(scope, RuleKey.PRICING)).policy
        assert isinstance(policy, SalesPricing)
        return policy

    async def handoff_copy(self, scope: SalesScope) -> HandoffCopy:
        policy = (await self.current(scope, RuleKey.HANDOFFS)).policy
        assert isinstance(policy, HandoffCopy)
        return policy

    async def followups(self, scope: SalesScope) -> SalesFollowups:
        policy = (await self.current(scope, RuleKey.FOLLOWUPS)).policy
        assert isinstance(policy, SalesFollowups)
        return policy

    async def artifact_copy(self, scope: SalesScope, stamps: Sequence[str]) -> ArtifactCopy:
        """What an artifact is drawn with: each copy at the version ``stamps``
        name (the template refs of the files already drawn at the case's
        version, the first that names that copy), else the tenant's current
        one; Design's mailboxes from the tenant's current quote rules, which
        the reply check reads too. A stamp this process no longer holds is
        refused: a file drawn again must be the file drawn before."""
        found: dict[RuleKey, Policy] = {}
        named = [_copy_ref(stamp) for stamp in stamps]
        for key in _ARTIFACT_COPY:
            stamped = next((ref for ref in named if ref.startswith(f"{key.value}@")), None)
            if stamped is None:
                found[key] = (await self.current(scope, key)).policy
                continue
            policy = await self.at(scope, key, stamped)
            if policy is None:
                raise ConflictError(
                    "mẫu của các tệp đã tạo ở phiên bản hồ sơ này không còn",
                    details={"copy": stamped, "reason": "template_version_gone"},
                )
            found[key] = policy
        emails, documents, upload = (found[key] for key in _ARTIFACT_COPY)
        assert isinstance(emails, SalesEmailCopy)
        assert isinstance(documents, SalesDocumentCopy)
        assert isinstance(upload, BravoUploadLayout)
        return ArtifactCopy(
            emails=emails,
            documents=documents,
            upload=upload,
            design_mailboxes=(await self.quote_rules(scope)).design_mailboxes,
        )


def _copy_ref(template_ref: str) -> str:
    """``sales_emails.confirmation_draft.vi@1.2.0`` as the copy it names,
    ``sales_emails@1.2.0``; an upload file's ref names its template already."""
    name, _, version = template_ref.rpartition("@")
    return f"{name.split('.', 1)[0]}@{version}"


@dataclass(frozen=True)
class RuleBookOrderRules:
    """Implements `OrderRulesPort` with the tenant's rule book."""

    book: TenantRuleBook

    async def rules(self, scope: SalesScope) -> OrderRules:
        return await self.book.order_rules(scope)

    async def rules_at(self, scope: SalesScope, ref: str) -> OrderRules | None:
        policy = await self.book.at(scope, RuleKey.ORDER_RULES, ref)
        return policy if isinstance(policy, OrderRules) else None


# --------------------------------------------------------------- views --


class RuleVersionView(BaseModel):
    """A version as the rules list shows it: who proposed and decided it, and
    the document only to whoever may propose, and a price-bearing key's only
    to whoever may also read prices."""

    model_config = ConfigDict(frozen=True)

    version_id: uuid.UUID
    key: RuleKey
    version: str
    ref: str
    layer: Layer
    status: RuleStatus
    proposed_by: uuid.UUID
    proposed_at: datetime
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    comment: str | None
    document: Mapping[str, Any]
    # The platform approval it is decided on (`POST /approvals/{id}/decisions`).
    approval_id: uuid.UUID | None
    # Applied by the head who wrote it, with no approval.
    applied_directly: bool = False


class PlatformRuleView(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: RuleKey
    ref: str


class RulesInForceView(BaseModel):
    """What applies to the tenant now, per key, and every version it holds."""

    model_config = ConfigDict(frozen=True)

    in_force: dict[RuleKey, str]
    layers: dict[RuleKey, Layer]
    platform: list[PlatformRuleView]
    versions: list[RuleVersionView]
    # The keys a version may be drafted for from the company's own file.
    draftable: list[RuleKey]


class RuleSchemaView(BaseModel):
    """What the rules editor draws one key's form from: the JSON Schema a
    proposal of it is validated by (ticket 40). The schema is the key's own
    model's, never a copy, so a field added to the model reaches the form."""

    model_config = ConfigDict(frozen=True)

    key: RuleKey
    json_schema: dict[str, Any]


class PlatformDocumentView(BaseModel):
    """One version of a key the platform released, whole: what a proposal may
    start from and what a diff compares with while the platform's applies."""

    model_config = ConfigDict(frozen=True)

    key: RuleKey
    ref: str
    version: str
    # What the platform ships now, as opposed to a version it released before.
    current: bool
    document: Mapping[str, Any]


def readable(gate: Gate, context: AccessContext, key: RuleKey) -> bool:
    """Whether ``context`` may read ``key``'s documents: a price-bearing key
    also asks for `sales.price.read` (dw_sales ADR 0003 §2). Where it says no,
    the key is absent from what is served, not empty."""
    return key not in PRICE_BEARING or gate.allows(context, SalesScopes.PRICE_READ)


def rule_schema(key: RuleKey) -> dict[str, Any]:
    """The JSON Schema of ``key``'s documents, as a proposal is validated."""
    return OVERRIDABLE[key].model_json_schema(by_alias=True)


def rule_key(key: str) -> RuleKey:
    """``key`` as a key a tenant may override, or not found."""
    try:
        return RuleKey(key)
    except ValueError:
        raise NotFoundError("no such rule key") from None


def _view(version: RuleVersion) -> RuleVersionView:
    return RuleVersionView(
        version_id=version.version_id,
        key=RuleKey(version.key),
        version=version.version,
        ref=version.ref,
        layer="tenant",
        status=version.status,
        proposed_by=version.proposed_by,
        proposed_at=version.proposed_at,
        decided_by=version.decided_by,
        decided_at=version.decided_at,
        comment=version.comment,
        document=version.document,
        approval_id=version.approval_id,
        applied_directly=version.applied_directly,
    )


# ------------------------------------------------- what the engine is given --


def _work(
    uow: SalesUnitOfWorkFactory,
) -> Callable[[AccessContext], AbstractAsyncContextManager[RuleWork]]:
    """The Sales unit of work as the engine opens it: from the verified
    context, as every Sales service scopes one."""

    def opened(context: AccessContext) -> AbstractAsyncContextManager[RuleWork]:
        return uow(sales_scope(context))

    return opened


@dataclass(frozen=True)
class _Names:
    """Implements `ProposerNamesPort` with the member directory."""

    directory: MemberDirectoryPort

    async def names(self, context: AccessContext) -> Mapping[uuid.UUID, str]:
        return {m.user_id: m.display_name for m in await self.directory.list_members(context)}


# Why an approved version was not applied: a model step it turns on had no
# passing measurement for the model and prompt it runs on when it was carried
# out (dw_sales ADR 0005, addendum of 2026-10-23).
_MODEL_BAR_UNMET_COMMENT: Final = (
    "Đã được duyệt nhưng không áp dụng: bước có mô hình mà phiên bản này bật ({steps})"
    " chưa có lần đo đạt ngưỡng trên mô hình và lời nhắc đang dùng. Đo lại rồi đề xuất lại."
)


@dataclass(frozen=True)
class SalesRuleChecks:
    """Implements `RuleChecksPort`: a version of the order rules may not
    turn on a model step whose live eval has not met its bar for the model
    and prompt it runs on now (dw_sales ADR 0005, addendum of 2026-10-23)."""

    book: TenantRuleBook
    readiness: ModelReadiness

    async def unready(self, scope: RuleScope, key: str, policy: BaseModel) -> Unready | None:
        steps = await model_steps_unready(
            self.readiness, self.book, SalesScope(scope.tenant_id, scope.workspace_id), policy
        )
        if not steps:
            return None
        return Unready(
            error=refusal(steps),
            rule=MODEL_BAR_UNMET,
            comment=_MODEL_BAR_UNMET_COMMENT.format(steps=", ".join(r.step.value for r in steps)),
        )


async def model_steps_unready(
    readiness: ModelReadiness, book: TenantRuleBook, scope: SalesScope, policy: BaseModel
) -> list[StepReadiness]:
    """Why a version of the order rules may not take effect: the model steps
    it turns on (on in it, off in the version in force) whose live eval has
    not met the bar for the model and prompt each runs on now. None for any
    other key, and for a version that turns none on."""
    if not isinstance(policy, OrderRules):
        return []
    return await readiness.unready(scope, policy, await book.order_rules(scope))


# ------------------------------------------------------------- service --


@dataclass(frozen=True)
class SalesRulesService:
    """Propose, decide and list the tenant's own rule versions."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    book: TenantRuleBook
    clock: UtcClock
    ids: IdGenerator
    # Who proposed the version a refused second proposal waits behind, by name.
    directory: MemberDirectoryPort
    # Whether a model step a version turns on has met its bar (dw_sales ADR
    # 0005, addendum of 2026-10-23): a version that turns on one that has not
    # is refused when it is proposed, decided and carried out.
    readiness: ModelReadiness

    @property
    def _engine(self) -> RuleVersionEngine:
        return RuleVersionEngine(
            REGISTRY,
            _work(self.uow),
            self.book,
            self.clock,
            self.ids,
            _Names(self.directory),
            SalesRuleChecks(self.book, self.readiness),
        )

    async def list(self, context: AccessContext) -> RulesInForceView:
        """Every key the caller may read, and the tenant's versions of them:
        a price-bearing key is absent, not empty, for a caller without
        `sales.price.read`."""
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        scope = sales_scope(context)
        keys = [key for key in OVERRIDABLE if self._readable(context, key)]
        versions = [v for v in await self._engine.list_all(context) if v.key in keys]
        in_force: dict[RuleKey, str] = {}
        layers: dict[RuleKey, Layer] = {}
        for key in keys:
            resolved = await self.book.current(scope, key)
            in_force[key] = resolved.policy.ref
            layers[key] = resolved.layer
        return RulesInForceView(
            in_force=in_force,
            layers=layers,
            platform=[PlatformRuleView(key=key, ref=self.book.platform[key].ref) for key in keys],
            versions=[_view(v) for v in versions],
            draftable=sorted(DRAFTABLE),
        )

    async def schema(self, context: AccessContext, key: str) -> RuleSchemaView:
        """The key's JSON Schema, to whoever may propose a version of it."""
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        rule = rule_key(key)
        await self._require_readable(context, rule)
        return RuleSchemaView(key=rule, json_schema=rule_schema(rule))

    async def platform_documents(
        self, context: AccessContext, key: str
    ) -> Sequence[PlatformDocumentView]:
        """Every version of the key the platform released, newest first, to
        whoever may propose it (a price-bearing key's to whoever may also
        read prices, as the tenant's own versions of it are)."""
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        rule = rule_key(key)
        await self._require_readable(context, rule)
        current = self.book.platform[rule].ref
        return [
            PlatformDocumentView(
                key=rule,
                ref=ref,
                version=ref.partition("@")[2],
                current=ref == current,
                document=policy.model_dump(mode="json", by_alias=True),
            )
            for ref, policy in self.book.platform_versions(rule)
        ]

    async def propose(
        self, context: AccessContext, key: RuleKey, document: Mapping[str, Any]
    ) -> RuleVersionView:
        """A version through the one door: the head's applies at once (Đạt,
        2026-10-28), anyone else's waits on a `sales.rules` approval."""
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        await self._require_readable(context, key)
        version = await self._engine.propose(
            context,
            key,
            document,
            applies_directly=self.gate.allows(context, SalesScopes.RULES_APPROVE),
        )
        return _view(version)

    def _readable(self, context: AccessContext, key: RuleKey) -> bool:
        return readable(self.gate, context, key)

    async def _require_readable(self, context: AccessContext, key: RuleKey) -> None:
        """403 naming `sales.price.read` for a key `_readable` refuses, the way
        the gate refuses any scope."""
        if not self._readable(context, key):
            await self.gate.require(
                context, SalesScopes.PRICE_READ, resource_type=_RESOURCE, resource_id=key.value
            )


# ----------------------------------------------------------- the decision --


@dataclass(frozen=True)
class RuleDecisions:
    """The platform's `ApprovalDecisionGuard` for `sales.rules`
    (`RuleDecisionGuard` with Sales' registry and checks)."""

    uow: SalesUnitOfWorkFactory
    book: TenantRuleBook
    readiness: ModelReadiness

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        await RuleDecisionGuard(
            REGISTRY, _work(self.uow), self.book, SalesRuleChecks(self.book, self.readiness)
        ).check(request, decision, context)


@dataclass(frozen=True)
class RuleSettlement:
    """Carries out a decided `sales.rules` approval: the worker's handler for
    `RULES_DECIDED` calls it with the decider's tenancy and identity, from the
    event's envelope (`RuleVersionSettlement` with Sales' registry)."""

    uow: SalesUnitOfWorkFactory
    book: TenantRuleBook
    clock: UtcClock
    ids: IdGenerator
    readiness: ModelReadiness

    async def settle(self, approval_id: uuid.UUID, decider: AccessContext) -> RuleVersionView:
        settled = await RuleVersionSettlement(
            REGISTRY,
            _work(self.uow),
            self.book,
            self.clock,
            self.ids,
            SalesRuleChecks(self.book, self.readiness),
        ).settle(approval_id, decider)
        return _view(settled)
