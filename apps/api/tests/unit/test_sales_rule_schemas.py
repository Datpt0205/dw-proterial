"""The rules editor's reads over HTTP (Sales ticket 40): each key's JSON
Schema and the platform's released documents, to holders of
`sales.rules.propose` only, and an unknown key answered as not found."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from dw_api.exception_handlers import register_exception_handlers
from dw_platform.application.access_context import AccessContext
from dw_sales.application.rules import OVERRIDABLE, RuleKey
from dw_sales.evals.graders import AN, CALLERS, READER, Caller
from dw_sales.evals.world import SampleSet, open_world
from dw_sales.presentation.routes import build_router

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]


def _app(caller: Caller) -> FastAPI:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)

    def context() -> AccessContext:
        return caller.context()

    def no_idempotency() -> None:
        raise AssertionError("a read claims no Idempotency-Key")

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(
        build_router(world.services, access_context=context, idempotency=no_idempotency)
    )
    return app


async def _get(caller: Caller, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app(caller))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get(path)


@pytest.mark.parametrize("key", list(RuleKey), ids=str)
async def test_a_pic_reads_each_keys_schema(key: RuleKey) -> None:
    response = await _get(AN, f"/api/v1/sales/rules/{key.value}/schema")
    assert response.status_code == 200
    body = response.json()
    assert body["key"] == key.value
    assert body["json_schema"] == OVERRIDABLE[key].model_json_schema(by_alias=True)


async def test_a_pic_reads_the_platforms_released_documents() -> None:
    response = await _get(AN, "/api/v1/sales/rules/sales_kpi/platform")
    assert response.status_code == 200
    (current, *_) = response.json()
    assert (current["ref"], current["current"]) == ("sales_kpi@1.0.0", True)
    assert current["document"]["policy_id"] == "sales_kpi"


@pytest.mark.parametrize("read", ["schema", "platform"])
async def test_without_the_propose_scope_both_reads_are_refused(read: str) -> None:
    refused = await _get(READER, f"/api/v1/sales/rules/sales_pricing/{read}")
    assert refused.status_code == 403
    assert "document" not in refused.text and "json_schema" not in refused.text
    # The scope is asked before the key: an unknown one is refused the same.
    assert (await _get(READER, f"/api/v1/sales/rules/sales_nothing/{read}")).status_code == 403


@pytest.mark.parametrize("read", ["schema", "platform"])
async def test_an_unknown_key_is_not_found(read: str) -> None:
    for key in ("sales_nothing", "SALES_KPI", "sales_kpi.x"):
        response = await _get(AN, f"/api/v1/sales/rules/{key}/{read}")
        assert response.status_code == 404, key
        assert response.json()["code"] == "not_found"
