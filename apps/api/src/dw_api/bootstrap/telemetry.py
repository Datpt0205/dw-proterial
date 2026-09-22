"""Tracing/metrics wiring.

Langfuse is not a second integration: it is an OTLP endpoint with auth headers,
so both paths end at the same exporter. The actual wiring lives in
`dw_observability.otel.build_telemetry` — this is settings-shaped glue, not a
second copy of that logic. It used to be one: this file called
`configure_tracing` itself and returned `NullTelemetry()` whenever no OTLP
endpoint was set, which meant `dw-api` never got a real `MeterProvider` at
all (Prometheus metrics need one regardless of whether tracing is
configured — see `dw_observability.otel`'s module docstring). `dw_worker`
already called the shared builder directly and never had the bug; found
while giving `dw-api` the same fix.
"""

from __future__ import annotations

from dw_api.settings import ApiSettings
from dw_observability.otel import build_telemetry as _build_telemetry
from dw_observability.telemetry import TelemetryPort


def build_telemetry(settings: ApiSettings, service_name: str = "dw-api") -> TelemetryPort:
    return _build_telemetry(
        service_name=service_name,
        langfuse_enabled=settings.langfuse_enabled,
        langfuse_host=settings.langfuse_host,
        langfuse_public_key=settings.langfuse_public_key,
        langfuse_secret_key=settings.langfuse_secret_key,
        otel_endpoint=settings.otel_endpoint,
    )
