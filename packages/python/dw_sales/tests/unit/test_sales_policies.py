"""The Sales policies the API loads: each validated by its own model, named
for the version it holds, and every key read by something."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from dw_sales.adapters.policy_files import load_kpi, load_policy, load_quote_rules
from dw_sales.application.quotation import QuoteRules
from dw_sales.domain.kpi import SalesKpi
from dw_sales.domain.process import WIV_STEPS

pytestmark = pytest.mark.unit

POLICIES = Path(__file__).resolve().parents[5] / "configs" / "policies"
KPI = POLICIES / "sales_kpi@1.0.0.yaml"
QUOTE_RULES = POLICIES / "sales_quote_rules@1.1.0.yaml"


def _raw(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_the_shipped_kpi_has_the_targets_and_a_baseline_for_every_surveyed_step() -> None:
    kpi = load_kpi(KPI)

    assert kpi.version == "sales_kpi@1.0.0"
    # Đạt, 2026-10-05: a quotation within a day of the request.
    assert kpi.quotation_target_days == 1
    assert set(kpi.manual_baseline_minutes) == {step.step_id for step in WIV_STEPS}


def test_a_kpi_policy_missing_a_steps_baseline_is_refused() -> None:
    raw = _raw(KPI)
    del raw["manual_baseline_minutes"]["Q12"]

    with pytest.raises(ValidationError, match="Q12"):
        SalesKpi.model_validate(raw)


def test_a_kpi_policy_naming_a_step_the_survey_lacks_is_refused() -> None:
    raw = _raw(KPI)
    raw["manual_baseline_minutes"]["O12"] = 5

    with pytest.raises(ValidationError, match="O12"):
        SalesKpi.model_validate(raw)


def test_the_kpi_policy_holds_no_key_the_overview_does_not_read() -> None:
    read = {
        "schema_version",
        "policy_id",
        "policy_version",
        "order_confirmation_target_hours",
        "quotation_target_days",
        "manual_baseline_minutes",
    }
    assert set(_raw(KPI)) == read == set(SalesKpi.model_fields)


def test_design_mailboxes_are_a_key_of_the_quote_rules() -> None:
    rules = load_quote_rules(QUOTE_RULES)

    assert rules.version == "sales_quote_rules@1.1.0"
    assert rules.design_mailboxes == ("design@seller.example",)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"design_mailboxes": ["not-an-address"]}, "design_mailboxes"),
        ({"design_mailboxes": ["d@seller.example", "D@seller.example"]}, "twice"),
    ],
)
def test_a_design_mailbox_that_is_not_one_address_is_refused(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        QuoteRules.model_validate(_raw(QUOTE_RULES) | change)


def test_quote_rules_without_design_mailboxes_are_refused_not_defaulted() -> None:
    raw = _raw(QUOTE_RULES)
    del raw["design_mailboxes"]

    with pytest.raises(ValidationError, match="design_mailboxes"):
        QuoteRules.model_validate(raw)


def test_a_policy_file_named_for_another_version_is_refused(tmp_path: Path) -> None:
    misnamed = tmp_path / "sales_kpi@9.9.9.yaml"
    misnamed.write_text(KPI.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match=r"holds sales_kpi@1\.0\.0"):
        load_policy(misnamed, SalesKpi)
