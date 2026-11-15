"""The skill a message is read with is picked by one scored call, and code
decides what the pick means (ticket 40, dw_sales ADR 0015 decision 5)."""

from __future__ import annotations

import uuid

import pytest

from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_agent_runtime.model.skills import Skill, SkillSet
from dw_sales.application.skill_pick import NO_SKILL, SKILL_PICK, SkillPicker, pick_schema
from dw_sales.evals.recorded import ScriptedPick
from dw_sales.evals.thread_agent import run_for

pytestmark = pytest.mark.unit

_SKILL = Skill(
    name="thread-intents",
    description="Reading what one message of a mail conversation does.",
    body="Say what the message does.",
    ref="sales_skill_thread_intents@1.0.0",
)
_INPUTS = {"context": "A customer wrote.", "subject": "Re: PO", "body": "Thanks."}


class _NoModels:
    def model_for(self, tenant_id: uuid.UUID) -> str:
        return "qwen"


def _set() -> SkillSet:
    run = run_for()
    return SkillSet(run.tenant_id, run.workspace_id, (_SKILL,))


async def _pick(model: object, floor: float = 0.9) -> object:
    picker = SkillPicker(model, _NoModels())  # type: ignore[arg-type]
    return await picker.pick(_set(), _INPUTS, floor=floor, run=run_for())


def test_the_schema_allows_only_the_served_names_and_none() -> None:
    schema = pick_schema(("thread-intents",))
    assert schema.model_json_schema()["properties"]["skill"]["enum"] == ["thread-intents", "none"]
    with pytest.raises(ValueError):
        schema.model_validate({"skill": "dw1-admin"})


async def test_a_sure_pick_of_a_served_skill_reads_with_it() -> None:
    picked = await _pick(ScriptedPick(None, 0.97))
    assert picked.skill == _SKILL  # type: ignore[attr-defined]
    assert (picked.answered, picked.confidence) == ("thread-intents", 0.97)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("said", "confidence"),
    [
        # A name the set does not serve, whatever the decoder let through.
        ("dw1-admin", 1.0),
        (NO_SKILL, 1.0),
        # Less sure than the tenant's floor, or with no confidence at all.
        (None, 0.89),
        (None, None),
    ],
)
async def test_code_reads_an_unserved_unsure_or_unscored_pick_as_none(
    said: str | None, confidence: float | None
) -> None:
    picked = await _pick(ScriptedPick(said, confidence))
    assert picked.skill is None  # type: ignore[attr-defined]


async def test_no_usable_answer_is_no_pick() -> None:
    class _Down:
        model_profile = "onprem"

        async def interpret_scored(self, *args: object, **kwargs: object) -> object:
            raise ModelUnavailableError("down")

    picked = await _pick(_Down())
    assert (picked.skill, picked.answered) == (None, None)  # type: ignore[attr-defined]


def test_the_pick_prompt_names_its_inputs() -> None:
    from pathlib import Path

    from dw_agent_runtime.model.prompts import PromptRegistry

    prompts = PromptRegistry()
    prompts.load_directory(Path(__file__).resolve().parents[5] / "configs" / "prompts")
    rendered = prompts.render(SKILL_PICK.prompt_id, SKILL_PICK.version, {"skills": "[]", **_INPUTS})
    assert "<input" in rendered.user
