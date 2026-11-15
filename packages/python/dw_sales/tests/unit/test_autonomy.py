"""What applies itself, and at what measured error (ticket 44, dw_sales ADR
0015): the tiers, the threshold by Learn-then-Test with the exact binomial
bound, the audits and the gate, all pure (`dw_sales.domain.autonomy`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from dw_sales.domain.autonomy import (
    STEP_TIERS,
    LabelledScore,
    ScoredCase,
    StepThreshold,
    Tier,
    audit_stopped,
    cases_needed,
    conformal_threshold,
    gate_route,
    in_audit_sample,
    lower_bound,
    measure,
    tier_of,
    upper_bound,
)
from dw_sales.domain.order_checks import Autonomy, ModelStep

pytestmark = pytest.mark.unit

AT = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)
PROMPT = "sales.description_attributes@1.0.0"
STEP = ModelStep.DESCRIPTION_ATTRIBUTES


def _correct(n: int, *, top: float = 0.999, step: float = 0.0001) -> list[ScoredCase]:
    return [ScoredCase(top - i * step, True) for i in range(n)]


# ------------------------------------------------------------------ tiers --


def test_every_step_declares_its_tier_and_one_left_out_never_applies_itself() -> None:
    assert set(STEP_TIERS) == set(ModelStep)
    # What a person approves (ADR 0015 decision 1): an approval, a change to
    # what the customer was confirmed.
    assert tier_of(ModelStep.LAYOUT_PROPOSAL) is Tier.PERSON_APPROVES
    assert tier_of(ModelStep.CHANGE_REQUEST) is Tier.PERSON_APPROVES
    assert tier_of(ModelStep.REQUEST_HANDOFF) is Tier.HAND_OFF
    assert tier_of(ModelStep.DESCRIPTION_ATTRIBUTES) is Tier.APPLIES_ITSELF
    # Fail closed: a step the table does not name.
    assert tier_of("a_step_added_later") is Tier.PERSON_APPROVES  # type: ignore[arg-type]


def test_a_tenant_may_tighten_the_targets_and_never_loosen_them() -> None:
    assert Autonomy().model_dump() == {
        "applies_itself_error": 0.05,
        "hand_off_error": 0.02,
        "audit_share": 0.03,
    }
    Autonomy(applies_itself_error=0.01, hand_off_error=0.005, audit_share=0.1)
    for loosened in (
        {"applies_itself_error": 0.06},
        {"hand_off_error": 0.03},
        {"audit_share": 0.02},
        {"audit_share": 0.0},
        {"applies_itself_error": 0.0},
    ):
        with pytest.raises(ValidationError):
            Autonomy.model_validate(loosened)


# ------------------------------------------------------------- statistics --


@pytest.mark.parametrize(("alpha", "needed"), [(0.05, 59), (0.02, 149), (0.01, 299)])
def test_the_cases_a_target_needs_are_the_adrs(alpha: float, needed: int) -> None:
    assert cases_needed(alpha) == needed
    assert upper_bound(0, needed) <= alpha < upper_bound(0, needed - 1)


def test_the_bounds_are_the_exact_binomial_ones() -> None:
    # Zero of n: 1 - delta ** (1 / n), the closed form.
    assert upper_bound(0, 59) == pytest.approx(1 - 0.05 ** (1 / 59), abs=1e-9)
    # k of k: delta ** (1 / k) from below.
    assert lower_bound(3, 3) == pytest.approx(0.05 ** (1 / 3), abs=1e-9)
    assert lower_bound(0, 10) == 0.0
    assert upper_bound(10, 10) == 1.0
    # One wrong of 100: a known value (about 0.0466).
    assert upper_bound(1, 100) == pytest.approx(0.0466, abs=5e-4)


def test_too_few_cases_set_no_threshold_however_right_they_were() -> None:
    assert conformal_threshold(_correct(58), 0.05) is None
    found = conformal_threshold(_correct(59), 0.05)
    assert found is not None and (found.accepted, found.errors) == (59, 0)
    assert found.score == pytest.approx(0.999 - 58 * 0.0001)


def test_the_finite_sample_correction_refuses_what_a_plain_error_rate_would_certify() -> None:
    """Two wrong of the top 59 is 3.4%, under 5%; the exact upper bound on it
    is about 11%, so nothing is certified. A plain rate would let these
    results apply themselves (the mutation this test catches)."""
    cases = [ScoredCase(1 - i / 1000, i % 30 != 10) for i in range(200)]
    top = sorted(cases, key=lambda c: -c.confidence)[:59]
    assert sum(not c.correct for c in top) / 59 <= 0.05
    assert conformal_threshold(cases, 0.05) is None


def test_the_threshold_stops_where_the_wrong_results_begin() -> None:
    right = _correct(150, top=0.99, step=0.001)
    wrong = [ScoredCase(0.5 - i / 1000, i % 2 == 0) for i in range(40)]
    found = conformal_threshold(right + wrong, 0.05)
    assert found is not None
    assert found.score > 0.4
    assert upper_bound(found.errors, found.accepted) <= 0.05
    # The next looser score would not be certified.
    looser = [c for c in right + wrong if c.confidence < found.score]
    nxt = max(c.confidence for c in looser)
    accepted = [c for c in right + wrong if c.confidence >= nxt]
    errors = sum(not c.correct for c in accepted)
    assert upper_bound(errors, len(accepted)) > 0.05


def test_cases_of_one_score_are_accepted_together() -> None:
    cases = [ScoredCase(0.9, True)] * 70 + [ScoredCase(0.8, False)] * 5
    found = conformal_threshold(cases, 0.05)
    assert found is not None and (found.score, found.accepted, found.errors) == (0.9, 70, 0)


def test_an_audited_error_above_the_target_stops_the_step() -> None:
    assert not audit_stopped(0, 0, 0.05)
    assert not audit_stopped(30, 0, 0.05)
    # One wrong of ten could be chance at 5%; three of ten is not.
    assert not audit_stopped(10, 1, 0.05)
    assert audit_stopped(10, 3, 0.05)


def test_the_audit_sample_is_the_same_for_an_item_and_about_its_share() -> None:
    keys = [f"tenant:M{i}:A1:1:description_attributes" for i in range(20_000)]
    sampled = [k for k in keys if in_audit_sample(k, 0.03)]
    assert 0.025 < len(sampled) / len(keys) < 0.035
    assert all(in_audit_sample(k, 0.03) for k in sampled)
    assert not in_audit_sample(keys[0], 0.0)
    assert in_audit_sample(keys[0], 1.0)


# ------------------------------------------------------------- the measure --


def _labels(
    n: int, *, wrong: int = 0, audits: int = 0, audit_wrong: int = 0
) -> list[LabelledScore]:
    labels = [
        LabelledScore(confidence=0.99 - i * 1e-4, verdict="confirmed", gate="person")
        for i in range(n)
    ]
    labels += [LabelledScore(confidence=0.2, verdict="corrected", gate="person")] * wrong
    labels += [LabelledScore(confidence=0.995, verdict="confirmed", gate="audit")] * (
        audits - audit_wrong
    )
    labels += [LabelledScore(confidence=0.995, verdict="rejected", gate="audit")] * audit_wrong
    return labels


def test_a_step_a_person_approves_is_never_measured() -> None:
    labels = _labels(500)
    assert measure(ModelStep.CHANGE_REQUEST, PROMPT, "onprem", labels, Autonomy(), AT) is None
    with pytest.raises(ValidationError):
        StepThreshold(
            step=ModelStep.CHANGE_REQUEST,
            prompt=PROMPT,
            model_profile="onprem",
            tier=Tier.PERSON_APPROVES,
            target=0.05,
            needed=59,
            cases=0,
            threshold=None,
            accepted=0,
            errors=0,
            audits=0,
            audit_errors=0,
            stopped=False,
            computed_at=AT,
        )


def test_a_step_measured_at_the_tenants_target_with_its_audits() -> None:
    few = measure(STEP, PROMPT, "onprem", _labels(40), Autonomy(), AT)
    assert few is not None and few.threshold is None and not few.applying
    assert (few.cases, few.needed) == (40, 59)

    enough = measure(STEP, PROMPT, "onprem", _labels(80, wrong=10), Autonomy(), AT)
    assert enough is not None and enough.applying
    assert enough.threshold is not None and enough.threshold > 0.2
    assert (enough.cases, enough.errors) == (90, 0)

    # A stricter tenant needs more cases for the same labels.
    strict = measure(
        STEP, PROMPT, "onprem", _labels(80, wrong=10), Autonomy(applies_itself_error=0.02), AT
    )
    assert strict is not None and strict.threshold is None and strict.needed == 149

    stopped = measure(STEP, PROMPT, "onprem", _labels(80, audits=10, audit_wrong=3), Autonomy(), AT)
    assert stopped is not None and stopped.stopped and not stopped.applying
    assert (stopped.audits, stopped.audit_errors) == (10, 3)
    assert stopped.audited_error == pytest.approx(0.3)


# ---------------------------------------------------------------- the gate --


def _threshold(*, score: float | None = 0.9, stopped: bool = False) -> StepThreshold:
    return StepThreshold(
        step=STEP,
        prompt=PROMPT,
        model_profile="onprem",
        tier=Tier.APPLIES_ITSELF,
        target=0.05,
        needed=59,
        cases=100,
        threshold=score,
        accepted=0 if score is None else 80,
        errors=0,
        audits=0,
        audit_errors=0,
        stopped=stopped,
        computed_at=AT,
    )


def _not_sampled() -> str:
    return next(k for k in (f"k{i}" for i in range(100)) if not in_audit_sample(k, 0.03))


def _sampled() -> str:
    return next(k for k in (f"k{i}" for i in range(1000)) if in_audit_sample(k, 0.03))


def test_the_gate_applies_only_a_confident_result_of_a_certified_step() -> None:
    key = _not_sampled()
    assert gate_route(STEP, 0.95, _threshold(), item_key=key, audit_share=0.03) == "applied"
    assert gate_route(STEP, 0.89, _threshold(), item_key=key, audit_share=0.03) == "person"
    assert gate_route(STEP, None, _threshold(), item_key=key, audit_share=0.03) == "person"
    assert gate_route(STEP, 0.99, None, item_key=key, audit_share=0.03) == "person"
    uncertified = _threshold(score=None)
    assert gate_route(STEP, 0.99, uncertified, item_key=key, audit_share=0.03) == "person"
    stopped = _threshold(stopped=True)
    assert gate_route(STEP, 0.99, stopped, item_key=key, audit_share=0.03) == "shadow"
    assert gate_route(STEP, 0.99, _threshold(), item_key=_sampled(), audit_share=0.03) == "audit"


def test_a_step_a_person_approves_is_never_let_through_whatever_its_confidence() -> None:
    other = _threshold().model_copy(update={"step": ModelStep.CHANGE_REQUEST})
    for step in (ModelStep.CHANGE_REQUEST, ModelStep.LAYOUT_PROPOSAL):
        route = gate_route(step, 1.0, other, item_key=_not_sampled(), audit_share=0.03)
        assert route == "person"
    # Nor a threshold set for another step.
    assert (
        gate_route(
            ModelStep.RFQ_EXTRACTION, 1.0, _threshold(), item_key=_not_sampled(), audit_share=0.03
        )
        == "person"
    )


def test_undoing_what_applied_itself_counts_against_the_step_as_an_audit() -> None:
    labels = (
        _labels(80)
        + [LabelledScore(confidence=0.995, verdict="rejected", gate="applied")] * 3
        + [LabelledScore(confidence=0.995, verdict="confirmed", gate="applied")] * 2
    )
    measured = measure(STEP, PROMPT, "onprem", labels, Autonomy(), AT)
    assert measured is not None and (measured.audits, measured.audit_errors) == (5, 3)
    assert measured.stopped
