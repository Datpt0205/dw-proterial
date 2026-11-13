# 18 — "Tải PO lên" for a file Sales downloaded, and a portal's CSV export

Status: done (2026-11-13)
Blocked by: none (which customers use portals: owed by Proterial)
Category: enhancement

## Why

Customer 2 sends no PO by mail: a notice says the PO is on its portal, and
Sales downloads a UTF-16, tab-separated CSV that mixes forecast lines with
firm ones, one PO number per line. DW never logs into a customer's portal
(Đạt, 11-13): a person downloads, then uploads to DW1. Today a file Sales
forwards to themselves arrives from an internal address, so DW1 cannot tell
the customer.

## Shape

- "Tải PO lên" on the inbox: a person picks the customer and drops one or
  more files. Each becomes a stored message whose sender is that person,
  whose customer is the one picked (the person's choice, audited), and
  whose files go through the same malware scan, sandbox and reading as
  mail.
- A PO reader for the portal's CSV layout (a layout like any other: the
  tenant's, learned or mapped), reading firm lines only; forecast lines are
  counted and shown, never ordered.
- The notice mail itself is routed "PO trên cổng khách" to the PIC.

## Acceptance

1. An upload as one person for customer 2 opens cases from the firm lines
   only; the forecast count is shown.
2. A person without the right to process the mailbox cannot upload
   (refused at the route, negative test).
3. The same file uploaded twice is stored once.

## Done

- **"Tải PO lên"** (`dw_sales/application/po_uploads.py`, `POST
  /api/v1/sales/inbox/upload`, 202): needs `sales.inbox.process` (route guard
  and service); the customer must be in the tenant's master data (404
  otherwise, another tenant's code included); each file under the tenant's
  `max_attachment_bytes`, the whole under the drop lane's `MAX_MAIL_BYTES`,
  at most 10 files; refused while DW1 is paused. One stored message per
  upload, sender the caller's own sign-in address (`own_address`, shared with
  "Gửi cho khách"), id `upload-<hash of the files' hashes>`, so the same files
  again are stored once (`already_stored`) and nothing new is queued. Queued
  for processing as the caller. Audited `sales.po.uploaded` (actor the
  person, the customer chosen) in the store's transaction.
- **The stamp** (migration `66c90b900f4a`): `sales.mailbox_messages.uploaded_by`
  and `uploaded_for`, written by the server beside the message, never inside
  the message document; `ck_mailbox_messages_upload` holds the stamp to an
  `upload-` id both ways. Intake (`OrderIntake.customer_of`, `UploadLookupPort`)
  takes the stamped customer for an upload, and the layout screen asks the
  same function; an upload no reader reads is a PO by the person's word
  (routed `attachment_unreadable` for a layout to be mapped), never classified
  by keywords or a model. In a demo the mock mailbox shows uploads beside it
  (`WithUploads`).
- **Portal export**: `formats.sniff` says `csv` for UTF-16 with its mark and a
  tab on the first line; `adapters/readers/export.py` reads it as text rows
  (never a formula) with the customer's `ExportMapping` (a PO layout of kind
  `csv`: column titles, the order-type column, its firm values, the currency
  it does not print), firm rows only; other rows counted
  (`PoDocument.forecast_rows`, shown "N dòng dự báo, không đặt hàng" in the
  case's coverage). Price, amount and currency it does not print are flagged
  `not_printed`. Each line keeps its own PO number (`PoLine.line_po`, shown
  on the case); **one case per export**: grouping by PO number is ticket 19.
  The source view shows the export as a sheet `CSV`. Layout checks: titles on
  one row, `no_firm_line`, plausibility (prices only where printed). The
  onboarding screen maps an export; no model pre-fill for one.
- **`portal_notice`**: intent kind and routing reason ("PO trên cổng
  khách", to the PIC, no case), `sales.message_intent@1.1.0`, four golden and
  one injection eval case, recorded live on qwen3.5-9b-dw (0.902 ≥ bar 0.9;
  1.1.0 needs its own `--attest` before a tenant's switch uses it). Model off:
  `other` as before.
- Web: "Tải PO lên" on the inbox (`Upload.Dragger`, `Select`), labels, the
  export mapping form, line PO numbers and the forecast count on the case.
- Tests: `test_portal_export_and_upload.py`, `test_sales_upload_routes.py`,
  `test_sales_po_uploads_db.py`, `po-upload.test.tsx`.
