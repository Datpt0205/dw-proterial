# 35 — The DW1 process map redrawn; the configuration made simple

Status: ready-for-agent
Blocked by: none (redrawn again as 24–29 land)
Category: enhancement

## Why

Đạt, 11-13: redraw DW1's flow on the portal (React Flow, the one place
`@xyflow/react` is allowed) to the BA's merged flows and dw_sales ADRs
0009–0012, and keep the configuration simple: few settings, each one a
non-technical head understands, never so many they confuse.

## Shape

- The map shows the BA's step codes (0-KH … 6.3; 1 … 2.1.6), the thread
  before the PO, the change loop and the confirmation wait. The moves come
  from code (`order_moves()` and the quote moves); the map never lists them
  a second time.
- The settings a tenant changes are a short list with defaults and one
  sentence each; everything else stays the platform's.

## Acceptance

1. A move added in code appears on the map without editing the map.
2. The settings a head sees fit one screen per DW, each with one sentence.
