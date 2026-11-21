# 51 — DW creates the sales order itself, through Bravo's own Import engine

Status: ready-for-agent (path 2 by default, ADR 0027; creation's columns wait on script 03c)
Blocked by: 63 (the gateway), 59 (creation needs the shared template, script 03c); 60 only adds a path
Category: enhancement

## Why

Đạt, 11-20: DW must perform the Import, not stop at proposing a file for the
PIC to press. Import runs Bravo's whole form engine: the SO screen's 404 field
rules and 27 validators. It numbers the SO, fires the triggers and logs the
author. Whatever path DW takes must keep that engine, or reproduce it exactly
(ticket 59).

## Shape

- **Paths** (ADR 0027, 2026-11-21):
  1. **The default, built now:** the gateway's `so.create`. DW's rule runner
     (ticket 59) computes the exact INSERT from the live layout and the shared
     template, under the PIC's user, with the checks in ticket 63.
  2. **When the vendor offers it (ticket 60):** the vendor's automatic Import
     or procedure, as a second creation path inside the gateway. Contexts do
     not change.
  3. **Last resort only:** UI automation of the Import button. It would need
     the PIC's Bravo password to author as the PIC.
- **The file** is still produced for each path, and for the manual fallback.
  - At export, DW reads the template in use from `B00ImportSetting` (template
    72 today) and writes exactly its columns.
  - A column the template lacks is not sent; the unit comes from the item.
  - Column U is the customer's description, from which Bravo converts the code
    itself.
- **Rules (Đạt, 11-20).**
  - The SO carries the PO's values.
  - One PO may become several SOs, tracked line by line.
  - An existing SO is never imported again; it is edited in place (ticket 53).
  - A PO No. + customer pair already on an SO is a warning to the PIC, not a
    block.
- **Lines** are imported whole. Splits come afterwards with Bravo's group fields.
- **Read-back.** After the import, DW reads the SO back and reconciles every
  line: code, quantity, price and dates, including that "XN giao hàng" was not
  cleared for being earlier than DocDate. It reports any difference to the PIC.

## Acceptance

1. A DWTEST PO goes from the PIC's approval to an SO in Bravo UAT with no one
   pressing Import, and reconciles field by field.
2. A changed template stops the export (ticket 50's drift check).

## Comments
