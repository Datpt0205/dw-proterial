"""The smoke datasets must pass in-process — same path `make eval-smoke` runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dw_evals.dataset import EvalDataset
from dw_evals.graders import GRADERS, GraderContext, GradeResult, compose_graders
from dw_evals.runner import load_dataset, run_dataset

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[5]
DATASETS = sorted((REPO_ROOT / "evals" / "datasets").glob("*.json"))
# The datasets the platform's own graders score. A context's dataset names
# graders its composition root injects, and is run by that context's tests
# and by `scripts/run_evals.py --smoke`.
PLATFORM_DATASETS = [
    path for path in DATASETS if {c.grader for c in load_dataset(path).cases} <= set(GRADERS)
]


def test_datasets_exist() -> None:
    assert {p.name for p in DATASETS} >= {"platform@1.1.0.json"}
    assert {p.name for p in PLATFORM_DATASETS} >= {"platform@1.1.0.json"}


@pytest.mark.parametrize("path", DATASETS, ids=lambda p: p.stem)
def test_dataset_has_full_security_coverage(path: Path) -> None:
    assert load_dataset(path).has_full_security_coverage()


@pytest.mark.parametrize("path", PLATFORM_DATASETS, ids=lambda p: p.stem)
def test_smoke_dataset_passes(path: Path) -> None:
    report = run_dataset(load_dataset(path), REPO_ROOT)
    failures = [r for r in report.results if not r.passed]
    assert not failures, f"failing cases: {[(f.case_id, f.details) for f in failures]}"
    assert report.ok


def _one_case(grader: str) -> EvalDataset:
    return EvalDataset.model_validate(
        {
            "dataset_id": "injected",
            "dataset_version": "1.0.0",
            "worker_id": "dw.test",
            "cases": [
                {
                    "case_id": "c1",
                    "category": "normal",
                    "description": "graded by an injected grader",
                    "input_ref": "evals/fixtures/cases/pf_side_effect.json",
                    "expected_ref": "evals/expected/pf_side_effect.json",
                    "grader": grader,
                }
            ],
        }
    )


def test_a_dataset_is_graded_by_the_graders_handed_in() -> None:
    def context_grader(
        ctx: GraderContext, input_data: dict[str, object], expected: dict[str, object]
    ) -> GradeResult:
        return GradeResult.ok(seen=sorted(input_data))

    graders = compose_graders(GRADERS, {"ctx.gate": context_grader})

    assert run_dataset(_one_case("ctx.gate"), REPO_ROOT, graders).passed == 1
    # Not handed in, not known: the platform's table holds no context's key.
    assert run_dataset(_one_case("ctx.gate"), REPO_ROOT).results[0].details["reason"] == (
        "unknown grader"
    )


def test_a_grader_key_cannot_be_registered_twice() -> None:
    with pytest.raises(ValueError, match="registered twice"):
        compose_graders(GRADERS, {"runtime.prompt_injection": GRADERS["memory.write_policy"]})


def test_failing_grader_is_reported_not_raised(tmp_path: Path) -> None:
    dataset = EvalDataset.model_validate(
        {
            "dataset_id": "broken",
            "dataset_version": "1.0.0",
            "worker_id": "dw.test",
            "cases": [
                {
                    "case_id": "unknown-grader",
                    "category": "failure",
                    "description": "grader does not exist",
                    "input_ref": "evals/fixtures/cases/pf_side_effect.json",
                    "expected_ref": "evals/expected/pf_side_effect.json",
                    "grader": "does.not.exist",
                }
            ],
        }
    )
    report = run_dataset(dataset, REPO_ROOT)
    assert report.failed == 1
    assert report.results[0].details["reason"] == "unknown grader"


def test_case_ref_cannot_escape_repository() -> None:
    dataset = EvalDataset.model_validate(
        json.loads(
            json.dumps(
                {
                    "dataset_id": "escape",
                    "dataset_version": "1.0.0",
                    "worker_id": "dw.test",
                    "cases": [
                        {
                            "case_id": "escape",
                            "category": "failure",
                            "description": "path traversal attempt",
                            "input_ref": "../outside.json",
                            "expected_ref": "evals/expected/pf_side_effect.json",
                            "grader": "runtime.side_effect_approval",
                        }
                    ],
                }
            )
        )
    )
    report = run_dataset(dataset, REPO_ROOT)
    assert report.failed == 1  # grader raised → failing case, never a crash
