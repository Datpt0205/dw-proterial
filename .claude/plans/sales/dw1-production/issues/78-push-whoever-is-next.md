# 78 — Push whoever's turn it is

Status: ready-for-agent
Blocked by: none
Category: enhancement (platform + Sales)

## Why

Only DW1's follow-up lane sends a web push (`followups.py`). A mail routed to
Sales, a cross-check due, a quotation waiting for the Manager, an NOC/ESF
waiting for the export-control PIC reach nobody's phone. `WHOSE_TURN`
(`overview_service.py`) knows two audiences, `pic` and `head`; the
cross-checker and export-control PIC are neither, so they are not told at all.

## What

- Push from the platform's notification `deliver` (batched, quiet hours from
  the tenant), so every context's notice can reach a phone; DW2 inherits it.
- `WHOSE_TURN` gains the audiences the flow has: cross-checker (holders of the
  cross-check scope, not the preparer), quote approver, export-control PIC.
- A mail routed to Sales notifies and pushes the case's PIC.
- Signing out cancels the device's push subscription.

## Acceptance

- Each audience above gets one notice and one push per item (idempotent by
  source key); the preparer is never told to cross-check their own order.
