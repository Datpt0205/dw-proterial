"""Ops hardening Phase 5: `/metrics` is a real Prometheus scrape target.

Root-level, not `/api/v1` — a scrape target's path does not version with the
API. Asserted end-to-end (through the ASGI app, not by reading the route
table) so a route mounted with nothing behind it — this repo's own Phase 4
lesson about a route nothing processes — would show up here as a 404 or an
empty body, not as a passing test.
"""

from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager
from opentelemetry import metrics

from dw_api.bootstrap import build_container
from dw_api.main import create_app
from dw_api.settings import ApiSettings

pytestmark = pytest.mark.unit


async def test_metrics_endpoint_serves_prometheus_exposition_format() -> None:
    # `build_container` installs the process-wide Prometheus `MeterProvider`
    # (see `dw_observability.otel`) unconditionally, so a stateless container
    # (no database configured) is enough to prove the wiring.
    container = build_container(ApiSettings(profile="test", database_url=None))
    meter = metrics.get_meter("dw-api-metrics-endpoint-test")
    meter.create_counter("dw_test_metrics_endpoint_total").add(1, {"probe": "unit-test"})

    app = create_app(container)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "dw_test_metrics_endpoint_total" in response.text
