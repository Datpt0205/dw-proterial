# 02 — The Bravo paste sheet in Proterial's real "SalesOrder" layout

Status: ready-for-agent (columns from the 11-09 recording and the 11-10 screens); final headers on B41
Blocked by: none to start; B41 (the SalesOrder file) to finish
Category: enhancement

## Why

Sales enters an order by pasting rows from an Excel "SalesOrder" sheet into
Bravo's "Đơn đặt hàng bán" grid. DW1's upload file (`sales_bravo_upload`
1.0.0 and 1.1.0) is a mock layout. The contract accepts a file where the ERP
offers no connection, and the file has to paste without retyping.

## Shape

- New `UploadField`s: `other_info_1..4`, `unit`, `unit_length`, `moq`,
  `lead_time`, `first_confirmed_date`, `confirmed_date`, `sales_accounting`,
  `delivery_mode`, `delivery_term`, `destination`. Code decides each value.
- Delivery mode, term, destination, payment terms and PIC come from the
  customer's master data (constant per customer on every SO seen). A PO that
  prints another value raises a finding instead of overwriting.
- One row per delivery date (the recording; ticket 21's schedules).
- Proterial's layout ships as a tenant version, `sales_bravo_upload@2.0.0`,
  with `mock: false` once B41 confirms the headers and their order.
- Cell formats as Bravo reads them: price to 5 decimals, quantity to 3,
  dates as Bravo's clipboard expects (checked on the plant PC).

## Acceptance

1. Rows from a real PO paste into Bravo's grid on the plant PC with no
   column moved by hand (Sales confirms on UAT day 1).
2. A PO whose delivery term differs from the customer's raises a finding.
3. amount = quantity × price and box quantity = quantity ÷ quantity per box
   are checked before the file is made.
4. A layout missing a required field is refused (mutation: drop the check).

## Comments
