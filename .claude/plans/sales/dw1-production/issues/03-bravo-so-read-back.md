# 03 — After the paste, DW reads the SO back and compares it with the PO

Status: needs-info
Blocked by: Bravo's read API (sales orders by customer PO); B42 ("in put PO")
Category: enhancement

## Why

Sales checks each entry with the "in put PO" workbook: the portal's
download beside the order as Bravo holds it, with a TRUE/FALSE column. DW1
today takes the PIC's statement (`bravo_entry_compared`) and an SO number
typed by hand.

## Shape

- A `BravoSalesOrders` port: `by_customer_po(customer, po_no)` returns the
  SO number, header, lines (code, quantity, unit price, requested, first
  confirmed and confirmed dates), status and closed flag. Adapter: the
  vendor's API (`docs/adr/0026`). Until it exists, an Excel export of the
  "Đơn đặt hàng bán" grid, uploaded by Sales, through the same port.
- Compare line by line with the case as approved; each difference is a
  finding on the case. When all are equal, `bravo_so_no` is filled from
  Bravo; the PIC still records the entry (human-in-command), with the
  comparison attached.
- Once the API carries "Chi tiết thực hiện", the same read answers the
  assistant's "đã giao chưa".

## Acceptance

1. A pasted SO with one wrong price shows one finding on that line.
2. Another customer's SO with the same PO number is never matched.
3. With the API down, the case says so and the manual path stays; nothing
   passes.

## Comments

- 2026-11-10 (Bravo screens): the grid to compare is "Edit detailSO all".
  Its checks are computable: amount = quantity × price, rounded half up to
  2 decimals; price in USD = price ÷ rate for VND. Delivered quantities are
  in the item's "Đơn hàng bán" tab (quantity done) and in "Chi tiết thực
  hiện".
