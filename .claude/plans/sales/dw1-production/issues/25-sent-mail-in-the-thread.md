# 25 — Sales' sent mail joins its thread

Status: done (2026-11-14), with a fake flow; the real export waits on 23
Blocked by: 23 for the real link field
Category: enhancement

## Why

dw_sales ADR 0009 decision 3: DW must see what Sales asked and when a
confirmation left, also when Sales answered from Outlook.

## Shape

- A message is outgoing when its sender is the member's own sign-in
  address (resolved by the server), never by the folder name.
- An outgoing message is stored and threaded, never processed into a case,
  never routed, never read for values. Its thread intents may be read
  (ticket 26).
- The mail drop lane reads it like any file; the inbox lists it under its
  thread, marked "Sales gửi".

## Acceptance

1. A sent copy from a PIC's folder is stored, threaded and has no
   disposition of its own.
2. A file whose sender is NOT the member is treated as incoming (the
   folder decides nothing).

## Done

- **The rule** (`application/outgoing.py`): `is_outgoing` = the sender is
  one of the workspace's people's sign-in addresses (`sales_addresses`, the
  platform's user record via `MemberDirectoryPort`, service accounts out),
  never the folder or anything a client sends; an upload (`UPLOAD_PREFIX`,
  moved to `order_ports.py` so both read one owner) is never outgoing; a
  member address with SPF/DKIM/DMARC `fail` (SPF `softfail`) is incoming.
- **Never a case**: `InboxProcessing` takes a message with no disposition
  that is outgoing down `_sent`: no classification, no intake, no route;
  `process_all` skips it; `Dw1Runs.process` and the drain report it as
  `outgoing` (no model-retry failure). A message processed before the rule
  keeps its disposition.
- **Store path**: `sales.sent_messages` (migration `7f3def432f82`: RLS
  ENABLE+FORCE, tenant AND workspace-or-offboarding policy, SELECT/INSERT
  only, UPDATE/DELETE revoked, `ck_sent_messages_reading`), `SentRead`,
  `SentReadLogPort`, `SqlSentReadLog`, the in-memory one in `evals/world.py`;
  one row per message taken up, with its reading (ticket 26) or none; a
  step row (`domain.activity.sent_outcomes`) and an audit row.
- **The lane** (`InboxLane`): an outgoing message is queued only while the
  tenant reads thread intents (`ThreadIntentsPort`, `OrderIntake.reads_thread_intents`)
  and only until it has its record: with the step off, Sales' mail costs no run.
- **Under its thread**: `threads.case_thread` (was `talk_before`) returns
  the talk before, Sales' sent mail on the thread and the own messages'
  times; a sent mail is on a case when addressed to someone who wrote one
  of that customer's mails there (`addressed_to`), the same rule as
  `ThreadLinks.sent_cases` uses for a reading. Views: `thread_sent`
  (`SentMessageView`) on the order and quote cases; `outgoing` on
  `MessageDispositionView`. Web: "Sales gửi" in the inbox (no "DW xử lý",
  not counted as waiting) and in the case's thread card.
- Tests: `test_sent_mail.py` (rule, uploads, forged, service accounts,
  acceptance 1 and 2, a PO file in Sales' mail opens nothing and a second
  processing is refused, another customer's recipient), `test_inbox_lane.py`
  (never queued with the step off; queued once with it on),
  `test_sent_messages_db.py` (one row, isolation across workspace and
  tenant, grants, the CHECK), `test_privileges.py`; web
  `inbox-processing.test.tsx`, `case-replies.test.tsx`; evals
  `sales.reply_sent_cross_customer`.

Decided here, not in the ticket: the forged-sender and upload exceptions;
"on a case" by recipients rather than by the customer of each recipient
(no catalog read on every case page); queueing only while the intents step
is on (runs per day are the plan's); the record in a table of its own
rather than a disposition, as the ticket says it has none. A PIC
forwarding a customer's PO to a colleague is now Sales' mail and opens
nothing (the customer's own mail opens the case): recorded in ADR 0009.

Remains: ticket 23 (the real Sent Items export, and whether it keeps
`In-Reply-To`: without it a sent copy has its own thread key and reaches a
case only through the customer's next reply naming it).
