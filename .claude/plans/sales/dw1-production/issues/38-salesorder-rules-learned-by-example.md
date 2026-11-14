# 38 — A customer's SalesOrder rules learned from a worked example, proven by replay

Status: done (2026-11-14) for the mechanism on synthetic pairs (acceptance 1-4); the real proof waits on one real pair per customer, see "Remains".

## Done

2026-11-14, dw_sales ADR 0013 and its "Applied to ticket 38" section (the
decisions the ADR left open).

- **Findings** `reel_length_mismatch` and `spec_mismatch` (order rules
  1.11.0, migration `bc50e4985878`): what a line's description states
  ("610X12" now reads as a reel length; "SPEC <no>") against the item's
  standard length and spec numbers (DW1's attribute or Bravo's
  specification column); each runs only where both sides are known and the
  coverage says so. Labels in CONTEXT.md and the web.
- **Rules** (`application/salesorder_rules.py`): key
  `sales_salesorder_rules` (platform 1.0.0 holds no customer;
  price-bearing), per customer per column a source (a normal-reading field
  or a customer value) and steps from the closed set (copy, constant,
  lookup in the customer's convert list or the item master, unit_factor,
  shift_days, round, cut, concat, multiply); anything else refused by the
  schema. `filled_row` is the one place a paste-sheet row is composed:
  `order_artifacts.bravo_upload` applies the customer's approved rules with
  no model (`line_values`/`delivery_rows`/`file_rows` shared with the
  replay).
- **Learning** (`application/salesorder_learning.py`, migration
  `d94bf01066d2`, `adapters/persistence/salesorder_examples.py`): the pair
  and the day the PO came in uploaded on the customer's row of the master
  data ("Học từ ví dụ"), read by the worker (the PO through
  `order_intake.CustomerPoReading`, the PIC's file in the reader sandbox,
  checked to be the tenant's layout), the model asked only when the layout
  alone does not reproduce the file (prompt `salesorder_rules_proposal@1.0.0`),
  its answer verified (constant: alone, on every row, not a PO value) and
  replayed cell by cell. "Gửi duyệt" only for a matching replay against the
  layout in force, refused in the service and the route (409
  `replay_differs`); the editor's and the words' doors refuse the key (422);
  never applied directly; the head approves on `/approvals`, which shows
  the replay (`/salesorder-examples/by-version/{id}`).
- **Eval** `sales_salesorder_rules@1.0.0` (golden three shapes like B41's,
  injection, wrong step and an unmatchable pair, missing evidence,
  cross-tenant, degrade): 6/6 on scripted answers; joins the live lane.
- Twelve guards each turned a test red when removed (reel and spec checks,
  the submit gate, never applied directly, constant from the PO, the
  editor's door, own convert rows, the upload applying rules, header check,
  dates by day, the closed step set, the approval's replay).

Checked against B41's three files and the "hk & cable" sheet (shapes only):
copies, fixed texts, the date as text, the -10 day shift, the joined
description, the rounded amount and the convert/item look-ups are
expressible. Not yet: a PO column the normal reading does not keep (PCS's
PRS number) as a source; a row number counted per PO (PCS's Stt); the EXW
date the PIC types and the ETD/ETA chained from it (a person's decision);
PC's dates (AG-AI) are left for the person and shown so. A per-PO value the
reading does not keep (PCS's LME center) would pass as a constant on a
one-PO example: the head sees it in the rules.

Fixed with it: the upload file wrote the header's PO number on a line that
prints its own (ticket 18's portal export); `line_values` now takes the
line's.

Remains: the real proof on one real pair per customer (B41's three files
with their POs); writing to Bravo through the API (ADR 0026).
