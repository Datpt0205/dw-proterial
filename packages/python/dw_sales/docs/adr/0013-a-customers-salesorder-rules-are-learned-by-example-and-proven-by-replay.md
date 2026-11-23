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

## Applied 2026-11-16: the skill with tools (ticket 41, by the agent, Đạt away)

The amendment above, built; what it did not settle was settled so, and is
recorded here because no rule above moved.

- **The skill**: one per customer, `salesorder-<customer code>`, a tenant
  rule version under `sales_skill_salesorder_<code>` in the skills' own
  store and flow (ADR 0014, ticket 40: proposed by whoever proposes rules,
  decided by the head on a `sales.skills` approval, never the proposer). The
  platform ships one generic skill (`configs/skills/dw1-salesorder`, fictional
  pairs only), which fills a customer with no version of its own; the skill
  book answers every customer's key with it but never lists one, so a thread
  turn's skill pick is offered DW1's skills alone. Migration `711e8b760139`
  admits the key family by pattern in `ck_rule_versions_key`.
- **A constant the skill names** is a text between backticks in its
  `## Constants` section, or the fixed text the layout holds in that
  column; nothing elsewhere in the skill counts, so a worked pair's values or
  a field's name never pass as one.
- **The tools are called by code, before the one turn**: the customer's
  record, its own convert list for every code the PO prints, the item each
  found code reaches (`salesorder_fill.prepared_calls`), each shown with an
  id the model names. The PO decides which look-ups exist, so nothing is
  withheld, and a turn that chose its own calls looped on Strata (ticket 40,
  0.183). The calendar and the unit factors are ADR 0013's closed set, which
  code redoes; the PO as read is the rows with an anchor per value,
  `R<row>.<field>`. A tool is bound to one customer when it is built
  (`SalesOrderTools.bound`): another customer's convert rows, and items only
  another customer's list reaches, are not in it.
- **The trace** (`salesorder_fill.trace`) writes code's value, never the
  model's text: the anchor must be the row's own, a call one made for the
  row's item and give the value again, a computation give it again, a
  constant be the skill's. A price column (the layout's `unit_price` or
  `amount`) takes only a source that reads the PO's price (ADR 0008). A
  column the layout fills that the answer leaves empty is flagged too
  (`not_filled`); PC's dates are left for the person as in every file.
- **Worked pairs** are ticket 38's examples: every uploaded pair whose PO the
  normal reading read and whose PIC's file is the layout is kept
  (`sales.salesorder_pairs`, workspace-narrowed, append-only), written in the
  transaction that settles the example. Not a labelled case of ticket 43: a
  labelled case is one item by reference, a pair is a whole file. Correcting
  a drawn file and uploading it is the same door.
- **A skill change** is replayed by the worker's lane
  `sales_salesorder_skill_replay` on the customer's newest 20 pairs, with it
  and with the skill in force, stored beside the version (`sales.skill_replays`,
  source `customer_pairs`). The head's approval is refused unless every
  pair came out as the PIC's file, every fill answered, and at least one pair
  proved it (`skills.PAIRS_BROKEN`); rejecting stays open. "Cannot be sent
  for approval" is built as "cannot be approved": proposing opens the
  approval at once in the skills' flow, and the refusal is where the head
  decides.
- **The gate**: `ModelStep.SALESORDER_SKILL`, switch
  `model_assist.salesorder_skill` (off in every platform version), tier T2
  (the file is still approved by a person, ADR 0026), bar 0.95 on the golden
  pairs' cell accuracy, held with no injected or other customer's value ever
  written. Asked when a case's `bravo_upload` file is drawn
  (`salesorder_case_fill.CaseSalesOrderFill`, through the one-call door, the
  caller's plan checked, before the draw's transaction): off, below the bar,
  no usable answer or the plan's day spent, the rules above fill it. A cell
  the trace refused is blank in the file and listed on its second sheet.
- **Measured on Strata, 2026-11-16 (Giang's home lab, not attested)**:
  1.0 cell accuracy on the three golden pairs (114 cells, every one traced,
  three calls, p50 11.5 s), with each customer's skill words as a PIC would
  write them; on a line shape no pair showed, 7 of 8 cells right and the
  eighth flagged, the unmapped code's item never written; no injected price
  and no other customer's code written. Three pairs whose skills were
  written knowing the pairs are a small set: the step stays off until a
  tenant's attested measurement on the plant's model, and its own customers'
  pairs, say otherwise.
- **Built 2026-11-17**: the skills page lists each customer's SalesOrder
  skill of the workspace, in force, and its versions with their pair replay,
  and proposes one through the same door. A wrong pair is withdrawn by a
  person who proposes rules and reads prices (a DELETE, audited in their
  name with ids and counts, migration `985e4fa0cd4f`); pairs older than the
  tenant's `learning.salesorder_pairs_kept_days` (365 by default, 30 to 1095) are dropped hourly by the `sales_salesorder_pairs_retention` lane in
  each workspace's scope. A replay stored before a pair left keeps the
  counts it was stored with.
- **Not built yet**: a PO column the reading does not keep is still no
  source.
