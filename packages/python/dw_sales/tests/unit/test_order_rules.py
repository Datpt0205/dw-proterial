"""Loading `sales_order_rules` from ``configs/policies`` and serving it per scope."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.application.order_ports import OrderRulesPort
from dw_sales.application.ports import SalesScope

pytestmark = pytest.mark.unit

SHIPPED = (
    Path(__file__).resolve().parents[5] / "configs" / "policies" / ("sales_order_rules@1.0.0.yaml")
)


def test_the_shipped_policy_loads() -> None:
    rules = load_order_rules(SHIPPED)

    assert rules.version == "sales_order_rules@1.0.0"


def test_a_file_named_for_another_version_is_refused(tmp_path: Path) -> None:
    renamed = tmp_path / "sales_order_rules@1.0.1.yaml"
    shutil.copy(SHIPPED, renamed)

    with pytest.raises(ValueError, match=r"holds sales_order_rules@1\.0\.0"):
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
