"""OpenTelemetry implementation of ``TelemetryPort``.

``configure_tracing`` builds a real SDK pipeline when an OTLP endpoint is
configured (plain collector or Langfuse — see ``dw_observability.langfuse``).
Without an endpoint the API-level no-op tracer applies, so instrumented code
never pays for unconfigured telemetry.

Metrics are a separate decision from tracing, on purpose. Before Ops
hardening Phase 5, ``metrics.get_meter(...)`` was called with no
``MeterProvider`` ever installed — every ``add_metric`` call in this
codebase (``dw_run_total``, ``dw_node_failure_total``, ...) was silently a
no-op against OTel's proxy meter, Langfuse configured or not. Measured, not
assumed: ``metrics.get_meter_provider()`` returns a ``_ProxyMeterProvider``
until something calls ``set_meter_provider``, and nothing here ever did.
Metrics now always get a real `MeterProvider` backed by
``PrometheusMetricReader`` — Prometheus is pull-based, so unlike the OTLP
trace exporter above it needs no destination configured to be worth turning
on, only something to scrape the process's own `/metrics`.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field

from opentelemetry import metrics, trace

# `create_gauge`'s return type is exported as `_Gauge` in this pinned SDK
# version (the synchronous Gauge instrument was still stabilising its public
# name) — this is that same class, not a private implementation detail.
from opentelemetry.metrics import Counter, Meter
from opentelemetry.metrics import _Gauge as Gauge
from opentelemetry.trace import Status, StatusCode, Tracer

from dw_kernel.errors import DWError
from dw_observability.telemetry import TelemetryPort, safe_attributes

_meter_provider_lock = threading.Lock()
_meter_provider_installed = False


def build_telemetry(
    *,
    service_name: str,
    langfuse_enabled: bool = False,
    langfuse_host: str | None = None,
    langfuse_public_key: str | None = None,
    langfuse_secret_key: str | None = None,
    otel_endpoint: str | None = None,
) -> TelemetryPort:
    """Turn Langfuse/OTLP settings into a ``TelemetryPort`` — one builder every app
    shares, so tracing is wired the same way in api, chat and worker.

    Langfuse is just an OTLP endpoint (§21.4) for TRACES. With no endpoint
    (neither Langfuse nor a plain collector), spans are a no-op — OTel's own
    default tracer, not ``NullTelemetry``: this always returns a real
    ``OtelTelemetry`` now, because metrics are wired regardless of whether
    tracing is.
    """
    endpoint = otel_endpoint
    headers: dict[str, str] | None = None
    if langfuse_enabled:
        from dw_observability.langfuse import langfuse_otlp_config

        if not (langfuse_host and langfuse_public_key and langfuse_secret_key):
            raise ValueError("Langfuse enabled but host/public_key/secret_key missing")
        endpoint, headers = langfuse_otlp_config(
            langfuse_host, langfuse_public_key, langfuse_secret_key
        )
    tracer, meter = configure_tracing(service_name, otlp_endpoint=endpoint, otlp_headers=headers)
    return OtelTelemetry(tracer=tracer, meter=meter)


def configure_tracing(
    service_name: str,
    *,
    otlp_endpoint: str | None = None,
    otlp_headers: Mapping[str, str] | None = None,
) -> tuple[Tracer, Meter]:
    """Install a tracer (only if an OTLP endpoint is set) and a meter
    (always). Exported spans go to `otlp_endpoint`; exported metrics go to
    this process's own `/metrics` — a Prometheus scraper is the composition
    root's job to expose (`apps/api`'s route, `apps/worker`'s metrics
    server), not this function's.
    """
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=otlp_endpoint,
                    headers=dict(otlp_headers) if otlp_headers else None,
                )
            )
        )
        trace.set_tracer_provider(provider)
    _ensure_meter_provider(service_name)
    return trace.get_tracer(service_name), metrics.get_meter(service_name)


def _ensure_meter_provider(service_name: str) -> None:
    """Install the process-wide Prometheus-backed ``MeterProvider`` exactly
    once. ``metrics.set_meter_provider`` is itself idempotent-safe (a second
    call is refused with a log warning, not an exception) but guarded here
    too so a second call in the same process — a second app/worker
    composition root import path, a test — never even attempts it or logs
    that warning.
    """
    global _meter_provider_installed
    with _meter_provider_lock:
        if _meter_provider_installed:
            return
        from opentelemetry.exporter.prometheus import PrometheusMetricReader
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource

        reader = PrometheusMetricReader()
        provider = MeterProvider(
            resource=Resource.create({"service.name": service_name}), metric_readers=[reader]
        )
        metrics.set_meter_provider(provider)
        _meter_provider_installed = True


def _exception_event(exc: Exception) -> dict[str, str]:
    """What a span says of an exception that crossed it: its type and, for a
    `DWError`, the message that is safe to log by contract. Never ``str(exc)``
    of any other exception, nor a stack trace (which quotes every chained
    cause's text): a parser's or a validator's message can hold the document
    it failed on, and a span leaves the process for a collector or Langfuse
    (Sales ticket 23). The stack trace stays in the process's own log."""
    kind = type(exc)
    return {
        "exception.type": f"{kind.__module__}.{kind.__qualname__}",
        "exception.message": exc.message if isinstance(exc, DWError) else kind.__name__,
    }


@dataclass
class OtelTelemetry:
    """``TelemetryPort`` on an OpenTelemetry tracer + meter."""

    tracer: Tracer
    meter: Meter
    _counters: dict[str, Counter] = field(default_factory=dict)
    _gauges: dict[str, Gauge] = field(default_factory=dict)

    @contextmanager
    def _span(self, name: str, attributes: Mapping[str, object]) -> Iterator[None]:
        # The SDK's own recording is off: left on, it adds ``str(exc)`` and the
        # stack trace to the span as the exception leaves the block, whatever
        # this method records (measured on the pinned SDK, Sales ticket 23).
        with self.tracer.start_as_current_span(
            name, record_exception=False, set_status_on_exception=False
        ) as span:
            for key, value in safe_attributes(attributes).items():
                span.set_attribute(key, value)
            try:
                yield
            except Exception as exc:
                event = _exception_event(exc)
                span.set_status(Status(StatusCode.ERROR, str(event["exception.message"])))
                span.add_event("exception", event)
                raise

    def span(self, name: str, attributes: Mapping[str, object]) -> AbstractContextManager[None]:
        return self._span(name, attributes)

    def add_metric(self, name: str, value: int | float, attributes: Mapping[str, object]) -> None:
        counter = self._counters.get(name)
        if counter is None:
            counter = self.meter.create_counter(name)
            self._counters[name] = counter
        counter.add(value, safe_attributes(attributes))

    def set_gauge(self, name: str, value: int | float, attributes: Mapping[str, object]) -> None:
        gauge = self._gauges.get(name)
        if gauge is None:
            gauge = self.meter.create_gauge(name)
            self._gauges[name] = gauge
        gauge.set(value, safe_attributes(attributes))
