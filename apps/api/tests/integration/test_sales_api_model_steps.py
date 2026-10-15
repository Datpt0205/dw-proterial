"""DW1 reads what no reader reads through a model, through the API the web
calls (tickets 29 and 31, dw_sales ADR 0005), against a real database.

The gateway answers every model step with the local model's recorded answers
(`evals/fixtures/cases/sales_*_recorded.json`), after rendering the versioned
prompt for the run's tenant as the real gateway does. What the API shows, what
PostgreSQL keeps (the message's intent reading, the quote case's flags and
confirmations), and that Sales confirms a model-read value, are this file's.
Live runs on the local model are the eval lane's (`run_evals.py --live onprem`).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls
from sales_api_harness import AN, BAO, BETA, DIEU, HA, REPO, Api, build_app
from sales_flow import process, quote
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_agent_runtime.ports import ModelRequest
from dw_platform.testing.seed_env import sid
from dw_sales.application.model_reading import PromptRef
from dw_sales.evals.recorded import answer_key, load_answers

pytestmark = pytest.mark.integration

CASES = REPO / "evals/fixtures/cases"
BY_KEY = {
    **load_answers(CASES / "sales_intent_recorded.json"),
    **load_answers(CASES / "sales_rfq_recorded.json"),
    **load_answers(CASES / "sales_handoff_recorded.json"),
}
DESCRIPTIONS = json.loads((CASES / "sales_descriptions_recorded.json").read_text(encoding="utf-8"))[
    "answers"
]
_LINE_NULLS = dict.fromkeys(
    [
        "family_span",
        "family",
        "stranding_span",
        "stranding",
        "conductor_span",
        "conductor",
        "shield_span",
        "shield",
        "colour_span",
        "colour",
        "packaging_span",
        "packaging",
        "cores_span",
        "gauge_span",
        "pack_length_span",
        "spec_no_span",
    ]
)


class RecordedGateway:
    """`ModelGateway` answering each step with what the local model answered
    for the same inputs, after rendering its prompt for the run's tenant."""

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
        if request.prompt_id == "sales.description_attributes":
            lines = [
                {"line_no": sent["line_no"], **_LINE_NULLS, **DESCRIPTIONS[sent["description"]]}
                for sent in json.loads(variables["lines"])
                if DESCRIPTIONS[sent["description"]] is not None
            ]
            return output_type.model_validate({"lines": lines})
        prompt = PromptRef(request.prompt_id, request.prompt_version)
        return output_type.model_validate(BY_KEY[answer_key(prompt, variables)])


@pytest.fixture
async def gateway() -> RecordedGateway:
    return RecordedGateway()


@pytest.fixture
async def model_api(
    sales_api_db: DatabaseUrls, clean_sales: None, gateway: RecordedGateway
) -> AsyncIterator[Api]:
    async with build_app(sales_api_db.app, model=gateway) as built:
        yield built


async def test_a_postponement_no_keyword_lists_is_read_and_names_m35s_order(
    model_api: Api, gateway: RecordedGateway, migrator: AsyncEngine
) -> None:
    an = model_api.as_(AN)
    m35 = await process(an, "M35")
    m40 = await process(an, "M40")

    assert (m40["kind"], m40["reason"]) == ("routed_to_sales", "delivery_change")
    reading = m40["reading"]
    assert (reading["kind"], reading["outcome"], reading["prompt"]) == (
        "delivery_change",
        "read",
        "sales.message_intent@1.0.0",
    )
    assert reading["rules"] == "sales_order_rules@1.5.1"
    ((reference),) = reading["references"]
    assert (reference["number"], reference["order_case_id"]) == (
        "BRN-PO-2609-052",
        m35["case_id"],
    )
    # M35's PO decided its own kind: M40's intent, then its hand-off
    # (ticket 33), both in M40's DW1 run.
    assert [request.prompt_id for request, _ in gateway.calls] == [
        "sales.message_intent",
        "sales.request_handoff",
    ]
    assert {(run.worker_id, run.tenant_id) for _, run in gateway.calls} == {
        ("sales-dw1", sid("tenant", "tenant-alpha"))
    }
    assert (m40["handoff"]["outcome"], m40["handoff"]["po_no"]) == (
        "read",
        "BRN-PO-2609-052",
    )
    async with migrator.connect() as conn:
        kept = await conn.scalar(
            sa.text("SELECT model_reading ->> 'kind' FROM sales.messages WHERE message_id = 'M40'")
        )
    assert kept == "delivery_change"
    listed = {m["message_id"]: m for m in (await an.get("/inbox")).json()}
    assert listed["M40"]["disposition"]["reading"]["kind"] == "delivery_change"


async def test_a_request_in_the_mail_body_opens_a_case_and_sales_confirms_each_value(
    model_api: Api, migrator: AsyncEngine
) -> None:
    dieu = model_api.as_(DIEU)
    disposition = await process(model_api.as_(AN), "M37")
    assert (disposition["kind"], disposition["case_kind"]) == ("case_created", "quote")
    assert disposition["reading"]["kind"] == "quote_request"
    case = await quote(dieu, disposition["case_id"])

    assert (case["rfq_no"], case["attachment_id"]) == (None, None)
    assert case["reading"]["prompt"] == "sales.rfq_extraction@1.0.0"
    assert sorted(case["model_read"]) == ["currency", "quote_due"]
    # The text is served on its own route, never inside the case (ticket 29).
    assert "message_text" not in case
    path = f"/quotes/{case['case_id']}/findings/value_uncertain:1/answer"
    body = {"case_version": case["case_version"], "field": "quantity", "value": "1250"}
    unopened = await dieu.post(path, body)
    assert unopened.status_code == 409, unopened.text
    assert "chưa mở nguồn" in unopened.text
    served = await dieu.get(f"/quotes/{case['case_id']}/message-text")
    assert served.status_code == 200, served.text
    text = served.json()["text"]
    assert "1.200 m" in text
    assert "5.000" not in text  # the quoted older offer was cut
    first = case["lines"][0]
    assert sorted(first["model_read"]) == ["description", "needed_by", "quantity", "uom"]
    chars = first["anchors"]["quantity"]["chars"]
    assert text[chars["start"] : chars["end"]] == first["anchors"]["quantity"]["quote"]
    async with migrator.connect() as conn:
        recorded = await conn.scalar(
            sa.text(
                "SELECT count(*) FROM sales.source_served WHERE quote_case_id = :id"
                " AND attachment_id IS NULL AND principal_id = :who"
            ),
            {"id": case["case_id"], "who": dieu.id},
        )
    assert recorded == 1
    uncertain = [f for f in case["findings"] if f["code"] == "value_uncertain"]
    assert {f["line_no"] for f in uncertain} == {None, 1, 2}

    # The YCBG waits until every value is confirmed: the case itself refuses
    # to leave `received` with a request finding open, as for rfq_incomplete.
    refused = await dieu.post(
        f"/quotes/{case['case_id']}/ycbg", {"case_version": case["case_version"]}
    )
    assert refused.status_code == 422, refused.text
    answered = await dieu.post(path, body)
    assert answered.status_code == 200, answered.text
    after = await quote(dieu, case["case_id"])
    assert after["lines"][0]["quantity"] == "1250"
    (line_one,) = [f for f in after["findings"] if f["key"] == "value_uncertain:1"]
    assert [(c["field"], c["read"], c["value"]) for c in line_one["confirmed"]] == [
        ("quantity", "1200", "1250")
    ]
    async with migrator.connect() as conn:
        event = await conn.scalar(
            sa.text(
                "SELECT field FROM sales.case_events WHERE action = 'quote.value_confirmed'"
                " AND case_id = :id"
            ),
            {"id": case["case_id"]},
        )
    assert event == "quantity"


async def test_a_stated_target_price_is_shown_as_the_customers_words_only(
    model_api: Api,
) -> None:
    disposition = await process(model_api.as_(AN), "M38")
    case = await quote(model_api.as_(DIEU), disposition["case_id"])

    first = case["lines"][0]
    assert first["target_price"] is None
    assert first["stated_target_price"] == "0.95"
    assert first["anchors"]["stated_target_price"]["page"] == 1
    assert case["attachment_id"] == "M38-A1"


async def test_a_request_in_the_customers_own_sheet_asks_for_its_blank_quantity(
    model_api: Api,
) -> None:
    disposition = await process(model_api.as_(AN), "M39")
    case = await quote(model_api.as_(DIEU), disposition["case_id"])

    assert case["rfq_no"] == "KMH-RFQ-261002-01"
    incomplete = [f for f in case["findings"] if f["code"] == "rfq_incomplete"]
    assert [(f["line_no"], f["missing"]) for f in incomplete] == [(2, ["quantity"])]
    assert len(case["lines"]) == 2  # the hidden row was never read


async def test_without_a_model_server_the_requests_are_routed_as_before(api: Api) -> None:
    an = api.as_(AN)
    for message_id in ("M37", "M38", "M39"):
        disposition = await process(an, message_id)
        assert (disposition["kind"], disposition["reason"]) == (
            "routed_to_sales",
            "attachment_unreadable",
        )
        assert disposition["reading"] is None
    m40 = await process(an, "M40")
    assert (m40["reason"], m40["reading"]) == ("other", None)


async def test_a_value_is_confirmed_only_by_a_preparer_of_the_tenant(model_api: Api) -> None:
    """The confirmation is enforced where it is written: a viewer is refused,
    and another tenant's preparer finds no such case."""
    disposition = await process(model_api.as_(AN), "M37")
    case = await quote(model_api.as_(DIEU), disposition["case_id"])
    body = {"case_version": case["case_version"], "field": "quantity", "value": "1"}
    path = f"/quotes/{case['case_id']}/findings/value_uncertain:1/answer"

    viewer = await model_api.as_(HA).post(path, body)
    other_tenant = await model_api.as_(BAO, tenant=BETA).post(path, body)
    # Nor is the mail served to someone who may not read prices, or to
    # another tenant.
    text = f"/quotes/{case['case_id']}/message-text"
    viewer_text = await model_api.as_(HA).get(text)
    other_text = await model_api.as_(BAO, tenant=BETA).get(text)

    assert viewer.status_code == 403, viewer.text
    assert other_tenant.status_code == 404, other_tenant.text
    assert viewer_text.status_code == 403, viewer_text.text
    assert other_text.status_code == 404, other_text.text
    after = await quote(model_api.as_(DIEU), case["case_id"])
    assert after["case_version"] == case["case_version"]
    assert after["lines"][0]["quantity"] == "1200"
