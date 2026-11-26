# 71 — Gateway: cancel an SO line (`so.line.cancel`)

Status: ready-for-agent
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
