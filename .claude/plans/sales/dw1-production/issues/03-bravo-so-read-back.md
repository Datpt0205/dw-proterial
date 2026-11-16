# 03 — After the paste, DW reads the SO back and compares it with the PO

Status: ready-for-agent (2026-11-16: the Excel path; B02 is Bravo's own "Customer order information (Form 1)" export, 81 columns, and the import skips refused rows, so this read-back is required)
Blocked by: none for the Excel path; the vendor API (R-list) replaces the upload later; B42 not received (B43's `hk & cable` sheet is Sales' own comparison)
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

**Measured 2026-11-16 (Đạt's screenshots of Bravo 8):** Sales imports the
PIC's SalesOrder file through "Đơn đặt hàng bán › Dữ liệu › Import"
(layout "Layout1", from row 4), and the dialog stands with **"Bỏ qua các
lỗi…" and "Không ghi nhật ký…" ticked**: a row Bravo refuses is skipped and
nothing records it. So an import that "finished" proves nothing, and this
read-back is what catches a lost line; it belongs before DW prepares any
file for import, not after. The exports share one shape (row 1 the screen's
title, row 2 the header; "Customer order information", "Cancelled order
information", "Báo giá, chào hàng", "Danh mục Base price", "Black list"),
described outside git in `Downloads\proterial\Bravo-export\_ANH.md`.
Still owed: the import's "2. Thiết lập import" (Layout1's column mapping)
and its result screen.

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

## In progress (2026-11-16)

- Built and committed: the row-by-row comparison
  (`domain/bravo_sales_orders.compare`, `ed7f8ec6`): per PO line a row per
  delivery in the paste sheet's order (`order_artifacts.upload_rows`, the one
  source of what is entered), item code, quantity, unit price as printed and
  the requested date; `missing_row` is a row Bravo's import skipped,
  `extra_row` one it holds beyond; a cancelled line expects none.
  Acceptance 1 holds at this level (one wrong price, one difference on that
  line).
- **Q-B6 answered by B02, partly:** one PO is not always one SO. B02 holds
  3 POs under one SO, 2 under two and 1 under four (revisions keyed again),
  and a PO line under 2-4 rows. So a PO Bravo holds under several SOs is not
  compared (which one the paste made is not guessed); it goes to Sales.
- Built, not committed (parked outside the repo while the parallel session
  holds `services.py`, `assembly.py`, `evals/world.py`, `routes.py`): the
  Customer order information (Form 1) reader (B02's titles; 81 columns, so
  the sandbox's 60-column cap goes to 100), one upload path for every Bravo
  screen (`ycbg_exports` generalised to `bravo_exports` with a `screen`;
  YCBG's tests to be kept green), the read-back kept per case
  (`order_bravo_read_backs`, stamped with the case version and the file) and
  shown on the order case beside the PIC's entry; it decides nothing.
- Decision owed (Đạt): should a read-back with differences block the
  cross-check, or only show beside it? Built to show (human-in-command); the
  safe default if asked to block is to refuse the cross-check while the
  latest read-back of the current case version differs.

## Done on the Excel path (2026-11-16, night)

- **One path for every Bravo screen** (`application/bravo_exports.py`):
  ticket 16's YCBG upload generalised. `POST /api/v1/sales/bravo-exports`
  takes the screen (`ycbg`, `sales_orders`); who may upload a screen and see
  its outcomes is one table (`SCREEN_SCOPES`: quote prepare, order prepare),
  read by the upload's gate and by the worker when it resolves the uploader
  again. The worker lane is `sales_bravo_exports`
  (`sales.bravo_export.uploaded`; ticket 16's old event type still reads the
  same row). Migration `7c6ad2350566` makes `sales.bravo_exports` and its
  files, copies ticket 16's rows across (each outcome's `ycbg_no` its `key`,
  tested on a database holding them), drops the old tables, and adds
  `sales.order_bravo_read_backs`; it is one way. YCBG's 62 tests kept green.
- **The sales orders read back** (`application/bravo_sales_orders.py`):
  "Customer order information (Form 1)" read by Bravo's titles (B02; the
  sandbox now reads 100 columns), grouped by direct customer and PO number,
  matched to the one case of that customer's PO waiting on or past its Bravo
  entry (`prepared`, `uploaded_to_bravo`), compared with its paste-sheet
  rows, and kept for the case with the case version and the file. No case,
  several cases, or a PO under several SOs go to Sales uncompared. Audited
  as the uploader.
- **On the pages:** "Đọc lại SO từ Bravo" on Đơn hàng (order prepare scope,
  refused while DW1 is paused); "Đối chiếu với Bravo" on an order case from
  `prepared` to `cross_checked`: equal, or each difference by line and field,
  stale when the case changed since, a price difference's values masked
  for a caller who may not read prices (decided in `ReadBackService`,
  mutation-checked). It decides nothing; the PIC still records the entry.
- Acceptance: 1 (one wrong price, one difference on that line) and 2
  (another customer's SO under the same PO number never matched) tested at
  the screen; 3: with nothing read the case says so and the manual entry
  stays.

Left: the vendor's API adapter (R10); filling `bravo_so_no` from Bravo when
equal (the PIC types it today, the panel shows Bravo's); the decision in
PLAN.md on blocking the cross-check.
