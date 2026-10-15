"""The live lane cannot pass on a model that read nothing.

Every model step degrades an unavailable answer to a person, and the guards
grade that as safe, so ticket 28's live lane reported PASS 6/6 on a run in
which every call timed out. Each sales grader now fails a live case in which
the model under test was called and gave no usable answer
(`recorded.failing_without_live_answers`); the smoke, with no live model,
is graded as before.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dw_evals.graders import GraderContext
from dw_evals.runner import load_dataset
from dw_sales.application.model_reading import ModelUnavailableError
from dw_sales.evals import GRADERS
from dw_sales.evals.recorded import Observed, Recorded, load_answers

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
DATASETS = REPO / "evals" / "datasets"
MODEL_STEPS = [
    "sales_descriptions@1.0.0",
    "sales_rfq@1.0.0",
    "sales_intent@1.0.0",
    "sales_reply@1.0.0",
    "sales_handoff@1.0.0",
    "sales_layout@1.0.0",
]
REASON = "the live model gave no usable answer"


def _unavailable() -> Observed:
    """The live lane's model when every call times out."""
    return Observed(inner=Recorded(failure=ModelUnavailableError("ReadTimeout")))


def _ref(ref: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((REPO / ref).read_text(encoding="utf-8"))
    return data


def test_the_model_steps_are_every_sales_dataset_with_a_live_lane() -> None:
    """A new model step's dataset joins `MODEL_STEPS`, or this goes red."""
    stepped = {
        path.stem
        for path in DATASETS.glob("sales_*@*.json")
        if any("golden" in case.grader for case in load_dataset(path).cases)
    }
    assert stepped == set(MODEL_STEPS)


@pytest.mark.parametrize("dataset", MODEL_STEPS)
def test_no_case_that_called_an_unavailable_live_model_passes(dataset: str) -> None:
    model = _unavailable()
    ctx = GraderContext(repo_root=REPO, live_model=model)
    called = []
    for case in load_dataset(DATASETS / f"{dataset}.json").cases:
        before = len(model.calls)
        result = GRADERS[case.grader](ctx, _ref(case.input_ref), _ref(case.expected_ref))
        if len(model.calls) == before:
            continue
        called.append(case.case_id)
        assert not result.passed, f"{case.case_id} passed on {len(model.calls) - before} calls"
        if result.details["reason"] == REASON:
            assert result.details["live_calls"] == len(model.calls) - before

    assert model.answered == 0
    # Not vacuous: the golden case reads through the live model.
    assert any("golden" in case_id for case_id in called), called


def test_a_live_model_that_answers_is_graded_by_the_graders_own_verdict() -> None:
    """The recorded answers, served as the live model: the golden case
    passes, its answers counted."""
    recorded = REPO / "evals" / "fixtures" / "cases" / "sales_intent_recorded.json"
    ctx = GraderContext(repo_root=REPO)
    model = Observed(inner=Recorded(answers=load_answers(recorded), prompts=ctx.prompt_registry))
    ctx.live_model = model
    (golden,) = (
        case
        for case in load_dataset(DATASETS / "sales_intent@1.0.0.json").cases
        if case.grader == "sales.intent_golden"
    )

    result = GRADERS[golden.grader](ctx, _ref(golden.input_ref), _ref(golden.expected_ref))

    assert result.passed, result.details
    assert result.details["live"] is True
    assert 0 < model.answered == len(model.calls)


def test_a_live_model_that_does_not_count_its_answers_fails_closed() -> None:
    ctx = GraderContext(repo_root=REPO, live_model=Recorded(failure=ModelUnavailableError("x")))
    (golden,) = (
        case
        for case in load_dataset(DATASETS / "sales_intent@1.0.0.json").cases
        if case.grader == "sales.intent_golden"
    )

    result = GRADERS[golden.grader](ctx, _ref(golden.input_ref), _ref(golden.expected_ref))

    assert not result.passed
    assert result.details["reason"] == "the live model is not observed: its answers are not counted"


def test_the_smoke_is_graded_as_before() -> None:
    """No live model: the wrap hands the case straight to its grader."""
    ctx = GraderContext(repo_root=REPO)
    for case in load_dataset(DATASETS / "sales_intent@1.0.0.json").cases:
        result = GRADERS[case.grader](ctx, _ref(case.input_ref), _ref(case.expected_ref))
        assert result.passed, (case.case_id, result.details)
