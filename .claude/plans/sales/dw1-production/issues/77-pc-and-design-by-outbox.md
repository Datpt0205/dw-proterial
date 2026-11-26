# 77 — PC and Design by the outbox; DW reads PC's reply itself

Status: in-progress — Design by the outbox done 2026-11-26; PC by the outbox done 2026-11-27; the PC-reply lane left
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

**2026-11-27, slice 2: PC by the outbox.** The order's `pc_request_draft`
is an `.eml` in the words the page already shows (`sales_handoffs`
`pc_request`, one owner: `handoffs.pc_asked_lines` feeds both the page's
`PcRequests.draft` and the draft, and a test holds the mail's subject and
body equal to the page's), addressed to the tenant's `pc_mailboxes` (order
rules) only, and refused while none is configured ("chưa cấu hình hộp thư
của PC", `pc_mailbox_unknown`). It opens where `OrderCase.ask_pc` does
(`in_review`, `prepared`). `ArtifactCopy` now carries the hand-off copy
(stamped `sales_handoffs.pc_request@<v>`, so a redraw at the same case
version uses the same words) and PC's mailboxes. `INTERNAL_SENDABLE` is one
table of artifact kind to team; the send checks every recipient against
that team's setting as it stands at the press ("người nhận không phải hộp
thư PC trong cấu hình", `recipient_not_pc`), never Design's. The receipt
records "Ghi đã hỏi PC" as the PIC through `PcRequests.ask`, from the
mail's `queued_at` (when they pressed), not from when the receipt was
read; a case that can no longer take it is left and the PIC is told ("Thư
hỏi PC đã gửi nhưng chưa ghi được"). The outbound notices no longer say
"cho khách" (they serve Design and PC mail too). Web: the draft has its
send button in the files panel, and the PC panel says it can be sent from
there. No config version bumped, no migration (artifact kinds are not
CHECK'd). The update loop's request to PC (step 11) is left out: its
`ask_pc` refuses while the change request is open, which the artifact gate
cannot see, so a mail could go that the receipt could not record.

Tests: outbound 17 (4 new: sent to PC's mailbox in the page's words and
recorded asked as An from the press; refused when PC's setting no longer
names the recipient even though Design's does; not drawn with no PC
mailbox; a receipt the case cannot take is told to the PIC), artifacts 198
(the kind's render/gate row), PC requests, PC dates, update loop, design
requests, rules, reply drafts and the rest of the copy's readers green; web
pc-request 3. Mutations, each red: the receipt not calling
`_mark_pc_asked`; the PC guard checking Design's mailboxes; the PIC not
told; `pc_email` not refusing an empty setting; the PC panel's hint shown
outside the askable states.

Left: the lane reading PC's reply into a proposal (below, next slice), and
"the reminder goes to PC first" (an automatic mail with nobody pressing:
ADR 0015 makes anything sent T2, so it waits on Đạt's word).
