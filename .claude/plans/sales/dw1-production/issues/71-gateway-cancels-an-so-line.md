# 71 — Gateway: cancel an SO line (`so.line.cancel`)

Status: in-progress — gateway done (2026-11-26); DW1's proposal (order page, chat) next
Blocked by: 70
Category: enhancement (tickets 53, 63)

## Why

The cancel was `pending` because no real cancel was traced. `02-trace-3.csv`
(11-25 17:31:50, test SO `SO2611-000002`) holds one, both lines in one save
(ticket 52, comment 2026-11-26).

## What

- Per line, one UPDATE with the client's columns: `IsCancel='Cancel'`,
  `CancelDate` (today), `CancelQuantity` (the old quantity), `CancelPrice`
  (the old unit price), `CancelAmount`, `CancelRemark` (the reason the person
  gives), `CancelPRS=DEFAULT`, and `Quantity`, `Quantity9`, `UnitCost`, the
  four amounts to 0, `OriginalUnitCost=DEFAULT`; `BoxQuantity`,
  `QuantityGroup`, `Divide` to 0 where the line carries them. The header's
  totals and `TotalQuantity` recomputed. The values come from the screen's
  rules the runner already runs, not typed into the statement builder.
- The contract kind leaves `pending`; the tenant switch stays off until a UAT
  proof (`uat_proof`).
- DW1's cancel button on the order page proposes the write; the PIC approves.

## Acceptance

- Replay of the 17:31:50 save: the gateway renders both UPDATEs and the
  header's with the client's values (assignments compared as a set).
- A cancel without a reason is refused; a line on a completed delivery
  (`ufn_Prevent_Edit`) is refused.

## Comments

**2026-11-26, the gateway part.** `so.line.cancel@1` is no longer pending
and carries the person's reason (added while still pending, so v1: no token,
switch or tenant version named a cancel without it). The gateway types what
the screen lets a person type, in its order: "Order status" `IsCancel =
'Cancel'` (which opens the quantity for typing and takes the cancelled price
from the unit price), the reason, then `Quantity9 = 0`; the layout computes
the rest. Two runner changes, each measured on the 17:31:50 save and each
mutation-tested (red when reverted):
- a rule setting several columns sets them all, then raises each change
  (the cancel's `OriginalUnitCost,UnitCost` reset);
- a NULL operand of a money rule counts as 0 (the client wrote `UnitCost` 0
  over a NULL `OriginalUnitCost`).
A NULL is written as `[Col]=DEFAULT`, as every NULL the client set in the
three traces is; read-back skips those columns (the column default decides).
A line of a split group (`Divide` set) is refused as unmeasured: the traced
cancel of such a line also cleared `Divide` by hand.

Replay (`test_a_traced_cancel_is_the_clients_own_statement`, trace 11-25 on):
the line outside the split group renders the client's UPDATE value for
value; the header's columns match (its totals differ: the client cancelled
two lines in one save). The header's process-group lookup is answered as
recorded in that test only; live it is ticket 50's.

Found, not caused here: `test_bravo_so_layout` and `test_bravo_rq_layout`
count the 11-20 trace's saves (6), so they fail on a later trace file; they
fail the same on the previous runner. Live, a quantity or cancel change
also calls `usp_B20BizProcessGroup` with the new total, which stays
undecided until procedures run against Bravo (ticket 50): the plan is
held back until then, as the quantity's is today.
