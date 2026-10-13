"""DW1 reads M36's descriptions through a model, through the API the web calls
(ticket 28, dw_sales ADR 0005), against a real database.

The gateway here answers with the local model's recorded answers
(`evals/fixtures/cases/sales_descriptions_recorded.json`), after rendering the
versioned prompt for the run's tenant as the real gateway does. What the API
shows, what PostgreSQL keeps on the line's check basis, which run the call was
attributed to, and that Sales confirms the candidate, are this file's. Live
runs on the local model are the eval lane's (`run_evals.py --live onprem`).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls
from sales_api_harness import AN, REPO, Api, build_app
from sales_flow import order, order_of
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_agent_runtime.ports import ModelRequest
from dw_platform.testing.seed_env import sid

pytestmark = pytest.mark.integration

RECORDED = json.loads(
    (REPO / "evals/fixtures/cases/sales_descriptions_recorded.json").read_text(encoding="utf-8")
)["answers"]
NULLS = dict.fromkeys(
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
    """`ModelGateway` answering with recorded answers, after rendering the
    prompt for the run's tenant (a prompt and its inputs that disagree fail
    here as on the real gateway)."""

    def __init__(self) -> None:
        self.prompts = PromptRegistry()
        self.prompts.load_directory(REPO / "configs" / "prompts")
        self.calls: list[tuple[ModelRequest, RunContext]] = []

    async def generate_structured(
        self, request: ModelRequest, output_type: type[Any], *, run_context: RunContext
    ) -> Any:
        self.prompts.render(
            request.prompt_id,
            request.prompt_version,
            dict(request.variables),
            tenant_id=run_context.tenant_id,
        )
        self.calls.append((request, run_context))
        lines = [
            {"line_no": sent["line_no"], **NULLS, **RECORDED[sent["description"]]}
            for sent in json.loads(request.variables["lines"])
            if RECORDED[sent["description"]] is not None
        ]
        return output_type.model_validate({"lines": lines})


@pytest.fixture
async def gateway() -> RecordedGateway:
    return RecordedGateway()


@pytest.fixture
async def model_api(
    sales_api_db: DatabaseUrls, clean_sales: None, gateway: RecordedGateway
) -> AsyncIterator[Api]:
    async with build_app(sales_api_db.app, model=gateway) as built:
        yield built


async def test_m36_lines_the_model_read_are_candidates_sales_confirms(
    model_api: Api, gateway: RecordedGateway, migrator: AsyncEngine
) -> None:
    an = model_api.as_(AN)
    case = await order_of(an, "M36")
    # The demo tenant's own rules, where the step is on.
    assert case["rules_version"] == "sales_order_rules@1.4.1"
    lines = {line["line_no"]: line for line in case["lines"]}

    # The recorded model left line 1's colour out and line 2's "BRD"
    # unlabelled: words no span covers, so both stay Sales' to map.
    for number in (1, 2):
        assert lines[number]["mapping"]["status"] == "unmapped"
        refused = lines[number]["basis"]["description_reading"]
        assert (refused["outcome"], refused["reason"]) == ("not_understood", "text_uncovered")
    third = lines[3]
    assert (third["mapping"]["status"], third["mapping"]["candidates"]) == (
        "candidate",
        ["CB-2001"],
    )
    reading = third["basis"]["description_reading"]
    assert (reading["outcome"], reading["prompt"], reading["model_profile"]) == (
        "read",
        "sales.description_attributes@1.0.0",
        "onprem",
    )
    by = {span["attribute"]: span["read_by"] for span in reading["spans"]}
    assert by["colour"] == "model" and by["gauge"] == "code" and by["cores"] == "code"
    for line in case["lines"]:
        assert line["mapping"]["status"] != "exact"

    # One call, in the DW1 run that processed M36, as its tenant.
    ((request, run),) = gateway.calls
    assert (request.model_profile, run.worker_id) == ("onprem", "sales-dw1")
    assert run.tenant_id == sid("tenant", "tenant-alpha")
    async with migrator.connect() as conn:
        worker = await conn.scalar(
            sa.text("SELECT worker_id FROM platform.worker_runs WHERE id = :id"),
            {"id": run.run_id},
        )
    assert worker == "sales-dw1"

    confirmed = await an.post(
        f"/orders/{case['case_id']}/lines/3/mapping",
        {"case_version": case["case_version"], "prv_code": "CB-2001"},
    )
    assert confirmed.status_code == 200, confirmed.text
    after = await order(an, case["case_id"])
    line = next(line for line in after["lines"] if line["line_no"] == 3)
    assert (line["mapping"]["status"], line["mapping"]["prv_code"]) == (
        "candidate_confirmed",
        "CB-2001",
    )
    # The reading stays the line's evidence after Sales confirms.
    assert line["basis"]["description_reading"]["outcome"] == "read"


async def test_without_a_model_server_m36_stays_sales_to_map(api: Api) -> None:
    case = await order_of(api.as_(AN), "M36")

    for line in case["lines"]:
        assert line["mapping"]["status"] == "unmapped"
        assert line["basis"]["description_reading"] is None
