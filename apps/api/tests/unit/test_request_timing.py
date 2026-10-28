"""One timing line per request, named by the route's template, never its ids."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from dw_api.middleware.timing import RequestTimingMiddleware

pytestmark = pytest.mark.unit


def _app() -> FastAPI:
    # Mounted the way the API mounts a context's router: an APIRouter with
    # its own paths, included under a prefix.
    router = APIRouter(prefix="/sales")

    @router.get("/orders/{case_id}/source/{attachment_id}")
    async def source(case_id: uuid.UUID, attachment_id: str) -> dict[str, str]:
        return {"ok": "yes"}

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.add_middleware(RequestTimingMiddleware)
    return app


@pytest.fixture
def lines() -> Iterator[list[str]]:
    """What the timing logger writes, read off its own handler (it does not
    propagate, so caplog's root handler would not see it)."""
    seen: list[str] = []

    class Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record.getMessage())

    logger = logging.getLogger("dw_api.timing")
    keep = Keep()
    logger.addHandler(keep)
    try:
        yield seen
    finally:
        logger.removeHandler(keep)


def test_a_request_is_logged_by_its_route_template(lines: list[str]) -> None:
    client = TestClient(_app())
    case = uuid.uuid4()
    assert client.get(f"/api/v1/sales/orders/{case}/source/M02-A1").status_code == 200

    (line,) = lines
    method, route, status, elapsed = line.split()[1:]
    assert (method, route, status) == (
        "GET",
        "/api/v1/sales/orders/{case_id}/source/{attachment_id}",
        "200",
    )
    assert elapsed.endswith("ms") and float(elapsed[:-2]) >= 0
    assert str(case) not in line


def test_an_unmatched_path_is_logged_with_its_ids_masked(lines: list[str]) -> None:
    client = TestClient(_app())
    case = uuid.uuid4()
    assert client.get(f"/api/v1/nothing/{case}").status_code == 404

    (line,) = lines
    assert line.split()[2:4] == ["/api/v1/nothing/{id}", "404"]
