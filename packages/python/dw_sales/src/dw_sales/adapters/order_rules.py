"""`OrderRulesPort` over the versioned policy file in ``configs/policies``."""

from __future__ import annotations

from pathlib import Path

import yaml

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

    The platform layer alone: what ships in ``configs/``. A tenant's own
    version is proposed, approved and resolved through
    `dw_sales.application.rules` (ticket 19).
    """

    def __init__(self, rules: OrderRules) -> None:
        self._rules = rules

    async def rules(self, scope: SalesScope) -> OrderRules:
        return self._rules

    async def rules_at(self, scope: SalesScope, ref: str) -> OrderRules | None:
        return self._rules if ref == self._rules.version else None


def load_tenant_order_rules(directory: Path) -> OrderRules | None:
    """The one `sales_order_rules@<version>.yaml` a tenant's directory holds,
    or None when it holds none. Two are refused: which applies is a decision,
    not a file-system order."""
    found = sorted(directory.glob("sales_order_rules@*.yaml")) if directory.is_dir() else []
    if len(found) > 1:
        raise ValueError(f"{directory.name} holds {len(found)} versions of sales_order_rules")
    return load_order_rules(found[0]) if found else None
