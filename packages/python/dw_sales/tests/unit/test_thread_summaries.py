"""A case's mail thread summarised by the model (the AI list, item 8): what
it reads, what code keeps of its answer, and who may ask."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    estimated_tokens,
)
from dw_kernel.errors import NotFoundError, PermissionDeniedError
from dw_sales.application.thread_summaries import (
    PROMPT_TOKENS,
    THREAD_SUMMARY,
    ModelThreadSummary,
    checked,
)
from dw_sales.domain.dispositions import CaseKind
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


class Answering(Recorded):
    def __init__(self, answer: Any) -> None:
        super().__init__(raw={})
        self.answer = answer

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        return schema.model_validate(self.answer(json.loads(inputs["thread"])))


async def _thread(model: Any) -> tuple[World, Any]:
    """M04, NRV's PO, and M07, its revision: one case, two mails."""
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=model, measured=False)
    seen = await world.process_each(AN, ["M04", "M07"])
    case = seen["M04"][1]
    assert case is not None and seen["M07"][0].case_id == case.case_id
    return world, case


def _faithful(thread: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "points": [
            {"text": f"Khách gửi PO, rồi gửi bản sửa ({m['mail_id']}).", "cites": [m["mail_id"]]}
            for m in thread
        ]
    }


async def test_the_thread_is_summarised_point_by_point_each_citing_its_mail() -> None:
    model = Answering(_faithful)
    world, case = await _thread(model)
    view = await world.services.thread_summaries.summarize(
        AN.context(), CaseKind.ORDER, case.case_id
    )
    assert view.status == "summarized" and view.mails == 2 and view.dropped == 0
    assert [p.cites for p in view.points] == [["M04"], ["M07"]]
    assert (view.prompt_ref, view.model_profile) == (str(THREAD_SUMMARY), "onprem")
    _, run, inputs = model.calls[-1]
    assert [m["mail_id"] for m in json.loads(inputs["thread"])] == ["M04", "M07"]
    assert (run.tenant_id, run.actor_id) == (ALPHA.tenant_id.value, AN.user_id)


def test_a_point_citing_another_mail_or_a_figure_its_mails_lack_is_dropped() -> None:
    mails = {"M1": "PO NRV-PO-26-0457, 500 m", "M2": "Rev1: 600 m"}
    answer = ModelThreadSummary.model_validate(
        {
            "points": [
                {"text": "PO NRV-PO-26-0457 đặt 500 m.", "cites": ["M1"]},
                {"text": "Bản sửa nâng lên 600 m.", "cites": ["M2"]},
                # The figure is the other mail's.
                {"text": "Bản sửa đặt 500 m.", "cites": ["M2"]},
                # A mail the thread does not hold, and none at all.
                {"text": "Khách đã xác nhận.", "cites": ["M9"]},
                {"text": "Khách đã xác nhận.", "cites": []},
            ]
        }
    )
    kept, dropped = checked(answer, mails)
    assert [p.text for p in kept] == ["PO NRV-PO-26-0457 đặt 500 m.", "Bản sửa nâng lên 600 m."]
    assert dropped == 3


async def test_an_answer_with_no_point_left_is_refused() -> None:
    def invented(thread: list[dict[str, str]]) -> dict[str, Any]:
        return {"points": [{"text": "Khách được giảm 15%.", "cites": ["M04"]}]}

    world, case = await _thread(Answering(invented))
    view = await world.services.thread_summaries.summarize(
        AN.context(), CaseKind.ORDER, case.case_id
    )
    assert (view.status, view.points, view.dropped) == ("refused", [], 1)


async def test_someone_who_reads_no_case_neither_asks_nor_is_answered() -> None:
    model = Answering(_faithful)
    world, case = await _thread(model)
    calls = len(model.calls)
    no_case = AN.context().model_copy(update={"scopes": frozenset({"sales.overview.read"})})
    with pytest.raises(PermissionDeniedError):
        await world.services.thread_summaries.summarize(no_case, CaseKind.ORDER, case.case_id)
    assert len(model.calls) == calls


async def test_another_tenant_finds_no_case_to_summarise() -> None:
    world, case = await _thread(Answering(_faithful))
    with pytest.raises(NotFoundError):
        await world.services.thread_summaries.summarize(
            OUTSIDER.context(BETA), CaseKind.ORDER, case.case_id
        )


async def test_without_a_usable_model_dw1_says_it_could_not_summarise() -> None:
    world, case = await _thread(Recorded(failure=ModelUnavailableError("down")))
    view = await world.services.thread_summaries.summarize(
        AN.context(), CaseKind.ORDER, case.case_id
    )
    assert (view.status, view.points) == ("unavailable", [])


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    from dw_agent_runtime.model.prompts import PromptRegistry

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        THREAD_SUMMARY.prompt_id,
        THREAD_SUMMARY.version,
        {"thread": ""},
        tenant_id=ALPHA.tenant_id.value,
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS


def test_a_figure_counts_whole_or_as_a_whole_part_never_as_a_substring() -> None:
    from dw_agent_runtime.model.figure_check import unsupported

    source = "Hạn 2026-10-09, đơn giá 0.79, PO NRV-PO-26-0457"
    assert unsupported("trước ngày 9 tháng 10 năm 2026", source) == set()
    assert unsupported("PO NRV-PO-26-0457, đơn giá 0.79", source) == set()
    assert unsupported("giảm 7%, còn 045", source) == {"7", "045"}
