"""A tenant's own Sales rule versions in memory (ticket 19): the in-memory
store the evals and the unit tests run on, and the demo tenant's version where
a process has no database (`demo_order_rules`)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from dw_kernel.errors import ConflictError
from dw_sales.application.ports import SalesScope
from dw_sales.application.rules import Policy, RuleKey, RuleVersion, TenantRuleBook
from dw_sales.domain.order_checks import OrderRules

# Who proposed and approved a version seeded as the demo tenant's (fictional).
SEEDED_BY = uuid.UUID(int=0x19A)
SEEDED_APPROVER = uuid.UUID(int=0x19B)
_SEEDED_AT = datetime(2026, 10, 1, tzinfo=UTC)


class MemoryRuleVersions:
    """Implements `RuleVersionLookupPort`, and `RuleVersionStorePort` for one
    tenant through `for_tenant`, over every tenant's versions held apart."""

    def __init__(self) -> None:
        self._held: dict[uuid.UUID, dict[uuid.UUID, RuleVersion]] = {}

    def for_tenant(self, tenant_id: uuid.UUID) -> TenantRuleVersions:
        return TenantRuleVersions(self._held.setdefault(tenant_id, {}))

    async def approved(self, scope: SalesScope, key: RuleKey) -> RuleVersion | None:
        held = self._held.get(scope.tenant_id.value, {}).values()
        return next((v for v in held if v.key == key and v.status == "approved"), None)

    async def find(self, scope: SalesScope, key: RuleKey, version: str) -> RuleVersion | None:
        held = self._held.get(scope.tenant_id.value, {}).values()
        return next((v for v in held if v.key == key and v.version == version), None)

    def seed_approved(self, tenant_id: uuid.UUID, policy: Policy) -> None:
        """``policy`` as a tenant's version in force, as if proposed and
        approved by two people, the version of its key in force before it
        superseded: a fixture for a process with no database, never a route
        around them."""
        held = self._held.setdefault(tenant_id, {})
        key, _, version = policy.ref.partition("@")
        for version_id, before in held.items():
            if before.key == key and before.status == "approved":
                held[version_id] = before.model_copy(update={"status": "superseded"})
        version_id = uuid.UUID(int=0x19 + len(held))
        held[version_id] = RuleVersion(
            version_id=version_id,
            key=RuleKey(key),
            version=version,
            document=policy.model_dump(mode="json", by_alias=True),
            status="approved",
            proposed_by=SEEDED_BY,
            proposed_at=_SEEDED_AT,
            decided_by=SEEDED_APPROVER,
            decided_at=_SEEDED_AT,
        )


class TenantRuleVersions:
    """`RuleVersionStorePort` over one tenant's versions, written at once (no
    rollback in memory), refusing what the table refuses."""

    def __init__(self, held: dict[uuid.UUID, RuleVersion]) -> None:
        self._held = held

    async def list_all(self) -> Sequence[RuleVersion]:
        return sorted(
            self._held.values(), key=lambda v: (v.proposed_at, v.version_id), reverse=True
        )

    async def get(self, version_id: uuid.UUID) -> RuleVersion | None:
        return self._held.get(version_id)

    async def add(self, version: RuleVersion) -> None:
        if any(v.key == version.key and v.version == version.version for v in self._held.values()):
            raise ConflictError(
                "the sales store refused the change",
                details={
                    "version_id": str(version.version_id),
                    "constraint": "uq_rule_versions_tenant_id_key_version",
                },
            )
        self._held[version.version_id] = version

    async def decide(self, version: RuleVersion, *, superseding: uuid.UUID | None) -> None:
        stored = self._held.get(version.version_id)
        if stored is None or stored.status != "proposed":
            raise ConflictError(
                "the version is decided already", details={"version_id": str(version.version_id)}
            )
        if superseding is not None and superseding in self._held:
            self._held[superseding] = self._held[superseding].model_copy(
                update={"status": "superseded"}
            )
        self._held[version.version_id] = version


def platform_book(*policies: Policy) -> TenantRuleBook:
    """A rule book holding ``policies`` as the platform layer and no tenant's
    version yet: a test's or a single-purpose eval's, keyed by each policy's
    own ``ref``."""
    platform = {RuleKey(policy.ref.partition("@")[0]): policy for policy in policies}
    return TenantRuleBook(platform=platform, stored=MemoryRuleVersions())


def static_rule_book(
    platform: OrderRules, scope: SalesScope, own: OrderRules | None
) -> TenantRuleBook:
    """The platform's order rules, with ``own`` as ``scope``'s tenant's
    approved version when given."""
    versions = MemoryRuleVersions()
    if own is not None:
        versions.seed_approved(scope.tenant_id.value, own)
    return TenantRuleBook(platform={RuleKey.ORDER_RULES: platform}, stored=versions)
