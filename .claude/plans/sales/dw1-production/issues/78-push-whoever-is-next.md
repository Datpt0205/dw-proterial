# 78 — Push whoever's turn it is

Status: in-progress — the platform push and the checkers done 2026-11-26; the export-control PIC and push off at sign-out left
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

## Comments

**2026-11-26, done.**
- **Every notice can reach a phone.** Migration `19a366484422`: the channel
  outbox (ADR 0006) gains `web_push`; `platform.deliver_notification` queues
  one for each recipient a notice was inserted for who holds a push
  subscription in that workspace (the opt-in), in the same statement. Worker
  lane `web_push_delivery` (`dw_worker.consumers.web_push_delivery`, on where
  the deployment has a VAPID key) sends them through `WebPushService.push`
  under one tag, so pushes replace each other on the lock screen; never the
  notice's body. So a mail routed to Sales, an approval, DW2's notices all
  push now, with no code in the context.
- **No double ring.** `p_push` (default true); Sales' follow-ups keep their
  own batched push (ticket 48) and are wired with
  `SqlNotificationRepository(push=False)`.
- **Who checks is told.** Where a case waits on a checker (`checker_scope`:
  cross-check, quotation approval), the follow-ups tell every holder of that
  scope but the assignee, beside the heads.
- Tests: Postgres 16 (a subscriber queued once, a non-subscriber and another
  workspace's subscription not, `push=False` queues none), migration
  down/up; lane unit 4; follow-ups 135 + 285 related. Mutations red:
  `p_push` ignored, any subscriber in the workspace, the checker not added,
  the assignee not excluded.

Left: the export-control PIC (an NOC/ESF waits as a finding, not a status
`WHOSE_TURN` reads); a device's subscription cancelled at sign-out.
