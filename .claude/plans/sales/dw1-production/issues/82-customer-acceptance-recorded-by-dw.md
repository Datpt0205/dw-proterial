# 82 — DW records the customer's acceptance or silence, with undo

Status: resolved for silence (2026-11-26, by recommendation); a reply read as accepting stays the PIC's press
Blocked by: none
Category: enhancement (ADR 0015)

## Why

The PIC clicks to record an event DW already knows: the customer's reply read
as accepting (with the cited sentence), or the tenant's silence days passed.

## Proposal

- DW records "accepted" or "implied" itself, tells the PIC, and offers undo for
  the tenant's undo window. Internal and reversible: ADR 0015 T0/T1.
- A reply read with low confidence goes to the PIC as today.

## Acceptance

- The mock customer's accepting reply moves the case and notifies; undo
  restores the previous state with both events audited.

## Comments

**2026-11-26, done for silence.** Decided by recommendation (Đạt 11-26);
dw_sales ADR 0011 amended.
- The follow-up lane, where `sales_followups.implied_acceptance.record` is on
  (default true; a version written before reads the default), records
  `agreed("implied")` as itself once the stamped term has run out
  (`SilenceRecorder`: a DW1 worker event, the lane's system actor, the same
  domain fences), then tells the PIC with `sales_reminders@1.2.0`'s
  `implied_recorded` ("DW1 đã ghi khách đồng ý ngầm … bấm Hoàn tác").
- "Hoàn tác": `POST /orders/{id}/agreement/undo`, `confirmed →
  confirmation_sent` (a new edge, `undo_implied` on the process map), only an
  agreement by silence; the order page shows the button beside it.
- A lane's move labels no shadow reading (already so in `label_reply_move`).
- Tests: unit 24 (recorded as the lane with a worker event and the new
  wording, undone by An; a customer's words never undone), web 9; the
  `record` switch mutated → red.

Left: a reply read as `accepts` recorded by DW1 too: it rests on a model's
reading, so it waits on that step's measured error rate (ADR 0015's T1),
not on code.
