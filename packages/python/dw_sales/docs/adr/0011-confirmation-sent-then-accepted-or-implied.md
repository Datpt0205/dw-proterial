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
