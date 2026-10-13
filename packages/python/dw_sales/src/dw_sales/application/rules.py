"""A tenant's own versions of the Sales rules: proposed, approved, resolved
(ticket 19, G15, spec decision 14).

One deployment serves customers whose rules differ (a lead-time table, an LME
rule, a KPI target), and a customer's value arrives as a version of its own at
runtime, never as an edit to the checkout (`CLAUDE.md`, "Per-tenant
artifacts"). The platform layer is the file in ``configs/policies``; a
tenant's layer is a version a person proposed and a second person approved.

- **Proposed** by a holder of `sales.rules.propose` (PIC or head), validated by
  the key's own schema; **approved or rejected** by a holder of
  `sales.rules.approve` (the head), never by its proposer (maker/checker, as
  in the rest of DW1; `ck_rule_versions_checker_not_maker` holds it whatever
  writes the row). Each step is audited in its transaction.
- **Resolved** through `TenantOverlay`: the tenant's approved version where it
  has one, the platform's otherwise, never another tenant's. The tenant is the
  scope's, from the run or the verified access context; no request names it.
- **Stamped**: a case stamps ``id@version`` when it is checked, and a later
  check reads that version (`TenantRuleBook.at`), not whatever is in force.
  A tenant version takes a number the platform layer does not ship, so a
  stamp names one document, and the rules list says which layer it is.

A key a tenant may override is one whose readers resolve it per tenant
(`OVERRIDABLE`): order rules (intake, checks, layouts) and the KPI policy (the
overview). Proposing any other key is refused (422): a stored version nothing
reads would look like a safeguard and be none (failure-modes #1).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from dw_kernel.errors import ConflictError, DomainError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.overlay import TenantOverlay
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.domain.kpi import SalesKpi
from dw_sales.domain.order_checks import OrderRules

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_RESOURCE: Final = "sales_rule_version"


class RuleKey(StrEnum):
    """The Sales policies a tenant may hold its own version of."""

    ORDER_RULES = "sales_order_rules"
    KPI = "sales_kpi"


# Each key's schema: what a proposal is validated by and what is resolved.
OVERRIDABLE: Final[Mapping[RuleKey, type[OrderRules] | type[SalesKpi]]] = MappingProxyType(
    {RuleKey.ORDER_RULES: OrderRules, RuleKey.KPI: SalesKpi}
)

type Policy = OrderRules | SalesKpi
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

    def policy(self) -> Policy:
        return OVERRIDABLE[self.key].model_validate(dict(self.document))


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
    """The rules in force for a scope's tenant, and the ones a stamp names."""

    platform: Mapping[RuleKey, Policy]
    stored: RuleVersionLookupPort

    async def current(self, scope: SalesScope, key: RuleKey) -> Resolved:
        """The tenant's approved version, or the platform's: never sideways."""
        overlay: TenantOverlay[RuleKey, Resolved] = TenantOverlay()
        overlay.put(key, Resolved(self.platform[key], "platform"))
        own = await self.stored.approved(scope, key)
        if own is not None:
            overlay.put(key, Resolved(own.policy(), "tenant"), tenant_id=scope.tenant_id.value)
        resolved = overlay.get(key, tenant_id=scope.tenant_id.value)
        assert resolved is not None  # the platform layer is always put
        return resolved

    async def at(self, scope: SalesScope, key: RuleKey, ref: str) -> Policy | None:
        """The version a stamp names: the platform's, or one of the tenant's
        (approved now or since superseded). None for a platform version this
        process no longer ships."""
        platform = self.platform[key]
        if ref == platform.version:
            return platform
        policy_id, _, version = ref.partition("@")
        if policy_id != key.value:
            return None
        own = await self.stored.find(scope, key, version)
        if own is None or own.status not in ("approved", "superseded"):
            return None
        return own.policy()

    async def order_rules(self, scope: SalesScope) -> OrderRules:
        policy = (await self.current(scope, RuleKey.ORDER_RULES)).policy
        assert isinstance(policy, OrderRules)
        return policy

    async def kpi(self, scope: SalesScope) -> SalesKpi:
        policy = (await self.current(scope, RuleKey.KPI)).policy
        assert isinstance(policy, SalesKpi)
        return policy


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
    )


class RuleDecision(BaseModel):
    model_config = _FROZEN

    approve: bool
    comment: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def _a_rejection_says_why(self) -> Self:
        if not self.approve and self.comment is None:
            raise ValueError("a rejection says why")
        return self


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
            in_force[key] = resolved.policy.version
            layers[key] = resolved.layer
        return RulesInForceView(
            in_force=in_force,
            layers=layers,
            platform=[
                PlatformRuleView(key=key, ref=self.book.platform[key].version)
                for key in OVERRIDABLE
            ],
            versions=[_view(v) for v in versions],
        )

    async def propose(
        self, context: AccessContext, key: RuleKey, document: Mapping[str, Any]
    ) -> RuleVersionView:
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        policy = _validated(key, document)
        platform = self.book.platform[key]
        if policy.version == platform.version:
            raise ConflictError(
                "a tenant version needs a number the platform does not ship",
                details={"key": key.value, "rule": "platform_version_reused"},
            )
        version = RuleVersion(
            version_id=self.ids.new_uuid(),
            key=key,
            version=policy.policy_version,
            document=policy.model_dump(mode="json", by_alias=True),
            status="proposed",
            proposed_by=context.principal_id,
            proposed_at=self.clock.now(),
        )
        async with self.uow(sales_scope(context)) as work:
            await work.rule_versions.add(version)
            await work.audit.append(self._audit(context, "sales.rules.proposed", version))
            await work.commit()
        return _view(version)

    async def decide(
        self, context: AccessContext, version_id: uuid.UUID, decision: RuleDecision
    ) -> RuleVersionView:
        await self.gate.require(
            context, SalesScopes.RULES_APPROVE, resource_type=_RESOURCE, resource_id=str(version_id)
        )
        details: dict[str, object] = {"version_id": str(version_id)}
        async with self.uow(sales_scope(context)) as work:
            proposed = await work.rule_versions.get(version_id)
            if proposed is None:
                raise NotFoundError("no such rule version", details=details)
            if proposed.status != "proposed":
                raise ConflictError(
                    "the version is decided already",
                    details={**details, "status": proposed.status},
                )
            if proposed.proposed_by == context.principal_id:
                raise ConflictError(
                    "the proposer of a version does not decide it",
                    details={**details, "rule": "maker_checker"},
                )
            superseding = None
            if decision.approve:
                if proposed.ref == self.book.platform[proposed.key].version:
                    raise ConflictError(
                        "the platform now ships this version number",
                        details={**details, "rule": "platform_version_reused"},
                    )
                current = next(
                    (
                        v
                        for v in await work.rule_versions.list_all()
                        if v.key == proposed.key and v.status == "approved"
                    ),
                    None,
                )
                superseding = current.version_id if current is not None else None
            decided = proposed.model_copy(
                update={
                    "status": "approved" if decision.approve else "rejected",
                    "decided_by": context.principal_id,
                    "decided_at": self.clock.now(),
                    "comment": decision.comment,
                }
            )
            decided = RuleVersion.model_validate(decided.model_dump())
            await work.rule_versions.decide(decided, superseding=superseding)
            action = "sales.rules.approved" if decision.approve else "sales.rules.rejected"
            await work.audit.append(self._audit(context, action, decided))
            await work.commit()
        return _view(decided)

    def _audit(self, context: AccessContext, action: str, version: RuleVersion) -> AuditEvent:
        """The key, the version and its status: never the document."""
        return AuditEvent(
            id=self.ids.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            actor_id=UserId(context.principal_id),
            action=action,
            resource_type=_RESOURCE,
            resource_id=str(version.version_id),
            occurred_at=self.clock.now(),
            details={
                "key": version.key.value,
                "version": version.version,
                "status": version.status,
            },
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
