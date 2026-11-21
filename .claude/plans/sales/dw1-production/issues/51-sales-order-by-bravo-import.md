# 51 — DW creates the sales order itself, through Bravo's own Import engine

Status: in-progress — the read-back through the gateway and the Import template's watch built offline (2026-11-21). pending: creation (`so.create`, script 03c: the shared template's columns), the file written from the live template's columns (needs which template is in use as tenant config, and a page), the UAT acceptance
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

## Done (2026-11-21, offline)

- **Read-back through the gateway** (`ReadBackService.read_from_bravo`,
  `POST /sales/orders/{case}/bravo-read-back`, `sales.order.prepare`): the
  case's PO read from Bravo (`so.by_customer_po`: `B30BizDoc` with
  `DocCode = 'SO'`, `CustomerCode`, `POCustomer`; lines with `POLine`,
  `ItemCode`, `Quantity9`, `OriginalUnitCost`, `PORequestDate`,
  `EstimatedTimeDelivery`, each named by template 72 or the schema) and
  compared line by line with the paste sheet as approved: code, quantity,
  price, the requested date and now **"XN giao hàng"**: a confirmed date the
  row carried that Bravo does not hold (cleared for being earlier than
  DocDate) is a difference. The Form 1 export carries no confirmed date, so
  that path compares none. Kept as the case's read-back with its audit row in
  one transaction (shared with the export's path); the stored digest is the
  gateway's answer's. Refused, storing nothing: no gateway, no SO for the
  PO, the PO under several SOs, Bravo not answering, a case not at its Bravo
  entry, no prepare right.
- **The Import template watched** (`dw_bravo.import_template`, the gateway's
  fingerprint): the screen's templates in `B00ImportSetting` (stored zipped
  like a layout: 682 bytes for a 1,219-character XML on UAT) are one
  `template` component per screen; a template changed, added or switched
  pauses the kinds that create on the screen (ticket 65's table), and a
  template the reader cannot read is named. The reader refuses a whole
  template with any part it does not know.
- **Not built, and why:** the file written from the live template's
  columns. Which of the five active SO templates is "in use" is the person's
  pick in Bravo's dialog, not a fact in the database (template 72 by the
  11-20 survey); it needs to be tenant configuration, and the check (DW's
  paste-sheet columns against the columns the template reads) a consumer
  (the export, or a page). Until then the paste sheet stays the tenant's
  layout (ticket 02), and a changed template is seen by the watch.
- Tests: domain and service 7, gateway route 1 + client 1, SQL Server 2
  (a PO's lines, the PO document excluded; a template changed and an
  unreadable one named), template reader 8; 9 mutations red.

## Comments
