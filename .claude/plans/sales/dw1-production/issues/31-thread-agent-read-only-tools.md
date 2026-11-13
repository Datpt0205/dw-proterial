# 31 — The thread agent with read-only tools

Status: ready-for-agent (behind 30's gate)
Blocked by: 26, 30
Category: enhancement

## Why

dw_sales ADR 0012 decisions 1, 2, 4.

## Shape

- Tool specs under `configs/tools/`, side effect none, a toolset under
  `configs/toolsets/` that `configs/workers/sales.yaml` pins; ADR 0005
  decision 5 as amended.
- Tools: thread messages, case snapshot, case by number, conversion
  lookup, lead time and calendar, PC status; customer and workspace bound
  from the run.
- Output: ticket 26's schema; ceilings on calls, spend, time; fallback to
  the one-call reading.

## Acceptance

1. No tool takes a customer, tenant or workspace argument (a test walks
   the specs).
2. A turn over its ceiling falls back and says so.
