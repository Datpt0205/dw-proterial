# 51 — DW creates the sales order itself, through Bravo's own Import engine

Status: needs-info (the path depends on ticket 60's answer; 52 measures Import)
Blocked by: 50 (read-back), 52 (does Import keep DW's price, does it run the validators), 60 (vendor's path) or 59 (rule runner)
Category: enhancement

## Why

Đạt, 11-20: DW must perform the Import, not stop at proposing a file for the
PIC to press. Import runs Bravo's whole form engine: the SO screen's 404 field
rules and 27 validators. It numbers the SO, fires the triggers and logs the
author. Whatever path DW takes must keep that engine, or reproduce it exactly
(ticket 59).

## Shape

- **Paths**, picked by ticket 60:
  1. a vendor procedure, or Bravo's own scheduled Import;
  2. UI automation of the client's Import button. The authorship question is
     open there: the robot account versus the PIC;
  3. DW's rule runner (ticket 59) writing through the staged job.
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
