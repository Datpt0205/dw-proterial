"""Loading `sales_order_rules` from ``configs/policies`` and serving it per scope."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.memory_rules import static_rule_book
from dw_sales.adapters.mock.fixtures import DATA_DIR
from dw_sales.adapters.order_rules import (
    PlatformOrderRules,
    load_order_rules,
    load_tenant_order_rules,
)
from dw_sales.application.order_ports import OrderRulesPort
from dw_sales.application.ports import SalesScope
from dw_sales.application.rules import RuleBookOrderRules

pytestmark = pytest.mark.unit

SHIPPED = (
    Path(__file__).resolve().parents[5] / "configs" / "policies" / ("sales_order_rules@1.6.0.yaml")
)

MOCK_POLICIES = DATA_DIR / "policies"


def test_the_shipped_policy_loads() -> None:
    rules = load_order_rules(SHIPPED)

    assert rules.version == "sales_order_rules@1.6.0"


def test_a_file_named_for_another_version_is_refused(tmp_path: Path) -> None:
    renamed = tmp_path / "sales_order_rules@1.2.1.yaml"
    shutil.copy(SHIPPED, renamed)

    with pytest.raises(ValueError, match=r"holds sales_order_rules@1\.6\.0"):
        load_order_rules(renamed)


def test_a_policy_missing_a_severity_is_refused_when_it_loads(tmp_path: Path) -> None:
    broken = tmp_path / SHIPPED.name
    text = SHIPPED.read_text(encoding="utf-8")
    broken.write_text(text.replace("  revised_po: warning\n", ""), encoding="utf-8")

    with pytest.raises(ValidationError, match="revised_po"):
        load_order_rules(broken)


async def test_every_tenant_gets_the_platform_rules_until_it_has_its_own() -> None:
    rules = load_order_rules(SHIPPED)
    port: OrderRulesPort = PlatformOrderRules(rules)

    for tenant in (1, 2):
        scope = SalesScope(TenantId(uuid.UUID(int=tenant)), WorkspaceId(uuid.UUID(int=9)))
        assert await port.rules(scope) is rules


async def test_a_tenants_own_rules_never_reach_another_tenant() -> None:
    """The demo tenant's version (model assist on) is its own: another tenant
    reads the platform's, with the step off, never the demo tenant's."""
    platform = load_order_rules(SHIPPED)
    own = load_tenant_order_rules(MOCK_POLICIES)
    assert own is not None
    alpha = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=9)))
    beta = SalesScope(TenantId(uuid.UUID(int=2)), WorkspaceId(uuid.UUID(int=9)))
    port: OrderRulesPort = RuleBookOrderRules(static_rule_book(platform, alpha, own))

    assert (await port.rules(alpha)).model_assist.description_attributes
    beta_rules = await port.rules(beta)
    assert beta_rules is platform
    assert not beta_rules.model_assist.description_attributes


def test_a_policy_without_the_model_assist_switch_is_refused(tmp_path: Path) -> None:
    broken = tmp_path / SHIPPED.name
    text = SHIPPED.read_text(encoding="utf-8")
    broken.write_text(text.replace("  description_attributes: false\n", ""), encoding="utf-8")

    with pytest.raises(ValidationError, match="model_assist"):
        load_order_rules(broken)


def test_the_demo_resets_version_is_the_sample_sets_with_every_model_step_off() -> None:
    """`make demo-reset` installs 1.5.3 (`seed_rules.DEMO_POLICIES`): the mock
    demo has no model server and records no measurement, so a step turned on
    would be refused by its bar and the tenant left on the platform's rules
    (dw_sales ADR 0005, addendum of 2026-10-23). It is 1.5.2, the version the
    tests run the model steps under, in every other field: a rule changed in
    one and not the other fails here."""
    from dw_sales.domain.order_checks import ModelStep, OrderRules
    from dw_sales.testing.seed_rules import DEMO_POLICIES, MODEL_STEP_POLICIES

    demo = load_tenant_order_rules(DEMO_POLICIES)
    steps_on = load_tenant_order_rules(MODEL_STEP_POLICIES)
    assert demo is not None and steps_on is not None
    assert (demo.version, steps_on.version) == (
        "sales_order_rules@1.5.3",
        "sales_order_rules@1.5.2",
    )
    assert not any(demo.model_assist.on(step) for step in ModelStep)
    assert all(steps_on.model_assist.on(step) for step in ModelStep)

    def rest(rules: OrderRules) -> dict[str, object]:
        dumped = rules.model_dump(mode="json")
        dumped.pop("policy_version")
        assist = dumped.pop("model_assist")
        dumped["unread_retry_hours"] = assist["unread_retry_hours"]
        return dumped

    assert rest(demo) == rest(steps_on)
