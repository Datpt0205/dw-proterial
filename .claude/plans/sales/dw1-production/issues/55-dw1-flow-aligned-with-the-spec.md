# 55 — DW1's flow aligned with the BA's spec and Đạt's 11-20 decisions

Status: needs-triage (slice after ticket 54 is answered)
Blocked by: 54 (for the points the BA must fix); 50 for reads from Bravo
Category: enhancement

## Why

DW1 was built on the 11-13 flow, with files and pasted sheets. The 20.11 spec
and the 11-20 decisions change the order of steps and several rules.

## Shape

- **Order and price.**
  - Convert the code before checking the price.
  - Look up the quotation and LME by the SO's DocDate.
  - The SO always carries the PO's values.
- **The only real mismatch** is between the customer's PO Excel and its PDF:
  items, quantities, prices or total. It is answered by a drafted mail asking
  the customer to correct.
- **Exceptions go to the case's own PIC in the case chat.** The PIC decides,
  and the case goes on from there (ticket 56). This covers:
  - a black-listed customer;
  - an ECP block;
  - a far delivery date on an order over 10,000 USD;
  - a cancel that touches materials;
  - a price change.
- **Design.** DW tells Sales, Sales mails Design, and Design fills in Bravo.
  DW sees the YCBG line turn `CLOSE` by itself; nobody has to tell it.
- **Numbers and limits.**
  - Numbers and targets ship as defaults the tenant configures.
  - Every loop gets a configured limit and an end state. That covers
    reminders, re-asking PC and reconciliation, and includes an expired
    quotation with no answer.

## Acceptance

- Each point has a test that fails before the change and passes after it.
- The process map (ticket 35) shows the new order.

## Comments
