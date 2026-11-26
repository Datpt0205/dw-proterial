# 77 — PC and Design by the outbox; DW reads PC's reply itself

Status: ready-for-agent (default below; Đạt may veto the internal recipients)
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
