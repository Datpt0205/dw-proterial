# 51 — Sales order created by Bravo's own Import, from a file DW writes

Status: needs-info (ticket 52's measurements first)
Blocked by: 50 (read-back), 52 (does Import keep DW's price, does it run the validators)
Category: enhancement

## Why

Import runs Bravo's whole form engine: the SO screen's 404 field rules and 27
validators. It numbers the SO, fires the triggers and logs the PIC as author.
Writing the SO through the database instead would mean rebuilding all of that.

## Shape

- **Export.**
  - DW reads the template in use from `B00ImportSetting` at export time
    (template 72 today) and writes exactly its columns.
  - A column the template lacks is not sent; the unit comes from the item.
  - The spec's 7.2 mapping is corrected to match the template: U is
    CustomerDescription, there is no Other information 2–3, and there are no
    line-level delivery fields.
- **Rules (Đạt, 11-20).**
  - The SO carries the PO's values.
  - One PO may become several SOs, tracked line by line.
  - An existing SO is never imported again; it is edited in place (ticket 53).
  - A PO No. + customer pair already on an SO is a warning to the PIC, not a
    block.
- **Lines.** Lines are imported whole. A split is done afterwards with Bravo's
  group fields (ticket 53), never as loose import lines.
- **Read-back.** After the PIC imports, DW reads the SO back and reconciles
  every line: code, quantity, price and dates. This includes checking that
  "XN giao hàng" was not cleared for being earlier than DocDate.

## Acceptance

1. A DWTEST PO imported on UAT reconciles field by field with the file.
2. A changed template stops the export (ticket 50's drift check).

## Comments
