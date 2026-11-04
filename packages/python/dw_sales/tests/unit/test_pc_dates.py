"""PC's answer on delivery dates, read from the mail Sales pastes (the AI
list, item 7): what the model is told, what code keeps, and who may ask."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    estimated_tokens,
)
from dw_kernel.errors import ConflictError, PermissionDeniedError
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


# ------------------------------------------------- PC's mail in the mailbox --

PASSED = {"spf": "pass", "dkim": "pass", "dmarc": "pass"}
FAILED = {"spf": "fail", "dkim": "fail", "dmarc": "fail"}
# M01's PO: VLX-PO-2609-0118, from velatrix.example.
PC_MAIL = {
    "message_id": "PC01",
    "sender": "pc@proterial.example",
    "subject": "Re: ngày giao VLX-PO-2609-0118",
    "received_at": "2026-10-28T09:00:00+07:00",
    "body": MAIL,
    "authentication": PASSED,
}
OTHERS = [
    PC_MAIL,
    # The customer's own mail naming its PO: not PC's answer.
    {**PC_MAIL, "message_id": "PC02", "sender": "an.trinh@velatrix.example"},
    # A mail the mail system did not verify.
    {**PC_MAIL, "message_id": "PC03", "authentication": FAILED},
    # A mail about another order.
    {**PC_MAIL, "message_id": "PC04", "subject": "Ngày giao VLX-PO-2609-0999"},
]


async def _order_with(model: Any) -> tuple[World, OrderCase, Any]:
    from dw_sales.evals.world import SampleWith

    sample = SampleWith(OTHERS)
    data = sample.__enter__()
    world = open_world(REPO, data, CALLERS, model=model, measured=False)
    _, case = (await world.process_each(AN, ["M01"]))["M01"]
    assert isinstance(case, OrderCase)
    return world, case, sample


async def test_the_mails_naming_the_order_s_po_are_listed_verified_and_not_the_customer_s() -> None:
    world, case, sample = await _order_with(Answering(RIGHT))
    try:
        listed = await world.services.pc_dates.mails(AN.context(), case.case_id)
        assert [m.message_id for m in listed] == ["PC01"]
        assert listed[0].sender == "pc@proterial.example"
    finally:
        sample.__exit__(None, None, None)


async def test_dates_are_read_from_a_listed_mail_as_from_a_pasted_one() -> None:
    model = Answering(RIGHT)
    world, case, sample = await _order_with(model)
    try:
        view = await world.services.pc_dates.read_mail(
            AN.context(), case.case_id, "PC01", case_version=case.case_version
        )
        assert view.status == "read"
        assert [(d.line_no, d.date) for d in view.dates] == [
            (1, date(2026, 10, 30)),
            (2, date(2026, 11, 5)),
        ]
        _, _, inputs = model.calls[-1]
        # The mail's newest part: its subject, then what PC wrote.
        assert inputs["mail"].endswith(MAIL) and "VLX-PO-2609-0118" in inputs["mail"]
    finally:
        sample.__exit__(None, None, None)


@pytest.mark.parametrize("message_id", ["PC02", "PC03", "PC04", "M01", "nope"])
async def test_a_mail_not_listed_is_not_read(message_id: str) -> None:
    from dw_kernel.errors import NotFoundError

    model = Answering(RIGHT)
    world, case, sample = await _order_with(model)
    try:
        calls = len(model.calls)
        with pytest.raises(NotFoundError):
            await world.services.pc_dates.read_mail(
                AN.context(), case.case_id, message_id, case_version=case.case_version
            )
        assert len(model.calls) == calls
    finally:
        sample.__exit__(None, None, None)


async def test_only_who_prepares_the_order_lists_or_reads_pc_s_mail() -> None:
    model = Answering(RIGHT)
    world, case, sample = await _order_with(model)
    try:
        with pytest.raises(PermissionDeniedError):
            await world.services.pc_dates.mails(READER.context(), case.case_id)
        with pytest.raises(PermissionDeniedError):
            await world.services.pc_dates.read_mail(
                READER.context(), case.case_id, "PC01", case_version=case.case_version
            )
    finally:
        sample.__exit__(None, None, None)


async def test_the_mail_the_order_came_in_is_never_pc_s_answer() -> None:
    """A PO a Sales address forwarded names no customer by its sender: the
    case's own mail is left out all the same."""
    import dataclasses
    from datetime import UTC, datetime

    from dw_sales.application.ports import Snapshot

    class NoCustomer:
        def __init__(self, inner: Any) -> None:
            self.inner = inner

        async def customer_by_sender(self, scope: Any, address: str) -> Any:
            return Snapshot(None, datetime(2026, 10, 1, tzinfo=UTC))

    world, case, sample = await _order_with(Answering(RIGHT))
    try:
        reader = world.services.pc_dates
        blind = dataclasses.replace(reader, catalog=NoCustomer(reader.catalog))
        listed = [m.message_id for m in await blind.mails(AN.context(), case.case_id)]
        assert "M01" not in listed and "PC01" in listed
    finally:
        sample.__exit__(None, None, None)


async def test_another_tenant_lists_no_mail_of_ours_and_reads_none() -> None:
    from dw_kernel.errors import NotFoundError
    from dw_sales.evals.graders import OUTSIDER
    from dw_sales.evals.world import BETA

    model = Answering(RIGHT)
    world, case, sample = await _order_with(model)
    try:
        calls = len(model.calls)
        with pytest.raises(NotFoundError):
            await world.services.pc_dates.mails(OUTSIDER.context(BETA), case.case_id)
        with pytest.raises(NotFoundError):
            await world.services.pc_dates.read_mail(
                OUTSIDER.context(BETA), case.case_id, "PC01", case_version=case.case_version
            )
        assert len(model.calls) == calls
    finally:
        sample.__exit__(None, None, None)
