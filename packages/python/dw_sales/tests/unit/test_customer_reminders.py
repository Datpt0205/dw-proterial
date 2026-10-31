"""A reminder to a customer DW1 waits on, drafted by the model (DW01 function
4): what it is told, what code keeps, which cases and who may ask."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    estimated_tokens,
)
from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_sales.application.customer_reminders import CUSTOMER_REMINDER, PROMPT_TOKENS
from dw_sales.domain.dispositions import CaseKind
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER, READER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.replies import correction_case, spec_discussion_case
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


class Answering(Recorded):
    def __init__(self, answer: Any) -> None:
        super().__init__(raw={})
        self.answer = answer

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        return schema.model_validate(self.answer(json.loads(inputs["facts"])))


def _reminding(facts: dict[str, Any]) -> dict[str, Any]:
    reference = facts.get("po_no") or facts["request_no"]
    lines = ", ".join(str(p["line_no"]) for p in facts.get("points_asked", []) if p["line_no"])
    return {
        "subject": f"Nhắc: {reference}",
        "body": (
            f"Kính gửi {facts['customer_name']},\n\nNgày {facts['asked_on']} chúng tôi đã hỏi "
            f"về {reference}" + (f" (dòng {lines})" if lines else "") + ". Mong quý công ty "
            "phản hồi.\n\nPhòng Kinh doanh"
        ),
    }


def _world(model: Any) -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=model, measured=False)


async def test_an_order_awaiting_its_correction_is_reminded_of_the_points_asked() -> None:
    model = Answering(_reminding)
    world = _world(model)
    case_id = await correction_case(world)
    view = await world.services.customer_reminders.draft(AN.context(), CaseKind.ORDER, case_id)
    assert view.status == "drafted", view
    assert view.subject == "Nhắc: NRV-PO-26-0457"
    assert view.to and all(a.endswith("norvanta.example") for a in view.to)
    assert (view.prompt_ref, view.model_profile) == (str(CUSTOMER_REMINDER), "onprem")
    _, run, inputs = model.calls[-1]
    facts = json.loads(inputs["facts"])
    assert facts["waiting_for"] == "corrected_po"
    assert {p["issue"] for p in facts["points_asked"]} == {"price_mismatch", "code_unmapped"}
    # A finding's values (the PO's price, the quotation's) are never told.
    assert "expected" not in inputs["facts"] and "actual" not in inputs["facts"]
    assert (run.tenant_id, run.actor_id) == (ALPHA.tenant_id.value, AN.user_id)


async def test_only_the_points_sent_back_to_the_customer_are_told() -> None:
    model = Answering(_reminding)
    world = _world(model)
    seen = await world.process_each(AN, ["M04"])
    case_id = seen["M04"][0].case_id
    assert case_id is not None
    commands, context = world.services.order_commands, AN.context()
    await commands.dispose(
        context,
        case_id,
        "price_mismatch:2",
        case_version=world.order(case_id).case_version,
        disposition="ask_customer",
    )
    await commands.request_correction(
        context, case_id, case_version=world.order(case_id).case_version
    )
    # `code_unmapped:3` stays Sales' own: still open, never asked of the customer.
    await world.services.customer_reminders.draft(context, CaseKind.ORDER, case_id)
    facts = json.loads(model.calls[-1][2]["facts"])
    assert facts["points_asked"] == [{"issue": "price_mismatch", "line_no": 2}]


async def test_a_quote_whose_spec_is_discussed_is_reminded_of_the_request() -> None:
    model = Answering(_reminding)
    world = _world(model)
    case_id = await spec_discussion_case(world)
    view = await world.services.customer_reminders.draft(AN.context(), CaseKind.QUOTE, case_id)
    assert view.status == "drafted", view
    facts = json.loads(model.calls[-1][2]["facts"])
    assert facts["waiting_for"] == "spec_answer" and "points_asked" not in facts


@pytest.mark.parametrize(
    "text",
    [
        "Đơn giá đúng là 12,5 USD theo báo giá.",
        "Chúng tôi giảm 3% nếu quý công ty xác nhận sớm.",
        "PO NRV-PO-26-0999 còn chờ.",
    ],
)
async def test_an_amount_or_a_figure_the_facts_lack_leaves_no_draft(text: str) -> None:
    model = Answering(lambda facts: {"subject": "Nhắc PO", "body": text})
    world = _world(model)
    case_id = await correction_case(world)
    view = await world.services.customer_reminders.draft(AN.context(), CaseKind.ORDER, case_id)
    assert (view.status, view.body) == ("refused", None)


async def test_only_a_case_waiting_on_the_customer_is_reminded() -> None:
    world = _world(Answering(_reminding))
    seen = await world.process_each(AN, ["M01"])
    case_id = seen["M01"][0].case_id
    assert case_id is not None
    with pytest.raises(ConflictError):
        await world.services.customer_reminders.draft(AN.context(), CaseKind.ORDER, case_id)


async def test_only_who_prepares_and_only_in_the_callers_tenant() -> None:
    world = _world(Answering(_reminding))
    case_id = await correction_case(world)
    with pytest.raises(PermissionDeniedError):
        await world.services.customer_reminders.draft(READER.context(), CaseKind.ORDER, case_id)
    with pytest.raises(NotFoundError):
        await world.services.customer_reminders.draft(
            OUTSIDER.context(BETA), CaseKind.ORDER, case_id
        )
    # The same id under the other kind is no case at all.
    with pytest.raises(NotFoundError):
        await world.services.customer_reminders.draft(AN.context(), CaseKind.QUOTE, case_id)


async def test_no_model_says_so_and_keeps_the_recipients() -> None:
    world = _world(Recorded(failure=ModelUnavailableError("down")))
    case_id = await correction_case(world)
    view = await world.services.customer_reminders.draft(AN.context(), CaseKind.ORDER, case_id)
    assert view.status == "unavailable" and view.to and view.body is None


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    from dw_agent_runtime.model.prompts import PromptRegistry

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        CUSTOMER_REMINDER.prompt_id,
        CUSTOMER_REMINDER.version,
        {"facts": ""},
        tenant_id=ALPHA.tenant_id.value,
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS
