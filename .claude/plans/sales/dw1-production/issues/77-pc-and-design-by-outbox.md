# 77 — PC and Design by the outbox; DW reads PC's reply itself

Status: in-progress — Design by the outbox done 2026-11-26; PC's draft and the PC-reply lane left
Blocked by: none for the code; ticket 23 for live sending
Category: enhancement (UX, flow steps 3, 4, 11, Q3)

## Why

Asking PC for a date is five actions over two channels (copy, Outlook, record
asked, open PC's mail, read it, record the date); asking Design is three. The
reminder after 24 h reminds the PIC, not PC or Design.

## What

- "Gửi PC" and "Gửi Design" send the drafts DW already writes through the
  outbox from the PIC's mailbox; recipients come **only** from tenant config
  (`pc_mailboxes`, `design_mailboxes`), never typed; the receipt records
  "asked".
- A lane reads mail from `pc_mailboxes` naming the case's PO, extracts the
  date(s) (the existing PC-date reading), and proposes them on the case: the
  PIC sees "PC trả ngày … [Đúng] [Sửa]" in their work item (ticket 79).
  Reversible, so under ADR 0015 it may later apply itself once measured.
- The reminder goes to PC first; the PIC is told only when it is overdue.
- A new item code appearing in the Bravo copy (ticket 50) is offered for the
  line that asked Design for it.

## Acceptance

- Mock outbox + a PC reply in the mock mailbox: the date is proposed on the
  case without any PIC action; a reply from an address outside
  `pc_mailboxes` proposes nothing.

## Comments

**2026-11-26, slice 1: Design by the outbox.** Decided by recommendation
(Đạt 11-26): internal mail goes through the outbox, recipients only from
tenant config. `INTERNAL_SENDABLE`: the quotation's `design_request_draft`
and the order's `design_code_request` may be sent from the PIC's mailbox,
and only when every recipient is one of the tenant's `design_mailboxes`
(refused otherwise: "người nhận không phải hộp thư Design trong cấu hình");
a customer draft is never one of them. The quotation's receipt records "Đã
gửi Design" as the PIC (`QuoteCommands.design_sent`). The order's request is
recorded per line by "Ghi đã gửi Design", which the draft does not name line
by line, so that stays the person's press. Web: the two drafts get their send
button; the confirmation no longer says "cho khách". Tests: outbound 13 (sent
to Design and recorded as Diệu; a draft naming no configured Design mailbox
refused); the recipient guard mutated → red.

Left: PC. The request to PC is text on the page (`PcRequests.draft`), not a
draft file: it needs an `.eml` draft addressed to `pc_mailboxes` (order rules)
before it can go through the outbox, then "Ghi đã hỏi PC" on the receipt;
then the lane reading PC's reply (`pc_dates`) on its own.
