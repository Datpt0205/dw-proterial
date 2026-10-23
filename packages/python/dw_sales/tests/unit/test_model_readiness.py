"""A model step earns its switch (dw_sales ADR 0005, addendum of 2026-10-23).

The bars have one owner (`model_readiness.BARS`), live measurements are kept
per tenant, and a step is used, or turned on in a version, only where the
latest measurement for the model and prompt it runs on now passed. Each
guard here has a test that turns red without it.
"""

from __future__ import annotations

import importlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from dw_kernel.errors import ConflictError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.domain.audit import system_actor
from dw_sales.adapters.assembly import step_model
from dw_sales.application.model_readiness import (
    ATTEST_LANE,
    BARS,
    MODEL_BAR_UNMET,
    ModelAttestation,
    ModelMeasurement,
    ModelReadiness,
    bar_verdict,
    step_measured_by,
)
from dw_sales.application.rules import RuleKey
from dw_sales.domain.order_checks import ModelAssist, ModelStep, OrderRules
from dw_sales.evals.graders import AN, CALLERS, GIANG, OUTSIDER
from dw_sales.evals.world import ALPHA, BETA, NOW, SampleSet, World, open_world
from dw_sales.testing.measurements import FixedStepModel, MemoryModelMeasurements, passing

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
MODEL = step_model(REPO / "configs", "onprem").model_for(ALPHA.tenant_id.value)
IDS = Uuid4Generator()


# ------------------------------------------------------------ the owner --


def test_every_model_step_is_a_switch_of_the_rules_and_has_one_bar() -> None:
    switches = {name for name, f in ModelAssist.model_fields.items() if f.annotation is bool}
    assert switches == {step.value for step in ModelStep}
    assert set(BARS) == set(ModelStep)
    assert len({owner.dataset for owner in BARS.values()}) == len(ModelStep)


@pytest.mark.parametrize("step", list(ModelStep))
def test_each_bar_names_a_dataset_whose_golden_case_its_grader_grades(step: ModelStep) -> None:
    owner = BARS[step]
    (path,) = (REPO / "evals" / "datasets").glob(f"{owner.dataset}@*.json")
    dataset = json.loads(path.read_text(encoding="utf-8"))
    assert dataset["dataset_id"] == owner.dataset
    assert owner.grader in {case["grader"] for case in dataset["cases"]}
    assert step_measured_by(owner.dataset) is step
    assert 0 < owner.bar <= 1


@pytest.mark.parametrize(
    "module", ["descriptions", "handoffs", "intents", "layouts", "replies", "requests"]
)
def test_no_eval_keeps_a_bar_of_its_own(module: str) -> None:
    """The second copy the addendum removed: an eval reads its bar here."""
    loaded = importlib.import_module(f"dw_sales.evals.{module}")
    assert not hasattr(loaded, "PROPOSED_BAR")
    assert loaded.bar_verdict is bar_verdict


def test_a_verdict_reads_the_metric_at_its_path_and_the_graders_own_condition() -> None:
    details = {"bar_set": {"kind_accuracy": 0.9}}
    verdict = bar_verdict(ModelStep.REPLY_INTENT, details)
    assert verdict == {
        "step": "reply_intent",
        "metric": "bar_set.kind_accuracy",
        "value": 0.9,
        "bar": 0.85,
        "passed": True,
    }
    assert not bar_verdict(ModelStep.REPLY_INTENT, details, holds=False)["passed"]
    assert not bar_verdict(ModelStep.REPLY_INTENT, {"bar_set": {"kind_accuracy": 0.84}})["passed"]
    with pytest.raises(KeyError):
        bar_verdict(ModelStep.REPLY_INTENT, {"all": {"kind_accuracy": 0.9}})


def test_a_passing_measurement_is_at_or_above_its_bar() -> None:
    row = passing(ModelStep.MESSAGE_INTENT, MODEL, NOW, IDS)
    with pytest.raises(ValidationError, match="at or above its bar"):
        ModelMeasurement.model_validate({**row.model_dump(), "value": row.bar - 0.01})
    with pytest.raises(ValidationError):
        ModelMeasurement.model_validate({**row.model_dump(), "recorded_by": "an.nguyen"})


# ------------------------------------------------------------- readiness --


def _gate(*rows: tuple[Any, ModelMeasurement], unreadable: bool = False) -> ModelReadiness:
    log = MemoryModelMeasurements(unreadable=unreadable)
    for scope, row in rows:
        log.seed(scope, row)
    return ModelReadiness(log, FixedStepModel(MODEL))


def _row(step: ModelStep = ModelStep.MESSAGE_INTENT, **changes: Any) -> ModelMeasurement:
    return ModelMeasurement.model_validate(
        {**passing(step, MODEL, NOW, IDS).model_dump(), **changes}
    )


async def test_a_step_never_measured_is_not_ready() -> None:
    readiness = await _gate().check(ALPHA, ModelStep.MESSAGE_INTENT)
    assert (readiness.ready, readiness.reason, readiness.latest) == (False, "not_measured", None)
    assert (readiness.model, readiness.prompt) == (MODEL, "sales.message_intent@1.0.0")


async def test_a_passing_measurement_on_the_model_and_prompt_it_runs_on_is_ready() -> None:
    readiness = await _gate((ALPHA, _row())).check(ALPHA, ModelStep.MESSAGE_INTENT)
    assert readiness.ready and readiness.reason == "ready"


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "another-model:7b"},
        {"prompt": "sales.message_intent@0.9.0"},
        {"step": ModelStep.REPLY_INTENT},
    ],
    ids=["another model", "another prompt version", "another step"],
)
async def test_a_pass_measured_on_anything_else_does_not_count(changes: dict[str, Any]) -> None:
    readiness = await _gate((ALPHA, _row(**changes))).check(ALPHA, ModelStep.MESSAGE_INTENT)
    assert not readiness.ready and readiness.reason == "not_measured"


async def test_the_latest_measurement_decides_and_a_later_failure_takes_the_pass_away() -> None:
    later = _row(value=0.5, passed=False, measured_at=NOW + timedelta(days=1))
    readiness = await _gate((ALPHA, _row()), (ALPHA, later)).check(ALPHA, ModelStep.MESSAGE_INTENT)
    assert not readiness.ready and readiness.reason == "failed"
    assert readiness.latest == later


async def test_a_pass_under_an_older_lower_bar_or_metric_does_not_count() -> None:
    lower = _row(value=0.8, bar=0.8)  # passed at 80%; today's bar is 90%
    assert not (await _gate((ALPHA, lower)).check(ALPHA, ModelStep.MESSAGE_INTENT)).ready
    other = _row(metric="vi_en.kind_accuracy")
    assert not (await _gate((ALPHA, other)).check(ALPHA, ModelStep.MESSAGE_INTENT)).ready


async def test_another_tenants_measurement_never_readies_this_tenants_step() -> None:
    readiness = await _gate((BETA, _row())).check(ALPHA, ModelStep.MESSAGE_INTENT)
    assert not readiness.ready


async def test_an_unreadable_store_is_not_ready() -> None:
    readiness = await _gate((ALPHA, _row()), unreadable=True).check(ALPHA, ModelStep.MESSAGE_INTENT)
    assert (readiness.ready, readiness.reason) == (False, "unreadable")


async def test_a_step_is_allowed_only_on_and_ready_and_off_reads_nothing(
    platform_rules: OrderRules, demo_rules: OrderRules
) -> None:
    gate = _gate((ALPHA, _row()))
    assert await gate.allows(ALPHA, demo_rules, ModelStep.MESSAGE_INTENT)
    assert not await gate.allows(ALPHA, demo_rules, ModelStep.REPLY_INTENT)  # not measured
    assert not await gate.allows(ALPHA, platform_rules, ModelStep.MESSAGE_INTENT)  # off
    # Off is answered without asking the store: an unreadable one is not reached.
    broken = _gate(unreadable=True)
    assert not await broken.allows(ALPHA, platform_rules, ModelStep.MESSAGE_INTENT)


# ----------------------------------------------------------- attestation --


async def test_the_lane_records_the_row_and_audits_as_itself() -> None:
    log = MemoryModelMeasurements()
    attest = ModelAttestation(log, FixedClock(NOW), IDS)
    row = await attest.attest(
        ALPHA,
        ModelStep.LAYOUT_PROPOSAL,
        model=MODEL,
        value=0.912345,
        held=True,
        dataset="sales_layout@1.0.0",
    )
    assert (row.value, row.bar, row.passed) == (0.9123, 0.90, True)
    assert row.recorded_by == f"system:{ATTEST_LANE}"
    assert (row.prompt, row.metric) == ("sales.po_layout_proposal@1.0.0", "all.right")
    (event,) = log.events
    assert event.actor_id == system_actor(ATTEST_LANE)
    assert event.details["actor"] == f"system:{ATTEST_LANE}"
    assert (event.tenant_id, event.resource_id) == (ALPHA.tenant_id, str(row.measurement_id))
    assert await log.latest(ALPHA, ModelStep.LAYOUT_PROPOSAL, model=MODEL, prompt=row.prompt) == (
        row
    )


async def test_a_run_whose_own_verdict_failed_records_a_failure_whatever_the_share() -> None:
    attest = ModelAttestation(MemoryModelMeasurements(), FixedClock(NOW), IDS)
    row = await attest.attest(
        ALPHA, ModelStep.LAYOUT_PROPOSAL, model=MODEL, value=0.99, held=False, dataset="x@1.0.0"
    )
    assert not row.passed
    below = await attest.attest(
        ALPHA, ModelStep.LAYOUT_PROPOSAL, model=MODEL, value=0.5, held=True, dataset="x@1.0.0"
    )
    assert not below.passed


# --------------------------------------------- a version that turns one on --


def _world() -> World:
    """Alpha starts with its own rules, every model step on, and no
    measurement: nothing here goes around the gate."""
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, OUTSIDER))


def _document(world: World, version: str, **switches: bool) -> dict[str, Any]:
    document = world.policies.order_rules.model_dump(mode="json", by_alias=True)
    document["policy_version"] = version
    document["model_assist"] = {**document["model_assist"], **switches}
    return document


async def _all_off(world: World) -> None:
    """Alpha on a version with every step off: turning steps off needs no
    measurement at all."""
    proposed = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _document(world, "9.1.0")
    )
    await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Tắt")
    in_force = await world.services.rules.book.order_rules(ALPHA)
    assert in_force.policy_version == "9.1.0"
    assert not any(in_force.model_assist.on(step) for step in ModelStep)


async def test_turning_a_step_off_is_always_allowed() -> None:
    await _all_off(_world())


async def test_turning_a_step_on_with_no_measurement_is_refused_naming_it() -> None:
    world = _world()
    await _all_off(world)
    with pytest.raises(ConflictError) as refused:
        await world.services.rules.propose(
            AN.context(), RuleKey.ORDER_RULES, _document(world, "9.1.1", message_intent=True)
        )
    assert refused.value.details["rule"] == MODEL_BAR_UNMET
    (step,) = cast(list[dict[str, object]], refused.value.details["steps"])
    assert step == {
        "step": "message_intent",
        "bar": 0.90,
        "model": MODEL,
        "prompt": "sales.message_intent@1.0.0",
        "reason": "not_measured",
        "latest": None,
    }
    message = str(refused.value)
    assert "«message_intent»" in message and "90%" in message and "chưa đo" in message
    assert (await world.services.rules.list(GIANG.context())).versions[0].version == "9.1.0"


@pytest.mark.parametrize(
    "changes",
    [{"model": "another-model:7b"}, {"prompt": "sales.message_intent@0.9.0"}],
    ids=["for another model", "for another prompt version"],
)
async def test_a_pass_measured_on_another_model_or_prompt_does_not_turn_it_on(
    changes: dict[str, Any],
) -> None:
    world = _world()
    await _all_off(world)
    world.measurements.seed(ALPHA, _row(**changes))
    with pytest.raises(ConflictError) as refused:
        await world.services.rules.propose(
            AN.context(), RuleKey.ORDER_RULES, _document(world, "9.1.1", message_intent=True)
        )
    assert refused.value.details["rule"] == MODEL_BAR_UNMET


async def test_a_failed_latest_measurement_is_named_with_its_share() -> None:
    world = _world()
    await _all_off(world)
    world.measurements.seed(ALPHA, _row(value=0.7, passed=False))
    with pytest.raises(ConflictError) as refused:
        await world.services.rules.propose(
            AN.context(), RuleKey.ORDER_RULES, _document(world, "9.1.1", message_intent=True)
        )
    assert "lần đo gần nhất 70.0%" in str(refused.value)
    assert refused.value.details["steps"][0]["latest"]["value"] == 0.7  # type: ignore[index]


async def test_a_step_measured_at_its_bar_is_turned_on_and_used() -> None:
    world = _world()
    await _all_off(world)
    world.measurements.seed(ALPHA, _row())
    proposed = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _document(world, "9.1.1", message_intent=True)
    )
    await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Bật")
    in_force = await world.services.rules.book.order_rules(ALPHA)
    assert in_force.policy_version == "9.1.1" and in_force.model_assist.message_intent
    readiness = world.services.rules.readiness
    assert await readiness.allows(ALPHA, in_force, ModelStep.MESSAGE_INTENT)


async def test_keeping_a_step_on_is_not_a_turn_on_and_is_still_not_used() -> None:
    """Alpha's own version has every step on and nothing measured: another
    version keeping them on is not refused (it turns nothing on), and the
    gate still keeps every one with a person."""
    world = _world()
    own = await world.services.rules.book.order_rules(ALPHA)
    document = own.model_dump(mode="json", by_alias=True)
    document["policy_version"] = "9.2.0"
    document["cross_check_required"] = not own.cross_check_required
    proposed = await world.services.rules.propose(AN.context(), RuleKey.ORDER_RULES, document)
    await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Đổi")
    in_force = await world.services.rules.book.order_rules(ALPHA)
    assert in_force.policy_version == "9.2.0"
    for step in ModelStep:
        assert not await world.services.rules.readiness.allows(ALPHA, in_force, step)


async def test_the_decision_is_refused_when_the_pass_went_away_and_a_rejection_is_not() -> None:
    world = _world()
    await _all_off(world)
    world.measurements.seed(ALPHA, _row())
    proposed = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _document(world, "9.1.1", message_intent=True)
    )
    world.measurements.seed(
        ALPHA, _row(value=0.5, passed=False, measured_at=NOW + timedelta(hours=1))
    )
    with pytest.raises(ConflictError) as refused:
        await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Bật")
    assert refused.value.details["rule"] == MODEL_BAR_UNMET
    await world.decide_rules(GIANG, proposed.version_id, approve=False, comment="Đo lại")
    listed = await world.services.rules.list(GIANG.context())
    assert next(v for v in listed.versions if v.version == "9.1.1").status == "rejected"


async def test_a_settlement_after_the_pass_went_away_records_it_not_applied() -> None:
    """Decided while the step was ready; the measurement changed before the
    worker carried it out: recorded as rejected with why, so the key is
    free, never left waiting on a decision already taken."""
    world = _world()
    await _all_off(world)
    world.measurements.seed(ALPHA, _row())
    proposed = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _document(world, "9.1.1", message_intent=True)
    )
    assert proposed.approval_id is not None
    await world.runtime.approval_flow.decide(
        approval_id=proposed.approval_id,
        approve=True,
        comment="Bật",
        context=GIANG.context(),
        authorization=ScopeAuthorizationService(),
    )
    world.measurements.seed(
        ALPHA, _row(value=0.5, passed=False, measured_at=NOW + timedelta(hours=1))
    )
    settled = await world.rule_settlement.settle(proposed.approval_id, GIANG.context())
    assert settled.status == "rejected"
    assert settled.comment is not None and "message_intent" in settled.comment
    in_force = await world.services.rules.book.order_rules(ALPHA)
    assert in_force.policy_version == "9.1.0"
    # The key is free again.
    await world.services.rules.propose(AN.context(), RuleKey.ORDER_RULES, _document(world, "9.1.2"))


@pytest.fixture
def platform_rules() -> OrderRules:
    return _world().policies.order_rules


@pytest.fixture
async def demo_rules() -> OrderRules:
    return await _world().services.rules.book.order_rules(ALPHA)
