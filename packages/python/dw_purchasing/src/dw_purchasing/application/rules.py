"""Which rules a call runs under, and how a tenant changes them.

`CLAUDE.md` "Per-tenant artifacts": the tenant comes from the verified access
context, never the request; resolution falls back to the platform, never
sideways to another tenant. A tenant's version is the platform's rule-version
engine's (`dw_platform.application.rule_versions`, ADR 0013/0014): proposed
by a holder of `purchasing.rules.propose`, decided by a holder of
`purchasing.rules.approve` who is not its proposer, carried out by the
worker. What is DW2's is registered here: the keys and their schemas, the
approval type (`purchasing.rules`, strict under `purchasing.`), the audit
names.

- **Who proposes**: the person who configures DW2 (`purchasing_configurer`)
  and the head (`purchasing_head`). The head also approves, so the head's own
  version applies at once, as a Sales head's does (`applied_directly`,
  audited `purchasing.rules.applied`); the configurer's waits for the head.
- **A stored version that no longer reads** under today's schema is refused,
  not skipped (409): falling back to the platform's rules would run a tenant
  under limits it replaced, quietly (failure-modes #7).
- **Stamped**: a case stamps the ref it was received under; the approval tier,
  the RFQ round and the Bravo layout are stamped where they are used, so a
  later change never rewrites a decision already taken.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, ValidationError

from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import (
    ContextScope,
    Layer,
    NoMoreChecks,
    RuleBook,
    RuleChecksPort,
    RuleDecisionGuard,
    RuleRegistry,
    RuleScope,
    RuleStatus,
    RuleVersion,
    RuleVersionEngine,
    RuleVersionSettlement,
)
from dw_platform.domain.approval import ApprovalRequest, decided_event_type
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.ports import PurchasingUnitOfWork
from dw_purchasing.domain.automation import POLICY_ID as AUTOMATION_ID
from dw_purchasing.domain.automation import PurchasingAutomation
from dw_purchasing.domain.rules import POLICY_ID, PurchasingRules

UNREADABLE: Final = "quy tắc mua hàng của công ty không đọc được: báo quản trị, chưa nhận yêu cầu"
_RESOURCE: Final = "purchasing_rule_version"

RULES_APPROVAL: Final = "purchasing.rules"
RULES_DECIDED: Final = decided_event_type(RULES_APPROVAL)
REGISTRY: Final = RuleRegistry(
    approval_type=RULES_APPROVAL,
    approve_scope=PurchasingScopes.RULES_APPROVE.value,
    resource_type=_RESOURCE,
    audit_prefix="purchasing.rules",
    reason="Quy tắc mua hàng chờ duyệt: người thứ hai duyệt, không phải người đề xuất",
)


class PurchasingRuleKey(StrEnum):
    """What a tenant may hold its own version of."""

    RULES = POLICY_ID
    # How far DW2 goes on its own, per step (`domain.automation`).
    AUTOMATION = AUTOMATION_ID


SCHEMAS: Final[Mapping[PurchasingRuleKey, type[BaseModel]]] = {
    PurchasingRuleKey.RULES: PurchasingRules,
    PurchasingRuleKey.AUTOMATION: PurchasingAutomation,
}


def _schemas() -> dict[Any, type[BaseModel]]:
    return dict(SCHEMAS)


@dataclass(frozen=True)
class PurchasingRuleBook(RuleBook):
    """The tenant's rules in force, and the version a stamp names."""

    schemas: Mapping[Any, type[BaseModel]] = field(default_factory=_schemas)

    async def resolve(self, context: AccessContext) -> PurchasingRules:
        try:
            resolved = await self.current(ContextScope.of(context), PurchasingRuleKey.RULES)
        except ValidationError as exc:
            raise ConflictError(UNREADABLE, details={"policy_id": POLICY_ID}) from exc
        assert isinstance(resolved.policy, PurchasingRules)
        return resolved.policy

    async def switches(self, context: AccessContext) -> PurchasingAutomation:
        return await self.switches_in_force(ContextScope.of(context))

    async def switches_in_force(self, scope: RuleScope) -> PurchasingAutomation:
        """The tenant's switches in force, else the platform's; a stored
        version that no longer reads stops what asks (409), never falls back
        to switches the tenant replaced."""
        try:
            resolved = await self.current(scope, PurchasingRuleKey.AUTOMATION)
        except ValidationError as exc:
            raise ConflictError(UNREADABLE, details={"policy_id": AUTOMATION_ID}) from exc
        assert isinstance(resolved.policy, PurchasingAutomation)
        return resolved.policy


def rule_key(key: str) -> PurchasingRuleKey:
    try:
        return PurchasingRuleKey(key)
    except ValueError:
        raise NotFoundError("no such rule key") from None


# --------------------------------------------------------------- views --


class PurchasingRuleVersionView(BaseModel):
    """A version as the settings page lists it."""

    model_config = ConfigDict(frozen=True)

    version_id: uuid.UUID
    key: PurchasingRuleKey
    version: str
    status: RuleStatus
    proposed_by: uuid.UUID
    proposed_at: datetime
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    comment: str | None
    document: Mapping[str, Any]
    approval_id: uuid.UUID | None
    applied_directly: bool


class PurchasingKeyInForce(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: PurchasingRuleKey
    ref: str
    layer: Layer
    # The version in force, whole: what a change starts from.
    document: Mapping[str, Any]
    platform_ref: str


class PurchasingRulesView(BaseModel):
    model_config = ConfigDict(frozen=True)

    keys: list[PurchasingKeyInForce]
    versions: list[PurchasingRuleVersionView]


def _view(version: RuleVersion) -> PurchasingRuleVersionView:
    return PurchasingRuleVersionView(
        version_id=version.version_id,
        key=PurchasingRuleKey(version.key),
        version=version.version,
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


@dataclass(frozen=True)
class _NoNames:
    """Who proposed a waiting version, by name: DW2 has no directory of its
    own yet, so the refusal names "another person" and the version."""

    async def names(self, context: AccessContext) -> Mapping[uuid.UUID, str]:
        return {}


async def unused_version(book: PurchasingRuleBook, scope: ContextScope, key: str, base: str) -> str:
    """The next patch number of ``base`` that neither the platform ships nor
    the tenant holds."""
    major, minor, patch = (int(part) for part in base.split("."))
    while True:
        patch += 1
        version = f"{major}.{minor}.{patch}"
        if not book.ships(key, f"{key}@{version}") and (
            await book.stored.find(scope, key, version) is None
        ):
            return version


@dataclass(frozen=True)
class PurchasingRulesService:
    """List, propose and read the schema of the tenant's rule versions."""

    uow: PurchasingUnitOfWork
    gate: Gate
    book: PurchasingRuleBook
    clock: UtcClock
    ids: IdGenerator
    # What a version meets beyond its schema: the switches' measurements.
    checks: RuleChecksPort = field(default_factory=NoMoreChecks)

    @property
    def _engine(self) -> RuleVersionEngine:
        return RuleVersionEngine(
            REGISTRY, self.uow, self.book, self.clock, self.ids, _NoNames(), self.checks
        )

    async def list(self, context: AccessContext) -> PurchasingRulesView:
        await self.gate.require(context, PurchasingScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        scope = ContextScope.of(context)
        keys = []
        for key in PurchasingRuleKey:
            resolved = await self.book.current(scope, key)
            keys.append(
                PurchasingKeyInForce(
                    key=key,
                    ref=resolved.policy.ref,
                    layer=resolved.layer,
                    document=resolved.policy.model_dump(mode="json", by_alias=True),
                    platform_ref=self.book.platform[key].ref,
                )
            )
        versions = await self._engine.list_all(context)
        return PurchasingRulesView(
            keys=keys, versions=[_view(v) for v in versions if v.key in set(PurchasingRuleKey)]
        )

    async def schema(self, context: AccessContext, key: str) -> dict[str, Any]:
        await self.gate.require(context, PurchasingScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        return SCHEMAS[rule_key(key)].model_json_schema(by_alias=True)

    async def propose(
        self, context: AccessContext, key: str, document: Mapping[str, Any]
    ) -> PurchasingRuleVersionView:
        """A version through the one door: the head's applies at once, the
        configurer's waits on a `purchasing.rules` approval."""
        await self.gate.require(context, PurchasingScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        rule = rule_key(key)
        if not {"policy_version", "version"} & document.keys():
            # A change made by a press (a switch) names no number: the next
            # one nobody has used, as a change in words gets. A number is the
            # platform's to give, never the page's.
            scope = ContextScope.of(context)
            base = (await self.book.current(scope, rule)).policy.model_dump(by_alias=True)
            document = {
                **document,
                "policy_version": await unused_version(
                    self.book, scope, rule.value, base["policy_version"]
                ),
            }
        version = await self._engine.propose(
            context,
            rule,
            document,
            applies_directly=self.gate.allows(context, PurchasingScopes.RULES_APPROVE),
        )
        return _view(version)


@dataclass(frozen=True)
class RuleDecisions:
    """The approval flow's guard for `purchasing.rules`."""

    uow: PurchasingUnitOfWork
    book: PurchasingRuleBook
    checks: RuleChecksPort = field(default_factory=NoMoreChecks)

    async def check(self, request: ApprovalRequest, decision: Any, context: AccessContext) -> None:
        await RuleDecisionGuard(REGISTRY, self.uow, self.book, self.checks).check(
            request, decision, context
        )


@dataclass(frozen=True)
class RuleSettlement:
    """The worker's handler for `RULES_DECIDED`."""

    uow: PurchasingUnitOfWork
    book: PurchasingRuleBook
    clock: UtcClock
    ids: IdGenerator
    checks: RuleChecksPort = field(default_factory=NoMoreChecks)

    async def settle(
        self, approval_id: uuid.UUID, decider: AccessContext
    ) -> PurchasingRuleVersionView:
        settled = await RuleVersionSettlement(
            REGISTRY, self.uow, self.book, self.clock, self.ids, self.checks
        ).settle(approval_id, decider)
        return _view(settled)


def released_book(rules: Any, switches: Any, stored: Any) -> PurchasingRuleBook:
    """The book over the platform's files (`PolicyFiles`, `SwitchFiles`) and
    the tenant's stored versions."""
    return PurchasingRuleBook(
        platform={
            PurchasingRuleKey.RULES: rules.current(),
            PurchasingRuleKey.AUTOMATION: switches.current(),
        },
        stored=stored,
        released={**rules.by_ref, **switches.by_ref},
    )
