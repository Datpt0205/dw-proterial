# 21 — A customer absent from the conversion list

Status: done (2026-11-14)
Blocked by: none (customer 4's codes: owed by Proterial)
Category: enhancement

## Why

The list is already keyed by (customer, customer code) (`convert_entry`).
Customer 4 has no rows at all; one description maps to different PRV codes
at different customers, so another customer's row is never a match.

## Shape

- A customer with no rows: every line is "chưa có mã" with the nearest PRV
  candidates by description, never another customer's mapping as a match.
- The PIC's confirmed code is remembered for that customer only (as today).

## Acceptance

1. A line of customer 4 never takes customer 1's mapping for the same
   description.
2. The PIC confirms a code once; the next PO of customer 4 maps it.

## Done

Verified 2026-11-14, by the agent: both acceptance criteria already held in
code, and no production code changed for this ticket.

- `_convert_entry` (`order_intake.py`) looks a line up under its own
  customer only, by code, else by its converting description; a customer
  with no rows gets None, and `map_line` then offers the item master's
  candidates by the description's attributes (`candidate`/`ambiguous`/
  `unmapped`, "chưa có mã"), never `exact` and never another customer's
  convert row. No existing mechanism shows another customer's mapping as a
  candidate, so none is shown.
- `OrderCommands.confirm_mapping` keeps the PIC's code for that customer and
  that customer's code (`learn_convert`), and the next PO maps it `exact`.
- Kept as guards: `test_bravo_master_lists.py::
  test_a_customer_with_no_rows_gets_candidates_and_keeps_what_the_pic_confirms`
  (customer 1's code and words, printed by a customer with no rows; the
  confirmation; every other customer unchanged), beside
  `test_one_customers_words_never_take_another_customers_mapping` and
  `test_convert_learning.py`.
- Owed by Proterial: customer 4's codes, for real data.

