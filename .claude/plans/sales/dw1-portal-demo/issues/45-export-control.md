# 45 — Export control, WIV-03-032: each step recorded, the orders it moves

Status: in progress (2026-10-28): backend done; the web page next
Blocked by: Proterial's WIV-03-032, red-flag form, ESF form and approvers
(customer questionnaire, questions 1–13): shipped as a sample until then
Category: enhancement

## Why

Đạt, 2026-10-28: "làm trước cái quy trình này". Proterial's survey lists six
steps: screen the product against PRV's list, check the customer on the
group's denial list, answer the red-flag questions, send the NOEC and receive
the NOC, have the ESF approved level by level (printed, signed, scanned), and
renew the ESF each fiscal year for every customer still buying. Until now DW1
only read the master data's NOC/ESF/denial date and raised `missing_noc_esf`.

## Shape

- **DW1 decides nothing.** A holder of `sales.compliance.ack` (the export-
  control PIC's permission set) records each step's result; DW1 keeps the
  latest per customer and step (`sales.export_control_screenings`, migration
  `1a21c3a78c93`, tenant AND workspace RLS, no DELETE), the audit trail keeps
  every one (`sales.export_control.<step>.<outcome>`, never the note).
- **One answer for every reader:** `effective_compliance(master, results)`;
  `ScreenedCatalog` wraps the approved master data at the composition root,
  so an order's `missing_noc_esf` follows a NOC received, an ESF approved, a
  denial-list match or an escalated red flag (both now hold the order). The
  master-data page, imports and the export-control page read underneath.
- **Steps:** product screen from `Item.export_classification` (a new optional
  master-data column, 該当/非該当); denial list `clear`/`match`; red flag
  answers to every question of the tenant's policy (`escalated` on any yes);
  NOC `requested`/`received` (with the document); ESF `approved` for a fiscal
  year (with the signed scan); the yearly renewal from the ERP export
  (`orders_since`, a year back).
- **Documents:** PDF, JPG or PNG, 10 MB, scanned; object storage under the
  tenant and workspace. **Drafts:** the NOEC mail (.eml, the customer's
  language) and the ESF form (xlsx or PDF, one signature line per approver).
- **Policy:** `sales_export_control@0.1.0`, a new `RuleKey` the tenant
  replaces on /sales/rules: red-flag questions (the published "know your
  customer" flags), ESF approvers, NOEC wording; `sample: true` until
  Proterial's.
- **API:** `GET /export-control`, `GET /export-control/{code}`,
  `POST …/denial-list|red-flag|noc|esf`, `GET …/noec-draft|esf-form|evidence/{step}`.

## Checked

Unit 21 (domain, the orders it moves, scopes, documents, isolation); five
mutations red (the screened catalog, the match hold, the scope, the scan, the
order hold); integration 5 on PostgreSQL (replace, RLS, no DELETE, CHECKs equal
to `OUTCOMES`); schema 31 with `ck_rule_versions_key`; eval smoke.

## Open

- The web page (`/sales/export-control`) and the master-data column label.
- Real forms and approvers: the questionnaire.
