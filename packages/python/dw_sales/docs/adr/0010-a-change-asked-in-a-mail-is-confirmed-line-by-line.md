---
status: Accepted
date: 2026-11-13
accepted: 2026-11-13 (Đạt, on the grilling's recommendations Q5, Q6, Q10)
amends: ADR 0005 (the body never changes a value), ADR 0004 (reply kinds of ticket 32)
---

# A change a customer asks for in a mail is proposed, then confirmed line by line

## Context

The BA's flow classifies incoming mail as a new PO, a PO adding codes or
quantities, or a change of price or schedule (step 1), and step 6.1A has the
customer ask, by mail, to pull in or push out, raise or cut a quantity,
change the place or the transport, or ship part early; 6-DW1 links it to the
original PO and compares. Box B03 has such a request as a table in the
mail's HTML body, with no file. `order_intake` held "the body never changes
a value", and a reply's reading (ticket 32) had kinds fixed to two waits.

## Decision

1. **One closed set of thread intents**, for a customer's mail and for
   Sales' own: `sends_po`, `requests_change`, `cancels`, `accepts`,
   `rejects`, `asks`, `adds_info`, `sends_rfq`, `unclear`. A message may
   carry several, each standing on its own quoted sentences that code
   locates in the newest part. The model gives the kinds and the quotes;
   which case and which step are code's, from the case's kind and status (a
   table, as `REPLY_STEPS`). It replaces ticket 32's `ReplyKind`.

   *Built 2026-11-14 (ticket 26), by the agent:* `domain/reply_intent.py`
   holds `ThreadIntent`, the model's answer (`ModelThreadIntents`: up to
   four intents, each with up to three quotes) and `verified_intents`: an
   intent with no quote located once in the newest part is `unclear`, an
   intent given twice is kept once. The table (`INTENT_STEPS`) is keyed by
   who wrote the message too, since the same words from Sales and from the
   customer lead to different steps: a customer's `accepts`/`rejects` on a
   spec discussion settle or decline it, `rejects` (keep the PO) or
   `accepts` on a correction request resume the review, `sends_po` awaits
   the revised PO; Sales' `asks` on an order in review proposes
   `request_correction`, on a quote with Design's reply `discuss_spec`:
   the two statuses `waiting_customer` watches. Intents pointing at two
   different steps propose nothing. Only the newest message of the case's
   thread, a reply or Sales' own, proposes; a person takes the step
   (HITL, Đạt 11-04). Prompt `sales.reply_intent@2.0.0` (context, subject,
   body; the context is code's sentence: who wrote it and what Sales last
   asked); the switch stays `model_assist.reply_intent`. Stored readings of
   1.0.0 were rewritten by migration `7f3def432f82` (kind to intent).
   Measured: see `.claude/plans/sales/dw1-production/issues/26-thread-intents.md`.
2. **A change request** (Yêu cầu điều chỉnh) is a record on the case: per
   line, the field, the value the case holds, the value asked, and a source
   anchor into the mail's characters. A model copies the asked value's text;
   code locates it and parses numbers and dates; a table in HTML is split by
   code. Nothing reaches the case until the PIC confirms each line; then the
   case takes a new version, and Bravo is written only after a person
   approves (ADR 0026). The rule becomes "**the body changes no value a
   person has not confirmed**"; a file still wins over the body where both
   speak.
3. **The update loop follows the BA's step 6.** Before the order is in
   Bravo, a confirmed change re-runs the checks (steps 2–3) like a revision
   and DW drafts the answer. Once it is in Bravo: a change to dates or
   quantities drafts the PC request (6-DW2) the PIC sends; PC's reply
   (`pc_dates`) leads to the drafted confirmation of the change (6-DW4) or
   the status and options (6-DW3); the customer's answer is read as above
   (keep the PO, accept, or ask PC again); the PIC approves the Bravo
   update (6.2-SP); the PO and schedule go back (6.3) and the case waits for
   the customer (ADR 0011).
4. **One change request open per case.** One that arrives while another is
   open queues behind it and the PIC is told; they are never merged.
5. **The PIC approves every 🔒 step**, as in the BA's flow; a cross-check
   applies as the tenant's rules stamped on the case say. No new role.

## Built 2026-11-15 (ticket 27), by the agent: decisions 2 and 4

What the decision did not settle, settled here; each can be reversed by a
new version of this note.

- **What a line may change**: a line's delivery date (`requested_date`) and
  its quantity, the BA's 6.1A pull-in, push-out, raise and cut. A price,
  the place or the transport are no value of a line DW1 holds; a mail
  asking one is read by a person.
- **Where a request comes from**: a customer's reply the thread headers
  attached to the order (ticket 32), and nothing else, so the sender is the
  order's own customer by code's link. A person records it ("Ghi yêu cầu
  thay đổi"); the reply's `requests_change` intent does not open one by
  itself, and no lane does (the intents step is off, and a request is the
  PIC's to record). One mail opens one request per order.
- **A table is read by code, by its values**: a row is the order's when one
  of its cells is the order's PO number; its line is the one whose customer
  item code (or PRV code) is a cell, a line number telling apart lines that
  share a code; the date columns are those whose cells all read as dates
  (and not as numbers), the held one is the column of the dates the order
  holds, the asked one is the one other. No header word is read. A quantity
  is never taken from a table: an id, a line number and a price column read
  as numbers too, and nothing in the values tells the asked one apart. Two
  candidate date columns, a row naming no line of the order: counted as
  unread, for a person.
- **Free text is a model step**, `model_assist.change_request`
  (`sales.change_request@1.0.0`, bar 0.85 on `all.right_change`, dataset
  `sales_change_request@1.0.0`): the model copies the words naming the line,
  the field and the words of the value; code finds both once, takes the
  line from an item code of the order inside the words or the one number in
  them, and parses the value through the mail's notation. Shown the mail
  only (no line of the order). Off for every tenant: the platform's rules
  versions do not name it, and it is not measured. A person types what DW1
  did not read, with the date picker and the number box. Measured live on
  2026-11-15 (local `qwen3.5-9b-dw`): 1.0 on 12 changes in 8 synthetic
  mails, the injected value not given; not attested for any tenant.
- **What blocks a confirmation**, stamped when read: no such line, a unit
  other than the line's (`km` against `m`, never converted), a line that
  prints several schedules. Such a line is rejected with a reason. A value
  the order no longer holds when confirmed (another change, a correction or
  a revision since) is refused (`held_changed`).
- **Where a confirmed line is applied**: only in `in_review`, or `prepared`,
  which it reopens; the checks run again on the changed values as for a
  value Sales typed (a pulled-in date may now be short of the lead time).
  Once the order is in Bravo the change is ticket 29's update loop, and is
  refused here. The confirmer is a maker of the case. The case keeps the
  value as read and the change beside it (`OrderLine.changes`), and a
  revision of the PO reads afresh.
- **The queue**: requests are numbered per order; the next queued one opens
  in the transaction that closes the one before. The PIC is told on the
  order's page ("Chờ yêu cầu trước"); no notification is sent.
- **What is audited**: ids, the line, the field and counts; never a value
  or the reason a person wrote, which stays on the request. The mail's text
  reaches only a reader of prices, as a PO read from a mail does.

## Built 2026-11-15 (ticket 29), by the agent: decision 3, in Bravo

What decisions 3 and 5 did not settle, settled here; each can be reversed by
a new version of this note.

- **Where the loop runs**: on an order whose confirmation left
  (`confirmation_sent`, or `confirmed` once the customer agreed: ticket 28
  split them, ADR 0011). A change line confirmed between the Bravo entry and the confirmation
  is refused (`change_status`) and stays open on the request until the order
  is confirmed. The loop is state on the case (`OrderCase.update_loop`,
  migration `0d1d0e4eb203`), so every step takes a case version.
- **The order does not change until the customer accepts.** A confirmed line
  joins the loop, not the line; PC's answer in the loop is held there; "keep
  the PO" ends the loop and leaves every value as it was. One loop per case,
  from one change request: a line of another request is refused while one
  runs (`update_busy`). PC is asked once every line of the request is
  decided (`change_request_open`); a line confirmed after PC was asked is
  refused (`update_step`).
- **6-DW2 is ticket 07's request** (`render_pc_request`, `sales_handoffs`'
  `pc_request`) with the values asked. Its words say "đặt PO", not "đổi":
  a better wording is a new version of the hand-off copy, owed.
- **6-DW4 or 6-DW3 is code's**: every delivery PC gives a changed line on
  the date asked (or held, when only the quantity changes) is 6-DW4, any
  other date 6-DW3. Equality, not "on or before": delivering earlier than
  asked is also something the customer is asked about. PC's quantities must
  add up to the quantity asked, as in ticket 07; never adjusted. The verdict
  is stamped when the last line is answered and drives which draft
  (`sales_emails@1.3.0`: `change_can_do_draft`, `change_options_draft`, vi,
  en and ja) the artifacts offer.
- **The customer's answer is a person's**: keep, accept, ask PC again, from
  "Chờ khách quyết định" only (a customer's word while PC has not answered is
  refused). The thread-intent step stays off and proposes nothing here yet:
  wiring `accepts`/`rejects` on a loop to a proposal is owed with ticket 28.
- **Accept** applies each change and PC's answer to its line through the
  re-check path ticket 27 uses, keeps each delivery's first confirmed date
  (`orders.reconfirmed`, now the one owner of ticket 07's rule), clears the
  line's confirmed dates, stands PC's answer as its agreement on a short
  lead time, and moves the order to `change_review` with its cross-check and
  confirmation cleared, as a revision in Bravo does. An order already in
  Bravo is no longer checked against its own Bravo entry when re-checked
  (it read as its own duplicate).
- **6.2-SP reuses the path a Bravo write takes today**: the PIC approves the
  exact file (`bravo_update`: the paste sheet's rows of the changed lines, in
  the tenant's layout and SalesOrder rules), drawn at the case's version, by
  id and hash; any later edit drops the approval; `apply_change` (the DW1
  run's "Ghi đã nhập Bravo") refuses an unapproved update
  (`bravo_update_not_approved`). Then the existing cross-check (a platform
  approval, by someone who is no maker; whoever approved the file is a
  maker) and confirmation, which ends the loop. The PIC approves, as
  decision 5 says; no head approval is added. That approval is the maker's
  own sign-off on the file (`POST .../update/bravo-file`), like "Tự kiểm
  xong", not a checker's decision: the checker's stays the cross-check on
  the platform approval (ADR 0004), and no Sales route decides it.
- **Reminders reuse the two follow-ups that exist**: `waiting_pc` from when
  PC was asked in the loop, `waiting_customer` from when the answer was
  recorded sent. No rule field changed, so `sales_followups` keeps 1.3.0.
- **What is audited**: ids, the step and code's verdict or the customer's
  answer as a code; never a quantity or a date.
