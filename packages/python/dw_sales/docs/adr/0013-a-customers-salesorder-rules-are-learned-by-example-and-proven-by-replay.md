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

## Applied to ticket 38 (2026-11-14, by the agent, Đạt away)

Built as decided; what the decision did not settle was settled so, and is
recorded here rather than in a new ADR, because no rule above moved.

- **One key for every customer.** The customers' rules are one tenant
  version, `sales_salesorder_rules`, a map by customer code: the platform's
  rule-version engine (approval, decision guard, settlement, stamps) holds
  it unchanged. A version sent from an example is the version in force with
  that customer's entry replaced. The engine's one-waiting-per-key rule
  therefore holds across customers: a second customer's example waits
  until the first one's version is decided.
- **Learned only.** The rules editor's door refuses the key
  (`rules.LEARNED_ONLY`, 422), and so does a draft in words; "Gửi duyệt"
  (`salesorder_learning.SalesOrderExamples.submit`) is the only way a
  version is proposed, and only for an example whose replay matched against
  the layout still in force. It is never applied directly, the head's
  included: the head approves, never the person who sent it. The key is
  price-bearing (`sales.price.read`): the files and the replay carry prices.
- **Sources are the normal reading's.** A column starts from a field the
  normal reading gives (the PO read with the customer's approved layout,
  `order_intake.CustomerPoReading`, the same code intake reads with) or a
  value of the customer's record. A PO column the reading does not keep
  (customer 1's PRS production number) is not a source yet: it would need a
  field of the PO layout, a later change.
- **Tables are the master data DW already owns.** `lookup` names the
  customer's own convert list (exact, never another customer's rows) or a
  column of the item master by PRV code. Colour letters reach the PRV code
  through the convert list, which Bravo writes the colour into; a separate
  colour-letter list is ticket 04's (its sheet is broken, `#REF!`).
- **A constant is held to the example**: it is a column's only step, the
  value every row of the PIC's file holds there, and not a value of the
  PO's own (its number, a code, a quantity, a price, a date), which would
  pass the first two on a one-PO file.
- **The comparison**: numbers by value, dates by day (a text written
  yyyy-mm-dd, yyyy/mm/dd or yyyy.mm.dd, with or without a time of day, is
  that day: customer 1 writes its date as text), text NFKC (the reader's own
  form) and trimmed; rows in order. The 02 file builder's own checks run on
  each row too.
- **What nothing fills is left for the person**, as in the file a case
  draws: a column neither the layout nor the rules fill is not compared,
  and is listed with how many rows the PIC filled (B41: PC's dates, the
  PIC's code). The model is asked about those columns with the differing
  ones; what it cannot explain stays visible to the head.
- **The day the PO came in** is given with the pair: the file's "Receipt
  date" is not in the PO.
- **The model is asked only when the layout alone does not reproduce the
  file**, is shown the layout's columns, the columns to explain and five
  rows of each side, and is outside the model-step gate, as
  `bravo_template_mapping` is: a one-call proposal a person asks for, which
  the replay proves before anyone may send it.
- **Kept**: an example never sent is dropped by the next request of its
  workspace after 30 days; a sent one stays, for its approval shows its
  replay.

## Amended 2026-11-16 (Đạt), under ADR 0014

One worked example under-specifies a customer: the first PO it did not show
is filled wrongly or not at all ("cứ chăm chăm vào ví dụ thì sau này gặp
trường hợp khác rất dễ sai"). The SalesOrder becomes a skill with tools
(ticket 41): the customer's way in words with several worked pairs, the
model filling each PO with read-only tools and naming each cell's source,
and code tracing every cell on every PO (its anchor, the lookup redone, the
computation redone, a constant the skill names); a cell it cannot trace is
flagged, never written. Decisions 3 to 6 hold: the replay now runs on all of
the customer's pairs, the head approves, and a person approves the file
before Bravo. The rules above stay as the fallback until the skill passes
its bar on Strata.
