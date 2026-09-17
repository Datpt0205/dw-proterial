"""Tracing/metrics wiring.

Langfuse is not a second integration: it is an OTLP endpoint with auth headers,
so both paths end at the same exporter.
"""

from __future__ import annotations

from dw_api.settings import ApiSettings
from dw_observability.telemetry import NullTelemetry, TelemetryPort


def build_telemetry(settings: ApiSettings, service_name: str = "dw-api") -> TelemetryPort:
    endpoint = settings.otel_endpoint
    headers: dict[str, str] | None = None
    if settings.langfuse_enabled:
        from dw_observability.langfuse import langfuse_otlp_config

        assert settings.langfuse_host is not None  # validate_for_profile enforced
        assert settings.langfuse_public_key is not None
        assert settings.langfuse_secret_key is not None
        endpoint, headers = langfuse_otlp_config(
            settings.langfuse_host,
            settings.langfuse_public_key,
            settings.langfuse_secret_key,
        )
    if endpoint is None:
        return NullTelemetry()
    from dw_observability.otel import OtelTelemetry, configure_tracing

    tracer, meter = configure_tracing(service_name, otlp_endpoint=endpoint, otlp_headers=headers)
    return OtelTelemetry(tracer=tracer, meter=meter)
