# 02 — The Bravo paste sheet in Proterial's real "SalesOrder" layout

Status: ready-for-agent (2026-11-14: the 2.0.0 layout, its column sources and the checks
built, see "## Done"; acceptance 2, a PO's delivery term against the customer's, remains)
Blocked by: none (B41 received 11-13 and measured below)
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
- **A column change is data, never code** (Đạt, 11-13: "tôi không thể cứ ở
  đây để maintain nếu họ đổi form"). Besides a field code computes, a
  column's source may be a fixed value, a field of the customer's record,
  or left blank for the person: all set in the tenant's version through
  "Tạo từ tệp mẫu" (the model maps headers, code verifies, the head
  approves). Only a column computed from the PO by a new rule needs code.
- B02 (Bravo's "Customer order information (Form 1)" export, 81 columns) is
  the view, not the paste grid; the paste sheet's columns are the ones Sales
  types (11-09 recording), B41 confirms them.
- **Per customer, learned by example** (Đạt 11-13, dw_sales ADR 0013,
  ticket 38): the steps between the customer's PO and this file (columns,
  colour letters, reel lengths, km/m, the date shift) are a customer's rule
  version proposed by the model from one worked pair and proven by replay;
  this ticket ships the common SalesOrder layout they write into.

## B41, measured 2026-11-13 (shapes only; the files stay outside git)

Box B41 holds the empty template (`IMPORT PO-TEMP/SalesOrder.xlsx`) and three
customers' filled files. Sheet1: row 1 title "File import Sales order"
(merged A1:AM1), row 2 group labels "ĐẦU PHIẾU" (A2:R2) and "CHI TIẾT"
(S2:AM2), **headers on row 3**, one row per (customer PO, PO line) from
row 4; Sales copies the rows and pastes them into Bravo's "Cập nhật đơn đặt
hàng bán". Sheet2 is Bravo's customer list (481 rows: code, name, direct or
indirect, currency, payment term, …), usable for ticket 36.

The 39 columns, A–AM, and what the three filled files put in them:

| Col | Header | Filled from |
| --- | --- | --- |
| A | Stt | row number |
| B, C | Ngày, Số | blank (Bravo's voucher) |
| D, E | Tiền tệ, Tỷ giá (Nếu USD thì là 1) | the PO's currency; 1 for USD |
| F | Type (Mass/Returned/Sample/SampleFee) | per customer, "Mass" in all three |
| G | Mã KH trực tiếp | the customer's Bravo code |
| H, I | Người đại diện, Mã khách hàng gián tiếp | blank |
| J | người lập | the PIC's Bravo staff code |
| K | LME center | one customer only (its PO prints LME) |
| L, S, U | Số PO của KH, PO line, Mã của KH | the PO |
| M | Receipt date | the day the PO was received |
| N, O, P, R | Delivery term, Delivery mode, Destination, Shipment type | per customer constant (one customer: destination per line, from the PO) |
| Q | End user | blank |
| **T** | **Mã hàng** (PRV code) | **blank in all three**: Bravo appears to convert the customer code itself on import |
| V–Y | Other infomation 1–4 | per customer: a copy of the customer code, another code of the PO, or a constant |
| Z, AB–AD | đvt, Unit length, MOQ, lead time | blank |
| AA, AE | Số lượng, Đơn giá nguyên tệ | the PO |
| AF | Ngày KH yêu cầu | the PO (one customer writes it as text yyyy/mm/dd) |
| AG, AH, AI | Ngày XN giao hàng lần đầu, Ngày XN giao hàng, Sales accounting | two customers fill them (PC's dates) |
| AJ–AL | Delivery mode, term, destination (line level) | blank |
| AM | Invoice Seperation | one customer, a constant |

So: the platform version is this 39-column layout with each column's
source among field / customer record / constant / blank / the PIC's
profile; what differs per customer (constants, Other infomation, the date
written as text) is ticket 38's, learned from these three files.

Owed by Proterial (short): does Bravo's import convert "Mã của KH" to the
PRV code itself (column T left blank), and is "người lập" each PIC's Bravo
staff code (DW then keeps it on the member, set by the admin).

## Acceptance

1. Rows from a real PO paste into Bravo's grid on the plant PC with no
   column moved by hand (Sales confirms on UAT day 1).
2. A PO whose delivery term differs from the customer's raises a finding.
3. amount = quantity × price and box quantity = quantity ÷ quantity per box
   are checked before the file is made.
4. A layout missing a required field is refused (mutation: drop the check).

## Comments

- 2026-11-10 (Bravo screens): the target grid's order is now known ("Edit
  detailSO all"): PO line, PO number, item code, description, base price
  name, specification, design number, other information 1–4 (customer line
  ref, second ref, empty, end customer), invoice separation (the item's
  product group, `CA`), quantity, unit, price, amount, currency, USD rate,
  price USD, total USD, delivery date, sales counting date. B41 still fixes
  which of these the paste sheet carries.

## Done

2026-11-14, against B41's measured template:

- `configs/policies/sales_bravo_upload@2.0.0.yaml`, `mock: false`, the
  platform default (`policy_files.py`; 1.0.0 and 1.1.0 stay loadable):
  sheet "Sheet1", the title and group rows (A1:AM1, A2:R2, S2:AM2) as
  `banner`, the 39 headers of row 3 spelled as the template spells them,
  data from row 4, a row per delivery (a split line is a row per date, each
  its own "Stt", the line's "PO line", its quantity and its date).
- Each column reads one source, a closed set validated by
  `BravoUploadLayout` (an unknown one refuses the version): `field` (code;
  new `row_no`, `received_date`, `usd_rate` = 1 for USD else blank),
  `customer` (`order_type`, `delivery_term`, `delivery_mode`,
  `destination`, `shipment_type`: new optional fields of the customer
  record, imported under Bravo's own headers as aliases), `constant`, or
  none (blank). "Mã hàng" is blank in 2.0.0; a tenant sets `field:
  prv_code` on it. "người lập" is blank: DW1 has no per-member attribute
  yet, so no `member` source was added.
- Formats from the template: quantity `#,##0`, price `#,##0.00000`, dates
  `dd/mm/yyyy` written as dates.
- Checked before the file is made: an amount column holds quantity × price
  (at the amount's places), and no number has more places than its
  column's format shows (a paste copies the shown text). A blank column is
  written empty by construction.
- An upload names the PO, the line, the quantity and the item by either
  code (PRV or the customer's): acceptance 4 now reads "the item" so.
- "Tạo từ tệp mẫu" (prompt `bravo_template_mapping@2.0.0`): the model
  answers per column letter (a duplicate header is two columns), with a
  field, a customer value or a fixed text, which code accepts only when
  every filled row of that column holds it; every template column is
  drafted at its place, the rows above row 3 as the banner. Eval dataset
  gained a synthetic B41-shaped template.

Remains: acceptance 2 needs the PO's delivery term read from the PO (not
read today) to compare with the customer's; box quantity has no column in
B41's layout, so acceptance 3's second check has nothing to check yet.
