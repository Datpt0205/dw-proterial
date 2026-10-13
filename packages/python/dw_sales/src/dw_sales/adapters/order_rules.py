"""`OrderRulesPort` over the versioned policy file in ``configs/policies``."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from pathlib import Path

import yaml

from dw_kernel.overlay import TenantOverlay
from dw_sales.application.ports import SalesScope
from dw_sales.domain.order_checks import OrderRules


def load_order_rules(path: Path) -> OrderRules:
    """The rules in ``path``, refused when invalid or named for another version.

    The file name and the content both state the version, and the release
    manifest records the content's: a name that disagrees is a file somebody
    edited without bumping one of the two.
    """
    rules = OrderRules.model_validate(yaml.safe_load(path.read_bytes()))
    if path.name != f"{rules.policy_id}@{rules.policy_version}.yaml":
        raise ValueError(f"{path.name} holds {rules.version}")
    return rules


class PlatformOrderRules:
    """Implements `OrderRulesPort` with the platform's rules for every tenant.

    The platform layer of the per-tenant lookup: what ships in ``configs/``.
    A tenant's own version is stored through the platform's policy overrides
    and resolved by the adapter that wraps this one when a tenant needs it.
    """

    def __init__(self, rules: OrderRules) -> None:
        self._rules = rules

    async def rules(self, scope: SalesScope) -> OrderRules:
        return self._rules


class TenantOrderRules:
    """Implements `OrderRulesPort` with a tenant layer over the platform's.

    A tenant's own version where it has one, the platform's otherwise, and
    never another tenant's (`TenantOverlay`). The tenant comes from the scope
    the service resolved from the verified access context, never from a
    request. A tenant version must carry its own version number: the case
    stamps ``id@version``, and two documents under one stamp would make the
    stamp say nothing about which was applied.

    Today the tenant layer holds what a composition root hands it (the demo
    tenant's version in the mock sample set); the stored, proposed and
    approved versions are ticket 19's.
    """

    def __init__(self, platform: OrderRules, tenants: Mapping[uuid.UUID, OrderRules]) -> None:
        self._overlay: TenantOverlay[str, OrderRules] = TenantOverlay()
        self._overlay.put(platform.policy_id, platform)
        for tenant_id, rules in tenants.items():
            if rules.version == platform.version:
                raise ValueError(
                    f"tenant rules reuse the platform's version {platform.version}:"
                    " a tenant version needs a number of its own"
                )
            self._overlay.put(rules.policy_id, rules, tenant_id=tenant_id)

    async def rules(self, scope: SalesScope) -> OrderRules:
        rules = self._overlay.get("sales_order_rules", tenant_id=scope.tenant_id.value)
        assert rules is not None  # the platform layer is put in __init__
        return rules


def load_tenant_order_rules(directory: Path) -> OrderRules | None:
    """The one `sales_order_rules@<version>.yaml` a tenant's directory holds,
    or None when it holds none. Two are refused: which applies is a decision,
    not a file-system order."""
    found = sorted(directory.glob("sales_order_rules@*.yaml")) if directory.is_dir() else []
    if len(found) > 1:
        raise ValueError(f"{directory.name} holds {len(found)} versions of sales_order_rules")
    return load_order_rules(found[0]) if found else None
