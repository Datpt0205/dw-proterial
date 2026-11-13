---
status: Accepted
date: 2026-11-13
accepted: 2026-11-13 (Đạt: "học bằng ví dụ, chứng minh bằng chạy lại")
---

# A customer's SalesOrder rules are learned from one worked example and proven by replaying it

## Context

For each customer, the PIC turns the customer's PO into Bravo's SalesOrder
import file by hand, in a workbook of their own (Box B01, customer 1): the
PO as received, its lines normalised, a check sheet ("hk & cable": reel
length against the standard 305/610 m, price against the price list and
LME, spec; TRUE/FALSE per line), then the SalesOrder sheet Bravo imports.
Each customer differs: column names and languages, colour letters, reel
lengths, km or m, a delivery date shifted from the customer's ETA (customer
1: EXW = request − 10 days). Writing that per customer in code does not
scale and needs FPT on site whenever a customer changes; letting a model
copy every PO's values into the file cannot be checked.

## Decision

1. **Learn from one pair.** The input is one customer's original PO and the
   SalesOrder file the PIC made from it.
2. **The model proposes rules, as data.** A tenant rule version for that
   customer: which source column feeds each SalesOrder column, and the
   customer's own steps, each one from a closed set code knows how to apply
   (copy, a constant, a lookup in a named master-data table, a unit factor,
   a date shift by whole days, a rounding, a text cut). Never code, never a
   free formula, never a value of a particular PO.
3. **Proven by replay.** Code applies the proposed rules to that same
   original PO; every cell of the output must equal the PIC's file. Any
   difference lists its cells (expected, got, which rule) and the version
   cannot be sent for approval.
4. **A person approves**: the head, never the proposer, sees the replay.
   From then on code applies the rules to every PO of that customer; the
   model never copies a PO's values.
5. **Tables are master data, not rules.** A lookup the PIC keeps hidden in
   the workbook (colour letters, PRL → PRV → spec → standard length, a price
   table) is imported as the tenant's master data with its own approval,
   and a rule only names it. A price formula waits on dw_sales ADR 0008.
6. **Written to Bravo** through the write API after a person approves the
   exact file (ADR 0026, amended 11-13); until the API exists, the file is
   exported for a person to import.

A new PO the approved rules cannot reproduce on its own customer's next
worked example (a form changed) is noticed the same way: Sales hands DW the
new pair, and the replay says which rule broke.
