"""No price, customer name or mail text in a span, a log line or an error (Sales ticket 23, G32).

Fixture POs processed end to end, as the API serves them: the real Sales
router behind the API's own exception handlers, DW1's runs on the real runner
and approval flow (`open_world`), and every span exported through the real
OpenTelemetry adapter into an in-memory exporter, the runtime's and Sales'
alike. Logs are captured at DEBUG from the root logger. What leaves the
process is then searched for every value the fixtures carry that is not an
id: prices, amounts, the customer's name, the mail's subject, body and
sender, file names, item descriptions.

The search is only as good as its needles, so the test first shows they are
real: each one is read from the case DW1 stored and the message it read, and
the success response that shows the case to a price holder contains them.
"""

from __future__ import annotations

import html
import json
import logging
import re
import uuid
from collections.abc import Iterable, Iterator, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from dw_agent_runtime.adapters.telemetry_usage import TelemetryUsageRecorder
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.gateway import ModelUsage, RoutingModelGateway
from dw_agent_runtime.model.profiles import ModelProfileRegistry, ModelRoute
from dw_agent_runtime.model.prompts import PromptRegistry, RenderedPrompt
from dw_agent_runtime.ports import ModelRequest
from dw_api.exception_handlers import register_exception_handlers
from dw_observability.metrics import DW_MODEL_COST_USD_TOTAL, DW_MODEL_TOKENS_TOTAL
from dw_observability.otel import OtelTelemetry
from dw_platform.application.access_context import AccessContext
from dw_sales.adapters.model_interpretation import GatewayInterpretation
from dw_sales.application.support import DW1_WORKER_ID, DW1_WORKER_VERSION
from dw_sales.application.telemetry import SPAN_ATTRIBUTES, SalesSpan
from dw_sales.domain.description_reading import ModelDescriptionLine
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN, CALLERS, DIEU
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world
from dw_sales.presentation.routes import build_router

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
# An Excel PO walked to its confirmation; a text PDF, and a scanned PDF DW1
# cannot read (routed to Sales), processed.
WALKED, PROCESSED = "M01", ("M03", "M16")


class _Exported:
    """The OpenTelemetry SDK as a deployment configures it, exporting to memory."""

    def __init__(self) -> None:
        self.spans = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(self.spans))
        self.metrics = InMemoryMetricReader()
        self.telemetry = OtelTelemetry(
            tracer=tracer_provider.get_tracer("dw-api"),
            meter=MeterProvider(metric_readers=[self.metrics]).get_meter("dw-api"),
        )

    def span_text(self) -> Iterator[str]:
        """Everything a span carries out of the process, as text."""
        for span in self.spans.get_finished_spans():
            yield span.name
            yield json.dumps(dict(span.attributes or {}), ensure_ascii=False, default=str)
            yield span.status.description or ""
            for event in span.events:
                yield event.name
                yield json.dumps(dict(event.attributes or {}), ensure_ascii=False, default=str)

    def metric_points(self, name: str) -> list[Any]:
        data = self.metrics.get_metrics_data()
        assert data is not None
        return [
            point
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == name
            for point in metric.data.data_points
        ]


class _Recorded:
    """The routes' `Idempotency-Key` operation, answering what it is given."""

    async def record[M: BaseModel](self, result: M, *, status_code: int = 200) -> M:
        return result


def _app(world: World) -> FastAPI:
    """The Sales router behind the API's exception handlers, signed in as An."""

    def access_context() -> AccessContext:
        return AN.context()

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(
        build_router(world.services, access_context=access_context, idempotency=_Recorded)
    )
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _process(client: httpx.AsyncClient, world: World, message_id: str) -> dict[str, Any]:
    """ "DW xử lý" as the page presses it (ticket 25): queued by the route (202),
    run by the worker's lane, and the disposition read back from the inbox."""
    response = await client.post(f"/api/v1/sales/inbox/{message_id}/process")
    assert response.status_code == 202, response.text
    await world.drain()
    inbox = await client.get("/api/v1/sales/inbox")
    assert inbox.status_code == 200, inbox.text
    shown: dict[str, Any] = next(
        m["disposition"] for m in inbox.json() if m["message_id"] == message_id
    )
    return shown


def _amounts(*values: Decimal | None) -> set[str]:
    """An amount as text, as stored and normalised, with and without thousands
    separators. One too short to be told from an id's hex digits is left out:
    a decimal needs four digits, a whole number six."""
    texts: set[str] = set()
    for value in values:
        if value is not None:
            for form in (value, value.normalize()):
                texts |= {format(form, "f"), format(form, ",f")}
    return {
        text
        for text in texts
        if len(text.replace(",", "").replace(".", "")) >= (4 if "." in text else 6)
    }


async def _document_values(world: World, message_id: str, case: OrderCase | None) -> set[str]:
    """Every value of the message, and of the case DW1 made of it, that is not an id."""
    message = await world.inbox.get_message(ALPHA, message_id)
    assert message is not None
    values = {
        message.subject,
        message.body_text,
        message.sender.address,
        message.sender.display_name,
        *(attachment.name for attachment in message.attachments),
    }
    if case is not None:
        customer = (await world.catalog.customer_by_code(ALPHA, case.customer_code)).data
        assert customer is not None
        values.add(customer.name)
        document = case.document
        values |= {text for text in (document.buyer,) if text}
        values |= _amounts(document.total.amount if document.total else None)
        for line in case.lines:
            values |= _amounts(line.po_line.unit_price, line.po_line.amount)
            quotation = line.basis.quotation
            values |= _amounts(quotation.unit_price if quotation else None)
            if len(line.po_line.description) >= 8:
                values.add(line.po_line.description)
        for finding in case.findings:
            values |= {text for text in (finding.expected, finding.actual) if text}
    return {value for value in values if value and len(value) >= 5}


def _log_text(records: Iterable[logging.LogRecord]) -> Iterator[str]:
    formatter = logging.Formatter()
    for record in records:
        yield record.getMessage()
        if record.exc_info:
            yield formatter.formatException(record.exc_info)
        yield json.dumps(record.__dict__, ensure_ascii=False, default=str)


def _leaks(needles: set[str], haystack: Iterable[str]) -> dict[str, str]:
    """Each needle found, and the first place it was found in."""
    found: dict[str, str] = {}
    for text in haystack:
        for needle in needles - found.keys():
            if needle in text:
                found[needle] = text[:300]
    return found


async def test_a_fixture_po_leaves_no_document_value_in_spans_logs_or_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    exported = _Exported()
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, telemetry=exported.telemetry)
    errors: list[httpx.Response] = []

    async with _client(_app(world)) as client:
        # 1. DW1 processes the POs, through the route and its run.
        processed = {}
        for message_id in (WALKED, *PROCESSED):
            processed[message_id] = await _process(client, world, message_id)
        case_id = uuid.UUID(processed[WALKED]["case_id"])
        assert processed["M16"]["kind"] == "routed_to_sales"

        # 2. The order walked to its confirmation: self-check, Bravo entry,
        # the cross-check decided on the approval its run paused on.
        await world.walk_to_uploaded(AN, case_id)
        await world.cross_check(DIEU, case_id)
        confirmed = await world.confirm(AN, case_id, date(2026, 11, 27))
        assert confirmed.status.value == "confirmed"
        shown = await client.get(f"/api/v1/sales/orders/{case_id}")
        assert shown.status_code == 200

        # 3. What the routes refuse, each with a document value in reach.
        unit_price = str(confirmed.lines[0].po_line.unit_price)
        customer = (await world.catalog.customer_by_code(ALPHA, confirmed.customer_code)).data
        assert customer is not None
        # The PDF's order, still in the PIC's self-check, is the one a value
        # is typed on.
        in_review = world.order(uuid.UUID(processed["M03"]["case_id"]))
        assert in_review.status.value == "in_review"
        corrections = f"/api/v1/sales/orders/{in_review.case_id}/findings/value_uncertain:1"
        refusals = [
            # Processed already: 409.
            client.post(f"/api/v1/sales/inbox/{WALKED}/process"),
            # A stale version: 409.
            client.post(f"/api/v1/sales/orders/{case_id}/prepare", json={"case_version": 1}),
            # A price typed for a finding the case does not have: 409.
            client.post(
                f"{corrections}/corrections",
                json={
                    "case_version": in_review.case_version,
                    "field": "unit_price",
                    "value": unit_price,
                },
            ),
            # A body the model refuses, the price and the customer's name in it:
            # FastAPI's own 422.
            client.post(
                f"{corrections}/corrections",
                json={
                    "case_version": in_review.case_version,
                    "field": "unit_price",
                    "value": f"{unit_price} {customer.name} " * 10,
                    "customer_name": customer.name,
                },
            ),
            # No such case: 404.
            client.get(f"/api/v1/sales/orders/{uuid.uuid4()}"),
        ]
        for refusal in refusals:
            response = await refusal
            assert response.status_code >= 400, response.text
            errors.append(response)
    assert sorted(r.status_code for r in errors) == [404, 409, 409, 409, 422]

    needles = await _document_values(world, WALKED, world.order(case_id))
    for message_id in PROCESSED:
        disposition = processed[message_id]
        case = world.order(uuid.UUID(disposition["case_id"])) if disposition["case_id"] else None
        needles |= await _document_values(world, message_id, case)

    # The needles are real: the case a price holder reads carries the walked
    # PO's prices and its customer's name's PO values, and the spans are there.
    assert unit_price in shown.text
    assert {unit_price, customer.name} <= needles
    names = [span.name for span in exported.spans.get_finished_spans()]
    assert names.count(SalesSpan.MESSAGE_PROCESSED.value) == 3
    assert "dw.run.start" in names and "dw.run.resume" in names
    assert caplog.records, "the capture saw no log line at all"

    assert _leaks(needles, exported.span_text()) == {}
    assert _leaks(needles, _log_text(caplog.records)) == {}
    error_text = [json.dumps(r.json(), ensure_ascii=False) for r in errors]
    assert _leaks(needles, error_text) == {}
    # No model is wired into this world (dw_sales ADR 0005: a process without
    # a model server calls none): nothing for Langfuse to receive.
    assert "dw.model.call" not in names


async def test_a_sales_span_carries_only_listed_attributes() -> None:
    exported = _Exported()
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, telemetry=exported.telemetry)
    async with _client(_app(world)) as client:
        processed = await _process(client, world, WALKED)
    case = world.order(uuid.UUID(processed["case_id"]))

    (span,) = [
        s
        for s in exported.spans.get_finished_spans()
        if s.name == SalesSpan.MESSAGE_PROCESSED.value
    ]
    attributes = dict(span.attributes or {})
    # Every listed key is one this span sets (but the reason a message was
    # routed): a key listed and never set is an allowance waiting for a value.
    assert set(attributes) == set(SPAN_ATTRIBUTES) - {"sales.routing_reason"}
    assert not span.events
    assert attributes["sales.case_id"] == str(case.case_id)
    assert attributes["sales.case_version"] == case.case_version
    assert attributes["sales.status"] == case.status.value == "in_review"
    assert attributes["sales.disposition"] == "case_created"
    assert attributes["sales.line_count"] == len(case.lines)
    assert attributes["sales.finding_count"] == len(case.findings)
    assert attributes["sales.finding_kinds"] == ",".join(sorted({f.code for f in case.findings}))
    assert attributes["dw.tenant_id"] == str(ALPHA.tenant_id.value)
    assert isinstance(attributes["sales.duration_ms"], float)


async def test_a_model_call_for_sales_exports_counts_and_cost_never_its_text() -> None:
    """DW1's model step (dw_sales ADR 0005) goes through the runtime's
    gateway, whose usage recorder is what reaches OTLP and Langfuse.
    What it exports is the profile, the model and the counts: no prompt
    variable and no completion, whatever the tenant (no tenant opts into
    content export; there is no such switch to turn)."""
    exported = _Exported()
    secret = "0.4850 USD Velatrix Electronics Vietnam Co., Ltd."
    request = ModelRequest(
        task="structured_extraction",
        prompt_id="sales.po_extract",
        prompt_version="1.0.0",
        variables={"po_text": secret, "subject": "PO VLX-PO-2609-0118"},
    )
    context = RunContext(
        run_id=uuid.uuid4(),
        tenant_id=ALPHA.tenant_id.value,
        workspace_id=ALPHA.workspace_id.value,
        actor_id=AN.user_id,
        worker_id=DW1_WORKER_ID,
        worker_version=DW1_WORKER_VERSION,
        channel="web",
        plan_id="professional",
        roles=frozenset(),
        scopes=frozenset(),
        trace_id="sales-model-call",
    )
    usage = ModelUsage(
        provider="mock",
        model="mock-structured",
        input_tokens=812,
        output_tokens=96,
        cost_usd=0.0123,
    )

    await TelemetryUsageRecorder(exported.telemetry).record(context, request, usage)

    (span,) = exported.spans.get_finished_spans()
    attributes = dict(span.attributes or {})
    assert attributes["gen_ai.usage.input_tokens"] == 812
    assert attributes["gen_ai.usage.output_tokens"] == 96
    tokens = {point.value for point in exported.metric_points(DW_MODEL_TOKENS_TOTAL)}
    assert tokens == {812, 96}
    (cost,) = exported.metric_points(DW_MODEL_COST_USD_TOTAL)
    assert cost.value == pytest.approx(0.0123)
    assert _leaks({secret, "PO VLX-PO-2609-0118"}, exported.span_text()) == {}


RECORDED: Mapping[str, Mapping[str, Any] | None] = json.loads(
    (REPO / "evals/fixtures/cases/sales_descriptions_recorded.json").read_text(encoding="utf-8")
)["answers"]
_LINES_INPUT = re.compile(r'<input name="lines">\n(.*?)\n</input>', re.DOTALL)


class _OnPremServer:
    """The ``onprem`` provider as the model server answers it: the recorded
    answers for the descriptions the rendered prompt carries, or, with
    ``refuse_schema``, the descriptions echoed back where the schema wants
    lines (what a pydantic error then holds as its ``input``)."""

    provider_name = "onprem"

    def __init__(self, *, refuse_schema: bool) -> None:
        self.refuse_schema = refuse_schema
        self.prompts: list[RenderedPrompt] = []

    async def complete_json(
        self,
        prompt: RenderedPrompt,
        json_schema: dict[str, object],
        route: ModelRoute,
        *,
        max_output_tokens: int | None,
    ) -> tuple[dict[str, object], ModelUsage, str | None]:
        self.prompts.append(prompt)
        match = _LINES_INPUT.search(prompt.user)
        assert match is not None, "the prompt no longer carries its lines"
        sent = json.loads(html.unescape(match.group(1)))
        usage = ModelUsage(provider="onprem", model=route.model, input_tokens=640, output_tokens=88)
        if self.refuse_schema:
            return {"lines": " / ".join(line["description"] for line in sent)}, usage, None
        unread = dict.fromkeys(set(ModelDescriptionLine.model_fields) - {"line_no"})
        lines = [
            {"line_no": line["line_no"], **unread, **answer}
            for line in sent
            if (answer := RECORDED[line["description"]]) is not None
        ]
        return {"lines": lines}, usage, None


def _model(exported: _Exported, server: _OnPremServer) -> GatewayInterpretation:
    """DW1's model step as the API wires it: the real gateway, its usage
    recorded to the process's telemetry, on the ``onprem`` profile."""
    profiles = ModelProfileRegistry()
    profiles.load_directory(REPO / "configs" / "models")
    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    gateway = RoutingModelGateway(
        profiles=profiles,
        prompts=prompts,
        adapters={"onprem": server},
        usage_recorder=TelemetryUsageRecorder(exported.telemetry),
        default_profile="onprem",
    )
    return GatewayInterpretation(gateway, model_profile="onprem", max_input_tokens=6000)


@pytest.mark.parametrize("refuse_schema", [False, True], ids=["answered", "outside_schema"])
async def test_a_model_reading_for_sales_exports_no_prompt_or_answer(
    caplog: pytest.LogCaptureFixture, refuse_schema: bool
) -> None:
    """Acceptance 2 through DW1's own model step (ticket 28's description
    reading of M36), not the recorder alone: what the model was sent and
    what it answered, including an answer the schema refuses (whose pydantic
    error holds it), reach no span, event, log record or response body."""
    caplog.set_level(logging.DEBUG)
    exported = _Exported()
    server = _OnPremServer(refuse_schema=refuse_schema)
    world = open_world(
        REPO,
        SampleSet.of(REPO, None),
        CALLERS,
        telemetry=exported.telemetry,
        model=_model(exported, server),
    )
    async with _client(_app(world)) as client:
        processed = await _process(client, world, "M36")
        case = world.order(uuid.UUID(processed["case_id"]))
        shown = await client.get(f"/api/v1/sales/orders/{case.case_id}")
        assert shown.status_code == 200

    # The model was called, through the gateway, as DW1's run.
    assert server.prompts, "M36 was processed without its model step"
    names = [span.name for span in exported.spans.get_finished_spans()]
    assert "dw.model.call" in names
    needles = await _document_values(world, "M36", case)
    sent = {line.po_line.description for line in case.lines}
    assert sent <= needles
    assert all(html.escape(text, quote=False) in server.prompts[0].user for text in sent)
    # What the model answered, span by span, where a span is long enough to
    # be told from a code (``BLACK`` is the colour code ``black`` in capitals).
    answered = {
        str(value)
        for answer in RECORDED.values()
        if answer is not None
        for key, value in answer.items()
        if key.endswith("_span") and isinstance(value, str) and len(value) >= 5
    }
    if not refuse_schema:
        readings = [line.basis.description_reading for line in case.lines]
        assert any(r is not None and r.outcome == "read" for r in readings)
        needles |= {text for text in answered if any(text in s for s in sent)}
    # And every 12 characters of a description: an error that quotes what it
    # refused (pydantic's ``input_value``) shortens it to its two ends, which
    # a search for the whole description does not find.
    needles |= {text[i : i + 12] for text in sent for i in range(len(text) - 11)}

    assert _leaks(needles, exported.span_text()) == {}
    assert _leaks(needles, _log_text(caplog.records)) == {}
