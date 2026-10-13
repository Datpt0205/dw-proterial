# 23 — No price, name or mail text reaches a span, log or error (G32)

Status: built (2026-10-12), review interrupted: its adversarial review still owed
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
