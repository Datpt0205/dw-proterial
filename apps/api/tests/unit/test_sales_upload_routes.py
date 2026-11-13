""" "Tải PO lên" (ticket 18) at the route, over the in-memory Sales services:
what the API answers, and what it refuses, before any database."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from dw_api.exception_handlers import register_exception_handlers
from dw_platform.application.access_context import AccessContext
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER, READER, Caller
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world
from dw_sales.presentation.routes import build_router

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
URL = "/api/v1/sales/inbox/upload"
EXPORT = b"\xff\xfe" + "PO No.\tPart No.\tPO Type\nCVG-PO-1\tCVG-0001\tFirm\n".encode("utf-16-le")


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


def _body(customer: str = "CVG", **extra: Any) -> dict[str, Any]:
    file = {"file_name": "ORD.csv", "content_b64": base64.b64encode(EXPORT).decode()}
    return {"customer_code": customer, "files": [file], **extra}


@pytest.fixture
def world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, OUTSIDER))


async def test_an_upload_is_stored_and_queued_as_the_caller(world: World) -> None:
    async with _client(_app(world, AN)) as client:
        answered = await client.post(URL, json=_body())
    assert answered.status_code == 202, answered.text
    body = answered.json()
    assert (body["customer_code"], body["already_stored"]) == ("CVG", False)
    assert body["job"]["status"] == "queued"
    message = await world.inbox.get_message(ALPHA, body["message_id"])
    assert message is not None and message.sender.address == AN.email


async def test_a_caller_without_the_mailbox_scope_is_refused_at_the_route(world: World) -> None:
    """Acceptance 2: refused before anything is decoded or stored."""
    async with _client(_app(world, READER)) as client:
        refused = await client.post(URL, json=_body())
    assert refused.status_code == 403
    assert await world.uploads.list_messages(ALPHA) == []


async def test_a_customer_not_in_the_tenants_master_data_is_refused(world: World) -> None:
    async with _client(_app(world, AN)) as client:
        unknown = await client.post(URL, json=_body("ZZZ"))
    async with _client(_app(world, OUTSIDER, BETA)) as client:
        elsewhere = await client.post(URL, json=_body("CVG"))
    assert (unknown.status_code, elsewhere.status_code) == (404, 404)
    assert await world.uploads.list_messages(ALPHA) == []
    assert await world.uploads.list_messages(BETA) == []


async def test_who_uploads_is_never_a_field_of_the_request(world: World) -> None:
    async with _client(_app(world, AN)) as client:
        claimed = await client.post(URL, json=_body(uploaded_by=str(READER.user_id)))
        sender = await client.post(URL, json=_body(sender="buyer@corvane-group.example"))
    assert (claimed.status_code, sender.status_code) == (422, 422)
    assert await world.uploads.list_messages(ALPHA) == []
