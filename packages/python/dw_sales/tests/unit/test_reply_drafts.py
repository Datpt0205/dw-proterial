"""A mail to a customer about an order worded by the model beside the
template's draft (ticket 32): what it is told, what code keeps, when it is
offered and who may ask.

Over the in-memory world with the fictional M04 order (NRV-PO-26-0457) as
`dw_sales.evals.reply_drafts` walks it: confirmed with every line on
2026-12-04, a synthetic reply asking when line 2 is delivered (read `asks`),
and a B03-shaped reply pulling line 2 in to 2026-11-20 that PC answers.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import ModelUnavailableError, estimated_tokens
from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_sales.application.reply_drafts import (
    PROMPT_TOKENS,
    REPLY_DRAFT,
    REPLY_KINDS,
    check_reply,
)
from dw_sales.domain.order_checks import ModelStep
from dw_sales.evals.graders import AN, OUTSIDER, READER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.reply_drafts import (
    ASKED,
    LATER,
    PO,
    QUESTIONS,
    answered_by_pc,
    confirmed,
    drafting_world,
    pull_in,
    reply,
    sample_for,
)
from dw_sales.evals.world import ALPHA, BETA, World

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
QUESTION = QUESTIONS["en"]
CONTACTS = ["hana.westbrook@norvanta.example", "po-desk@norvanta.example"]


class Writing(Recorded):
    """The model under test: writes what ``answer`` makes of the facts."""

    def __init__(self, answer: Any) -> None:
        super().__init__(raw={})
        self.answer = answer

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        return schema.model_validate(self.answer(json.loads(inputs["facts"])))


def _quoting(facts: dict[str, Any]) -> dict[str, str]:
    """A mail stating only facts: the PO and line 2's dates as given."""
    (line,) = [x for x in facts["lines"] if x["line_no"] == 2]
    dates = [d["date"] for key in ("confirmed", "deliveries") for d in line.get(key, [])]
    return {"subject": f"PO {facts['po_no']}", "body": f"Line 2: {', '.join(dates)}."}


def _says(body: str) -> Writing:
    return Writing(lambda facts: {"subject": f"PO {facts['po_no']}", "body": body})


def _facts(model: Recorded) -> dict[str, Any]:
    facts: dict[str, Any] = json.loads(model.calls[-1][2]["facts"])
    return facts


async def _asked(world: World) -> uuid.UUID:
    case_id = await confirmed(world)
    await world.process_each(AN, ["R2"])
    return case_id


async def _draft(world: World, case_id: uuid.UUID, kind: Any, **kw: Any) -> Any:
    context = kw.pop("context", AN.context())
    return await world.services.reply_drafts.draft(context, case_id, kind, **kw)


def _question_sample() -> Any:
    return sample_for("en", pull_in(), reply("R2", body=QUESTION, hour=11))


# ------------------------------------------------------------- the check --


def test_the_check_keeps_only_figures_the_facts_hold_and_no_amount_or_address() -> None:
    facts = json.dumps({"po_no": PO, "lines": [{"line_no": 2, "date": "04 Dec 2026"}]})
    kept = check_reply(f"PO {PO}\nLine 2 ships on 04 Dec 2026.", facts)
    assert (kept.refusal, kept.figures) == (None, 4)
    assert check_reply("Line 2 ships on 05 Dec 2026.", facts).unsupported == ("05",)
    assert check_reply("Line 2: 2 USD.", facts).refusal == "amount"
    assert check_reply("Line 2: 2%.", facts).refusal == "amount"
    assert check_reply("Line 2 for buyer@rival.example.", facts).refusal == "address"
    assert check_reply("Line 2: see https://rival.example", facts).refusal == "address"


# ------------------------------------------------------- what is drafted --


async def test_a_question_is_answered_from_the_orders_facts_to_the_customers_contacts() -> None:
    model = Writing(_quoting)
    with _question_sample() as sample:
        world = drafting_world(REPO, sample, model, question=QUESTION)
        case_id = await _asked(world)
        view = await _draft(world, case_id, "question_answer", message_id="R2")

    assert view.status == "drafted", view
    assert (view.subject, view.body) == (f"PO {PO}", "Line 2: 04 Dec 2026.")
    assert view.to == CONTACTS and view.language == "en"
    assert (view.prompt_ref, view.figures_checked) == (str(REPLY_DRAFT), 4)
    prompt, run, inputs = model.calls[-1]
    assert prompt == REPLY_DRAFT
    assert (run.tenant_id, run.actor_id) == (ALPHA.tenant_id.value, AN.user_id)
    # The question is the sentence code located; the example, the tenant's letter.
    assert inputs["question"] == QUESTION
    assert inputs["example"].startswith("Subject: Re: your order ${po_no}")
    facts = json.loads(inputs["facts"])
    assert facts["reply"] == "question_answer" and facts["order_status"] == "confirmation_sent"
    assert [line["line_no"] for line in facts["lines"]] == [1, 2, 3]


@pytest.mark.parametrize(
    ("kind", "day", "dates"),
    [
        ("change_can_do_draft", ASKED, ["20 Nov 2026"]),
        ("change_options_draft", LATER, ["25 Nov 2026"]),
    ],
)
async def test_pcs_answer_is_worded_from_pcs_deliveries(kind: str, day: Any, dates: Any) -> None:
    model = Writing(_quoting)
    with sample_for("en", pull_in()) as sample:
        world = drafting_world(REPO, sample, model)
        case_id = await confirmed(world)
        await answered_by_pc(world, case_id, day)
        view = await _draft(world, case_id, kind)

    assert view.status == "drafted", view
    (line,) = _facts(model)["lines"]
    assert [d["date"] for d in line["deliveries"]] == dates
    # 6-DW3 says what was asked; 6-DW4 does not need to.
    assert ("asked" in line) is (kind == "change_options_draft")


# ---------------------------------------------- acceptance 1: the figures --


@pytest.mark.parametrize("kind", ["question_answer", "confirmation_draft"])
async def test_a_figure_no_fact_supports_drops_the_draft(kind: str) -> None:
    model = _says("Line 2 ships on 28 Nov 2026 from lot LOT-2611-07.")
    with _question_sample() as sample:
        world = drafting_world(REPO, sample, model, question=QUESTION)
        case_id = await _asked(world)
        view = await _draft(
            world, case_id, kind, message_id="R2" if kind == "question_answer" else None
        )

    assert (view.status, view.refusal) == ("refused", "figure")
    assert view.unsupported == ["2611-07", "28"]
    assert view.subject is None and view.body is None and view.to == CONTACTS


async def test_a_figure_only_the_question_holds_is_no_fact() -> None:
    """The customer's own date, echoed as if confirmed, is dropped: the
    check reads the facts alone."""
    question = "Can line 2 ship on 27 Nov 2026 instead?"
    model = _says("Line 2 will ship on 27 Nov 2026.")
    with sample_for("en", reply("R2", body=question, hour=11)) as sample:
        world = drafting_world(REPO, sample, model, question=question)
        case_id = await _asked(world)
        view = await _draft(world, case_id, "question_answer", message_id="R2")

    assert model.calls[-1][2]["question"] == question
    assert (view.status, view.refusal, view.unsupported) == ("refused", "figure", ["27"])


# --------------------------------------------- acceptance 2: no amount --


async def test_no_kind_is_told_a_price_an_amount_or_a_currency() -> None:
    model = Writing(_quoting)
    with _question_sample() as sample:
        world = drafting_world(REPO, sample, model, question=QUESTION)
        case_id = await _asked(world)
        told = []
        await _draft(world, case_id, "question_answer", message_id="R2")
        told.append(model.calls[-1][2]["facts"])
        await _draft(world, case_id, "confirmation_draft")
        told.append(model.calls[-1][2]["facts"])
        await answered_by_pc(world, case_id, ASKED)
        await _draft(world, case_id, "change_can_do_draft")
        told.append(model.calls[-1][2]["facts"])
        case = world.order(case_id)

    prices = {str(line.effective.unit_price) for line in case.lines}
    assert prices and None not in {line.effective.unit_price for line in case.lines}
    currency = case.effective_header.currency
    assert currency
    for facts in told:
        assert not any(price in facts for price in prices), facts
        assert f'"{currency}"' not in facts and "price" not in facts and "amount" not in facts


@pytest.mark.parametrize("amount", ["3600 USD", "3600 đồng", "2%", "¥3600"])
async def test_a_draft_naming_an_amount_is_dropped_though_its_figures_are_facts(
    amount: str,
) -> None:
    model = _says(f"Line 2: 3600 m, {amount}.")
    with sample_for("en", pull_in()) as sample:
        world = drafting_world(REPO, sample, model)
        case_id = await confirmed(world)
        view = await _draft(world, case_id, "confirmation_draft")

    assert (view.status, view.refusal, view.unsupported) == ("refused", "amount", [])


# ------------------------------------------------- recipients are code's --


async def test_the_model_names_no_recipient_and_writes_no_address() -> None:
    with _question_sample() as sample:
        # The answer's schema has no recipient: an answer naming one is no
        # answer, as the gateway refuses one outside the schema.
        addressed = Recorded(
            raw={"subject": "PO", "body": "Line 2.", "to": ["buyer@rival.example"]}
        )
        world = drafting_world(REPO, sample, addressed, question=QUESTION)
        case_id = await _asked(world)
        view = await _draft(world, case_id, "question_answer", message_id="R2")
        assert (view.status, view.to) == ("unavailable", CONTACTS)
        world = drafting_world(
            REPO, sample, _says("Line 2. Copying buyer@rival.example."), question=QUESTION
        )
        case_id = await _asked(world)
        view = await _draft(world, case_id, "question_answer", message_id="R2")

    assert (view.status, view.refusal, view.to) == ("refused", "address", CONTACTS)


# ------------------------------------------------------ when it is offered --


async def test_offered_only_where_the_template_draft_is() -> None:
    with _question_sample() as sample:
        world = drafting_world(REPO, sample, Writing(_quoting), question=QUESTION)
        ((disposition, _),) = (await world.process_each(AN, ["M04"])).values()
        assert disposition.case_id is not None
        # Not confirmed yet: no confirmation, and no answer of PC's to word.
        for kind in ("confirmation_draft", "change_can_do_draft", "change_options_draft"):
            with pytest.raises(ConflictError) as refused:
                await _draft(world, disposition.case_id, kind)
            assert refused.value.details["rule"] == "not_offered"


async def test_a_question_is_a_reply_on_this_order_read_as_asking() -> None:
    with _question_sample() as sample:
        world = drafting_world(REPO, sample, Writing(_quoting), question=QUESTION)
        case_id = await _asked(world)
        seen = await world.process_each(AN, ["R1", "M01"])
        other = seen["M01"][0].case_id
        assert other is not None and other != case_id
        # R2 is a question, read `asks`, but on M04's order, not on M01's.
        with pytest.raises(NotFoundError):
            await _draft(world, other, "question_answer", message_id="R2")
        # R1 asks nothing (its table is a change): read `unclear`.
        with pytest.raises(ConflictError) as refused:
            await _draft(world, case_id, "question_answer", message_id="R1")
        assert refused.value.details["rule"] == "not_asked"
        # Another customer's mail, or a mail no one processed, is not this order's.
        for mail in ("M01", "M99"):
            with pytest.raises(NotFoundError):
                await _draft(world, case_id, "question_answer", message_id=mail)
        with pytest.raises(DomainError):
            await _draft(world, case_id, "question_answer")
        with pytest.raises(DomainError):
            await _draft(world, case_id, "confirmation_draft", message_id="R2")


# ------------------------------------------------ the gate and the model --


async def test_the_step_unmeasured_is_off_and_no_model_is_asked() -> None:
    model = Writing(_quoting)
    with sample_for("en", pull_in()) as sample:
        world = drafting_world(REPO, sample, model, measured=False)
        case_id = await confirmed(world)
        view = await _draft(world, case_id, "confirmation_draft")

    assert (view.status, view.to) == ("off", CONTACTS)
    assert model.calls == []


async def test_the_step_off_in_the_rules_is_off_whatever_was_measured() -> None:
    model = Writing(_quoting)
    with sample_for("en", pull_in()) as sample:
        world = drafting_world(REPO, sample, model)
        current = world.policies.order_rules
        world.store.rule_versions.seed_approved(
            ALPHA.tenant_id.value,
            current.model_copy(
                update={
                    "policy_version": "1.91.0",
                    "model_assist": current.model_assist.model_copy(update={"reply_draft": False}),
                }
            ),
        )
        case_id = await confirmed(world)
        view = await _draft(world, case_id, "confirmation_draft")

    assert view.status == "off" and model.calls == []


async def test_the_template_path_works_with_the_step_off() -> None:
    with sample_for("en", pull_in()) as sample:
        world = drafting_world(REPO, sample, Writing(_quoting), measured=False)
        case_id = await confirmed(world)
        await answered_by_pc(world, case_id, ASKED)
        (record,) = await world.services.artifacts.render_order(
            AN.context(),
            case_id,
            kind="change_can_do_draft",
            case_version=world.order(case_id).case_version,
        )
        view = await _draft(world, case_id, "change_can_do_draft")

    assert record.kind == "change_can_do_draft" and view.status == "off"


@pytest.mark.parametrize("model", [Recorded(failure=ModelUnavailableError("down")), None])
async def test_no_model_says_so_and_keeps_the_recipients(model: Any) -> None:
    with sample_for("en", pull_in()) as sample:
        world = drafting_world(REPO, sample, model)
        case_id = await confirmed(world)
        view = await _draft(world, case_id, "confirmation_draft")

    assert (view.status, view.to, view.body) == ("unavailable", CONTACTS, None)


async def test_where_deployed_no_example_is_read_from_mock_copy() -> None:
    model = Writing(_quoting)
    with sample_for("en", pull_in()) as sample:
        world = drafting_world(REPO, sample, model)
        case_id = await confirmed(world)
        deployed = dataclasses.replace(world.services.reply_drafts, deployed=True)
        with pytest.raises(ConflictError) as refused:
            await deployed.draft(AN.context(), case_id, "confirmation_draft")

    assert refused.value.details["rule"] == "mock_copy" and model.calls == []


# ----------------------------------------------------------- who may ask --


async def test_only_who_prepares_orders_and_only_in_the_callers_tenant() -> None:
    model = Writing(_quoting)
    with sample_for("en", pull_in()) as sample:
        world = drafting_world(REPO, sample, model)
        case_id = await confirmed(world)
        with pytest.raises(PermissionDeniedError):
            await _draft(world, case_id, "confirmation_draft", context=READER.context())
        with pytest.raises(NotFoundError):
            await _draft(world, case_id, "confirmation_draft", context=OUTSIDER.context(BETA))

    assert model.calls == []


# ------------------------------------------------------------- the prompt --


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    from dw_agent_runtime.model.prompts import PromptRegistry
    from dw_sales.application.model_readiness import BARS

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        REPLY_DRAFT.prompt_id,
        REPLY_DRAFT.version,
        {"facts": "", "example": "", "question": ""},
        tenant_id=ALPHA.tenant_id.value,
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS
    assert BARS[ModelStep.REPLY_DRAFT].prompt == REPLY_DRAFT
    # Every kind the prompt explains is one code drafts.
    assert all(f'"{kind}"' in rendered.system for kind in REPLY_KINDS)
