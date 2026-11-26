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

**2026-11-27, slice 3a: where PC's reply is kept, and its switch.**
`OrderCase.pc_reply` (`PcReply`, migration `79418de5ab48`, a jsonb object
column under the table's existing grants and RLS): the dates PC's mail gives
the lines asked, each with its words and the mail it came from, and every
mail read for this wait, so none is read twice. `read_pc_reply` takes one
mail only while the case waits on PC, only one received since the request,
only once; it keeps dates for lines asked that have no answer since the
request, and per line the newer mail's dates stand (PC answering line 1,
then line 2, leaves both). Nothing of the case's values changes. One rule
in `_next`: the proposal ends with the wait (so answering the last line
closes both, never refused) and keeps a line only while the line is as it
was when the dates answered it (an answer, a correction or a change drops
it); asking again starts with none. The validator refuses a proposal
without a wait or for a line not asked.

The reading has no person pressing, so it is a model step
(dw_sales ADR 0005 decision 8): `ModelStep.PC_REPLY`, switch
`model_assist.pc_reply`, **off where a version does not say** (no platform
version says; no config bump), tier `PERSON_APPROVES` (each line waits on
the PIC; making it apply itself is a later ADR 0015 decision), bar 0.85 on
`all.right` of `sales.pc_date_golden` (the golden mails Sales' own reading
of PC's mail is graded on), not measured live, so not ready anywhere. The
same migration admits `pc_reply` in the four step CHECKs. Process settings
show the switch at O4 beside `pc_mailboxes`, labelled. Contracts and API
types regenerated (the ModelStep enum, the rules schema).

Tests: domain 7 (`test_pc_replies.py`), PC integration 6 (round trip in its
own tenant only, the CHECK), schema 41, readiness, process settings, order
rules. Mutations, each red: ask_pc keeping the old proposal; `_next` not
narrowing it; a mail older than the request taken; the newer-wins rule
dropped; the migration not admitting the step. Also fixed: the readiness
test that holds switches to steps had been red since 11-24 (`shadow` is one
switch for every shadow reading, not a step).

**2026-11-27, slice 3b: the lane that reads PC's reply.** Worker lane
`sales_pc_replies` (`application/pc_replies.py`, every 300 s, built only
where the worker reaches a model server). Per workspace it reads nothing
unless the tenant names `pc_mailboxes`, `model_assist.pc_reply` is on and
the step's live eval passed (`ModelStepGatePort`); then, over the orders
waiting on PC (`orders.waiting_on_pc()`, SQL `pc_request IS NOT NULL`), it
picks PC's answer by code alone: a verified mail from a PC mailbox, received
since the request (the request's `at` is the mail's `queued_at` when sent
through the outbox, slice 2), naming the PO or the Bravo SO of exactly one
waiting order (a mail naming two is left to the person's list: line numbers
repeat across orders), not read already. Its newest part only (DW1's own
request quoted below is never read, so the customer's requested date is
never proposed as PC's) goes through `pc_dates.reading`, the reading
Sales' own uses (split out of `PcDateReplies.read`, unchanged for the
person). Kept with `work.orders.save`, a worker case event
`order.pc_reply_read` and one lane audit row (counts only), with
`require_running` asked inside that transaction; a case that moved while
the mail was read is read again next tick; the model down keeps nothing and
reads again; a mail read to no date is kept as read (one call). The PIC is
told once per mail that gave dates, the assignee or else who asked PC, with
no PO number. `pc_dates`'s docstring no longer says internal mail never
reaches DW1.

Tests: `test_pc_replies.py` 22 (acceptance: the mock PC reply proposed
with no PIC action, nothing recorded, the wait open, the PIC told once
without the PO, read once; a colleague, the customer, an unverified mail, a
mail before the request, another order's: nothing; switch off, no PC
mailbox, not waiting, not measured: no model call; paused; model down;
no-date mail; a reply quoting only DW1's request; a mail naming two
waiting orders), worker registration, PC integration (`waiting_on_pc` in
its own workspace only), `sales_pc_dates` eval smoke PASS 5/5 with the
bar reported, import contracts 17 kept. Mutations, each red: the sender
filter, the received-since bound, the verified check, empty mailboxes
read as any sender, the one-order rule, the step gate, the pause check,
the full text read instead of the newest part, the lane not registered.
Also: `dw_worker/main.py` had an unsorted import in HEAD (ruff I001), fixed
by `ruff --fix` on the file.

Left (next): the PIC's "Đúng" per line and its source gate (ui-quality §7),
the labelled case on each "Đúng"/"Sửa", the PC panel showing the proposal,
the `waiting_pc` reminder while a proposal waits, and whether accepting
marks PC's routed mail handled. Owed by measurement, not code: whether
Proterial's internal Exchange mail reads as verified (SPF/DKIM/DMARC pass);
if not, the lane, like the person's list, sees none of PC's mail.
