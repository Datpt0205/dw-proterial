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

from dw_platform.application.rule_versions import RuleVersionLookupPort
from dw_purchasing.application.rules import PurchasingRuleBook, released_book
from dw_purchasing.domain.automation import POLICY_ID as AUTOMATION_ID
from dw_purchasing.domain.automation import PurchasingAutomation
from dw_purchasing.domain.rules import POLICY_ID, PurchasingRules


def _semver(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("-")[0].split("."))


def load_rules(path: Path) -> PurchasingRules:
    raw = yaml.safe_load(path.read_bytes())
    if not isinstance(raw, dict) or raw.get("policy_id") != POLICY_ID:
        raise ValueError(f"{path.name} is not a {POLICY_ID} document")
    raw.pop("schema_version", None)
    rules = PurchasingRules.model_validate(raw)
    if path.name != f"{rules.ref}.yaml":
        raise ValueError(f"{path.name} holds {rules.ref}")
    return rules


@dataclass(frozen=True)
class PolicyFiles:
    """The platform layer: every released version, the newest in force."""

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
    def by_ref(self) -> dict[str, PurchasingRules]:
        """Every released version by the ref a case stamps."""
        return {r.ref: r for r in self.released}


def load_switches(path: Path) -> PurchasingAutomation:
    raw = yaml.safe_load(path.read_bytes())
    if not isinstance(raw, dict) or raw.get("policy_id") != AUTOMATION_ID:
        raise ValueError(f"{path.name} is not a {AUTOMATION_ID} document")
    raw.pop("schema_version", None)
    switches = PurchasingAutomation.model_validate(raw)
    if path.name != f"{switches.ref}.yaml":
        raise ValueError(f"{path.name} holds {switches.ref}")
    return switches


@dataclass(frozen=True)
class SwitchFiles:
    """The switches' platform layer: every released version, the newest in force."""

    released: tuple[PurchasingAutomation, ...]

    @classmethod
    def load(cls, policies_dir: Path) -> SwitchFiles:
        found = [load_switches(p) for p in sorted(policies_dir.glob(f"{AUTOMATION_ID}@*.yaml"))]
        if not found:
            raise ValueError(f"no {AUTOMATION_ID} document in {policies_dir}")
        return cls(tuple(sorted(found, key=lambda r: _semver(r.version))))

    def current(self) -> PurchasingAutomation:
        return self.released[-1]

    @property
    def by_ref(self) -> dict[str, PurchasingAutomation]:
        return {r.ref: r for r in self.released}


def platform_rule_book(policies_dir: Path, stored: RuleVersionLookupPort) -> PurchasingRuleBook:
    """DW2's rule book: every released platform version of each key, under
    the tenant's own versions in ``stored``."""
    return released_book(PolicyFiles.load(policies_dir), SwitchFiles.load(policies_dir), stored)
