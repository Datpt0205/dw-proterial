# 23 — No price, name or mail text reaches a span, log or error (G32)

Status: done (built 2026-10-12, reviewed and closed 2026-10-13)
Blocked by: —
Category: enhancement

Split from ticket 12 on 2026-10-12.

## What

DW1 handles prices, customer names and email text. Approval payloads, run
results and audit already carry ids only (ticket 10), but nothing asserts the
same for OpenTelemetry spans, Langfuse traces, log lines and error responses,
and there is no attribute allowlist for Sales components.

## Acceptance

1. Sales spans carry attributes from one allowlist (case id, version, kind,
   status, finding kinds, counts, durations, safe tenant/workspace ids); any
   other attribute is dropped at the Sales span helper, not merely not set.
2. Model calls made for Sales do not export prompt or completion text to
   Langfuse/OTel unless the tenant's classification allows it (default: do
   not); token counts and cost still export.
3. A test processes a fixture PO end to end with an in-memory span exporter
   and a captured log handler, and asserts that none of its prices, customer
   names, email subject/body, or file names appear in any span attribute or
   event, log record, or error response body.
4. Error responses from Sales routes name the error code and ids, never a
   value from the document.
5. Mutation check: add the unit price as a span attribute and watch the test
   go red.

## Out of scope

- Where the data plane runs (waits on Proterial's deployment answer,
  ticket 12).

## Sources (as of 2026-10-12)

- `dw_sales/application/` (run and processing services), the platform's
  tracing setup, `CLAUDE.md` "Observability and evaluation".

## Comments

- Decided by the agent (Đạt away), 2026-10-12: **a Sales span is a marker
  emitted after the step**, as the runtime's `dw.model.call` is: the outcome
  (case, status, findings) is known only then, so the duration is the
  attribute `sales.duration_ms`, not the span's own start and end. A side
  effect wanted here: an exception raised by a Sales step is never on a
  Sales span.
- Decided by the agent (Đạt away), 2026-10-12: **the allowlist checks the
  value's shape, not only the key.** An id must be a `uuid.UUID`, a version
  or count a non-negative int, a duration a non-negative number, everything
  else a member of a closed code set (case kind, order/quote status,
  disposition, routing reason, finding codes). A price under `sales.status`
  is dropped like a price under a key of its own. The mailbox message id is
  not listed: a real mailbox's Internet message id can carry the sender's
  domain. The case id is.
- Decided by the agent (Đạt away), 2026-10-12: **acceptance 2 needs no new
  switch.** DW1 calls no model (spec decision 13). Model calls go through the
  runtime's `TelemetryUsageRecorder`, the only path to OTLP and Langfuse,
  and it exports the profile, the model, token counts and cost, never a
  prompt variable or a completion, for every tenant. No tenant
  classification that opts into content export exists, and none is built: it
  would be a control nobody reads (failure-modes #1) until DW1 calls a model
  and a tenant asks for content traces. The test pins today's behaviour for a
  call made as DW1.
- Decided by the agent (Đạt away), 2026-10-12: **the API's 422 for a request
  body no longer echoes `input`, platform-wide.** FastAPI's default handler
  returned each refused value, so a correction body with a price, or a field
  the model forbids holding a customer name, came back in the error.
  Exception handlers are per app, so a Sales-only handler is not possible.
  The envelope is unchanged (`{"detail": [{loc, type, msg, ctx}]}`) and so is
  the OpenAPI document (`input` was optional there). The web client reads no
  422 `detail`.

### As built (2026-10-12)

1. `dw_sales.application.telemetry`: `SPAN_ATTRIBUTES` (key → shape),
   `allowed_attributes`, `SalesSpans.emit` (the one way Sales emits a span),
   `case_attributes`, and `SpanPort`, the narrow Protocol the platform's
   `TelemetryPort` satisfies. `InboxProcessing` emits
   `sales.message.processed` for every message DW1 processes: tenant and
   workspace ids, disposition, routing reason, and for a case its kind, id,
   version, status, finding codes, line and finding counts, and the
   duration. Wired from the process's own telemetry: `assemble(telemetry=)`,
   `build_dw1(telemetry=)`, the API's `build_sales` from
   `wiring.seam.telemetry`, the worker's mailbox lane from its own;
   `open_world(telemetry=)` and `MemoryRuntime.build(telemetry=)` hand one
   port to DW1 and the runtime. `dw_sales` declares `dw-observability`.
2. `dw_api.exception_handlers`: `RequestValidationError` → 422 without
   `input`.
3. Tests. `apps/api/tests/unit/test_sales_telemetry.py`: M01 (Excel) walked
   to `confirmed` (processed through the route, self-check, Bravo entry,
   cross-check decided on the approval its run paused on, confirmation), M03
   (text PDF) and M16 (scanned PDF, routed) processed, through the real
   Sales router behind the API's exception handlers, the runtime's and
   Sales' spans exported through `OtelTelemetry` into an
   `InMemorySpanExporter`, logs captured at DEBUG from the root. Five
   refusals (already processed, stale version, a price typed for a finding
   the case lacks, a body the model refuses holding the price and the
   customer's name, an unknown case). Then 43 needles read from the stored
   cases and messages (unit prices, line amounts, totals and quotation
   prices in every printed form, customer names, the buyer, subject, body,
   sender, file names, item descriptions, finding evidence) are searched for
   in every span name, attribute, event and status, every log record
   (message, exception, extras), and every error body: none is found. A
   second test checks that the processing span carries every listed key and
   nothing else. A third checks that a model call made as DW1 exports counts
   and cost and no prompt text. `packages/python/dw_sales/tests/unit/test_telemetry.py`
   covers the allowlist key by key (17 refused shapes).
4. Mutation checks (each run against the passing tree, then restored):
   the unit price emitted through the helper under a new key stays green,
   which is acceptance 1 (the helper drops it). The same key also listed
   turns the end-to-end test red (`0.042` found in the span). The helper
   bypassed turns both span tests red. The 422 handler echoing `input` again
   turns it red (`0.042 Velatrix …` in the body). The price logged at DEBUG
   turns it red. The allowlist keeping every value turns the unit test red,
   and a key listed but never set turns the attribute test red.
5. Seen and not changed (platform, outside this ticket):
   `OtelTelemetry._span` records `str(exc)` and the stack trace as a span
   event for any exception that crosses a span, such as the runner's
   `dw.run.start`. The worker's mailbox lane `logger.exception`s a failed
   message. Sales raises `DWError`s with fixed messages and id-only details,
   and its models hide their input, so the walk finds nothing. A
   non-`DWError` exception whose text holds document content (a parser's,
   say) would reach both. Narrowing what a span records of an exception is a
   platform decision.

### Review (2026-10-13)

The adversarial review cut off on 2026-10-12, done against the tree after
tickets 28–33, which made DW1 call a model (dw_sales ADR 0005) and so
outdated the comment above that "DW1 calls no model".

Findings, each fixed:

1. **Acceptance 2 was tested at the recorder, not through a Sales model
   step.** The third test fed `TelemetryUsageRecorder` a request by hand, and
   the end-to-end test asserted `dw.model.call` was absent. New:
   `test_a_model_reading_for_sales_exports_no_prompt_or_answer`, twice
   (answered; an answer outside the schema). M36 is processed through the
   route with ticket 28's description reading on the real
   `RoutingModelGateway` (`onprem` profile, the real prompt registry), behind
   `GatewayInterpretation` as the API wires it, its usage recorded to the
   exported telemetry. The descriptions are shown to be in the rendered
   prompt, `dw.model.call` is shown to be exported, and then no description,
   no 12-character window of one, and no span text the model answered with
   is in any span or log record.
2. **Every span exported the text of any exception that crossed it.**
   `OtelTelemetry._span` set the status to `str(exc)` and called
   `record_exception`; and, measured on the pinned SDK, `start_as_current_span`
   records the exception a second time on its own (message and stack trace,
   which quotes every chained cause). A parser's or a validator's message, or
   a `KeyError` on a description, would have reached the collector and
   Langfuse from `dw.run.start`. Now a span records the exception's type and,
   for a `DWError`, its message (safe to log by contract), nothing else; the
   SDK's own recording is off. Stack traces stay in the process's log.
   `dw_observability` test
   `test_an_exception_on_a_span_exports_its_type_never_its_text`.

Checked and found sound: no Sales code calls the telemetry port but
`SalesSpans.emit`; no HTTP auto-instrumentation exports URLs; every
`DWError` Sales raises carries ids, codes and field names (a layout's refusal
names `problem:field`, never a cell); every Sales model hides its input in
errors; the model adapter logs the error's type only; FastAPI's 422 drops
`input`.

Mutation checks (each against the passing tree, then restored):

- `dw.model.call` given the prompt variables → both model tests red.
- the gateway logs the model's raw answer at DEBUG → both red.
- the Sales model adapter logs with `exc_info` AND `ModelDescriptionReading`
  stops hiding its input → `outside_schema` red (`Dây điện AWG24 lõi …` in
  the log). Either alone stays green, correctly: the other still holds.
- the SDK's exception recording back on → red; the event's message back to
  `str(exc)` → red.

- Decided by the agent (Đạt away), 2026-10-13: **a span records an
  exception's type, and a `DWError`'s message, and nothing else, for every
  process.** The ticket's earlier note called this a platform decision; it
  is taken on the fail-closed default (failure-modes #7): a trace can go to a
  hosted Langfuse, and losing a stack trace from a trace costs a log lookup,
  while a customer's price in a third party's store cannot be taken back.
  Logs keep their stack traces: they stay in the deployment's own pipeline.
  The worker's mailbox lane still `logger.exception`s a failed message; that
  is a log, and stays.

### As built — review (2026-10-13)

- `packages/python/dw_observability/src/dw_observability/otel.py`:
  `_exception_event`; the SDK's `record_exception`/`set_status_on_exception`
  off.
- `packages/python/dw_observability/tests/unit/test_telemetry.py`: one test.
- `apps/api/tests/unit/test_sales_telemetry.py`: the model-step test (two
  cases) and its `_OnPremServer`.
