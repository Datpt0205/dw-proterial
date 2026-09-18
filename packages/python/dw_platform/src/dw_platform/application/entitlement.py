"""Entitlement service: plan-level capability checks (implements ``EntitlementPort``)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from dw_kernel.errors import EntitlementDeniedError
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.entities import Plan

# Each plan's daily spend cap is half its theoretical worst case: the runs it
# grants times the highest per-run ceiling any model profile configures
# ($2.00, see configs/models/). Half, so the cap binds when a tenant's runs are
# unusually expensive while leaving ordinary mixed use — where cheap runs
# dominate — untouched. A cap at the worst case would never bind at all.
#
# Canonical POC plans; the seeded DB rows mirror these (system of record for
# billing integrations later — the catalog here is the runtime source). Only
# platform capabilities appear here; a bounded context adds its own worker
# feature when it lands.
DEFAULT_PLANS: dict[str, Plan] = {
    "basic": Plan(
        plan_id="basic",
        name="Basic",
        features=frozenset({"knowledge_search"}),
        quotas={"runs_per_day": 20, "spend_usd_per_day": 20},
    ),
    "professional": Plan(
        plan_id="professional",
        name="Professional",
        features=frozenset({"knowledge_search"}),
        quotas={"runs_per_day": 200, "spend_usd_per_day": 200},
    ),
    "enterprise": Plan(
        plan_id="enterprise",
        name="Enterprise",
        features=frozenset({"knowledge_search", "audit_export"}),
        quotas={"runs_per_day": 2000, "spend_usd_per_day": 2000},
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

    def spend_usd_per_day(self, plan_id: str) -> Decimal | None:
        """Satisfies ``dw_agent_runtime.ports.RunAllowancePort``.

        An unknown plan is refused outright, exactly as `runs_per_day` refuses
        it, and for the same reason: of the two ways a mistake here can end, an
        operator seeing a tenant stopped for a plan they just created is the one
        that gets fixed. Unlimited spend on an unpriced plan is the one nobody
        notices until the invoice.

        A plan that names no cap is unmetered — a real answer for an internal
        tenant, and not the same as a cap of zero.
        """
        plan = self.plans.get(plan_id)
        if plan is None:
            return Decimal(0)
        cap = plan.quotas.get("spend_usd_per_day")
        return None if cap is None else Decimal(str(cap))

    async def require_feature(self, context: AccessContext, feature: str) -> None:
        if self.has_feature(context, feature):
            return
        raise EntitlementDeniedError(
            "plan does not include this capability",
            details={"feature": feature, "plan_id": context.plan_id},
        )
