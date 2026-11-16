# 04 — The conversion workbook's rules and colour codes as master data

Status: ready-for-agent (2026-11-16: B43 received 11-14 with sheets `PRL PO`, `PRV vs PRL`, `Price 1/2` and the colour table in `Sheet1`; its VLOOKUPs are broken `#REF!` on 259/260 rows, so read the table, not the lookups)
Blocked by: none (Proterial: confirm the colour table is current)
Category: enhancement

## Why

Customer codes become PRV codes through a large formula workbook, and a
colour code is part of the PRV code. DW1 converts through the convert list
and what Sales confirmed (item 3), not through these rules.

## Shape

- Read the workbook first, then decide per rule whether it is data (a
  mapping row, imported through master data) or a rule (a pattern code
  applies).
- Colour codes become a master-data table. Code composes the PRV code from
  its parts; the model never does.
- Every converted line keeps which row or rule converted it (check basis).

## Acceptance

1. Every PO line in B43's sample converts to the code the workbook gives.
2. A colour not in the table leaves the line unmapped, with a finding.

## Comments

- 2026-11-10 (Bravo screens): the convert list is Bravo's own, "Converting
  customer to PRV item", with an approval ("Duyệt Convert Master List") and
  the colour written into the converting description. So this ticket reads
  Bravo's approved rows through the Bravo port (ticket 14); it does not
  rebuild the workbook's formulas. A mapping Sales confirms in DW1 (item 3)
  stays usable until Bravo has the row. DW1 lists the confirmed mappings
  Bravo does not have yet, for Sales to enter and approve there. Bravo's row
  then answers first, so the facts do not end up kept in two places.
- 2026-11-10: states 1 and 2 of Bravo's convert list were empty that day,
  but they are steps (Đạt: an empty screen is no data, not no step). A
  mapping Sales confirms in DW1 is followed through Bravo's states 1 → 2 → 3.
  Only state 3 (approved) answers a PO line; 1 and 2 show as "waiting for
  approval in Bravo".

## Done in part (2026-11-16): Bravo's approval states

- **Only a row Bravo approved answers a PO line.** The reader sandbox keeps
  each group label it leaves out (`ImportedTable.groups`); a convert row
  takes the state of the group above it (`ConvertEntry.bravo_state`):
  approved under Bravo's "3. Đã duyệt", waiting under any other label (states
  1 and 2, whatever Bravo calls them). `SnapshotSalesCatalog.convert_entry`
  answers an approved row only, so a waiting one leaves the line unmapped as
  a row missing does. DW1's own template (no groups) reads as approved, as
  before. Tested at the lookup, both guards mutation-checked.
- **A reader image older than this is refused**, not read as a sheet with
  no groups (which would approve every row): the table reply must state its
  groups (`reader_wire.TableRowsReply`), else `reader_version_mismatch`.
- Measured outside git: B04, 1 group, **11,423 rows approved** (only state
  3 held rows that day, as the 11-10 screens showed).

Left: the colour codes (S001…) as a list and the rule that puts a colour
into a PRV code wait on Q-B12; listing the mappings Sales confirmed in DW1
that Bravo does not hold yet, and the waiting rows, on the master-data page.
