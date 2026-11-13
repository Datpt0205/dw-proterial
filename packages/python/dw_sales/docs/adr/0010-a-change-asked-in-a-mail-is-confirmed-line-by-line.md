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
