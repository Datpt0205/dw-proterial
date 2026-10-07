"""DW1's eval dataset passes as CI runs it, and each grader can fail.

The dataset runs through `dw_evals.runner` with the graders composed the way
`scripts/run_evals.py` composes them. Each grader is then handed a world in
which the thing it guards is broken (a truth that disagrees, a README that
claims another finding, a mock that answers every tenant, a price view that
shows every amount) and must go red: a grader that cannot fail is
failure-modes #3.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from dw_evals.graders import GRADERS as PLATFORM_GRADERS
from dw_evals.graders import GraderContext, merge_graders
from dw_evals.runner import load_dataset, run_dataset
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.mock.fixtures import DATA_DIR, MOCK_ROOT
from dw_sales.application import access
from dw_sales.evals import GRADERS

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
DATASET = REPO / "evals" / "datasets" / "sales@1.0.0.json"
CTX = GraderContext(repo_root=REPO)


def _case(name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    def read(folder: str) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(
            (REPO / "evals" / folder / f"{name}.json").read_text(encoding="utf-8")
        )
        return data

    return read("fixtures/cases"), read("expected")


def test_the_sales_dataset_passes_with_full_security_coverage() -> None:
    dataset = load_dataset(DATASET)
    report = run_dataset(dataset, REPO, merge_graders(PLATFORM_GRADERS, GRADERS))

    failures = [(r.case_id, r.details) for r in report.results if not r.passed]
    assert not failures
    assert report.ok and dataset.has_full_security_coverage()
    assert {c.grader for c in dataset.cases} == set(GRADERS)


def test_every_grader_is_keyed_under_the_context() -> None:
    assert all(key.startswith("sales.") for key in GRADERS)


# ------------------------------------------------- each grader can fail --


def test_extraction_fails_when_a_value_differs_from_the_truth(tmp_path: Path) -> None:
    rows = json.loads((DATA_DIR / "purchase_orders.json").read_text(encoding="utf-8"))
    m01 = next(row for row in rows if row["message_id"] == "M01")
    m01["lines"][0]["unit_price"] = "9.9999"
    (tmp_path / "purchase_orders.json").write_text(json.dumps(rows), encoding="utf-8")
    case, expected = _case("sales_extraction")

    result = GRADERS["sales.extraction_accuracy"](
        CTX, case, expected | {"truth": str(tmp_path / "purchase_orders.json")}
    )

    assert not result.passed
    assert result.details["by_field"]["unit_price"] == 1
    # The report names the field, never the value.
    assert "9.9999" not in json.dumps(result.details)


def test_extraction_fails_when_a_routed_document_is_not_expected_routed() -> None:
    case, expected = _case("sales_extraction")

    result = GRADERS["sales.extraction_accuracy"](CTX, case, expected | {"routed": {}})

    assert not result.passed


def test_findings_recall_fails_on_a_finding_the_readme_claims_and_dw1_misses(
    tmp_path: Path,
) -> None:
    readme = (MOCK_ROOT / "README.md").read_text(encoding="utf-8")
    row = next(line for line in readme.splitlines() if line.startswith("| `M01`"))
    cells = row.split("|")
    cells[-2] = " `price_mismatch` (line 1) "  # M01 is clean: DW1 raises nothing
    tampered = readme.replace(row, "|".join(cells))
    assert tampered != readme
    (tmp_path / "README.md").write_text(tampered, encoding="utf-8")
    case, expected = _case("sales_findings")

    result = GRADERS["sales.findings_recall"](
        CTX, case, expected | {"readme": str(tmp_path / "README.md")}
    )

    assert not result.passed
    assert result.details["missed"] == ["M01 price_mismatch:1"]


def test_findings_recall_fails_when_design_replies_meet_no_waiting_case() -> None:
    """Without Sales recording the YCBG, Design's replies are routed, not
    attached: the README's disposition is the process's, not DW1's alone."""
    case, expected = _case("sales_findings")

    result = GRADERS["sales.findings_recall"](CTX, case | {"sales_steps": {}}, expected)

    assert not result.passed
    assert result.details["messages"] == ["M18", "M25", "M29", "M30"]


def test_injection_case_fails_when_the_message_no_longer_carries_the_attack() -> None:
    case, expected = _case("sales_injection_m12")

    result = GRADERS["sales.injection_contained"](
        CTX, case | {"injected": ["not in the message"]}, expected
    )

    assert not result.passed


def test_scope_binding_fails_when_the_mocks_answer_every_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def every_tenant(self: MockInbox, scope: object) -> Any:
        return self._messages

    monkeypatch.setattr(MockInbox, "list_messages", every_tenant)
    monkeypatch.setattr(MockSalesCatalog, "_many", lambda self, scope, records: _unbound(records))
    case, expected = _case("sales_cross_tenant")

    result = GRADERS["sales.scope_binding"](CTX, case, expected)

    assert not result.passed
    assert "inbox lists another tenant's mail" in result.details["breaches"]


def _unbound(records: Any) -> Any:
    from datetime import UTC, datetime

    from dw_sales.application.ports import Snapshot

    return Snapshot(data=records, as_of=datetime(2026, 10, 1, tzinfo=UTC))


def test_never_clean_fails_when_a_blocking_finding_is_not_raised() -> None:
    case, expected = _case("sales_missing_evidence_gate")
    blocking = expected["blocking"] | {"M01": ["line_total_mismatch:-"]}

    result = GRADERS["sales.never_clean"](CTX, case, expected | {"blocking": blocking})

    assert not result.passed


def test_separation_of_duties_fails_on_another_outcome() -> None:
    case, expected = _case("sales_maker_checker_order")
    claimed = expected["outcomes"] | {"preparer": "ok"}

    result = GRADERS["sales.separation_of_duties"](CTX, case, {"outcomes": claimed})

    assert not result.passed
    assert result.details["outcomes"]["preparer"] == "409:maker_checker"


def test_price_confidentiality_fails_when_every_caller_sees_amounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        access.PriceView, "of", classmethod(lambda cls, context, authz: cls(True, True))
    )
    case, expected = _case("sales_price_confidentiality")

    result = GRADERS["sales.price_confidentiality"](CTX, case, expected)

    assert not result.passed
    assert result.details["reason"] == "a price reached a reader without the price scope"


def test_a_sample_set_outside_the_package_is_read_from_its_own_directory(
    tmp_path: Path,
) -> None:
    """Proterial's sample set lives outside git in the same layout: the graders
    read whatever directory the case names, not the fictional set."""
    shutil.copytree(DATA_DIR, tmp_path / "data")
    rows = json.loads((tmp_path / "data" / "convert_list.json").read_text(encoding="utf-8"))
    (tmp_path / "data" / "convert_list.json").write_text(
        json.dumps([r for r in rows if r["customer_code"] != "VLX"]), encoding="utf-8"
    )
    case, expected = _case("sales_extraction")
    sample = {"data_dir": str(tmp_path / "data"), "attachments_dir": str(MOCK_ROOT / "attachments")}

    result = GRADERS["sales.extraction_accuracy"](CTX, case | {"sample_set": sample}, expected)

    # VLX's codes are no longer in this set's convert list: DW1 maps none of
    # them exactly, and the truth (read from the same set) expects exactly that.
    assert result.passed, result.details
