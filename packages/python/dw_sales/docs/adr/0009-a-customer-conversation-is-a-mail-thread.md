---
status: Accepted
date: 2026-11-13
accepted: 2026-11-13 (Đạt, on the grilling's recommendations Q1–Q4, Q8, Q12)
source:
    - ../../../../../.claude/plans/sales/dw1-production/spec.md
---

# A customer conversation is a mail thread read from its headers; cases hang off it

## Context

Before a final PO, a customer and Sales write back and forth in one Outlook
conversation: a PO or a request first, then questions, corrections, changes
asked in the body, a revised file, the confirmation. The real mail (Box
B03, B11, B17, B22, measured 11-13 with the headers' shape only) shows:

- a mail as received carries `In-Reply-To`, `References` with the whole
  chain (7–16 Message-IDs) and `Thread-Index`; a copy saved from Sent Items
  carries none of them;
- one conversation covers several POs (a pull-in thread of 9 mails over
  weeks, a confirmation listing other POs' schedules), and one PO is talked
  about in several conversations (its new-PO thread and a later pull-in).

`ThreadLinks` (ticket 32) attached a reply to a case only when its headers
named exactly one case. Once one mail opens a case per PO (ticket 19), every
reply in that mail's thread names several, and nothing would link.

The Teams drop exports each person's Inbox only (11-12), so Sales' own mail
is invisible; and a Power Automate rule tagging "existing PO thread / new
thread" was proposed.

## Decision

1. **A mail thread is derived, not a second lifecycle.** Code gives every
   stored message a thread key when it is stored, from `Message-ID`,
   `In-Reply-To` and `References` (an exported `conversationId` only where
   the headers say nothing), within one workspace and one customer: headers
   are the sender's to write, so a chain naming another customer's message
   joins nothing. A thread has no status; every state stays on the order or
   quote case (`OrderCase`, `QuoteCase`).
2. **Thread to case is many to many.** A case opens only when a document is
   read (a PO or a request), as before; messages before it stay on the
   thread and show on the case as the talk before the PO. A message in a
   thread with several open cases belongs to the ones whose numbers it names
   (read by a model, resolved by code against the sender's customer); naming
   none, Sales picks the case. Nothing is guessed.

   *Built 2026-11-14 (ticket 24), by the agent; what the ticket left open:*
   the key (`threads.thread_key`) is the earliest stored named message's,
   computed within the workspace only; the customer is applied where a
   thread is read (`ThreadLinks.cases`, the case's talk before it), since
   the store cannot know who a sender is and Bravo's contacts or the ledger
   may change that later. A message stored before what it answers keeps its
   own key, and a thread is read as the union of its own key and those of
   the stored messages its headers name; two replies sharing only an
   ancestor stored after both stay apart. The talk before a case shows only
   mails DW1 processed as that case's customer's. Several cases and the
   model off or unanswering (after the intent step's retry window): routed
   `reply_to_case` with the cases offered; Sales picks with
   `sales.inbox.process`, as "DW xử lý" asks, and only an offered case.

   *Built 2026-11-14 (ticket 19), by the agent:* one stored message may be
   on several order cases, one per PO number it carries; its disposition
   names the first and lists the rest (`sales.message_cases`), and the log's
   `cases_of` returns every one of them, so a reply in the thread of a
   three-PO mail is attached to the PO it names or offered the three. A
   mail's cases are written in the transaction that records it: processed
   again, it is refused whole.
3. **Sales' sent mail joins the thread.** Each person's flow also exports
   Sent Items to the same folder. A message is outgoing when its sender is
   the member's own address, resolved by the server, never by the folder the
   flow wrote. An outgoing message never opens a case and never changes a
   value; it is context (what Sales asked, when a confirmation left). Before
   building it, measure whether the export of a sent item keeps its thread
   headers (ticket 23). The "Gửi cho khách" button stays.
4. **Power Automate transports and decides nothing.** No flow tags a mail as
   an existing or new thread: that would be a second decider beside the
   thread key, written as subject keywords, blind to DW's cases (the host
   has no internet) and copied by hand per person. A flow may add facts
   Exchange holds (`conversationId`, inbound or sent) beside the `.eml`.
5. **Who the customer is, is Bravo's first.** A sender's address belongs to
   the customer whose contacts in Bravo (R01, master data until the API)
   list it; then to the customer Sales confirmed that exact address as (the
   sender ledger, `sender_customers.py`, AI list item 5, Đạt 10-29); the
   domain decides only where it is not shared (ticket 20). An address Bravo
   lists is never overridden by the ledger, and a ledger entry Bravo
   contradicts is shown to Sales, not used. A mail from an address neither
   lists is routed `customer_unknown` with the model's suggestion; Sales
   confirms the customer and the mail is processed again with it, opening
   its case then. A customer Bravo does not have yet is ticket 15's (DW
   drafts the request for a code; a person creates it).

   *Amended 2026-11-13, by the agent while Đạt was away:* the grilling's
   Q4/Q8 proposed a provisional case and a choice held per thread, and "no
   contact table of DW's own". The sender ledger already existed and does
   the same with less: a confirmed address, never a domain, audited, the
   mail re-processed. So it stays, below Bravo, and no provisional case or
   per-thread choice is built. Owed: Đạt's confirmation (`.claude/PLAN.md`).

   *Built 2026-11-14 (ticket 20), by the agent:* `customer_by_sender` reads
   in this order: the one customer whose contacts in the master data list
   the address; else the sender ledger, never against those contacts (an
   address several customers list is chosen by the ledger among them only);
   else the customer whose own domain it is, unless the tenant lists the
   domain in its order rules' `shared_mail_domains` (1.13.0, empty on the
   platform; Proterial's group list, Box B37, is theirs to enter). A shared
   domain with no matching address is routed `customer_unknown` as before;
   Sales' confirmation keeps that address, and the next mail from it is that
   customer's. The ledger refuses an address one customer's contacts list,
   or one whose unshared domain already answers. A ledger entry naming a
   customer no longer in the list decides nothing: the mail goes to a person.

## Considered options

- **A conversation entity with its own states** (open, negotiating,
  settled), cases as its children: rejected, a second lifecycle over
  `OrderCase`'s, and the two would drift.
- **Only the "Gửi cho khách" button for outgoing mail:** Sales answers from
  Outlook too, and its receipt carries no Message-ID.
- **Only the customer's next `References`:** says Sales replied, not what
  or when, so no clock can start from a confirmation.
