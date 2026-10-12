# 23 — No price, name or mail text reaches a span, log or error (G32)

Status: ready-for-agent
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
