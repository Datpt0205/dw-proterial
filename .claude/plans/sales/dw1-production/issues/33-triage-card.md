# 33 — A triage card for a mail nothing else read

Status: ready-for-agent (behind 30's gate); held 2026-11-16 until Đạt decides dw_sales ADR 0014 (deep agent with tenant skills), under which it is rebuilt
Blocked by: 31
Category: enhancement

## Shape

- A mail routed `other` gets a card: what it seems to be, which case it
  seems to concern (resolved by code), one step from the closed set; Sales
  takes it or not. The card is advice; the routing stays.

## Acceptance

1. A card never names a case of another customer.
2. Without the step on, the mail is routed exactly as before.
