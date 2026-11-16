---
name: salesorder
description: Filling the SalesOrder file Bravo imports from one customer's purchase order, a row per delivery, each cell from the PO, a look-up, a constant this skill names or a computation. The platform's generic way; a company writes one per customer (salesorder-<customer code>) with that customer's exceptions and worked pairs.
metadata:
    version: "1.0.0"
---

# Filling a customer's PO into Bravo's SalesOrder file

You fill the rows of the file Sales pastes into Bravo. Each row is one
delivery of one PO line, already numbered for you. For every column you
fill, say where the value came from; a cell you cannot explain stays empty
for the PIC.

## The usual way

Where the column's "layout" names a field, take that field's value from the
row: "field po_no" is the anchor R<row>.po_no, copied as it is. Where it
names a customer value ("customer delivery_term"), take it from the
customer call's result, key "delivery_term". A blank column stays empty
unless this skill says what goes there.

- The item's code in Bravo, where a column asks for it, is the convert
  call's "prv_code" for the row's customer_item_code. A code the convert
  list does not hold stays empty: never make one up.
- An item's specification, colour or standard length is the item call's
  result for that code.
- Prices are the PO's own unit price and amount, as printed, or converted
  by a unit factor where the customer writes quantities in another unit.
  Never another price.
- Dates are written yyyy-mm-dd. A date this customer moves (for example a
  delivery date some days before the date the customer asks) is a
  computation: shift_days from the requested_date anchor.
- A quantity the customer writes in km while the file holds metres is
  unit_factor from "km" to "m"; its price per km becomes a price per m with
  unit_factor from "m" to "km".

## Constants

None in the generic skill. A customer's own skill lists here, each between
backticks, every fixed text its rows carry (a group code, a staff code a
column always holds), with why.

## Worked pairs (fictional)

A PO of customer "ZZA" (row 1: R1.po_no "ZZA-0001", R1.customer_item_code
"Z-10", R1.quantity "2", R1.uom "KM", R1.unit_price "50", R1.requested_date
"2027-01-20"), whose convert call c2 found "PRV-Z10" and whose item call c3
found colour "blue". The PIC's file holds, for row 1:

- the PO number column: "ZZA-0001", source po R1.po_no;
- the colour column: "blue", source tool c3, key colour;
- the quantity column: "2000", computation from po R1.quantity with
  unit_factor km to m;
- the unit price column: "0.05", computation from po R1.unit_price with
  unit_factor m to km;
- the delivery date column: "2027-01-10", computation from po
  R1.requested_date with shift_days -10.

A PO of customer "ZZB" (row 2: R2.po_no "ZB77", R2.line_no "2",
R2.quantity "305", R2.unit_price "0.3"): the column the PIC writes as the PO
and line joined is "ZB77/2", computation from po R2.po_no with concat of
line_no, separator "/"; the amount column is "91.50", computation from po
R2.quantity, multiply by unit_price, round 2 places.
