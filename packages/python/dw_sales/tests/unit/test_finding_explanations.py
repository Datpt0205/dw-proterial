"""A finding explained in words by the model (the AI list, item 12): what it
is told, what code refuses of its answer, and who may ask."""

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
from dw_sales.application.finding_explanations import (
    FINDING_EXPLANATION,
    PROMPT_TOKENS,
    ModelExplanation,
    unsupported_figures,
)
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN, CALLERS, READER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
PRICE = "price_mismatch:2"


class Scripted(Recorded):
    """Answers with what ``write`` makes of the facts it is sent."""

    def __init__(self, write: Any) -> None:
        super().__init__(raw={})
        self.write = write

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        return schema.model_validate(self.write(json.loads(inputs["facts"])))


async def _m04(model: Any) -> tuple[World, OrderCase]:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=model)
    _, case = (await world.process_each(AN, ["M04"]))["M04"]
    assert isinstance(case, OrderCase)
    return world, case


def _faithful(facts: dict[str, Any]) -> dict[str, Any]:
    quote = facts["checked_against"]["quotation"]
    line = facts["line"]
    return {
        "explanation": (
            f"Đơn giá trên PO là {line['unit_price']}, báo giá {quote['quote_no']} "
            f"ghi {quote['unit_price']} {quote['currency']}."
        ),
        "check": f"Kiểm báo giá {quote['quote_no']} còn hiệu lực đến {quote['valid_to']}.",
    }


async def test_a_finding_is_explained_from_the_facts_code_gathered() -> None:
    model = Scripted(_faithful)
    world, case = await _m04(model)
    calls = len(model.calls)

    view = await world.services.finding_explanations.explain(AN.context(), case.case_id, PRICE)

    assert view.status == "explained", view
    assert view.explanation is not None and "Đơn giá trên PO" in view.explanation
    assert (view.prompt_ref, view.model_profile) == (str(FINDING_EXPLANATION), "onprem")
    _, run, inputs = model.calls[calls]
    facts = json.loads(inputs["facts"])
    assert facts["finding"]["code"] == "price_mismatch" and facts["line"]["unit_price"]
    assert (run.tenant_id, run.actor_id) == (ALPHA.tenant_id.value, AN.user_id)


async def test_an_answer_with_a_number_no_fact_holds_is_refused() -> None:
    def invented(facts: dict[str, Any]) -> dict[str, Any]:
        return {"explanation": "Khách được giảm 15% nên giá thấp hơn.", "check": None}

    world, case = await _m04(Scripted(invented))
    view = await world.services.finding_explanations.explain(AN.context(), case.case_id, PRICE)
    assert (view.status, view.explanation) == ("refused", None)


def test_a_figure_counts_only_when_a_fact_holds_it() -> None:
    facts = '{"quote_no": "Q26-0104", "unit_price": "0.712", "valid_to": "2026-12-31"}'
    ok = ModelExplanation(explanation="Báo giá Q26-0104 ghi 0.712, hết hạn 2026-12-31.")
    bad = ModelExplanation(explanation="Báo giá Q26-0999 ghi 0.5.")
    assert unsupported_figures(ok, facts) == set()
    assert unsupported_figures(bad, facts) == {"Q26-0999", "0.5"}


async def test_a_price_finding_is_not_explained_to_someone_who_reads_no_price() -> None:
    model = Scripted(_faithful)
    world, case = await _m04(model)
    calls = len(model.calls)
    with pytest.raises(PermissionDeniedError):
        await world.services.finding_explanations.explain(READER.context(), case.case_id, PRICE)
    assert len(model.calls) == calls


async def test_no_amount_reaches_the_model_for_someone_who_reads_no_price() -> None:
    def plain(facts: dict[str, Any]) -> dict[str, Any]:
        return {"explanation": "Mã hàng của khách chưa khớp mã nào.", "check": None}

    model = Scripted(plain)
    world, case = await _m04(model)
    calls = len(model.calls)
    view = await world.services.finding_explanations.explain(
        READER.context(), case.case_id, "code_unmapped:3"
    )
    assert view.status == "explained"
    facts = json.loads(model.calls[calls][2]["facts"])
    assert "unit_price" not in facts.get("line", {})
    assert "unit_price" not in json.dumps(facts.get("checked_against", {}))


async def test_without_a_usable_model_dw1_says_it_could_not_explain() -> None:
    world, case = await _m04(Recorded(failure=ModelUnavailableError("down")))
    view = await world.services.finding_explanations.explain(AN.context(), case.case_id, PRICE)
    assert view.status == "unavailable" and view.explanation is None


async def test_another_tenant_finds_no_case_to_explain() -> None:
    from dw_sales.evals.graders import OUTSIDER

    world, case = await _m04(Scripted(_faithful))
    with pytest.raises(NotFoundError):
        await world.services.finding_explanations.explain(
            OUTSIDER.context(BETA), case.case_id, PRICE
        )


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    from dw_agent_runtime.model.prompts import PromptRegistry

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        FINDING_EXPLANATION.prompt_id,
        FINDING_EXPLANATION.version,
        {"facts": ""},
        tenant_id=ALPHA.tenant_id.value,
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS
