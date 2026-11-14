# 24 — The mail thread: a key on every stored message; thread to case many to many

Status: done (2026-11-14)
Blocked by: none
Category: enhancement

## Why

dw_sales ADR 0009 decisions 1–2. `ThreadLinks` links a reply only when its
headers name exactly one case; once ticket 19 opens a case per PO, every
reply in a multi-PO mail's thread names several and links nowhere.

## Shape

- A thread key on each stored message, computed when stored from
  Message-ID / In-Reply-To / References (the earliest known message of the
  chain), never from the subject or a model.
- `ThreadLinks` returns every case of the sender's customer the thread
  holds, not only one. One: attached as today. Several: the numbers the
  message names (`message_intent.resolve`, or a document's PO number)
  choose; none named: routed `reply_to_case` with the candidate cases for
  Sales to pick ("Chọn hồ sơ").
- A case shows its thread(s), including the messages before its PO.

## Acceptance

1. A reply in a thread with three cases naming one PO number attaches to
   that case only.
2. The same reply naming none is routed with the three cases offered.
3. A reply whose References name another customer's message links nothing
   (negative test).
4. A message whose References name messages of two threads joins the
   earliest; the key never changes once stored.

## Done

- **Thread key** (`sales.mailbox_messages.thread_key`, migration
  `0e77f2ca8c45`, backfilled in stored order; `ix_mailbox_messages_thread_key`):
  set by `threads.thread_key` when `SqlMailbox` stores a mail or an upload,
  and by `ThreadIndex` for the mock mailbox; never updated (no UPDATE grant).
  A thread is read by `thread_keys` (own key plus the keys of what its
  headers name), through `ThreadMembersPort.thread_messages`, never by
  listing the mailbox. Out of order: documented in `threads.py`.
- **`ThreadLinks.cases`**: every case of the sender's customer a message of
  the thread is on (`MessageLogPort.cases_of`, a set of messages, ready for
  ticket 19's several cases per message).
- **Several cases** (`order_intake._among`): the intent model's numbers,
  resolved by `IntentReader.resolve`, choose (`named_cases`); else routed
  `reply_to_case` with `thread_cases` (`sales.messages.thread_cases`,
  `ck_messages_thread_cases`).
- **"Chọn hồ sơ"**: `POST /sales/inbox/{id}/case` (`sales.inbox.process`),
  `RoutedMailService.pick_case`, only an offered case; the reply records
  `picked_by`; audited `sales.message.case_picked`. Inbox panel
  `inbox/thread-cases.tsx`.
- **The talk before the PO**: `thread_before` on the order and quote case
  views (`threads.talk_before`), shown in the case's thread card.
- Tests: `test_mail_thread.py` (acceptance 1-4, out of order, no mailbox
  scan, numbers outside the thread), `test_sales_mailbox.py` and
  `test_sales_store.py` (keys, union, isolation, the CHECK),
  `test_service_scopes.py`, web `thread-cases.test.tsx`,
  `case-replies.test.tsx`.

Remains (known, recorded in ADR 0009's "Built 2026-11-14"):

- Two mails of one thread stored at the same moment by two workers can
  each miss the other's key (the lock is per mail); the union on read covers
  a direct ancestor, not two siblings sharing an ancestor stored after both.
- With the intent step off, a reply on a thread of several cases always goes
  to Sales ("Chọn hồ sơ").
- The talk before the PO lists only mails DW1 processed as the customer's
  own; `thread_summaries.py` still builds a thread from the case's own mails.
