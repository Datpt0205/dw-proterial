"""A customer suggested for a sender no domain matched (the AI list, item 5):
what code lets the model choose from, what it refuses of the answer, and what
Sales' confirmation records."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_sales.application.model_reading import ModelUnavailableError, estimated_tokens
from dw_sales.application.sender_customers import (
    PROMPT_TOKENS,
    SENDER_CUSTOMER,
    candidates,
    distinctive_words,
)
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER, READER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, BETA, SampleWith, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
FIXTURE = json.loads(
    (REPO / "evals/fixtures/cases/sales_sender_customers.json").read_text(encoding="utf-8")
)


def spec(message: dict[str, Any]) -> dict[str, Any]:
    """A fixture message as `SampleWith` takes it, with the M15 order."""
    attached = {**FIXTURE["attachment"], "file": str(REPO / FIXTURE["attachment"]["file"])}
    return {
        "message_id": message["message_id"],
        "sender": message["sender"],
        "subject": message["subject"],
        "received_at": "2026-10-28T09:00:00+07:00",
        "body": message["body"],
        "authentication": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
        "attachments": [{**attached, "attachment_id": f"{message['message_id']}-A1"}],
    }


class Answering(Recorded):
    """Answers what ``answer`` makes of the inputs it is sent."""

    def __init__(self, answer: Any) -> None:
        super().__init__(raw={})
        self.answer = answer

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        return schema.model_validate(self.answer(inputs))


def _brennic(inputs: dict[str, str]) -> dict[str, Any]:
    return {"customer_code": "BRN", "company": "Công ty TNHH Brennic Việt Nam"}


@contextmanager
def routed(model: Any, *messages: dict[str, Any]) -> Iterator[World]:
    """A world whose mailbox holds ``messages``, each processed (and routed
    `customer_unknown`) before the test begins."""
    with SampleWith([spec(m) for m in messages]) as sample:
        world = open_world(REPO, sample, CALLERS, model=model, measured=False)
        yield world


async def _process(world: World, message_id: str) -> None:
    disposition, _ = (await world.process_each(AN, [message_id]))[message_id]
    assert disposition.reason == "customer_unknown", disposition


S01 = FIXTURE["golden"][0]


async def test_only_a_word_no_other_customer_holds_makes_a_candidate() -> None:
    from dw_sales.adapters.mock.catalog import MockSalesCatalog

    customers = (await MockSalesCatalog.load(ALPHA).customers(ALPHA)).data
    own = distinctive_words(customers)
    assert "brennic" in own["BRN"] and "vietnam" not in own["BRN"]
    assert [c.code for c in candidates(customers, "Regards, Brennic team")] == ["BRN"]
    assert candidates(customers, "Co., Ltd. Vietnam") == []


async def test_a_sender_is_suggested_the_customer_its_signature_names() -> None:
    model = Answering(_brennic)
    with routed(model, S01) as world:
        await _process(world, "S01")
        view = await world.services.sender_customers.suggest(AN.context(), "S01")
    assert (view.status, view.customer_code) == ("suggested", "BRN"), view
    assert view.evidence == "Công ty TNHH Brennic Việt Nam"
    assert (view.prompt_ref, view.model_profile) == (str(SENDER_CUSTOMER), "onprem")
    _, run, inputs = model.calls[-1]
    assert inputs["candidates"] == "BRN: Công ty TNHH Brennic Việt Nam"
    assert (run.tenant_id, run.actor_id) == (ALPHA.tenant_id.value, AN.user_id)


@pytest.mark.parametrize(
    "answer",
    [
        # Words the mail does not hold.
        {"customer_code": "BRN", "company": "Brennic Holdings"},
        # A customer code was not a candidate.
        {"customer_code": "VLX", "company": "Brennic"},
        # Words in the mail that name no distinctive word of the customer.
        {"customer_code": "BRN", "company": "Phòng Mua hàng"},
    ],
)
async def test_an_answer_the_mail_does_not_bear_out_is_no_suggestion(answer: Any) -> None:
    with routed(Answering(lambda _: answer), S01) as world:
        await _process(world, "S01")
        view = await world.services.sender_customers.suggest(AN.context(), "S01")
    assert (view.status, view.customer_code) == ("no_match", None), view


async def test_confirming_records_the_sender_and_processes_the_mail_again() -> None:
    second = {**S01, "message_id": "S01b", "subject": "PO tháng 12"}
    with routed(Answering(_brennic), S01, second) as world:
        await _process(world, "S01")
        job = await world.services.sender_customers.confirm(AN.context(), "S01", "BRN")
        assert job.message_id == "S01"
        assert await world.drain() == 1
        disposition = next(
            m.disposition
            for m in await world.services.inbox.messages(AN.context())
            if m.message_id == "S01"
        )
        later, _ = (await world.process_each(AN, ["S01b"]))["S01b"]
        actions = [e.action for e in world.audit()]
    assert disposition.customer_code == "BRN" and disposition.reason != "customer_unknown"
    assert later.customer_code == "BRN" and later.reason != "customer_unknown"
    assert "sales.message.customer_confirmed" in actions


async def test_only_a_message_routed_for_want_of_a_customer_is_matched() -> None:
    with routed(Answering(_brennic), S01) as world:
        await world.process_each(AN, ["M01"])
        with pytest.raises(ConflictError):
            await world.services.sender_customers.suggest(AN.context(), "M01")
        with pytest.raises(ConflictError):
            await world.services.sender_customers.confirm(AN.context(), "M01", "BRN")


async def test_someone_who_cannot_process_mail_neither_asks_nor_confirms() -> None:
    model = Answering(_brennic)
    with routed(model, S01) as world:
        await _process(world, "S01")
        calls = len(model.calls)
        with pytest.raises(PermissionDeniedError):
            await world.services.sender_customers.suggest(READER.context(), "S01")
        with pytest.raises(PermissionDeniedError):
            await world.services.sender_customers.confirm(READER.context(), "S01", "BRN")
        assert len(model.calls) == calls


async def test_another_tenant_finds_no_message_to_match() -> None:
    with routed(Answering(_brennic), S01) as world:
        await _process(world, "S01")
        with pytest.raises(NotFoundError):
            await world.services.sender_customers.suggest(OUTSIDER.context(BETA), "S01")
        with pytest.raises(NotFoundError):
            await world.services.sender_customers.confirm(OUTSIDER.context(BETA), "S01", "BRN")


async def test_without_a_usable_model_dw1_says_it_could_not_read_it() -> None:
    with routed(Recorded(failure=ModelUnavailableError("down")), S01) as world:
        await _process(world, "S01")
        view = await world.services.sender_customers.suggest(AN.context(), "S01")
    assert (view.status, view.customer_code) == ("unavailable", None)


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    from dw_agent_runtime.model.prompts import PromptRegistry

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        SENDER_CUSTOMER.prompt_id,
        SENDER_CUSTOMER.version,
        {"mail": "", "candidates": ""},
        tenant_id=ALPHA.tenant_id.value,
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS
