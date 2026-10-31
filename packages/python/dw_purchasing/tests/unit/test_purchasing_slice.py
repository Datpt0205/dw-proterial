"""The generated slice, end to end, no infrastructure.

Kept because a scaffold that shipped untested code would be teaching the wrong
habit on the first file a new context ever has.
"""

from __future__ import annotations

import uuid

import pytest

from dw_purchasing.adapters.sink import InMemoryPurchasingSink
from dw_purchasing.application.handlers import HandlePurchasing
from dw_purchasing.domain.entities import PurchasingRequest

pytestmark = pytest.mark.unit


async def test_a_handled_request_reaches_the_sink_and_comes_back_summarised() -> None:
    sink = InMemoryPurchasingSink()
    request = PurchasingRequest(
        request_id=uuid.uuid4(), tenant_id=uuid.uuid4(), subject="  báo giá quý 4  "
    )

    summary = await HandlePurchasing(sink)(request)

    assert summary == "báo giá quý 4"
    assert sink.recorded == [request]


def test_each_built_router_serves_its_own_handler() -> None:
    """Two apps, two handlers: each request lands in its own app's sink."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dw_purchasing.presentation.routes import build_router

    first, second = InMemoryPurchasingSink(), InMemoryPurchasingSink()
    first_app, second_app = FastAPI(), FastAPI()
    first_app.include_router(build_router(HandlePurchasing(first)))
    second_app.include_router(build_router(HandlePurchasing(second)))

    path = "/api/v1/purchasing/requests"
    response = TestClient(second_app).post(path, json={"subject": "x"})

    assert response.status_code == 200
    assert len(second.recorded) == 1
    assert first.recorded == []


def test_an_empty_subject_is_refused_by_the_entity() -> None:
    """In the constructor, so nothing downstream has to ask whether it is valid."""
    # One id for both fields, so this line stays inside the line limit whatever
    # the context is named — the generated code has to pass `ruff format --check`
    # for every legal name, not just a short one.
    an_id = uuid.uuid4()
    with pytest.raises(ValueError):
        PurchasingRequest(request_id=an_id, tenant_id=an_id, subject="")
