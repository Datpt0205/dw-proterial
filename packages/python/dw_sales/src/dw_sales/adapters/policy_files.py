"""The Sales policies in ``configs/policies``, each validated by its own model.

The platform layer of the per-tenant lookup: what ships in the repository. A
file's name and its content both state the version, and the release manifest
records the content's: a name that disagrees is a file somebody edited
without bumping one of the two, refused when it loads.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import yaml
from pydantic import BaseModel

from dw_sales.adapters.order_rules import load_order_rules
from dw_sales.application.artifact_content import (
    BravoUploadLayout,
    SalesDocumentCopy,
    SalesEmailCopy,
)
from dw_sales.application.handoffs import HandoffCopy
from dw_sales.application.quotation import QuoteRules
from dw_sales.application.rules import (
    OVERRIDABLE,
    Policy,
    RuleKey,
    RuleVersionLookupPort,
    TenantRuleBook,
    read_over,
)
from dw_sales.domain.followups import SalesFollowups
from dw_sales.domain.kpi import SalesKpi
from dw_sales.domain.order_checks import OrderRules
from dw_sales.domain.pricing import SalesPricing


def load_policy[T: BaseModel](path: Path, model: type[T]) -> T:
    """``path`` validated by ``model``, refused when named for another version."""
    loaded = model.model_validate(yaml.safe_load(path.read_bytes()))
    version = getattr(loaded, "version", None)
    if not isinstance(version, str) or path.name != f"{version}.yaml":
        raise ValueError(f"{path.name} holds {version}")
    return loaded


def load_quote_rules(path: Path) -> QuoteRules:
    return load_policy(path, QuoteRules)


def load_pricing(path: Path) -> SalesPricing:
    return load_policy(path, SalesPricing)


def load_kpi(path: Path) -> SalesKpi:
    return load_policy(path, SalesKpi)


def load_followups(path: Path) -> SalesFollowups:
    return load_policy(path, SalesFollowups)


def load_bravo_upload(path: Path) -> BravoUploadLayout:
    return load_policy(path, BravoUploadLayout)


def load_copy[T: (SalesEmailCopy, SalesDocumentCopy, HandoffCopy)](path: Path, model: type[T]) -> T:
    """``configs/copy/<copy_id>@<version>.yaml``, refused when named for
    another copy or version."""
    loaded = model.model_validate(yaml.safe_load(path.read_bytes()))
    if path.name != f"{loaded.ref}.yaml":
        raise ValueError(f"{path.name} holds {loaded.ref}")
    return loaded


@dataclass(frozen=True, slots=True)
class SalesPolicies:
    """The platform layer DW1 runs: every policy and copy file, loaded. A
    service reads none of it directly: each resolves its tenant's version
    through the rule book (`rule_book`, tickets 19 and 36)."""

    order_rules: OrderRules
    quote_rules: QuoteRules
    pricing: SalesPricing
    kpi: SalesKpi
    # What every artifact is drawn with, each file pinned by the release manifest.
    emails: SalesEmailCopy
    documents: SalesDocumentCopy
    upload: BravoUploadLayout
    # The words of a hand-off to PC or QA (ticket 33).
    handoff_copy: HandoffCopy
    # When DW1 reminds a person, and the morning brief (ticket 42).
    followups: SalesFollowups
    # Every version of each key the checkout ships, by ref, the ones above
    # included: what a case stamped before a release is read with after it.
    released: Mapping[str, Policy]

    def current(self) -> dict[RuleKey, Policy]:
        return {
            RuleKey.ORDER_RULES: self.order_rules,
            RuleKey.KPI: self.kpi,
            RuleKey.QUOTE_RULES: self.quote_rules,
            RuleKey.PRICING: self.pricing,
            RuleKey.EMAILS: self.emails,
            RuleKey.DOCUMENTS: self.documents,
            RuleKey.BRAVO_UPLOAD: self.upload,
            RuleKey.HANDOFFS: self.handoff_copy,
            RuleKey.FOLLOWUPS: self.followups,
        }


def load_sales_policies(policies_dir: Path, copy_dir: Path) -> SalesPolicies:
    """The one place that names which version of each file DW1 runs.

    The API's composition root and the eval world both load through here, so
    an eval grades the rules the API serves, not a version a second list of
    file names still points at.
    """
    current = SalesPolicies(
        order_rules=load_order_rules(policies_dir / "sales_order_rules@1.5.0.yaml"),
        quote_rules=load_quote_rules(policies_dir / "sales_quote_rules@1.1.0.yaml"),
        pricing=load_pricing(policies_dir / "sales_pricing@1.0.0.yaml"),
        kpi=load_kpi(policies_dir / "sales_kpi@1.0.0.yaml"),
        emails=load_copy(copy_dir / "sales_emails@1.2.0.yaml", SalesEmailCopy),
        documents=load_copy(copy_dir / "sales_documents@1.2.0.yaml", SalesDocumentCopy),
        upload=load_bravo_upload(policies_dir / "sales_bravo_upload@1.1.0.yaml"),
        handoff_copy=load_copy(copy_dir / "sales_handoffs@1.0.0.yaml", HandoffCopy),
        followups=load_followups(policies_dir / "sales_followups@1.0.0.yaml"),
        released={},
    )
    released = load_released(current.current(), policies_dir, copy_dir)
    return replace(current, released=released)


def load_released(
    current: Mapping[RuleKey, Policy], policies_dir: Path, copy_dir: Path
) -> dict[str, Policy]:
    """Every ``<key>@<version>.yaml`` of each overridable key, read over the
    current version (`read_over`), each refused when named for another.

    A released file is never edited or deleted (`test_released_policies.py`
    holds every file a release manifest pinned to its checksum), so a case
    stamped with any of them is still read after a deploy."""
    released: dict[str, Policy] = {}
    for key, schema in OVERRIDABLE.items():
        for directory in (policies_dir, copy_dir):
            for path in sorted(directory.glob(f"{key.value}@*.yaml")):
                policy = read_over(schema, yaml.safe_load(path.read_bytes()), current[key])
                if path.name != f"{policy.ref}.yaml":
                    raise ValueError(f"{path.name} holds {policy.ref}")
                released[policy.ref] = policy
    return released


def rule_book(policies: SalesPolicies, stored: RuleVersionLookupPort) -> TenantRuleBook:
    """The rules a tenant may hold its own version of, over the platform's
    files: each `RuleKey` with the policy this module loaded for it, and
    every version released before it."""
    return TenantRuleBook(platform=policies.current(), stored=stored, released=policies.released)
