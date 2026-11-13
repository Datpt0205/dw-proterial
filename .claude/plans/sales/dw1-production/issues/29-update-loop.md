# 29 — The update loop: from a confirmed change to the customer's answer

Status: ready-for-agent
Blocked by: 27, 07
Category: enhancement

## Why

dw_sales ADR 0010 decision 3, BA step 6 (6-DW2, 6-PC, 6-DW3, 6-DW4,
"Khách quyết định?", 6.2-SP, 6.3).

## Shape

- Before Bravo: a confirmed change re-runs the checks; DW drafts the
  answer.
- In Bravo: dates/quantities draft the PC request; PC's answer drafts 6-DW4
  or 6-DW3; the customer's answer proposes keep / accept / ask PC again;
  the PIC approves the Bravo update; 6.3 drafts the PO and schedule back;
  the case returns to `confirmation_sent`.
- Each draft is sent by a person.

## Acceptance

1. A pull-in on an order in Bravo walks to `confirmation_sent` with every
   draft and approval recorded.
2. A customer keeping the original PO closes the change request and leaves
   the order as it was.
