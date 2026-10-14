"""Every released rules version is still read after a deploy (ticket 37).

A case stamps the rules it was checked under, and a later step reads that
stamp. A release that dropped the file, or changed the schema under it, would
leave every case opened before it unable to take its next step (409
`rules_version_gone`), so the platform keeps every version it released and a
version written before a field existed reads that field as the platform's
current version has it.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from dw_kernel.errors import ConflictError
from dw_sales.adapters.memory_rules import MemoryRuleVersions
from dw_sales.adapters.policy_files import load_sales_policies, rule_book
from dw_sales.application.artifact_content import SalesEmailCopy
from dw_sales.application.rules import (
    OVERRIDABLE,
    RuleKey,
    RuleVersion,
    TenantRuleBook,
    read_over,
)
from dw_sales.domain.order_checks import OrderRules
from dw_sales.domain.orders import FindingCode
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER
from dw_sales.evals.world import BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
POLICIES, COPY = REPO / "configs" / "policies", REPO / "configs" / "copy"
_AT = datetime(2026, 10, 14, tzinfo=UTC)


def _manifest_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "release_manifest", REPO / "scripts" / "release_manifest.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pinned() -> dict[str, set[str]]:
    """Every Sales policy and copy file any release manifest pinned, by ref,
    with each checksum it was pinned at."""
    release = REPO / "contracts" / "release"
    pinned: dict[str, set[str]] = {}
    for path in [release / "manifest.json", *sorted((release / "history").glob("*.json"))]:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for entry in [*manifest.get("policies", []), *manifest.get("copy_bundles", [])]:
            name = entry.get("policy_id") or entry["copy_id"]
            if name in {key.value for key in OVERRIDABLE}:
                pinned.setdefault(f"{name}@{entry['version']}", set()).add(entry["checksum"])
    return pinned


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, OUTSIDER))


def _stored(key: RuleKey, version: str, document: dict[str, Any], status: str) -> RuleVersion:
    return RuleVersion.model_validate(
        {
            "version_id": uuid.uuid4(),
            "key": key,
            "version": version,
            "document": document,
            "status": status,
            "proposed_by": uuid.UUID(int=1),
            "proposed_at": _AT,
            "decided_by": None if status == "proposed" else uuid.UUID(int=2),
            "decided_at": None if status == "proposed" else _AT,
            "comment": "x" if status == "rejected" else None,
        }
    )


def _order_rules(version: str, **changes: Any) -> dict[str, Any]:
    document = load_sales_policies(POLICIES, COPY).order_rules.model_dump(
        mode="json", by_alias=True
    )
    return {**document, "policy_version": version, **changes}


def test_a_released_file_is_never_edited_or_deleted() -> None:
    checksum = _manifest_module()._checksum
    pinned = _pinned()
    assert "sales_order_rules@1.0.0" in pinned  # the history is read at all
    for ref, checksums in pinned.items():
        found = [path for path in (POLICIES / f"{ref}.yaml", COPY / f"{ref}.yaml") if path.exists()]
        assert found, f"{ref} was released and is gone"
        assert checksums == {checksum(found[0])}, f"{ref} was edited after its release"


def test_every_released_version_is_held_and_reads_under_todays_schema() -> None:
    policies = load_sales_policies(POLICIES, COPY)
    assert set(_pinned()) <= set(policies.released)
    for ref, policy in policies.released.items():
        assert policy.ref == ref
    for key, policy in policies.current().items():
        assert policies.released[policy.ref] == policy, key


async def test_a_case_stamped_before_a_release_reads_the_version_it_was_checked_under() -> None:
    world = _world()
    port = world.services.layouts.rules
    current = world.policies.order_rules
    stamped = await port.rules_at(BETA, "sales_order_rules@1.4.0")
    assert stamped is not None and stamped.version == "sales_order_rules@1.4.0"
    assert stamped != current
    # 1.4.0 predates the requested-date check: it reads the platform's severity.
    code = FindingCode.REQUESTED_DATE_MISSING
    assert stamped.findings[code] == current.findings[code]
    # The quote rules a quotation was opened under, the same way.
    book = rule_book(world.policies, MemoryRuleVersions())
    assert await book.quote_rules_at(BETA, "sales_quote_rules@1.0.0") is not None
    assert await port.rules_at(BETA, "sales_order_rules@0.9.0") is None


def test_a_field_a_version_predates_reads_as_the_platform_has_it_now() -> None:
    platform = load_sales_policies(POLICIES, COPY).order_rules
    document = _order_rules("1.0.9", cross_check_required=not platform.cross_check_required)
    del document["layout_onboarding"]
    del document["model_assist"]["layout_proposal"]
    del document["findings"][FindingCode.REQUESTED_DATE_MISSING.value]

    read = read_over(OrderRules, document, platform)

    assert isinstance(read, OrderRules)
    assert read.layout_onboarding == platform.layout_onboarding
    assert read.model_assist.layout_proposal == platform.model_assist.layout_proposal
    assert read.findings == platform.findings
    # What the version says, it keeps.
    assert read.cross_check_required is not platform.cross_check_required
    assert read.policy_version == "1.0.9"


def test_a_mapping_of_data_is_never_topped_up_and_an_unknown_field_is_refused() -> None:
    platform = load_sales_policies(POLICIES, COPY).emails
    assert len(platform.emails) > 1
    first = next(iter(platform.emails))
    document = platform.model_dump(mode="json", by_alias=True)
    document["emails"] = {first: document["emails"][first]}

    read = read_over(SalesEmailCopy, document, platform)

    assert isinstance(read, SalesEmailCopy)
    assert list(read.emails) == [first]
    with pytest.raises(ValueError):
        read_over(SalesEmailCopy, {**document, "no_such_field": 1}, platform)


async def test_a_tenant_version_written_before_a_field_existed_is_still_in_force() -> None:
    world = _world()
    document = _order_rules("1.5.7", cross_check_required=False)
    del document["layout_onboarding"]
    stored = _stored(RuleKey.ORDER_RULES, "1.5.7", document, "approved")
    await world.store.rule_versions.for_tenant(BETA.tenant_id.value).add(stored)

    in_force = await world.services.layouts.rules.rules(BETA)

    assert in_force.version == "sales_order_rules@1.5.7"
    assert not in_force.cross_check_required
    assert in_force.layout_onboarding == world.policies.order_rules.layout_onboarding


async def test_a_tenant_takes_no_number_the_platform_ever_released() -> None:
    world = _world()
    with pytest.raises(ConflictError) as refused:
        await world.services.rules.propose(AN.context(), RuleKey.ORDER_RULES, _order_rules("1.4.0"))
    assert refused.value.details["rule"] == "platform_version_reused"


async def test_a_number_the_platform_ships_after_a_tenant_took_it_means_the_tenants() -> None:
    policies = load_sales_policies(POLICIES, COPY)
    later = OrderRules.model_validate(_order_rules("1.6.0"))
    also_later = OrderRules.model_validate(_order_rules("1.7.0"))
    versions = MemoryRuleVersions()
    tenant = versions.for_tenant(BETA.tenant_id.value)
    await tenant.add(
        _stored(
            RuleKey.ORDER_RULES,
            "1.6.0",
            _order_rules("1.6.0", cross_check_required=False),
            "approved",
        )
    )
    await tenant.add(_stored(RuleKey.ORDER_RULES, "1.7.0", _order_rules("1.7.0"), "rejected"))
    book = TenantRuleBook(
        platform=policies.current(),
        stored=versions,
        released={**policies.released, later.ref: later, also_later.ref: also_later},
    )

    own = await book.at(BETA, RuleKey.ORDER_RULES, "sales_order_rules@1.6.0")
    assert isinstance(own, OrderRules) and not own.cross_check_required
    # A number the tenant proposed and was refused is the platform's.
    assert await book.at(BETA, RuleKey.ORDER_RULES, "sales_order_rules@1.7.0") == also_later
