# 37 — A customer's notation learned from Sales' confirmations; evals tell wrong from deferred

Status: ready-for-agent
Blocked by: none
Category: enhancement

## Why

The hardcode audit's batch C (11-13) made one owner for numbers, dates and
currency (`dw_platform.domain.notation`): `1.250`, `05/12/2026` or a bare
`$` that the document itself does not settle goes to a person instead of
being read one way. Nothing is read wrong any more, but the replay goldens
fell (RFQ 0.946 → 0.828, hand-off 0.945 → 0.849), under the live bar
(0.85), so neither step can be turned on for a tenant.

A customer writes its numbers and dates one way. Who knows it is Sales, the
first time they confirm such a value.

## Shape

- When Sales confirms or corrects a value DW left as ambiguous, code records
  which notation that settles for that customer (thousands separator, date
  order, the currency a bare symbol stands for), with who and on which case:
  one record per customer and kind, shown on the customer's master data
  screen, changeable by a person. No setting to fill in by hand first.
- A later document of that customer is settled by it when the document
  itself says nothing; a document that contradicts it goes to a person.
- The goldens' graders report two numbers: **wrong** (a value read other
  than the mail states; the bar holds it near zero) and **deferred** (left
  to a person; reported, with its own floor). The live bar reads right =
  1 − wrong − deferred as today until Đạt sets the split.

## Acceptance

1. A customer whose first PO's `1.200 m` Sales confirms as 1200 m has its
   next PO's `1.500 m` read as 1500 m, flagged as settled by that record.
2. Another customer's record never settles this customer's document.
3. The goldens report wrong and deferred separately.
