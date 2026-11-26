# 77 — PC and Design by the outbox; DW reads PC's reply itself

Status: in-progress — Design and PC by the outbox, and DW1 reading PC's reply into a per-line proposal, done 2026-11-27 (the reading off until a tenant turns it on and it is measured live); the reminder to PC first waits on Đạt
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

Left after 3b: the PIC's press, its source gate, the labels, the panel and
the reminder (slice 3c below).

**2026-11-27, slice 3c: the PIC confirms or corrects each line.** On the
order's "Hỏi PC ngày giao" panel, a line DW1 read dates for shows them
tagged "Máy đọc, cần kiểm", each with the words of PC's mail it rests on,
and three controls: "Xem thư" (`GET /orders/{id}/pc-reply/mail?message_id=`,
`PcRequests.reply_mail`: only a mail the proposal was read from, only to
`sales.order.prepare`; it serves the mail's newest part and records it
served to that person at the case's version), "Đúng" (`POST
/orders/{id}/lines/{n}/pc-reply/accept`, Idempotency-Key,
`PcRequests.accept_reply`: one line per press, the proposal's dates with the
line's own delivery quantities, recorded through the same path as the
person's typed answer, as the person; refused with "chưa mở nguồn" until
every mail behind the line was opened at this version, so after one press
the next line's mail is opened again; refused "pc_reply_incomplete" when the
mail does not date every delivery of the line), and "Sửa" (the answer form,
filled with DW1's dates). The button stays disabled with the reason in
words until the mail has loaded for this person (ui-quality §7).

Decision (by recommendation, recorded here): PC's mail is served as a
one-page source of its own in `sales.source_served` (`pcmail.<sha256 of the
message id>`, page 1), the shape the table's CHECKs already admit, rather
than a new column or table; a reviewer who wants a separate kind adds a
migration then.

Every answer to a line DW1 had proposed dates for writes a labelled case
(`pc_reply_label`, step `pc_reply`, field `pc_dates`): "Đúng" confirmed,
"Sửa" with other dates corrected, in the answer's transaction. The
`waiting_pc` reminder is not sent while a proposal holds dates
(`WaitingCase.pc_proposed`, SQL `jsonb_array_length(pc_reply->'dates') >
0`): PC answered, and the PIC was told then. The case view carries
`pc_reply`; the event `order.pc_reply_read` is labelled.

Tests: `test_pc_replies.py` 27 (5 new: "Đúng" refused until opened, then
recorded as An for line 1 only with the labelled case confirmed; opened
again at the next version; "Sửa" labelled corrected; refused to a reader,
at a stale version, for a line with no proposal, for a mail not behind the
proposal, in another tenant; refused when the mail does not date every
delivery), follow-ups 64 (a proposal stops the reminder), PC integration 7
(the served region read back per person and version, the labelled case
admitted, `pc_proposed` from SQL), API route units, web pc-request 6.
Mutations, each red: the opened check removed; the deliveries check
removed; the label not written; `accept_reply` without its scope check;
the web "Đúng" not waiting for the mail.

Left, and why:
- "The reminder goes to PC first; the PIC is told only when overdue": an
  automatic mail to PC with nobody pressing. ADR 0015 makes anything sent
  T2 and `outbound_mail` sends nothing without a press. Owed: Đạt's word,
  and an ADR 0015 amendment if yes.
- "A new item code appearing in the Bravo copy (ticket 50) is offered for
  the line that asked Design for it": not built in this ticket's slices;
  it reads ticket 50's Bravo copy, which is ticket 50/06's seam.
- The update loop's request to PC (step 11) through the outbox, and its
  proposals: its `ask_pc` refuses while the change request is open, which
  the artifact gate cannot see; left so a mail never goes that cannot be
  recorded.
- Accepting does not mark PC's routed mail handled in "Việc cần làm":
  the inbox lane routes it as any internal mail; it may show twice.
- Owed by measurement on the plant (tickets 52/83): whether Proterial's
  internal Exchange mail reads as verified (SPF/DKIM/DMARC pass). If it does
  not, the lane, like the person's own list, sees none of PC's mail;
  `verified` is not loosened silently.
- Owed from Proterial: `pc_mailboxes` (ships empty: the draft and the lane
  refuse until named), ticket 23's flows for live sending, and a live run of
  `sales_pc_dates` on the plant's model before the switch can turn on.
- Not tested against real RLS for the lane end to end (the unit world plus
  the SQL `waiting_on_pc` negative stand in); an integration run of the
  lane over two tenants is owed.
