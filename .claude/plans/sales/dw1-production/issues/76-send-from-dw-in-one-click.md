# 76 — Send every customer draft from DW in one click, and record on receipt

Status: resolved (2026-11-26) for the code; live sending needs ticket 23's flow
Blocked by: none for the code
Category: enhancement (UX, `docs/sales/dw1-luong-va-viec-con-lai.md` steps 6, 9, Q5/Q6)

## Why

`outbound_mail.SENDABLE` allows `send_draft` (quote) and `confirmation_draft`
(order) only. A correction request, a reply, a decline or a spec discussion
must be copied into Outlook or downloaded as `.eml`. A confirmation must be
recorded as sent before it can be sent.

## What

- `SENDABLE` adds the customer drafts the case already writes (correction,
  reply, decline, spec discussion), each behind its gate.
- One button per draft: "Gửi" queues it through the outbox; the receipt
  (`sent`) records the step (confirmation sent, correction asked), so no
  separate "ghi đã gửi". `failed`/`stalled` tell the person as today.
- Recipients are the case's customer contacts only, as today.

## Acceptance

- Each new draft kind sends through the mock outbox and its receipt moves the
  case; a draft from a stale case version is refused.
- The two-click path (record, then send) is gone from the order page.

## Comments

**2026-11-26, done.** `SENDABLE` holds every draft DW1 writes to the customer
(order: confirmation, correction request, the change's two answers, the
internal-change notice, cannot-supply; quote: send, spec discussion,
decline), never a draft to Design or PC (a test holds it). On the receipt, a
change's answer records "Ghi đã gửi khách" as the person who pressed, through
`UpdateLoops.answer_sent` cut to the prepare scope, as the quotation's "Đã gửi
KH" already did; the others were recorded before their draft opened. Left
by design: the order confirmation still asks for "Ghi đã gửi xác nhận",
because that step records each line's confirmed dates. Web: one send per
customer draft on the case's artifacts card, each saying its own draft's
mail. Tests: server 11 (the answer sent from DW1 moves the loop to
`waiting_customer`, audited as An); web 4. Mutations red: the answer not
recorded, the draft not sendable, the status read from another draft.
