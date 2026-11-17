"""The worked-example routes (ticket 38, dw_sales ADR 0013), over the
in-memory Sales services: "Gửi duyệt" refused at the route for a replay that
differs, the scopes asked, another tenant finding nothing, and the rules
editor's own door refusing the key; and a customer's worked pairs listed and
one withdrawn (ticket 41). Before any database."""

from __future__ import annotations

import base64
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from dw_api.exception_handlers import register_exception_handlers
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import SalesScopes
from dw_sales.application.rules import RuleKey
from dw_sales.application.salesorder_learning import Replay, SalesOrderExample
from dw_sales.application.salesorder_rules import CustomerSalesOrderRules
from dw_sales.evals.graders import CALLERS, GIANG, READER, Caller
from dw_sales.evals.graders import OUTSIDER as _OUTSIDER
from dw_sales.evals.salesorder_rules import Bench, load_cases, pair
from dw_sales.evals.salesorder_skill import kept_pair
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world
from dw_sales.presentation.routes import build_router

pytestmark = pytest.mark.unit

# Beta's member holding the learner's scopes, as beta's head would: a refusal
# for want of a scope would hide whether isolation holds.
OUTSIDER = replace(
    _OUTSIDER, scopes=_OUTSIDER.scopes | {SalesScopes.RULES_PROPOSE, SalesScopes.PRICE_READ}
)
REPO = Path(__file__).resolve().parents[4]
BASE = "/api/v1/sales"
RULES = CustomerSalesOrderRules.model_validate(
    {"columns": [{"column": "W", "steps": [{"step": "constant", "value": "HK"}]}]}
)


class _Recorder:
    async def record[M: BaseModel](self, result: M, *, status_code: int = 200) -> M:
        return result


def _app(world: World, caller: Caller, scope: Any = None) -> FastAPI:
    def context() -> AccessContext:
        return caller.context(scope) if scope is not None else caller.context()

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(
        build_router(world.services, access_context=context, idempotency=lambda: _Recorder())
    )
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest.fixture
def world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, OUTSIDER))


async def _replayed(world: World, *, differences: int) -> uuid.UUID:
    """An example as the worker leaves one, its replay matching or not."""
    layout = (await world.services.rules.list(GIANG.context(ALPHA))).in_force[RuleKey.BRAVO_UPLOAD]
    example = SalesOrderExample(
        example_id=uuid.uuid4(),
        customer_code="NRV",
        status="replayed",
        requested_by=GIANG.user_id,
        requested_at=datetime(2026, 11, 14, 2, 0, tzinfo=UTC),
        received_on=date(2026, 11, 14),
        po_file_name="po.xlsx",
        po_sha256="0" * 64,
        po_size=1,
        salesorder_file_name="SalesOrder.xlsx",
        salesorder_sha256="1" * 64,
        salesorder_size=1,
        rules=RULES,
        replay=Replay(
            layout_ref=layout,
            rows_expected=2,
            rows_got=2,
            cells_compared=34,
            differences_total=differences,
        ),
    )
    async with world.example_store(ALPHA) as work:
        await work.examples.add(example, b"po", b"so")
        await work.commit()
    return example.example_id


async def test_a_replay_that_differs_is_refused_at_the_route(world: World) -> None:
    differing = await _replayed(world, differences=2)
    matching = await _replayed(world, differences=0)
    async with _client(_app(world, GIANG)) as client:
        refused = await client.post(
            f"{BASE}/salesorder-examples/{differing}/submissions", json={"version": "9.0.1"}
        )
        sent = await client.post(
            f"{BASE}/salesorder-examples/{matching}/submissions", json={"version": "9.0.1"}
        )
        shown = await client.get(
            f"{BASE}/salesorder-examples/by-version/{sent.json()['version_id']}"
        )
    assert (refused.status_code, refused.json()["details"]["rule"]) == (409, "replay_differs")
    assert sent.status_code == 200, sent.text
    # Waiting on the head, whoever sent it: never applied directly.
    assert (sent.json()["status"], sent.json()["applied_directly"]) == ("proposed", False)
    assert (shown.status_code, shown.json()["example_id"]) == (200, str(matching))


async def test_the_rules_editor_door_refuses_the_learned_key(world: World) -> None:
    async with _client(_app(world, GIANG)) as client:
        document = (await client.get(f"{BASE}/rules/sales_salesorder_rules/platform")).json()[0][
            "document"
        ]
        refused = await client.post(
            f"{BASE}/rules/sales_salesorder_rules/versions",
            json={"document": {**document, "policy_version": "9.0.1"}},
        )
        words = await client.post(
            f"{BASE}/rules/sales_salesorder_rules/drafts/words", json={"request": "lùi 10 ngày"}
        )
    assert (refused.status_code, refused.json()["details"]["rule"]) == (
        422,
        "learned_from_example_only",
    )
    assert (words.status_code, words.json()["details"]["rule"]) == (
        422,
        "learned_from_example_only",
    )


async def test_a_caller_without_the_scopes_is_refused_and_another_tenant_finds_nothing(
    world: World,
) -> None:
    example = await _replayed(world, differences=0)
    body = {
        "received_on": "2026-11-14",
        "po": {"file_name": "po.xlsx", "content_b64": base64.b64encode(b"x").decode()},
        "salesorder": {"file_name": "so.xlsx", "content_b64": base64.b64encode(b"x").decode()},
    }
    no_price = replace(GIANG, scopes=GIANG.scopes - {SalesScopes.PRICE_READ})
    for caller in (READER, no_price):
        async with _client(_app(world, caller)) as client:
            assert (await client.get(f"{BASE}/salesorder-examples/{example}")).status_code == 403
            assert (
                await client.post(f"{BASE}/customers/NRV/salesorder-examples", json=body)
            ).status_code == 403
            assert (
                await client.post(
                    f"{BASE}/salesorder-examples/{example}/submissions", json={"version": "9.0.1"}
                )
            ).status_code == 403
    async with _client(_app(world, OUTSIDER, BETA)) as client:
        assert (await client.get(f"{BASE}/salesorder-examples/{example}")).status_code == 404
        assert (
            await client.post(
                f"{BASE}/salesorder-examples/{example}/submissions", json={"version": "9.0.1"}
            )
        ).status_code == 404
        # Alpha's customer is not beta's: nothing is kept for it.
        assert (
            await client.post(f"{BASE}/customers/NRV/salesorder-examples", json=body)
        ).status_code == 404


async def test_a_pair_is_queued_for_the_worker_and_listed_on_the_customer(world: World) -> None:
    body = {
        "received_on": "2026-11-14",
        "po": {"file_name": "po.xlsx", "content_b64": base64.b64encode(b"po").decode()},
        "salesorder": {"file_name": "so.xlsx", "content_b64": base64.b64encode(b"so").decode()},
    }
    async with _client(_app(world, GIANG)) as client:
        queued = await client.post(f"{BASE}/customers/NRV/salesorder-examples", json=body)
        listed = await client.get(f"{BASE}/customers/NRV/salesorder-examples")
        wrong = await client.post(
            f"{BASE}/customers/NRV/salesorder-examples",
            json={**body, "salesorder": {**body["salesorder"], "file_name": "so.pdf"}},
        )
    assert queued.status_code == 202, queued.text
    assert (queued.json()["status"], queued.json()["submittable"]) == ("queued", False)
    assert [e["example_id"] for e in listed.json()] == [queued.json()["example_id"]]
    assert (wrong.status_code, wrong.json()["details"]["rule"]) == (422, "file_type")


async def _a_pair(world: World) -> uuid.UUID:
    """A customer's worked pair as the learning keeps one (ticket 41)."""
    kept = await kept_pair(Bench.of(REPO, None, (GIANG,)), pair(load_cases(REPO), "SR02"))
    async with world.example_store(ALPHA) as work:
        await work.pairs.add(kept)
        await work.commit()
    return kept.pair_id


async def test_a_pair_is_listed_and_withdrawn_by_a_proposer_who_reads_prices(
    world: World,
) -> None:
    pair_id = await _a_pair(world)
    no_price = replace(GIANG, scopes=GIANG.scopes - {SalesScopes.PRICE_READ})
    for caller in (READER, no_price):
        async with _client(_app(world, caller)) as client:
            assert (await client.get(f"{BASE}/customers/KHB/salesorder-pairs")).status_code == 403
            assert (await client.delete(f"{BASE}/salesorder-pairs/{pair_id}")).status_code == 403
    # Beta's proposer finds none of alpha's pairs, and withdraws nothing.
    async with _client(_app(world, OUTSIDER, BETA)) as client:
        assert (await client.get(f"{BASE}/customers/KHB/salesorder-pairs")).json() == []
        assert (await client.delete(f"{BASE}/salesorder-pairs/{pair_id}")).status_code == 404
    async with _client(_app(world, GIANG)) as client:
        listed = await client.get(f"{BASE}/customers/KHB/salesorder-pairs")
        withdrawn = await client.delete(f"{BASE}/salesorder-pairs/{pair_id}")
        after = await client.get(f"{BASE}/customers/KHB/salesorder-pairs")
    assert [p["pair_id"] for p in listed.json()] == [str(pair_id)]
    assert "expected" not in listed.json()[0] and "document" not in listed.json()[0]
    assert withdrawn.status_code == 200, withdrawn.text
    assert after.json() == []
