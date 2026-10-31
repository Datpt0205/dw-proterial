"""The morning brief written by the model (the AI list, item 10): when it is
asked, what it is told, and what code sends of its answer."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    estimated_tokens,
)
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_sales.adapters.policy_files import rule_book
from dw_sales.application.brief_writing import MORNING_BRIEF, PROMPT_TOKENS, BriefWriter
from dw_sales.application.followups import BRIEF, FollowupLane
from dw_sales.domain.followups import SalesFollowups
from dw_sales.evals.graders import AN, CALLERS, GIANG
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world
from dw_sales.evals.world import Directory as Holders

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
_HOUR = timedelta(hours=1)


@dataclass
class Sender:
    calls: list[tuple[tuple[uuid.UUID, ...], str, str]] = field(default_factory=list)

    async def deliver(
        self,
        context: AccessContext,
        *,
        recipients: Sequence[uuid.UUID],
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None:
        if f":{BRIEF}:" in source_key:
            self.calls.append((tuple(recipients), title, body))


class Answering(Recorded):
    def __init__(self, answer: Any) -> None:
        super().__init__(raw={})
        self.answer = answer

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        return schema.model_validate(self.answer(json.loads(inputs["facts"])))


def _first(facts: dict[str, Any]) -> dict[str, Any]:
    case = facts["cases"][0]
    return {"text": f"Bạn nên xử lý {case['reference']} trước: {case['next_step']}"}


def _opening_switched(world: World, on: bool) -> None:
    """ALPHA's own `sales_followups`, the written opening switched as ``on``."""
    document = world.policies.followups.model_dump(mode="json", by_alias=True)
    document["policy_version"] = "9.0.0"
    document["morning_brief"] = {**document["morning_brief"], "model_opening": on}
    world.store.rule_versions.seed_approved(
        ALPHA.tenant_id.value, SalesFollowups.model_validate(document)
    )


async def _brief(model: Any, *, on: bool = True) -> tuple[Sender, World]:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    seen = await world.process_each(AN, ["M01"])
    order_id = seen["M01"][0].case_id
    assert order_id is not None
    _opening_switched(world, on)
    book = rule_book(world.policies, world.store.rule_versions)
    sender = Sender()
    received = world.order(order_id).received_at
    clock = FixedClock(received)
    lane = FollowupLane(
        uow=world.store,
        policies=book,
        holders=Holders(CALLERS),
        notifications=sender,
        clock=clock,
        ids=Uuid4Generator(),
        writer=BriefWriter(
            model=model,
            access=Holders(CALLERS),
            ids=Uuid4Generator(),
            worker_id="sales-dw1",
            worker_version="1.0.0",
        ),
    )
    # The next working morning's brief slot, after the PO arrived.
    for hours in range(1, 72):
        clock.advance_to(received.replace(minute=0, second=0) + hours * _HOUR)
        await lane.tick(ALPHA)
        if sender.calls:
            break
    return sender, world


def _body_of(sender: Sender, person: uuid.UUID) -> str:
    return next(body for recipients, _, body in sender.calls if person in recipients)


async def test_the_brief_opens_with_what_the_model_wrote_and_keeps_its_counts() -> None:
    model = Answering(_first)
    sender, _ = await _brief(model)
    body = _body_of(sender, AN.user_id)
    assert body.startswith("DW1 viết: Bạn nên xử lý VLX-PO-2609-0118 trước")
    assert "hồ sơ mới" in body  # the counts follow, as before
    facts = json.dumps(json.loads(model.calls[0][2]["facts"]))
    assert "price" not in facts and "Velatrix" not in facts  # no amount, no name
    _, run, _ = model.calls[0]
    assert run.actor_id in {AN.user_id, GIANG.user_id}


async def test_a_figure_the_facts_lack_sends_the_plain_brief() -> None:
    sender, _ = await _brief(Answering(lambda _: {"text": "Bạn có 15 đơn quá hạn."}))
    assert not _body_of(sender, AN.user_id).startswith("DW1 viết:")


async def test_a_digital_workers_name_is_no_figure_the_facts_must_hold() -> None:
    def naming(facts: dict[str, Any]) -> dict[str, Any]:
        return {"text": f"DW1 đã đọc {facts['cases'][0]['reference']}, DW2 chưa nhận."}

    sender, _ = await _brief(Answering(naming))
    assert _body_of(sender, AN.user_id).startswith("DW1 viết: DW1 đã đọc VLX-PO-2609-0118")


async def test_the_model_is_not_asked_where_the_opening_is_switched_off() -> None:
    model = Answering(_first)
    sender, _ = await _brief(model, on=False)
    assert sender.calls and model.calls == []
    assert not _body_of(sender, AN.user_id).startswith("DW1 viết:")


async def test_without_a_usable_model_the_plain_brief_goes_out() -> None:
    sender, _ = await _brief(Recorded(failure=ModelUnavailableError("down")))
    assert sender.calls
    assert not _body_of(sender, AN.user_id).startswith("DW1 viết:")


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    from dw_agent_runtime.model.prompts import PromptRegistry

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        MORNING_BRIEF.prompt_id,
        MORNING_BRIEF.version,
        {"facts": ""},
        tenant_id=ALPHA.tenant_id.value,
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS
