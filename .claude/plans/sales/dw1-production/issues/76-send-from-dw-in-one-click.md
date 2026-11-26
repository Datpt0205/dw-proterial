# 76 — Send every customer draft from DW in one click, and record on receipt

Status: ready-for-agent (live sending needs ticket 23's flow)
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
