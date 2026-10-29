"""A mail asking the customer about an unordered quotation, drafted by the
model (the AI list, item 11): what it is told, what code keeps, who may ask."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import NotFoundError, PermissionDeniedError
from dw_sales.application.model_reading import ModelUnavailableError, estimated_tokens
from dw_sales.application.screening_followups import PROMPT_TOKENS, SCREENING_FOLLOWUP
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER, READER
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
        return schema.model_validate(self.answer(json.loads(inputs["facts"])))


def _asking(facts: dict[str, Any]) -> dict[str, Any]:
    quote = facts["quotations"][0]
    return {
        "subject": f"Báo giá {quote['quote_no']} cho mã {facts['item_code']}",
        "body": (
            f"Kính gửi {facts['customer_name']},\n\nBáo giá {quote['quote_no']} còn hiệu lực "
            f"đến {quote['valid_to']}. Quý công ty còn dự định đặt hàng không?\n\nPhòng Kinh doanh"
        ),
    }


def _world(model: Any) -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=model, measured=False)


async def test_the_draft_asks_about_the_quotation_from_the_facts_code_gathered() -> None:
    model = Answering(_asking)
    view = await _world(model).services.screening_followups.draft(AN.context(), "NRV", "CB-2006")
    assert view.status == "drafted", view
    assert view.subject == "Báo giá Q26-0123 cho mã CB-2006"
    assert view.to and all(a.endswith("norvanta.example") for a in view.to)
    assert (view.prompt_ref, view.model_profile) == (str(SCREENING_FOLLOWUP), "onprem")
    _, run, inputs = model.calls[-1]
    facts = inputs["facts"]
    assert "Q26-0123" in facts and "price" not in facts and "unit_price" not in facts
    assert (run.tenant_id, run.actor_id) == (ALPHA.tenant_id.value, AN.user_id)


@pytest.mark.parametrize(
    "text",
    [
        "Chúng tôi giảm 5% nếu quý công ty đặt trong tháng này.",
        "Báo giá Q26-0999 sắp hết hạn.",
    ],
)
async def test_a_figure_the_facts_lack_leaves_no_draft(text: str) -> None:
    model = Answering(lambda facts: {"subject": "Hỏi về báo giá", "body": text})
    view = await _world(model).services.screening_followups.draft(AN.context(), "NRV", "CB-2006")
    assert (view.status, view.body) == ("refused", None)


async def test_only_a_row_of_the_screening_is_drafted_and_only_by_who_prepares_quotes() -> None:
    world = _world(Answering(_asking))
    with pytest.raises(NotFoundError):
        await world.services.screening_followups.draft(AN.context(), "VLX", "CB-2006")
    with pytest.raises(PermissionDeniedError):
        await world.services.screening_followups.draft(READER.context(), "NRV", "CB-2006")
    with pytest.raises(NotFoundError):
        await world.services.screening_followups.draft(OUTSIDER.context(BETA), "NRV", "CB-2006")


async def test_without_a_usable_model_dw1_says_it_could_not_draft() -> None:
    world = _world(Recorded(failure=ModelUnavailableError("down")))
    view = await world.services.screening_followups.draft(AN.context(), "NRV", "CB-2006")
    assert (view.status, view.subject) == ("unavailable", None)


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    from dw_agent_runtime.model.prompts import PromptRegistry

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        SCREENING_FOLLOWUP.prompt_id,
        SCREENING_FOLLOWUP.version,
        {"facts": ""},
        tenant_id=ALPHA.tenant_id.value,
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS


@pytest.mark.parametrize(
    "text, amount",
    [
        ("Báo giá Q26-0123 còn hiệu lực đến 31/12/2026.", False),
        ("giảm 5%", True),
        ("値引き5\uff05", True),
        ("単価は100円です", True),
        ("0.65 USD per metre", True),
    ],
)
def test_an_amount_is_seen_in_any_of_the_customers_languages(text: str, amount: bool) -> None:
    from dw_sales.application.screening_followups import _AMOUNT

    assert bool(_AMOUNT.search(text)) is amount
