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

    The platform layer of the per-tenant lookup: what ships in ``configs/``.
    A tenant's own version is stored through the platform's policy overrides
    and resolved by the adapter that wraps this one when a tenant needs it.
    """

    def __init__(self, rules: OrderRules) -> None:
        self._rules = rules

    async def rules(self, scope: SalesScope) -> OrderRules:
        return self._rules
