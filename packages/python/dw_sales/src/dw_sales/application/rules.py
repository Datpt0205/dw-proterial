"""A tenant's own versions of the Sales rules: proposed, approved, resolved
(ticket 19, G15, spec decision 14).

One deployment serves customers whose rules differ (a lead-time table, an LME
rule, a KPI target), and a customer's value arrives as a version of its own at
runtime, never as an edit to the checkout (`CLAUDE.md`, "Per-tenant
artifacts"). The platform layer is the file in ``configs/policies``; a
tenant's layer is a version a person proposed and a second person approved.

- **Proposed** by a holder of `sales.rules.propose` (PIC or head), validated by
  the key's own schema; the proposal opens a run-less platform approval,
  `sales.rules`, in its transaction, stamped with `sales.rules.approve` and
  naming the proposer as its maker (dw_sales ADR 0004, ticket 38).
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
(every artifact), and the hand-off copy (the inbox), since ticket 36.
Proposing any other key is refused (422): a stored version nothing reads would
look like a safeguard and be none (failure-modes #1).

Where a case stamps the version it used, a later read takes the stamp: the
order rules a case was checked under, the quote rules a quotation was opened
under (`quote_rules_at`), and the copy the files of one case version were
drawn with (`artifact_copy`), so a file drawn again is the file drawn before.
"""

from __future__ import annotations

import typing
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, StrEnum
from types import MappingProxyType
from typing import Any, Final, Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.overlay import TenantOverlay
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    decided_event_type,
)
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.artifact_content import (
    BravoUploadLayout,
    SalesDocumentCopy,
    SalesEmailCopy,
)
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.drafting import ArtifactCopy
from dw_sales.application.handoffs import HandoffCopy
from dw_sales.application.ports import SalesScope
from dw_sales.application.quotation import QuoteRules
from dw_sales.domain.kpi import SalesKpi
from dw_sales.domain.order_checks import OrderRules
from dw_sales.domain.pricing import SalesPricing

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_RESOURCE: Final = "sales_rule_version"

# The platform approval a version's proposal opens, and the event its decision
# is announced by. Under `sales.`, so the strict rule (a second person who is
# not the maker, and a written comment) holds for it as for every Sales one.
RULES_APPROVAL: Final = "sales.rules"
RULES_DECIDED: Final = decided_event_type(RULES_APPROVAL)
_RULES_REASON: Final = (
    "Phiên bản quy tắc chờ duyệt: Sales đề xuất, Trưởng bộ phận duyệt (ticket 38)"
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


type Policy = (
    OrderRules
    | SalesKpi
    | QuoteRules
    | SalesPricing
    | SalesEmailCopy
    | SalesDocumentCopy
    | BravoUploadLayout
    | HandoffCopy
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
    }
)
# The copy an artifact is drawn with, in the order `ArtifactCopy` takes it.
_ARTIFACT_COPY: Final = (RuleKey.EMAILS, RuleKey.DOCUMENTS, RuleKey.BRAVO_UPLOAD)
RuleStatus = Literal["proposed", "approved", "rejected", "superseded"]
Layer = Literal["platform", "tenant"]


class RuleVersion(BaseModel):
    """One version of one key a person of the tenant proposed, and what was
    decided about it. ``document`` is the whole policy, never a patch."""

    model_config = _FROZEN

    version_id: uuid.UUID
    key: RuleKey
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    document: Mapping[str, Any]
    status: RuleStatus
    proposed_by: uuid.UUID
    proposed_at: AwareDatetime
    decided_by: uuid.UUID | None = None
    decided_at: AwareDatetime | None = None
    comment: str | None = Field(default=None, max_length=500)
    # The `sales.rules` approval it is decided on; None on a version decided
    # before ticket 38 moved the decision onto the platform's approvals.
    approval_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _decided_by_another(self) -> Self:
        decided = self.decided_by is not None
        if (self.status == "proposed") == decided or decided != (self.decided_at is not None):
            raise ValueError("a decided version names who decided it and when")
        if self.decided_by is not None and self.decided_by == self.proposed_by:
            raise ValueError("the proposer of a version does not decide it")
        return self

    @property
    def ref(self) -> str:
        return f"{self.key.value}@{self.version}"


def read_over(schema: type[Policy], document: Mapping[str, Any], platform: Policy) -> Policy:
    """``document``, written under an earlier schema, read by today's.

    A field the document predates takes the value the platform's current
    version has: what the platform ships is what a tenant without its own
    version runs, so it is the default this deployment already stands behind.
    Only the schema's own shape is filled — its fields, at any depth, and the
    keys of a mapping over a closed set (a severity per finding code). A
    mapping of data (a customer's lead time, a template by name) is the
    version's own and is never topped up with the platform's entries.
    """
    base = platform.model_dump(mode="json", by_alias=True)
    return schema.model_validate(_predated(schema, document, base))


def _predated(
    model: type[BaseModel], document: Mapping[str, Any], base: Mapping[str, Any]
) -> dict[str, Any]:
    filled = dict(document)
    for name, spec in model.model_fields.items():
        key = spec.alias or name
        if key not in base:
            continue
        if key not in filled:
            filled[key] = base[key]
            continue
        mine, theirs = filled[key], base[key]
        if not (isinstance(mine, Mapping) and isinstance(theirs, Mapping)):
            continue
        if (nested := _model_in(spec.annotation)) is not None:
            filled[key] = _predated(nested, mine, theirs)
        elif _closed_keys(spec.annotation):
            filled[key] = {**theirs, **mine}
    return filled


def _model_in(annotation: Any) -> type[BaseModel] | None:
    for candidate in (annotation, *typing.get_args(annotation)):
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
    return None


def _closed_keys(annotation: Any) -> bool:
    """A mapping whose keys are an enum or a literal: every key is a field."""
    if typing.get_origin(annotation) not in (Mapping, dict):
        return False
    keys = typing.get_args(annotation)[0]
    return typing.get_origin(keys) is Literal or (isinstance(keys, type) and issubclass(keys, Enum))


class RuleVersionLookupPort(Protocol):
    """The tenant's stored versions, as resolution reads them: one short read
    bound to the scope's tenant (RLS), never another's."""

    async def approved(self, scope: SalesScope, key: RuleKey) -> RuleVersion | None: ...

    async def find(self, scope: SalesScope, key: RuleKey, version: str) -> RuleVersion | None: ...


class RuleVersionStorePort(Protocol):
    """The tenant's versions inside a unit of work."""

    async def list_all(self) -> Sequence[RuleVersion]:
        """Every version of every key, newest proposed first."""
        ...

    async def get(self, version_id: uuid.UUID) -> RuleVersion | None: ...

    async def add(self, version: RuleVersion) -> None:
        """A proposal. Refused with a conflict when the key already has the version."""
        ...

    async def decide(self, version: RuleVersion, *, superseding: uuid.UUID | None) -> None:
        """The decision on a proposal (refused with a conflict when it is no
        longer one), and the approved version it replaces, superseded."""
        ...


@dataclass(frozen=True, slots=True)
class Resolved:
    policy: Policy
    layer: Layer


@dataclass(frozen=True)
class TenantRuleBook:
    """The rules in force for a scope's tenant, and the ones a stamp names.

    Each reader asks through its own port, which a typed method here
    satisfies: `KpiPort`, `QuotePoliciesPort`, `ArtifactCopyPort` and
    `HandoffCopyPort`; `OrderRulesPort` through `RuleBookOrderRules`."""

    platform: Mapping[RuleKey, Policy]
    stored: RuleVersionLookupPort
    # Every platform version the checkout still ships, by ref, the current
    # ones included (`policy_files.load_sales_policies`): what a stamp made
    # before a release resolves to after it.
    released: Mapping[str, Policy] = field(default_factory=dict)

    def ships(self, key: RuleKey, ref: str) -> bool:
        """Whether ``ref`` is a number the platform layer has released."""
        return ref == self.platform[key].ref or ref in self.released

    def _read(self, version: RuleVersion) -> Policy:
        return read_over(OVERRIDABLE[version.key], version.document, self.platform[version.key])

    async def current(self, scope: SalesScope, key: RuleKey) -> Resolved:
        """The tenant's approved version, or the platform's: never sideways."""
        overlay: TenantOverlay[RuleKey, Resolved] = TenantOverlay()
        overlay.put(key, Resolved(self.platform[key], "platform"))
        own = await self.stored.approved(scope, key)
        if own is not None:
            overlay.put(key, Resolved(self._read(own), "tenant"), tenant_id=scope.tenant_id.value)
        resolved = overlay.get(key, tenant_id=scope.tenant_id.value)
        assert resolved is not None  # the platform layer is always put
        return resolved

    async def at(self, scope: SalesScope, key: RuleKey, ref: str) -> Policy | None:
        """The version a stamp names: one of the tenant's (approved now or
        since superseded), else one the platform released. None for a number
        neither holds.

        The tenant's is asked first: a tenant version takes a number the
        platform had not released, so where the platform ships that number
        later, every stamp of it on this tenant's cases still means the
        tenant's document."""
        policy_id, _, version = ref.partition("@")
        if policy_id != key.value:
            return None
        own = await self.stored.find(scope, key, version)
        if own is not None and own.status in ("approved", "superseded"):
            return self._read(own)
        platform = self.platform[key]
        return platform if ref == platform.ref else self.released.get(ref)

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
    the document only to whoever may propose (it can hold price rules)."""

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


def _view(version: RuleVersion) -> RuleVersionView:
    return RuleVersionView(
        version_id=version.version_id,
        key=version.key,
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
    )


class RuleApprovalAsked(BaseModel):
    """The approval's payload: ids, the key and the version, never the
    document (it can hold price rules, and the inbox serves the payload to
    whoever may decide it)."""

    model_config = _FROZEN

    approval_type: Literal["sales.rules"]
    required_scope: str
    version_id: uuid.UUID
    key: RuleKey
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    makers: tuple[uuid.UUID, ...]

    @classmethod
    def of(cls, version: RuleVersion) -> RuleApprovalAsked:
        return cls(
            approval_type="sales.rules",
            required_scope=SalesScopes.RULES_APPROVE.value,
            version_id=version.version_id,
            key=version.key,
            version=version.version,
            makers=(version.proposed_by,),
        )


# ------------------------------------------------------------- service --


@dataclass(frozen=True)
class SalesRulesService:
    """Propose, decide and list the tenant's own rule versions."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    book: TenantRuleBook
    clock: UtcClock
    ids: IdGenerator

    async def list(self, context: AccessContext) -> RulesInForceView:
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            versions = list(await work.rule_versions.list_all())
        in_force: dict[RuleKey, str] = {}
        layers: dict[RuleKey, Layer] = {}
        for key in OVERRIDABLE:
            resolved = await self.book.current(scope, key)
            in_force[key] = resolved.policy.ref
            layers[key] = resolved.layer
        return RulesInForceView(
            in_force=in_force,
            layers=layers,
            platform=[
                PlatformRuleView(key=key, ref=self.book.platform[key].ref) for key in OVERRIDABLE
            ],
            versions=[_view(v) for v in versions],
        )

    async def propose(
        self, context: AccessContext, key: RuleKey, document: Mapping[str, Any]
    ) -> RuleVersionView:
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        policy = _validated(key, document)
        if self.book.ships(key, policy.ref):
            raise ConflictError(
                "a tenant version needs a number the platform does not ship",
                details={"key": key.value, "rule": "platform_version_reused"},
            )
        version = RuleVersion(
            version_id=self.ids.new_uuid(),
            key=key,
            version=policy.ref.partition("@")[2],
            document=policy.model_dump(mode="json", by_alias=True),
            status="proposed",
            proposed_by=context.principal_id,
            proposed_at=self.clock.now(),
            approval_id=self.ids.new_uuid(),
        )
        approval_id = version.approval_id
        assert approval_id is not None
        async with self.uow(sales_scope(context)) as work:
            await work.approvals.add(
                ApprovalRequest(
                    id=approval_id,
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    approval_type=RULES_APPROVAL,
                    requested_by=UserId(context.principal_id),
                    reason=_RULES_REASON,
                    payload=RuleApprovalAsked.of(version).model_dump(mode="json"),
                    required_scope=SalesScopes.RULES_APPROVE.value,
                )
            )
            # After its approval: the row names it (`fk_rule_versions_approval_requests`).
            await work.rule_versions.add(version)
            await work.audit.append(
                _audit(self.ids, self.clock, context, "sales.rules.proposed", version)
            )
            await work.commit()
        return _view(version)


# ----------------------------------------------------------- the decision --


def _asked(request: ApprovalRequest) -> RuleApprovalAsked:
    """The approval as a proposal opened it, or a refusal: its payload
    unreadable, or stamped with a scope other than `sales.rules.approve`
    (the column, which the platform's decision enforced)."""
    refused = ConflictError(
        "the approval is not one a rules proposal opened",
        details={"approval_id": str(request.id)},
    )
    if request.approval_type != RULES_APPROVAL:
        raise refused
    try:
        asked = RuleApprovalAsked.model_validate(request.payload)
    except ValidationError:
        raise refused from None
    if request.required_scope != SalesScopes.RULES_APPROVE.value or (
        asked.required_scope != request.required_scope
    ):
        raise PermissionDeniedError(
            "a rule version is decided with sales.rules.approve",
            details={"approval_type": request.approval_type},
        )
    return asked


def _waiting(version: RuleVersion | None, request: ApprovalRequest) -> RuleVersion:
    """The version this approval was opened for, still waiting on it."""
    if version is None:
        raise NotFoundError("no such rule version", details={"approval_id": str(request.id)})
    if version.approval_id != request.id or version.status != "proposed":
        raise ConflictError(
            "phiên bản quy tắc không còn chờ quyết định này",
            details={
                "version_id": str(version.version_id),
                "status": version.status,
                "rule": "decision_stale",
            },
        )
    return version


def _unreleased(book: TenantRuleBook, version: RuleVersion) -> None:
    """Refuses approving a number the platform has released since it was
    proposed: a stamp of it would name two documents."""
    if book.ships(version.key, version.ref):
        raise ConflictError(
            "the platform now ships this version number",
            details={"version_id": str(version.version_id), "rule": "platform_version_reused"},
        )


@dataclass(frozen=True)
class RuleDecisions:
    """The platform's `ApprovalDecisionGuard` for `sales.rules`: the decision
    as the version would take it, refused or not, unwritten. Called after the
    decider's scope and the separation of duties, before it is recorded. A
    version's document never changes after it is proposed, so a decision
    names no subject version."""

    uow: SalesUnitOfWorkFactory
    book: TenantRuleBook

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        asked = _asked(request)
        async with self.uow(sales_scope(context)) as work:
            version = _waiting(await work.rule_versions.get(asked.version_id), request)
        if version.proposed_by == context.principal_id:
            raise ConflictError(
                "the proposer of a version does not decide it",
                details={"version_id": str(version.version_id), "rule": "maker_checker"},
            )
        if decision.approve:
            _unreleased(self.book, version)


@dataclass(frozen=True)
class RuleSettlement:
    """Carries out a decided `sales.rules` approval: the worker's handler for
    `RULES_DECIDED` calls it with the decider's tenancy and identity, from the
    event's envelope."""

    uow: SalesUnitOfWorkFactory
    book: TenantRuleBook
    clock: UtcClock
    ids: IdGenerator

    async def settle(self, approval_id: uuid.UUID, decider: AccessContext) -> RuleVersionView:
        """The decision on the version, as its decider. What was decided is
        read from the approval row, which the decision wrote, not from the
        event; the reason given is the decision's comment, stamped on the
        version as the rules list shows it (cut to the version's 500
        characters; the approval keeps it whole). Idempotent:
        a redelivery finds the version decided on this approval and writes
        nothing, and so does one that lost a race with another delivery (the
        worker and the demo seed both carry the same decision out). Raises the
        refusals the version makes (409, 404); none changes on a retry."""
        # Read as the decider holding the stamp the platform required of them
        # when they decided: nobody reaches here but through that decision.
        audience = ApprovalAudience(
            context=decider.model_copy(
                update={"scopes": frozenset({SalesScopes.RULES_APPROVE.value})}
            ),
            holds_decide=True,
        )
        try:
            return await self._settle(approval_id, decider, audience)
        except ConflictError:
            # Another delivery may have decided the version between this one's
            # read and its write (CI run 38545009082: the seed and the worker).
            async with self.uow(sales_scope(decider)) as work:
                request = await work.approvals.get(
                    approval_id, workspace_id=decider.workspace_id, audience=audience
                )
                stored = (
                    None
                    if request is None
                    else await work.rule_versions.get(_asked(request).version_id)
                )
            if stored is None or stored.approval_id != approval_id or stored.status == "proposed":
                raise
            return _view(stored)

    async def _settle(
        self, approval_id: uuid.UUID, decider: AccessContext, audience: ApprovalAudience
    ) -> RuleVersionView:
        async with self.uow(sales_scope(decider)) as work:
            request = await work.approvals.get(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            if request is None:
                raise NotFoundError(
                    "rules approval not found", details={"approval_id": str(approval_id)}
                )
            asked = _asked(request)
            stored = await work.rule_versions.get(asked.version_id)
            # Settled already, by an earlier delivery of the same event.
            if (
                stored is not None
                and stored.approval_id == request.id
                and stored.status != "proposed"
            ):
                return _view(stored)
            proposed = _waiting(stored, request)
            if request.status is ApprovalStatus.PENDING:
                raise ConflictError(
                    "the rules approval is not decided yet",
                    details={"approval_id": str(approval_id)},
                )
            approve = request.status is ApprovalStatus.APPROVED
            decision = await work.approvals.latest_decision(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            superseding = None
            if approve:
                _unreleased(self.book, proposed)
                current = next(
                    (
                        v
                        for v in await work.rule_versions.list_all()
                        if v.key == proposed.key and v.status == "approved"
                    ),
                    None,
                )
                superseding = current.version_id if current is not None else None
            decided = RuleVersion.model_validate(
                {
                    **proposed.model_dump(),
                    "status": "approved" if approve else "rejected",
                    "decided_by": decider.principal_id,
                    "decided_at": self.clock.now(),
                    "comment": _reason(decision),
                }
            )
            await work.rule_versions.decide(decided, superseding=superseding)
            action = "sales.rules.approved" if approve else "sales.rules.rejected"
            await work.audit.append(_audit(self.ids, self.clock, decider, action, decided))
            await work.commit()
        return _view(decided)


# What `rule_versions.comment` holds (`ck_rule_versions_comment`).
_COMMENT_LIMIT: Final = 500


def _reason(decision: ApprovalDecision | None) -> str | None:
    """The decider's comment as the version keeps it: None for none."""
    comment = "" if decision is None else decision.comment.strip()
    if not comment:
        return None
    if len(comment) <= _COMMENT_LIMIT:
        return comment
    return comment[: _COMMENT_LIMIT - 1] + "…"


def _audit(
    ids: IdGenerator, clock: UtcClock, context: AccessContext, action: str, version: RuleVersion
) -> AuditEvent:
    """The key, the version, its status and its approval: never the document."""
    details: dict[str, object] = {
        "key": version.key.value,
        "version": version.version,
        "status": version.status,
    }
    if version.approval_id is not None:
        details["approval_id"] = str(version.approval_id)
    return AuditEvent(
        id=ids.new_uuid(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action=action,
        resource_type=_RESOURCE,
        resource_id=str(version.version_id),
        occurred_at=clock.now(),
        details=details,
    )


def _validated(key: RuleKey, document: Mapping[str, Any]) -> Policy:
    """The document as the key's schema reads it; a refusal names where it
    failed, never a value of it."""
    try:
        policy = OVERRIDABLE[key].model_validate(dict(document))
    except ValidationError as exc:
        raise DomainError(
            "the document is not a valid version of this key",
            details={
                "key": key.value,
                "errors": [".".join(str(part) for part in e["loc"]) for e in exc.errors()][:20],
            },
        ) from None
    return policy
