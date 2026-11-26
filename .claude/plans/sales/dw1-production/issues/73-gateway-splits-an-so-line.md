# 73 — Gateway: split an SO line (`so.line.split`)

Status: ready-for-agent (code); ready-for-human (the UAT proof)
Blocked by: 70
Category: enhancement (tickets 53, 63)

## Why

`02-trace-3.csv` 11-25 17:28:58 shows a split's statements, inside a mixed
save (an empty line deleted, a quantity set on an unsaved line, then 135 + 115)
on a roller item, unit Pc.

## What

- Original line UPDATE: `Quantity`, `Quantity9`, amounts, `BoxQuantity`
  (= `Quantity9 / (QuantityBox * Length)`, 8212's `Eval_BoxQuantity_SetValue`),
  `QuantityBox`, `QuantityGroup` = the total, `GroupDivi`, `Divide` = 1.
- New line INSERT: copied columns plus `OriginalQuantity`, `GroupDivi`,
  `POLine` 0; header totals, `TotalQuantity`, `LMEFixed`.
- Switch stays off until the UAT session (ticket 52) traces a clean split of a
  saved quantity on a cable item (SO2609-000335 was proposed).

## Acceptance

- The 17:28:58 split part replays; the clean UAT split replays column for
  column before the switch's `uat_proof` is written.
