"""The Purchasing rules in ``configs/policies``: the platform layer.

Every version the checkout ever released stays loadable, and the newest is
the one in force. A file's name and its content both state the version and
the policy id: a name that disagrees is a file somebody edited without
bumping one of the two, refused when it loads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from dw_purchasing.domain.rules import POLICY_ID, PurchasingRules


def _semver(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("-")[0].split("."))


def load_rules(path: Path) -> PurchasingRules:
    raw = yaml.safe_load(path.read_bytes())
    if not isinstance(raw, dict) or raw.pop("policy_id", None) != POLICY_ID:
        raise ValueError(f"{path.name} is not a {POLICY_ID} document")
    raw.pop("schema_version", None)
    rules = PurchasingRules.model_validate(raw)
    if path.name != f"{rules.ref}.yaml":
        raise ValueError(f"{path.name} holds {rules.ref}")
    return rules


@dataclass(frozen=True)
class PolicyFiles:
    """Implements `PlatformRulesPort` over every released version."""

    released: tuple[PurchasingRules, ...]

    @classmethod
    def load(cls, policies_dir: Path) -> PolicyFiles:
        found = [load_rules(p) for p in sorted(policies_dir.glob(f"{POLICY_ID}@*.yaml"))]
        if not found:
            raise ValueError(f"no {POLICY_ID} document in {policies_dir}")
        return cls(tuple(sorted(found, key=lambda r: _semver(r.version))))

    def current(self) -> PurchasingRules:
        return self.released[-1]

    @property
    def versions(self) -> frozenset[str]:
        return frozenset(r.version for r in self.released)
