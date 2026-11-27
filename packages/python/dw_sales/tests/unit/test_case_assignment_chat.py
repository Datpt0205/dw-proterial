"""A case given to a colleague named in its conversation (ticket 79): DW1 finds
exactly one of the people the case may be given to and says it back; the case
is given only when the head confirms that statement's hash, on that case, at
that version, through "Giao lại" itself, which checks the right again. Nothing
the model writes is an id: it writes a name, which code looks for."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import ConflictError, PermissionDeniedError
from dw_sales.application.chat_prompts import QUESTION_INTENT
from dw_sales.domain.assistant import CaseKey, QuestionKind
from dw_sales.domain.dispositions import CaseKind
from dw_sales.evals.graders import AN, CALLERS, DIEU, GIANG
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


class Reader(Recorded):
    """Reads every question as ``reading``."""

    def __init__(self, reading: dict[str, Any]) -> None:
        super().__init__(raw={})
        self.reading = reading

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        if prompt == QUESTION_INTENT:
            return schema.model_validate(self.reading)
        return schema.model_validate({"answer": "x"})


async def _order(assignee: str | None) -> tuple[World, CaseKey]:
    world = open_world(
        REPO,
        SampleSet.of(REPO, None),
        CALLERS,
        model=Reader({"kind": "assign_case", "assignee": assignee}),
        measured=False,
    )
    ((disposition, _),) = (await world.process_each(AN, ["M01"])).values()
    assert disposition.case_id is not None
    return world, CaseKey(CaseKind.ORDER, disposition.case_id)


def _assignee(world: World, key: CaseKey) -> uuid.UUID | None:
    return world.store.state(ALPHA).orders[key.case_id].origin.assigned_to


async def _ask(world: World, key: CaseKey, who: Any = GIANG) -> Any:
    return (await world.services.assistant.ask(who.context(), "giao cho Diệu nhé", key)).turn


async def test_the_head_names_a_colleague_and_the_case_is_given_only_once_confirmed() -> None:
    world, key = await _order("Diệu")
    assert _assignee(world, key) == AN.user_id

    turn = await _ask(world, key)

    assert turn.kind is QuestionKind.ASSIGN_CASE
    proposal = turn.proposal
    assert proposal is not None and proposal.action == "assign"
    assert proposal.assignee_name == "Hoàng Thị Diệu" and "Hoàng Thị Diệu" in turn.answer
    # Said, not done.
    assert _assignee(world, key) == AN.user_id

    done = await world.services.assistant.confirm(
        GIANG.context(), key, turn.seq, proposal.content_hash
    )

    assert _assignee(world, key) == DIEU.user_id
    assert done.case_version == world.order(key.case_id).case_version


async def test_a_name_no_candidate_has_asks_who_and_states_nothing() -> None:
    world, key = await _order("Ông Không Có")

    turn = await _ask(world, key)

    assert turn.proposal is None and "Hoàng Thị Diệu" in turn.answer


async def test_someone_without_the_right_to_give_cases_is_stated_nothing() -> None:
    world, key = await _order("Diệu")

    turn = await _ask(world, key, who=AN)

    assert turn.proposal is None
    assert _assignee(world, key) == AN.user_id


async def test_a_hash_not_the_statements_gives_nothing() -> None:
    world, key = await _order("Diệu")
    turn = await _ask(world, key)

    with pytest.raises(ConflictError):
        await world.services.assistant.confirm(GIANG.context(), key, turn.seq, "0" * 64)
    assert _assignee(world, key) == AN.user_id


async def test_the_right_is_checked_again_where_the_case_is_given() -> None:
    world, key = await _order("Diệu")
    turn = await _ask(world, key)
    assert turn.proposal is not None
    # The head's right withdrawn between the statement and the confirmation.
    lowered = GIANG.context().model_copy(
        update={"scopes": GIANG.context().scopes - {"sales.case.assign"}}
    )

    with pytest.raises(PermissionDeniedError):
        await world.services.assistant.confirm(lowered, key, turn.seq, turn.proposal.content_hash)
    assert _assignee(world, key) == AN.user_id
