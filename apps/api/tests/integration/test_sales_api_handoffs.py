"""A hand-off to PC or QA pre-filled from a routed mail, through the API the
web calls (ticket 33, dw_sales ADR 0005), against a real database.

The gateway is scripted (it renders the versioned prompt for the run's tenant,
as the real one does): M31 read as the complaint it is, and its spans copied.
What PostgreSQL keeps, what the inbox shows and to whom, and that another
tenant reaches none of it, are this file's. Accuracy on the local model is the
eval lane's (`sales_handoff@1.0.0`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls
from sales_api_harness import AN, BAO, BETA, HA, REPO, Api, build_app
from sales_flow import process
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_agent_runtime.ports import ModelRequest

pytestmark = pytest.mark.integration

PROBLEM = "có 2 cuộn bị móp lõi cuộn, dây bên trong bị trầy vỏ"


class ScriptedComplaint:
    """`ModelGateway` reading M31 as a complaint and copying its spans."""

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
        answers = {
            "sales.message_intent": {
                "language": "vi",
                "referenced_number_spans": ["VLX-PO-2608-0102"],
                "kind": "complaint",
            },
            "sales.request_handoff": {
                "po_no_span": "VLX-PO-2608-0102",
                "lot_no_span": "LOT-2609-118",
                "problem_quote_spans": [PROBLEM],
            },
        }
        return output_type.model_validate(answers[request.prompt_id])


@pytest.fixture
async def gateway() -> ScriptedComplaint:
    return ScriptedComplaint()


@pytest.fixture
async def model_api(
    sales_api_db: DatabaseUrls, clean_sales: None, gateway: ScriptedComplaint
) -> AsyncIterator[Api]:
    async with build_app(sales_api_db.app, model=gateway) as built:
        yield built


async def test_a_routed_complaint_carries_a_hand_off_code_wrote_and_kept(
    model_api: Api, gateway: ScriptedComplaint, migrator: AsyncEngine
) -> None:
    an, ha, bao = model_api.as_(AN), model_api.as_(HA), model_api.as_(BAO, BETA)

    m31 = await process(an, "M31")

    assert (m31["kind"], m31["reason"]) == ("routed_to_sales", "complaint")
    handoff = m31["handoff"]
    assert (handoff["kind"], handoff["po_no"], handoff["so_no"]) == (
        "complaint",
        "VLX-PO-2608-0102",
        "SO26-0812",
    )
    assert [q["text"] for q in handoff["quotes"]] == [PROBLEM]
    assert [r.prompt_id for r, _ in gateway.calls] == [
        "sales.message_intent",
        "sales.request_handoff",
    ]
    assert all(run.worker_id == "sales-dw1" for _, run in gateway.calls)
    async with migrator.connect() as conn:
        kept = await conn.scalar(
            sa.text("SELECT handoff ->> 'po_no' FROM sales.messages WHERE message_id = 'M31'")
        )
    assert kept == "VLX-PO-2608-0102"
    # A case reader sees the hand-off as they see the mail it was copied from.
    listed = {m["message_id"]: m for m in (await an.get("/inbox")).json()}
    draft = listed["M31"]["handoff_draft"]
    assert (draft["to"], draft["template_ref"]) == ("qa", "sales_handoffs@1.0.0#complaint")
    assert "VLX-PO-2608-0102" in draft["subject"] and "LOT-2609-118" in draft["subject"]
    assert f"«{PROBLEM}»" in draft["body"]
    # Leadership reads aggregates only, and another tenant's mailbox is its own.
    assert (await ha.get("/inbox")).status_code == 403
    assert all(m["message_id"] != "M31" for m in (await bao.get("/inbox")).json())


async def test_without_a_model_the_complaint_is_routed_as_before_with_no_hand_off(
    api: Api, migrator: AsyncEngine
) -> None:
    an = api.as_(AN)

    m31 = await process(an, "M31")

    assert (m31["reason"], m31["handoff"]) == ("complaint", None)
    listed = {m["message_id"]: m for m in (await an.get("/inbox")).json()}
    assert listed["M31"]["handoff_draft"] is None
    async with migrator.connect() as conn:
        kept = await conn.scalar(
            sa.text("SELECT handoff FROM sales.messages WHERE message_id = 'M31'")
        )
    assert kept is None
