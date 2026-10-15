"""Every dataset passes with the grader table `make eval-smoke` builds.

Here rather than in `dw_evals`: the table is the eval composition root's
(`scripts/run_evals.py`, `grader_table`) and includes the bounded contexts'
graders, which `dw_evals` must not import. This package already depends on every
context, so it can load the script and run the same table the script runs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from dw_evals import runner
from dw_evals.dataset import EvalDataset
from dw_evals.runner import CaseResult, EvalReport, load_dataset, run_dataset
from dw_sales.application.model_reading import ModelUnavailableError
from dw_sales.evals.recorded import Observed, Recorded

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
DATASETS = sorted((REPO_ROOT / "evals" / "datasets").glob("*.json"))


def _load_script() -> ModuleType:  # scripts/ is loaded by path, as make runs it
    spec = importlib.util.spec_from_file_location(
        "run_evals", REPO_ROOT / "scripts" / "run_evals.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_evals"] = module
    spec.loader.exec_module(module)
    return module


def test_the_platform_dataset_is_found() -> None:
    assert {p.name for p in DATASETS} >= {"platform@1.2.0.json"}


@pytest.mark.parametrize("path", DATASETS, ids=lambda p: p.stem)
def test_smoke_dataset_passes(path: Path) -> None:
    report = run_dataset(load_dataset(path), REPO_ROOT, _load_script().grader_table())
    failures = [r for r in report.results if not r.passed]
    assert not failures, f"failing cases: {[(f.case_id, f.details) for f in failures]}"
    assert report.ok


def test_a_grader_name_the_table_lacks_fails_its_case() -> None:
    dataset = EvalDataset.model_validate(
        {
            "dataset_id": "unregistered",
            "dataset_version": "1.0.0",
            "worker_id": "dw.test",
            "cases": [
                {
                    "case_id": "unregistered",
                    "category": "normal",
                    "description": "a context grader nobody registered",
                    "input_ref": "evals/fixtures/cases/pf_side_effect.json",
                    "expected_ref": "evals/expected/pf_side_effect.json",
                    "grader": "acme.not_registered",
                }
            ],
        }
    )
    report = run_dataset(dataset, REPO_ROOT, _load_script().grader_table())
    assert not report.results[0].passed
    assert not report.ok
    assert report.results[0].details["reason"] == "unknown grader"


# ------------------------------------------------------------- live lane --


def _report(*details: dict[str, object]) -> EvalReport:
    return EvalReport(
        dataset_id="sales_intent",
        dataset_version="1.0.0",
        worker_id="sales-dw1",
        total=len(details),
        passed=len(details),
        failed=0,
        security_coverage_ok=True,
        results=tuple(
            CaseResult(
                case_id=f"case-{n}", category="normal", grader="sales.x", passed=True, details=d
            )
            for n, d in enumerate(details)
        ),
    )


def _answered(answers: int, calls: int) -> Observed:
    model = Observed(inner=Recorded())
    model.answered = answers
    model.calls.extend([None] * calls)  # type: ignore[list-item]
    return model


def test_a_live_run_that_read_nothing_falls_short_whatever_its_cases_say() -> None:
    shortfalls = _load_script().live_shortfalls(_report({"live": True}), _answered(0, 9))

    assert shortfalls == ["nothing was read: 9 model calls, none gave a usable answer"]


def test_a_live_run_that_never_called_the_model_falls_short() -> None:
    shortfalls = _load_script().live_shortfalls(_report({}), _answered(0, 0))

    assert shortfalls == ["nothing was read: 0 model calls, none gave a usable answer"]


def test_a_live_run_below_a_cases_bar_falls_short() -> None:
    report = _report(
        {"proposed_bar": 0.9, "meets_proposed_bar": False},
        {"proposed_bar_vi_en": 0.7, "meets_proposed_bar_vi_en": False},
        {"proposed_bar": 0.85, "meets_proposed_bar": True},
    )

    shortfalls = _load_script().live_shortfalls(report, _answered(5, 9))

    assert shortfalls == ["case-0: below proposed_bar 0.9", "case-1: below proposed_bar_vi_en 0.7"]


def test_a_live_run_that_read_and_met_its_bar_has_no_shortfall() -> None:
    report = _report({"proposed_bar_vi_en": 0.7, "meets_proposed_bar_vi_en": True}, {})

    assert _load_script().live_shortfalls(report, _answered(1, 9)) == []


def test_the_live_lane_exits_non_zero_when_every_call_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end through `main`: the model times out on every call."""
    script = _load_script()
    model = Observed(inner=Recorded(failure=ModelUnavailableError("ReadTimeout")))
    monkeypatch.setattr(script, "live_model_for", lambda profile: model)
    written: list[EvalReport] = []

    def write_report(report: EvalReport, reports_dir: Path) -> Path:
        written.append(report)  # kept out of the checkout's evals/reports
        return reports_dir / f"{report.dataset_id}@{report.dataset_version}.json"

    monkeypatch.setattr(runner, "write_report", write_report)
    dataset = REPO_ROOT / "evals" / "datasets" / "sales_intent@1.0.0.json"
    monkeypatch.setattr(
        sys, "argv", ["run_evals.py", "--live", "onprem", "--dataset", str(dataset)]
    )

    assert script.main() == 1
    out = capsys.readouterr().out
    assert out.startswith("[FAIL] sales_intent@1.0.0")
    assert "the live model gave no usable answer" in out
    assert "✗ live: nothing was read" in out
    (report,) = written
    golden = next(r for r in report.results if r.grader == "sales.intent_golden")
    assert not golden.passed
