"""The rule draft routes ("Tạo từ tệp mẫu"), over the in-memory Sales
services: what the API answers, and what it refuses, before any database."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from dw_api.exception_handlers import register_exception_handlers
from dw_platform.application.access_context import AccessContext
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER, READER, Caller
from dw_sales.evals.rule_drafts import template_xlsx
from dw_sales.evals.world import BETA, SampleSet, World, open_world
from dw_sales.presentation.routes import build_router

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
BASE = "/api/v1/sales/rules"
_TEMPLATE = {
    "id": "T",
    "sheet": "NhapDonBan",
    "columns": [["Số PO", "po_no"], ["Dòng", "line_no"], ["Mã hàng", "prv_code"], ["SL", None]],
}


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


def _body(data: bytes, name: str = "mau.xlsx") -> dict[str, str]:
    return {"file_name": name, "content_b64": base64.b64encode(data).decode()}


@pytest.fixture
def world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, OUTSIDER))


async def test_a_template_is_queued_and_read_back(world: World) -> None:
    async with _client(_app(world, AN)) as client:
        queued = await client.post(
            f"{BASE}/sales_bravo_upload/drafts", json=_body(template_xlsx(_TEMPLATE))
        )
        assert queued.status_code == 202, queued.text
        assert queued.json()["status"] == "queued"
        draft = await client.get(f"{BASE}/drafts/{queued.json()['draft_id']}")
    assert draft.status_code == 200
    assert (draft.json()["file_name"], draft.json()["document"]) == ("mau.xlsx", None)


async def test_a_key_with_no_drafting_and_a_file_that_is_no_workbook_are_refused(
    world: World,
) -> None:
    async with _client(_app(world, AN)) as client:
        emails = await client.post(f"{BASE}/sales_emails/drafts", json=_body(b"x"))
        pdf = await client.post(
            f"{BASE}/sales_bravo_upload/drafts", json=_body(b"%PDF-1", "mau.pdf")
        )
        unknown = await client.post(f"{BASE}/no_such_key/drafts", json=_body(b"x"))
    assert (emails.status_code, emails.json()["details"]["rule"]) == (422, "key_not_draftable")
    assert (pdf.status_code, pdf.json()["details"]["rule"]) == (422, "file_type")
    assert unknown.status_code == 422


async def test_a_reader_is_refused_and_another_tenant_finds_nothing(world: World) -> None:
    async with _client(_app(world, AN)) as client:
        queued = await client.post(
            f"{BASE}/sales_bravo_upload/drafts", json=_body(template_xlsx(_TEMPLATE))
        )
    draft_id = queued.json()["draft_id"]
    async with _client(_app(world, READER)) as client:
        refused = await client.post(
            f"{BASE}/sales_bravo_upload/drafts", json=_body(template_xlsx(_TEMPLATE))
        )
        assert refused.status_code == 403
        assert (await client.get(f"{BASE}/drafts/{draft_id}")).status_code == 403
    async with _client(_app(world, OUTSIDER, BETA)) as client:
        assert (await client.get(f"{BASE}/drafts/{draft_id}")).status_code == 404
        assert (await client.get(f"{BASE}/drafts/{uuid.uuid4()}")).status_code == 404
