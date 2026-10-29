"""PC's answer on delivery dates, read from the mail Sales pastes (the AI
list, item 7): what the model is told, what code keeps, and who may ask."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import ConflictError, PermissionDeniedError
from dw_sales.application.model_reading import ModelUnavailableError, estimated_tokens
from dw_sales.application.pc_dates import PC_DATES, PROMPT_TOKENS, reads_as
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN, CALLERS, READER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
MAIL = "Chào chị,\nDòng 1 giao được ngày 30/10/2026, dòng 2 ngày 05/11.\nPC"


class Answering(Recorded):
    def __init__(self, answer: Any) -> None:
        super().__init__(raw={})
        self.answer = answer

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        return schema.model_validate(self.answer)


RIGHT = {
    "dates": [
        {"line_no": 1, "delivery": 1, "date_text": "30/10/2026", "date": "2026-10-30"},
        {"line_no": 2, "delivery": 1, "date_text": "05/11", "date": "2026-11-05"},
    ]
}


async def _order(model: Any) -> tuple[World, OrderCase]:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=model, measured=False)
    _, case = (await world.process_each(AN, ["M01"]))["M01"]
    assert isinstance(case, OrderCase)
    return world, case


async def _read(world: World, case: OrderCase, caller: Any = AN, text: str = MAIL) -> Any:
    return await world.services.pc_dates.read(
        caller.context(), case.case_id, case_version=case.case_version, text=text
    )


async def test_pcs_dates_are_read_per_line_with_the_words_they_rest_on() -> None:
    model = Answering(RIGHT)
    world, case = await _order(model)
    view = await _read(world, case)
    assert view.status == "read" and view.dropped == 0
    assert [(d.line_no, d.date, d.quote) for d in view.dates] == [
        (1, date(2026, 10, 30), "30/10/2026"),
        (2, date(2026, 11, 5), "05/11"),
    ]
    assert (view.prompt_ref, view.model_profile) == (str(PC_DATES), "onprem")
    _, run, inputs = model.calls[-1]
    assert [line["line_no"] for line in json.loads(inputs["lines"])] == [
        line.line_no for line in case.lines
    ]
    assert inputs["mail"] == MAIL
    assert (run.tenant_id, run.actor_id) == (ALPHA.tenant_id.value, AN.user_id)


@pytest.mark.parametrize(
    "wrong",
    [
        # Words the mail does not hold.
        {"line_no": 1, "delivery": 1, "date_text": "31/10/2026", "date": "2026-10-31"},
        # Words it holds, read as another day (month before day).
        {"line_no": 2, "delivery": 1, "date_text": "05/11", "date": "2026-05-11"},
        # A line the case does not have, and a delivery its line does not.
        {"line_no": 99, "delivery": 1, "date_text": "30/10/2026", "date": "2026-10-30"},
        {"line_no": 1, "delivery": 2, "date_text": "30/10/2026", "date": "2026-10-30"},
    ],
)
async def test_a_date_the_mail_or_the_case_does_not_bear_out_is_dropped(
    wrong: dict[str, Any],
) -> None:
    world, case = await _order(Answering({"dates": [wrong]}))
    view = await _read(world, case)
    assert (view.status, view.dates, view.dropped) == ("nothing", [], 1)


async def test_a_line_named_twice_keeps_neither_date() -> None:
    twice = {
        "dates": [
            RIGHT["dates"][0],
            {**RIGHT["dates"][0], "date_text": "05/11", "date": "2026-11-05"},
        ]
    }
    world, case = await _order(Answering(twice))
    view = await _read(world, case)
    assert (view.status, view.dropped) == ("nothing", 2)


def test_a_date_reads_as_the_day_it_writes_day_before_month() -> None:
    assert reads_as("30/10/2026", date(2026, 10, 30))
    assert reads_as("2026-10-30", date(2026, 10, 30))
    assert reads_as("30.10.26", date(2026, 10, 30))
    assert reads_as("05/11", date(2026, 11, 5))
    assert not reads_as("05/11", date(2026, 5, 11))
    assert not reads_as("30 tháng 10", date(2026, 10, 30))


async def test_only_who_prepares_the_order_asks_and_only_at_the_version_they_saw() -> None:
    model = Answering(RIGHT)
    world, case = await _order(model)
    calls = len(model.calls)
    with pytest.raises(PermissionDeniedError):
        await _read(world, case, READER)
    with pytest.raises(ConflictError):
        await world.services.pc_dates.read(
            AN.context(), case.case_id, case_version=case.case_version + 1, text=MAIL
        )
    assert len(model.calls) == calls


async def test_without_a_usable_model_dw1_says_it_could_not_read_them() -> None:
    world, case = await _order(Recorded(failure=ModelUnavailableError("down")))
    view = await _read(world, case)
    assert (view.status, view.dates) == ("unavailable", [])


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    from dw_agent_runtime.model.prompts import PromptRegistry

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        PC_DATES.prompt_id,
        PC_DATES.version,
        {"lines": "", "mail": ""},
        tenant_id=ALPHA.tenant_id.value,
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS


def test_a_date_counts_only_when_the_mail_writes_it_whole() -> None:
    from dw_sales.application.pc_dates import written_in

    assert written_in("05/11", "dòng 2 ngày 05/11.")
    assert not written_in("1/11/2026", "giao 01/11/2026")
    assert not written_in("05/11", "giao 05/11/2026")


def test_a_full_stop_ending_the_sentence_is_no_part_of_the_date() -> None:
    from dw_sales.application.pc_dates import written_in

    assert written_in("06/11/2026", "as requested, 06/11/2026.\nPC")
    assert written_in("05/12", "giao được từ 05/12. Các dòng khác")
    assert not written_in("30.10", "ngày 30.10.26")
