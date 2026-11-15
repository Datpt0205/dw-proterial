"""A result applying itself (ticket 44, dw_sales ADR 0015): the gate the
intake asks, the effect `AutoApply` takes as the `sales_auto_apply` lane, the
undo that is a labelled case, the lane that sets the thresholds, and the
head's view, each with what it must refuse.

Over the in-memory world (`dw_sales.evals.world`) and the intake the model
reading's own tests build; the table, its RLS and grants are
`tests/integration/test_sales_step_thresholds.py`'s.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import PromptRef
from dw_agent_runtime.model.scoring import Scored
from dw_kernel.errors import ConflictError, PermissionDeniedError
from dw_kernel.ids import UserId
from dw_kernel.ports import FixedClock
from dw_platform.domain.audit import system_actor
from dw_sales.application import auto_apply as auto_apply_module
from dw_sales.application.auto_apply import AutoApply
from dw_sales.application.autonomy import (
    AUTO_APPLY_LANE,
    AutonomyGate,
    ThresholdLane,
    applied_by,
)
from dw_sales.application.case_store import Stored
from dw_sales.application.ports import SalesScope
from dw_sales.domain.autonomy import StepThreshold, Tier, in_audit_sample
from dw_sales.domain.labelled_cases import LabelledCase
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import MappingStatus, OrderCase
from dw_sales.evals.descriptions import Replayed
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER, READER
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world

from .test_activity import _reading
from .test_labelled_cases import CASE_READER, REPO, _activity, _labels
from .test_model_reading import ANSWERS, LINE_1, SCOPE, _case, _intake

pytestmark = pytest.mark.unit

AT = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)
STEP = ModelStep.DESCRIPTION_ATTRIBUTES
PROMPT = "sales.description_attributes@1.0.0"
LANE_ACTOR = system_actor(AUTO_APPLY_LANE)


def _threshold(score: float | None = 0.9, *, stopped: bool = False) -> StepThreshold:
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


class _Thresholds:
    """`StepThresholdReadPort` holding what a test gives it, for one scope."""

    def __init__(self, scope: SalesScope, found: StepThreshold | None) -> None:
        self.scope, self.found = scope, found

    async def threshold(
        self, scope: SalesScope, step: ModelStep, prompt: str, model_profile: str
    ) -> StepThreshold | None:
        found = self.found
        if scope != self.scope or found is None:
            return None
        return (
            found
            if (found.step, found.prompt, found.model_profile)
            == (
                step,
                prompt,
                model_profile,
            )
            else None
        )

    async def thresholds(self, scope: SalesScope) -> Sequence[StepThreshold]:
        return [] if self.found is None or scope != self.scope else [self.found]


@dataclasses.dataclass
class _Scoring(Replayed):
    """`Replayed`, scored: every value the probability ``score``, or as
    ``scores`` says for a description's attribute."""

    score: float = 0.97
    scores: Mapping[tuple[str, str], float] = dataclasses.field(default_factory=dict)

    async def interpret_scored[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> Scored[OutputT]:
        answer = await self.interpret(
            prompt, inputs, schema, run=run, max_output_tokens=max_output_tokens
        )
        sent = {line["line_no"]: line["description"] for line in json.loads(inputs["lines"])}
        confidences: dict[str, float] = {}
        for index, line in enumerate(answer.model_dump()["lines"]):
            for name in line:
                confidences[f"lines.{index}.{name}"] = self.scores.get(
                    (sent[line["line_no"]], name), self.score
                )
        return Scored(answer, confidences)


async def _m36(model: Any, threshold: StepThreshold | None, scope: SalesScope = SCOPE) -> OrderCase:
    intake = dataclasses.replace(
        _intake(model), autonomy=AutonomyGate(_Thresholds(scope, threshold))
    )
    return await _case(intake, "M36")


def _key(line_no: int) -> str:
    return f"{SCOPE.tenant_id.value}:M36:M36-A1:{line_no}:{STEP.value}"


# --------------------------------------------------------------- the gate --


async def test_a_confident_reading_of_a_certified_step_is_let_apply_itself() -> None:
    case = await _m36(_Scoring(answers=ANSWERS), _threshold(0.9))
    for line_no in (1, 3):
        reading = case.line(line_no).basis.description_reading
        assert reading is not None and reading.confidence == pytest.approx(0.97)
        expected = "audit" if in_audit_sample(_key(line_no), 0.03) else "applied"
        assert reading.gate == expected
    # A line code refused carries no confidence and no gate.
    refused = case.line(2).basis.description_reading
    assert refused is not None and (refused.confidence, refused.gate) == (None, None)


async def test_with_no_threshold_or_below_it_every_line_goes_to_a_person() -> None:
    for threshold in (None, _threshold(None), _threshold(0.98)):
        case = await _m36(_Scoring(answers=ANSWERS), threshold)
        for line_no in (1, 3):
            reading = case.line(line_no).basis.description_reading
            assert reading is not None and reading.gate == "person", threshold


async def test_the_least_sure_label_is_the_lines_confidence() -> None:
    model = _Scoring(answers=ANSWERS, scores={(LINE_1, "colour"): 0.6})
    case = await _m36(model, _threshold(0.9))
    reading = case.line(1).basis.description_reading
    assert reading is not None and reading.confidence == pytest.approx(0.6)
    assert reading.gate == "person"


async def test_a_reading_with_no_token_probabilities_never_applies_itself() -> None:
    case = await _m36(Replayed(answers=ANSWERS), _threshold(0.1))
    reading = case.line(1).basis.description_reading
    assert reading is not None and (reading.confidence, reading.gate) == (None, "person")


async def test_another_tenants_threshold_is_never_read() -> None:
    other = SalesScope(BETA.tenant_id, BETA.workspace_id)
    case = await _m36(_Scoring(answers=ANSWERS), _threshold(0.5), scope=other)
    reading = case.line(1).basis.description_reading
    assert reading is not None and reading.gate == "person"


# ------------------------------------------------------------- the effect --


async def _m05(gate: str = "applied") -> tuple[World, OrderCase]:
    """M05, line 2 (one candidate, CB-2005) read by a model at 0.97 and
    stamped by the gate as ``gate``."""
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    _, case = (await world.process_each(AN, ["M05"]))["M05"]
    assert isinstance(case, OrderCase)
    reading = _reading("read", confidence=0.97, gate=gate)
    lines = tuple(
        line.model_copy(
            update={"basis": line.basis.model_copy(update={"description_reading": reading})}
        )
        if line.line_no == 2
        else line
        for line in case.lines
    )
    case = case.model_copy(update={"lines": lines})
    stored = world.store.state(ALPHA).orders[case.case_id]
    world.store.state(ALPHA).orders[case.case_id] = Stored(case, stored.origin)
    return world, case


def _auto(world: World) -> AutoApply:
    ids = itertools.count(0xA0)
    return AutoApply(
        world.intake,
        FixedClock(AT),
        type("Ids", (), {"new_uuid": staticmethod(lambda: uuid.UUID(int=next(ids)))})(),
    )


async def _apply(world: World, case: OrderCase) -> OrderCase:
    async with world.store(ALPHA) as work:
        applied = await _auto(world).apply(work, ALPHA, case, run_id=None)
        await work.commit()
    return applied


async def _line_view(world: World, case: OrderCase, line_no: int) -> Any:
    view = await world.services.orders.get(AN.context(), case.case_id)
    return next(line for line in view.lines if line.line_no == line_no)


async def test_a_line_let_apply_itself_is_confirmed_as_the_lane_audited_and_shown() -> None:
    world, case = await _m05()
    audits_before = len(world.audit())

    applied = await _apply(world, case)

    mapping = world.order(case.case_id).line(2).mapping
    assert (mapping.status, mapping.prv_code) == (MappingStatus.CANDIDATE_CONFIRMED, "CB-2005")
    assert mapping.confirmed_by == applied_by() == LANE_ACTOR.value
    assert applied.case_version == case.case_version + 1
    (row,) = world.audit()[audits_before:]
    assert (row.action, row.actor_id, row.details["actor"]) == (
        "sales.order.mapping_applied",
        UserId(LANE_ACTOR.value),
        f"system:{AUTO_APPLY_LANE}",
    )
    assert (row.details["line"], row.details["step"]) == (2, STEP.value)
    event = world.store.state(ALPHA).events[-1]
    assert (event.action, event.actor_kind) == ("order.mapping_applied", "worker")
    assert (await _line_view(world, case, 2)).mapping.applied_by_dw
    # Applying is no person's decision: no labelled case.
    assert _labels(world) == []


async def test_undo_puts_the_line_back_and_is_a_labelled_case() -> None:
    world, case = await _m05()
    await _apply(world, case)
    version = world.order(case.case_id).case_version

    with pytest.raises(PermissionDeniedError):
        await world.services.order_commands.undo_applied_mapping(
            READER.context(), case.case_id, 2, case_version=version
        )
    assert _labels(world) == []

    await world.services.order_commands.undo_applied_mapping(
        AN.context(), case.case_id, 2, case_version=version
    )

    line = world.order(case.case_id).line(2)
    assert (line.mapping.status, line.mapping.candidates) == (
        MappingStatus.CANDIDATE,
        ("CB-2005",),
    )
    (label,) = _labels(world)
    assert isinstance(label, LabelledCase)
    assert (label.verdict, label.gate, label.confidence) == ("rejected", "applied", 0.97)
    assert (label.proposed, label.kept, label.decided_by) == (["CB-2005"], None, AN.user_id)
    assert not (await _line_view(world, case, 2)).mapping.applied_by_dw
    # Undone once; a second undo finds nothing DW applied.
    with pytest.raises(ConflictError):
        await world.services.order_commands.undo_applied_mapping(
            AN.context(), case.case_id, 2, case_version=world.order(case.case_id).case_version
        )


async def test_a_code_a_person_confirmed_is_not_undone_as_dws() -> None:
    world, case = await _m05()
    await world.services.order_commands.confirm_mapping(
        AN.context(), case.case_id, 2, case_version=case.case_version, prv_code="CB-2005"
    )
    with pytest.raises(ConflictError):
        await world.services.order_commands.undo_applied_mapping(
            AN.context(), case.case_id, 2, case_version=world.order(case.case_id).case_version
        )
    assert not (await _line_view(world, case, 2)).mapping.applied_by_dw


async def test_a_step_a_person_approves_is_refused_at_the_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whatever the stamp says: the effect asks the tier itself (failure-
    modes #5), so a gate gone wrong cannot apply a step a person approves."""
    world, case = await _m05()
    monkeypatch.setattr(auto_apply_module, "tier_of", lambda step: Tier.PERSON_APPROVES)
    audits_before = len(world.audit())

    async with world.store(ALPHA) as work:
        with pytest.raises(PermissionDeniedError):
            await _auto(world).apply_mapping(work, ALPHA, case, 2, STEP, None)
    after = await _apply(world, case)

    assert after == case
    assert world.order(case.case_id).line(2).mapping.status is MappingStatus.CANDIDATE
    assert world.audit()[audits_before:] == []


@pytest.mark.parametrize("gate", ["person", "audit", "shadow"])
async def test_a_line_not_let_apply_itself_is_left_for_a_person(gate: str) -> None:
    world, case = await _m05(gate)
    after = await _apply(world, case)
    assert after == case
    assert world.order(case.case_id).line(2).mapping.status is MappingStatus.CANDIDATE


async def test_an_audited_line_looks_to_its_person_as_any_other() -> None:
    """Blind (ADR 0015 decided 3): nothing served on the case says a line
    was sampled for the audit rather than below the threshold."""
    audited_world, audited = await _m05("audit")
    person_world, person = await _m05("person")
    seen = (await _line_view(audited_world, audited, 2)).model_dump()
    plain = (await _line_view(person_world, person, 2)).model_dump()
    assert seen == plain


# --------------------------------------------------------------- the lane --


def _seed(world: World, scope: SalesScope, n: int, **gated: Any) -> None:
    base = _labels_of(world, scope)
    for i in range(n):
        base.append(
            LabelledCase(
                label_id=uuid.UUID(int=0x1000 + len(base)),
                decided_at=AT,
                step=STEP,
                lane="order",
                case_id=None,
                customer_code="KMH",
                message_id=f"M{i}",
                attachment_id=None,
                line_no=1,
                field="prv_code",
                proposed=["CB-2005"],
                kept=gated.get("kept", ["CB-2005"]),
                prompt=PROMPT,
                model_profile="onprem",
                rules=None,
                decided_by=AN.user_id,
                confidence=gated.get("confidence", 0.99 - i * 1e-4),
                gate=gated.get("gate", "person"),
            )
        )


def _labels_of(world: World, scope: SalesScope) -> list[LabelledCase]:
    return world.store.state(scope).labelled_cases


def _lane(world: World) -> ThresholdLane:
    ids = itertools.count(0xB0)
    return ThresholdLane(
        labels=world.store,
        thresholds=world.store,
        rules=world.intake.rules,
        clock=FixedClock(AT),
        ids=type("Ids", (), {"new_uuid": staticmethod(lambda: uuid.UUID(int=next(ids)))})(),
    )


async def test_the_lane_sets_a_threshold_from_enough_cases_and_audits_it_moving() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    _seed(world, ALPHA, 40)
    (few,) = await _lane(world).tick(ALPHA)
    assert few.threshold is None and few.cases == 40

    _seed(world, ALPHA, 40)
    (enough,) = await _lane(world).tick(ALPHA)
    assert enough.applying and enough.cases == 80
    stored = await world.store.threshold(ALPHA, STEP, PROMPT, "onprem")
    assert stored == enough
    moved = [e for e in world.audit() if e.action == "sales.autonomy.threshold_set"]
    assert len(moved) == 2
    assert {e.actor_id for e in moved} == {UserId(LANE_ACTOR.value)}

    # Nothing moved: nothing audited again.
    await _lane(world).tick(ALPHA)
    assert len([e for e in world.audit() if e.action == "sales.autonomy.threshold_set"]) == 2


async def test_audits_above_the_target_stop_the_step_and_its_results_go_to_shadow() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    _seed(world, ALPHA, 80)
    # Audited when the threshold was lower: the measure now sets it above
    # them, and their error still stops the step until it is re-measured.
    _seed(world, ALPHA, 7, gate="audit", confidence=0.95)
    _seed(world, ALPHA, 3, gate="audit", confidence=0.95, kept=None)

    (stopped,) = await _lane(world).tick(ALPHA)

    assert stopped.stopped and not stopped.applying
    assert stopped.threshold is not None and stopped.threshold > 0.95
    assert (stopped.audits, stopped.audit_errors) == (10, 3)
    gate = AutonomyGate(world.store)
    route = await gate.route(
        ALPHA,
        await world.intake.rules.rules(ALPHA),
        STEP,
        prompt=PROMPT,
        model_profile="onprem",
        confidence=0.999,
        item_key="any",
    )
    assert route == "shadow"


async def test_one_tenants_cases_set_no_other_tenants_threshold() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    _seed(world, ALPHA, 80)
    await _lane(world).tick(ALPHA)

    assert await _lane(world).tick(BETA) == []
    assert await world.store.thresholds(BETA) == []
    assert await world.store.threshold(BETA, STEP, PROMPT, "onprem") is None
    beta = await AutonomyGate(world.store).route(
        BETA,
        await world.intake.rules.rules(BETA),
        STEP,
        prompt=PROMPT,
        model_profile="onprem",
        confidence=0.999,
        item_key="any",
    )
    assert beta == "person"


# ------------------------------------------------------------ head's view --


async def test_the_heads_view_shows_each_step_its_mode_and_numbers() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    _seed(world, ALPHA, 80)
    await _lane(world).tick(ALPHA)

    view = await _activity(world).autonomy(AN.context())

    steps = {s.step: s for s in view.steps}
    assert set(steps) == set(ModelStep)
    described = steps[STEP]
    assert (described.mode, described.cases, described.needed) == ("applying", 80, 59)
    assert described.threshold is not None and described.target == 0.05
    assert steps[ModelStep.CHANGE_REQUEST].mode == "never"
    assert steps[ModelStep.CHANGE_REQUEST].target is None
    assert steps[ModelStep.MESSAGE_INTENT].mode == "measuring"

    # Another tenant sees none of it; a caller who may not read the summary
    # is refused.
    beta = await _activity(world).autonomy(OUTSIDER.context(BETA))
    assert {s.cases for s in beta.steps} == {0}
    assert {s.mode for s in beta.steps} <= {"never", "measuring"}
    with pytest.raises(PermissionDeniedError):
        await _activity(world).autonomy(CASE_READER.context())
