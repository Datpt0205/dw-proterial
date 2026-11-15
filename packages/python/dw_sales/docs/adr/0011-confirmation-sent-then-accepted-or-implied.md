---
status: Accepted
date: 2026-11-13
accepted: 2026-11-13 (Đạt, on the grilling's recommendation Q7)
---

# A final confirmation is sent, then accepted in words or by silence, and a person records which

## Context

After the talk, Sales sends the final PO back to confirm it (the customer's
own PO stamped, plus the processed Excel: Box B11). Đạt: the customer then
agrees, or says nothing, and silence is agreement after a time that depends
on the customer. The BA's flow ends at 5.3-KH "the customer receives it"
and the samples hold no customer answer, so silence as agreement is
Proterial's to confirm, per customer. The order case had one state,
`confirmed`, entered when Sales sent the confirmation.

## Decision

- **Two states.** `confirmation_sent` (Đã gửi xác nhận, chờ khách) is
  entered when the confirmation leaves: by the "Gửi cho khách" button's
  receipt, or by a sent copy in the case's thread that carries the Excel DW
  made for this case version (matched by sha256), which code proposes and
  the PIC confirms. Its clock starts at that mail's time. `confirmed`
  (Khách đã đồng ý) carries how: `accepted` (a reply read as `accepts`,
  with its quote) or `implied` (no answer within the customer's days).
- **A person records it.** The PIC (or the head) presses; the follow-up lane
  tells the PIC when a customer's days have passed. DW never moves the case
  itself (human-in-command, Đạt 11-04: no HITL relaxed before the plant).
- **The days are tenant config per customer, off by default**: a customer
  with no value never gets implied acceptance. This is not customer 4's
  "confirm within 48 h", which is Proterial's deadline, not the customer's.
- A `rejects` or `requests_change` after the confirmation moves the case to
  `change_review` (ADR 0010).

## Built 2026-11-15 (ticket 28), by the agent

What the decision did not settle, settled here; each can be reversed by a
new version of this note.

- **Existing orders.** Before the split, `confirmed` was entered when the PIC
  recorded the confirmation ("Ghi đã gửi xác nhận", with each line's
  confirmed dates), and nothing ever recorded a customer's answer: every such
  row was a confirmation sent. Migration `64d50dbc1d00` moves them to
  `confirmation_sent`, sent at `confirmed_at`, with no term (never implied),
  renames their events, keeps their version and `updated_at`.
- **The button path.** "Ghi đã gửi xác nhận" enters `confirmation_sent`
  directly, its clock at the press. The confirmation draft is drawn only once
  it is recorded (it carries the confirmed dates), so "Gửi cho khách"'s
  receipt moves nothing: the order is already there. The receipt does not
  reset the clock either.
- **The sent copy.** It proposes while the order awaits its confirmation
  (`cross_checked`, or `uploaded_to_bravo` with no cross-check required),
  when a mail Sales sent on the case's thread (the ticket 25 rule) carries a
  file whose sha256 is that of the paste sheet DW1 stored at the case's
  current version (`bravo_upload`: the processed Excel, below). The PIC
  records it from that mail; the request names the mail and the server finds
  it again, so the clock is that mail's time. A copy saved from Sent Items
  carries no thread headers (ticket 23), so until then it reaches a case only
  through a reply naming it.
- **The term.** `sales_order_rules@1.14.0` `implied_acceptance`, per
  customer code: `days` (1 to 60), `day_count` `calendar` (default) or
  `business` (Monday to Friday: no tenant holiday calendar exists; the
  followups' working days are Proterial's, not the customer's), and
  `counted_from` `confirmation_sent` (default) or `po_date`. The start day is
  not counted; silence counts from midnight, the tenant's time zone, after
  the last day. It is read from the rules stamped on the case when the
  confirmation is recorded, and its instant stamped on the confirmation: a
  version approved later reaches the orders checked after it.
- **The follow-up.** `sales_followups@1.4.0` `implied_acceptance.enabled`:
  the PIC is told once, as the days run out; the lane writes nothing on the
  case.
- **The answer.** Recorded only from `confirmation_sent`, by a holder of
  `sales.order.prepare`. `accepted` may name the customer's reply on the
  case, received after the confirmation left, and keeps the sentences DW1
  located there as `accepts`; with none (the intents step off, a call) it
  is still recorded. `implied` names no reply. "Khách từ chối" moves to
  `change_review`, clearing the cross-check and the confirmation, as a
  revision in Bravo does. While a customer's change runs in the update loop,
  their answer is the loop's, and both are refused (`update_running`).
- **The proposals.** A customer's newest reply on `confirmation_sent` read
  as `accepts` proposes "Khách đã đồng ý", as `rejects` "Khách từ chối"
  (`INTENT_STEPS`); nothing is proposed while the loop runs. A
  `requests_change` proposing "Ghi yêu cầu thay đổi" is still owed (ticket
  27's remains).
- **Where it shows.** `confirmation_sent` is Sales' part done, as
  `confirmed` was: not in the work list, not counted as waiting on the
  customer (with no days it may wait for good), "Đã xong" on the order list.
- **The processed Excel.** The confirmation draft now attaches the
  customer's own PO files of the current revision, byte for byte (the PO and
  its print copy; none for a PO written in the mail), and the paste sheet as
  the processed Excel. Which Excel Proterial calls "processed" (B11) is
  theirs to confirm; the paste sheet carries an internal sheet naming the
  case version and template.
