"""A customer's reply in a case's thread, through the API the web calls
(ticket 32, dw_sales ADR 0005), against a real database.

The thread headers attach the reply to its case with no model; where the
demo tenant's rules turn it on, a model reads it (here a scripted gateway that
renders the versioned prompt for the run's tenant, as the real one does) and
the case proposes a step. What PostgreSQL keeps, what the case view shows,
that the step is Sales' to take, that keeping the PO disposes no finding, and
that another tenant reaches none of it, are this file's. Accuracy on the local
model is the eval lane's (`sales_reply@1.0.0`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls
from sales_api_harness import AN, BAO, BETA, HA, REPO, Api, build_app
from sales_flow import decide, open_sources, order, process, quote, replied
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_agent_runtime.ports import ModelRequest

pytestmark = pytest.mark.integration

ACCEPT = "We accept the proposed specification without changes."
KEEP = "Please keep the PO as it is."


class ScriptedReplies:
    """`ModelGateway` reading a reply as the subject says, after rendering
    the versioned prompt for the run's tenant; any other step is refused."""

    def __init__(self) -> None:
        self.prompts = PromptRegistry()
        self.prompts.load_directory(REPO / "configs" / "prompts")
        self.calls: list[tuple[ModelRequest, RunContext]] = []

    async def generate_structured(
        self, request: ModelRequest, output_type: type[Any], *, run_context: RunContext
    ) -> Any:
        variables = dict(request.variables)
        self.prompts.render(
            request.prompt_id, request.prompt_version, variables, tenant_id=run_context.tenant_id
        )
        self.calls.append((request, run_context))
        if request.prompt_id != "sales.reply_intent":
            raise AssertionError(f"not scripted: {request.prompt_id}")
        if "RFQ" in variables["subject"]:
            return output_type.model_validate({"quote_spans": [ACCEPT], "kind": "accepts_spec"})
        return output_type.model_validate({"quote_spans": [KEEP], "kind": "keeps_po_as_is"})


@pytest.fixture
async def gateway() -> ScriptedReplies:
    return ScriptedReplies()


@pytest.fixture
async def model_api(
    sales_api_db: DatabaseUrls, clean_sales: None, gateway: ScriptedReplies
) -> AsyncIterator[Api]:
    async with build_app(sales_api_db.app, model=gateway) as built:
        yield built


async def _spec(an: Any, case: dict[str, Any], step: str) -> dict[str, Any]:
    response = await an.post(
        f"/quotes/{case['case_id']}/spec-discussion",
        {"case_version": case["case_version"], "step": step},
    )
    assert response.status_code == 200, response.text
    return await quote(an, case["case_id"])


async def _sent_back(an: Any) -> dict[str, Any]:
    """M04 with both findings sent back to the customer."""
    opened = await process(an, "M04")
    case = await order(an, opened["case_id"])
    for key in ("price_mismatch:2", "code_unmapped:3"):
        case = await decide(
            an, case, f"findings/{key}/disposition", {"disposition": "ask_customer"}
        )
    case = await decide(an, case, "correction-request")
    assert case["status"] == "correction_requested"
    return case


async def test_a_reply_joins_its_order_and_keeping_the_po_decides_no_finding(
    api: Api, migrator: AsyncEngine
) -> None:
    """No model is wired: the thread headers alone attach M42 to M04's case;
    Sales resumes the review and every finding is still theirs to decide."""
    an = api.as_(AN)
    case = await _sent_back(an)

    m42 = await process(an, "M42")

    assert (m42["kind"], m42["case_kind"], m42["case_id"]) == (
        "attached_to_case",
        "order",
        case["case_id"],
    )
    assert m42["reply"] == {"linked_to": "M04", "reading": None}
    async with migrator.connect() as conn:
        kept = await conn.scalar(
            sa.text(
                "SELECT case_reply ->> 'linked_to' FROM sales.messages WHERE message_id = 'M42'"
            )
        )
    assert kept == "M04"
    (reply,) = (await order(an, case["case_id"]))["replies"]
    assert (reply["message_id"], reply["outcome"], reply["proposal"]) == ("M42", None, None)

    resumed = await decide(an, await order(an, case["case_id"]), "resume-review")

    assert resumed["status"] == "in_review"
    asked = {f["key"] for f in resumed["findings"] if f["disposition"]["kind"] == "ask_customer"}
    assert asked == {"price_mismatch:2", "code_unmapped:3"}
    await open_sources(an, resumed)
    refused = await an.post(
        f"/orders/{case['case_id']}/prepare", {"case_version": resumed["case_version"]}
    )
    assert refused.status_code == 409
    assert all(key in str(refused.json()["details"]["ask_customer"]) for key in asked)


async def test_the_model_reads_the_reply_and_the_case_proposes_what_sales_confirms(
    model_api: Api, gateway: ScriptedReplies, migrator: AsyncEngine
) -> None:
    an = model_api.as_(AN)
    case = await replied(an, "M09", "YCBG-2609-028", "M18")
    case = await _spec(an, case, "start")

    m41 = await process(an, "M41")

    reading = m41["reply"]["reading"]
    assert (reading["kind"], reading["prompt"], reading["rules"]) == (
        "accepts_spec",
        "sales.reply_intent@1.0.0",
        "sales_order_rules@1.4.1",
    )
    assert [q["text"] for q in reading["quotes"]] == [ACCEPT]
    ((request, run),) = gateway.calls
    assert (request.prompt_id, run.worker_id) == ("sales.reply_intent", "sales-dw1")
    # The quoted older message never reached the model.
    assert "infusion pump" not in request.variables["body"]
    shown = await quote(an, case["case_id"])
    assert shown["status"] == "spec_discussion"
    (reply,) = shown["replies"]
    assert (reply["kind"], reply["proposal"], reply["quotes"]) == (
        "accepts_spec",
        "settle_spec",
        [ACCEPT],
    )
    async with migrator.connect() as conn:
        kept = await conn.scalar(
            sa.text(
                "SELECT case_reply #>> '{reading,kind}' FROM sales.messages"
                " WHERE message_id = 'M41'"
            )
        )
    assert kept == "accepts_spec"
    # Sales confirms the step, through the case's own route.
    settled = await _spec(an, shown, "settle")
    assert settled["status"] == "design_replied"
    assert (await quote(an, case["case_id"]))["replies"][0]["proposal"] is None


async def test_resuming_review_is_a_preparers_step_and_another_tenant_reaches_nothing(
    api: Api,
) -> None:
    an, ha, bao = api.as_(AN), api.as_(HA), api.as_(BAO, BETA)
    case = await _sent_back(an)
    await process(an, "M42")
    body = {"case_version": case["case_version"]}

    assert (await ha.post(f"/orders/{case['case_id']}/resume-review", body)).status_code == 403
    assert (await bao.post(f"/orders/{case['case_id']}/resume-review", body)).status_code == 404
    assert (await bao.get(f"/orders/{case['case_id']}")).status_code == 404
    # Beta's inbox is its own: the demo mailbox, replies included, is not there.
    assert all(m["message_id"] != "M42" for m in (await bao.get("/inbox")).json())
    assert (await order(an, case["case_id"]))["status"] == "correction_requested"
