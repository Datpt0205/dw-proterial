"""Entitlement service: plan-level capability checks (implements ``EntitlementPort``)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dw_kernel.errors import EntitlementDeniedError
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.entities import Plan

# Canonical POC plans; the seeded DB rows mirror these (system of record for
# billing integrations later — the catalog here is the runtime source). Only
# platform capabilities appear here; a bounded context adds its own worker
# feature when it lands.
DEFAULT_PLANS: dict[str, Plan] = {
    "basic": Plan(
        plan_id="basic",
        name="Basic",
        features=frozenset({"knowledge_search"}),
        quotas={"runs_per_day": 20},
    ),
    "professional": Plan(
        plan_id="professional",
        name="Professional",
        features=frozenset({"knowledge_search"}),
        quotas={"runs_per_day": 200},
    ),
    "enterprise": Plan(
        plan_id="enterprise",
        name="Enterprise",
        features=frozenset({"knowledge_search", "audit_export"}),
        quotas={"runs_per_day": 2000},
    ),
}


@dataclass(frozen=True)
class PlanEntitlementService:
    """Checks features against the plan catalog + per-tenant feature flags."""

    plans: Mapping[str, Plan]

    def has_feature(self, context: AccessContext, feature: str) -> bool:
        if context.has_feature(feature):  # per-tenant override, resolved at build
            return True
        plan = self.plans.get(context.plan_id)
        return plan is not None and feature in plan.features

    def runs_per_day(self, plan_id: str) -> int | None:
        """Satisfies ``dw_agent_runtime.ports.RunAllowancePort``.

        An unknown plan is refused outright rather than treated as unlimited.
        It should be unreachable — `entitlements.plan_id` is a foreign key into
        `platform.plans`, so a tenant cannot hold a plan the database has never
        heard of — and the one way to get here is a plan added to the database
        without being added to `DEFAULT_PLANS`. Of the two ways that can end,
        an operator seeing runs refused for a plan they just created is the
        one that gets fixed; unlimited runs on an unpriced plan is the one
        nobody notices until the invoice.
        """
        plan = self.plans.get(plan_id)
        if plan is None:
            return 0
        return plan.quotas.get("runs_per_day")

    async def require_feature(self, context: AccessContext, feature: str) -> None:
        if self.has_feature(context, feature):
            return
        raise EntitlementDeniedError(
            "plan does not include this capability",
            details={"feature": feature, "plan_id": context.plan_id},
        )
