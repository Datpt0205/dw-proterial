"""DW2's three-level switch per step (Đạt, 2026-11-01): the level set, held
to the product's ceiling in code, and `ai_auto` taking effect only once the
step's model reading is measured on the plant's model."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_agent_runtime.model.readiness import Attestation
from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.application.rule_versions import ContextScope
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.automation import ATTEST_LANE, BARS
from dw_purchasing.domain.automation import (
    STEPS,
    AutomationLevel,
    AutomationStep,
    PurchasingAutomation,
    PurchasingModelStep,
)
from dw_purchasing.testing.world import ALPHA, BETA, EVERY_SCOPE, World, caller, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
ANSWERS = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)["answers"]
HEAD = uuid.UUID(int=0x4EAD)
CONFIGURER = uuid.UUID(int=0xC0F)


def _world() -> World:
    return open_world(REPO, ANSWERS)


def _head(scope: tuple[uuid.UUID, uuid.UUID] = ALPHA) -> Any:
    return caller(scope, scopes=EVERY_SCOPE | {"approvals.decide"}, principal=HEAD)


def _switches(version: str, **levels: str) -> dict[str, Any]:
    steps = {step.value: AutomationLevel.AI_REVIEW.value for step in AutomationStep}
    steps |= {AutomationStep.SUBMISSION.value: AutomationLevel.AI_AUTO.value}
    return {"policy_version": version, "steps": steps | levels}


async def _measure(world: World, scope: tuple[uuid.UUID, uuid.UUID], value: float) -> None:
    attest = Attestation(
        world.measurements,
        world.clock,
        _Ids(),
        BARS,
        lane=ATTEST_LANE,
        action="purchasing.model_step.measured",
        resource_type="purchasing_model_step_measurement",
    )
    await attest.attest(
        ContextScope(TenantId(scope[0]), WorkspaceId(scope[1])),
        PurchasingModelStep.PR_MAIL_READING,
        model="qwen3.5:9b",
        value=value,
        held=True,
        dataset="purchasing_pr_intake@1.0.0",
    )


class _Ids:
    def new_uuid(self) -> uuid.UUID:
        return uuid.uuid4()


def test_a_step_above_its_ceiling_is_no_version() -> None:
    assert STEPS[AutomationStep.RFQ].ceiling is AutomationLevel.AI_REVIEW
    with pytest.raises(ValidationError, match="above what the product allows"):
        PurchasingAutomation.model_validate(_switches("9.0.0", rfq="ai_auto"))
    with pytest.raises(ValidationError, match="every step has a level"):
        PurchasingAutomation.model_validate({"policy_version": "9.0.0", "steps": {}})


async def test_the_platforms_switches_run_unmeasured_readings_at_ai_review() -> None:
    world = _world()
    view = await world.switches.view(caller())
    levels = {s.step: (s.chosen, s.level, s.why) for s in view.steps}
    assert levels[AutomationStep.PR_DRAFTING] == (
        AutomationLevel.AI_AUTO,
        AutomationLevel.AI_REVIEW,
        "not_measured",
    )
    # A step that is code's alone needs no measurement.
    assert levels[AutomationStep.SUBMISSION] == (
        AutomationLevel.AI_AUTO,
        AutomationLevel.AI_AUTO,
        "set",
    )
    assert levels[AutomationStep.RFQ] == (
        AutomationLevel.AI_REVIEW,
        AutomationLevel.AI_REVIEW,
        "set",
    )
    drafting = next(s for s in view.steps if s.step is AutomationStep.PR_DRAFTING)
    assert drafting.waiting_on == [PurchasingModelStep.PR_MAIL_READING]


async def test_a_pass_at_the_bar_lets_ai_auto_take_effect_for_that_tenant_only() -> None:
    world = _world()
    await _measure(world, ALPHA, 0.95)
    mine = await world.switches.level(caller(), AutomationStep.PR_DRAFTING)
    theirs = await world.switches.level(caller(BETA), AutomationStep.PR_DRAFTING)
    assert (mine.level, mine.why) == (AutomationLevel.AI_AUTO, "set")
    assert (theirs.level, theirs.why) == (AutomationLevel.AI_REVIEW, "not_measured")


async def test_a_pass_below_the_bar_is_not_one() -> None:
    world = _world()
    await _measure(world, ALPHA, BARS[PurchasingModelStep.PR_MAIL_READING].bar - 0.01)
    assert (
        await world.switches.level(caller(), AutomationStep.PR_DRAFTING)
    ).level is AutomationLevel.AI_REVIEW


async def test_raising_a_step_to_ai_auto_before_it_is_measured_is_refused() -> None:
    world = _world()
    # Lowered first (a head's own version applies at once, and lowering is
    # never refused).
    lowered = await world.rules.propose(_head(), "purchasing_automation", _switches("9.0.0"))
    assert lowered.status == "approved"
    with pytest.raises(ConflictError) as refused:
        await world.rules.propose(
            _head(), "purchasing_automation", _switches("9.0.1", pr_drafting="ai_auto")
        )
    assert refused.value.details["rule"] == "model_bar_unmet"
    assert "purchasing_pr_mail_reading" in str(refused.value)
    await _measure(world, ALPHA, 0.95)
    raised = await world.rules.propose(
        _head(), "purchasing_automation", _switches("9.0.1", pr_drafting="ai_auto")
    )
    assert raised.status == "approved"


async def test_an_approval_decided_after_its_measurement_fails_is_not_applied() -> None:
    world = _world()
    await world.rules.propose(_head(), "purchasing_automation", _switches("9.0.0"))
    await _measure(world, ALPHA, 0.95)
    configurer = caller(
        scopes=frozenset({PurchasingScopes.RULES_PROPOSE.value}), principal=CONFIGURER
    )
    asked = await world.rules.propose(
        configurer, "purchasing_automation", _switches("9.0.1", pr_drafting="ai_auto")
    )
    approval_id = asked.approval_id or uuid.UUID(int=0)
    request = world.store.rows(*ALPHA).approvals[approval_id]
    await world.rule_decisions.check(request, ProposedDecision(True, "ok", {}, None), _head())
    world.store.decide(
        approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=True,
        decided_by=HEAD,
        at=world.clock.now(),
        comment="ok",
    )
    # A newer measurement fails before the worker carries the decision out.
    world.clock.advance_to(world.clock.now() + timedelta(hours=1))
    await _measure(world, ALPHA, 0.5)
    settled = await world.rule_settlement.settle(approval_id, _head())
    assert settled.status == "rejected"
    assert "chưa có lần đo đạt ngưỡng" in (settled.comment or "")
    assert (
        await world.switches.level(caller(), AutomationStep.PR_DRAFTING)
    ).chosen is AutomationLevel.AI_REVIEW


def test_the_assembly_checks_every_door_a_version_goes_through() -> None:
    """The service a person proposes through, the API's decision guard and
    the worker's settlement each carry the switches' check: a door built
    without it would let `ai_auto` in unmeasured (failure-modes #5)."""
    from dw_kernel.ports import SystemClock, Uuid4Generator
    from dw_purchasing.adapters import assembly
    from dw_purchasing.application.automation import AutomationChecks
    from dw_purchasing.application.ports import NoNotices

    services = assembly.build_purchasing(
        demo_scope=ALPHA,
        configs=REPO / "configs",
        session_factory=None,  # type: ignore[arg-type]  # nothing is read while building
        audit=None,  # type: ignore[arg-type]
        approvals=None,  # type: ignore[arg-type]
        authorization=None,  # type: ignore[arg-type]
        model=None,
        clock=SystemClock(),
        ids=Uuid4Generator(),
        deployed=True,
        notices=NoNotices(),
    )
    assert services.orders.deployed
    guard = assembly.rule_decisions(REPO / "configs", None, None, None)  # type: ignore[arg-type]
    settlement = assembly.rule_settlement(
        REPO / "configs",
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        SystemClock(),
        Uuid4Generator(),
    )
    for door in (services.rules, guard, settlement):
        assert isinstance(door.checks, AutomationChecks), door
