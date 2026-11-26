# 82 — DW records the customer's acceptance or silence, with undo

Status: needs-info (Đạt amends dw_sales ADR 0011)
Blocked by: none
Category: enhancement (ADR 0015)

## Why

The PIC clicks to record an event DW already knows: the customer's reply read
as accepting (with the cited sentence), or the tenant's silence days passed.

## Proposal

- DW records "accepted" or "implied" itself, tells the PIC, and offers undo for
  the tenant's undo window. Internal and reversible: ADR 0015 T0/T1.
- A reply read with low confidence goes to the PIC as today.

## Acceptance

- The mock customer's accepting reply moves the case and notifies; undo
  restores the previous state with both events audited.
