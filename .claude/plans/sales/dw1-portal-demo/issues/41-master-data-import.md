# 41 — Master data imported from a file, previewed and approved

Status: done (2026-10-19; Đạt's goal of 2026-10-18; built by the agent, `80c9b29`, `035d5a7`, `9b80a3f`, `ed78006` and the plan commit; unit-tested and mutation-checked; integration tests written and owed while Docker is down)
Blocked by: —
Category: enhancement

## What

Proterial's master data must not be hard-coded mock files: business users
load and update it themselves, and real data replaces the mock as it arrives
(Đạt, 2026-10-18). Later the same lists may be synced from the on-premises
Bravo ERP through another adapter, so storage and approval do not depend on
where the rows came from. `SalesCatalogPort` was read-only and implemented
only by the mock (`adapters/mock/catalog.py`); `/sales/master-data` showed it
read-only.

## Acceptance

1. A persistent, tenant- and workspace-scoped catalog for the lists Sales
   maintains by hand: customers, items, convert list, quotations, LME months.
   Each import is a versioned snapshot (as_of, who, source, file name,
   sha256). Bravo's orders and open YCBG stay on the existing port and mock:
   they come from the ERP, not from a file.
2. A tenant with no approved snapshot of a list reads the mock for that list;
   the page says which (dữ liệu mẫu / bản nhập ngày … bởi …). Every
   exact-lookup semantic of the port kept.
3. Import from Excel/CSV: a template per list with Vietnamese headers,
   tolerant header matching, per-row validation with row number and reason in
   Vietnamese; the file is parsed in the reader sandbox by the worker, never
   in the API; nothing applies on upload.
4. Preview and approval: the diff against the list in force (added, changed
   old to new, removed, counts, rejected rows); the PIC submits; the head
   approves on platform approvals (a stamped type, maker-checker); approval
   makes it current, earlier snapshots stay readable; every step audited;
   Idempotency-Key on every mutation.
5. Tests: unit, negative (another tenant, the proposer, a role without the
   scope), API unit, web vitest; integration written; mutation checks.

## As built

- **Domain** `domain/master_data.py`: `CatalogList`, the columns of each
  list (`SPECS`: Vietnamese header, aliases, cell kind, guidance), header
  matching without diacritics/case/punctuation (`header_key`), `parse_rows`
  (a record or a `RejectedRow(row, column, reason)` per row; a key twice, an
  email domain two customers claim and a quote number two customers use are
  refused at the later row; a missing required column refuses the file),
  number reading in either grouping with "1.000" refused as ambiguous, dates
  day first, and `diff` column by column as the template prints values.
- **Application** `application/catalog_imports.py`: `CatalogSnapshot`
  (status `queued → parsed | failed → submitted → approved | rejected`,
  `superseded`, `discarded`; `source` `file` or `erp`), the narrow ports
  (`CatalogUnitOfWork` with snapshots, approvals, audit, outbox;
  `TableReaderPort`; `CatalogTemplatePort`), `CatalogImportService` (state,
  template, upload, preview, submit), `CatalogParsing` (the worker: scan,
  reader sandbox, parse, references checked by exact code against the lists
  in force, LME months after `as_of` refused, file dropped), `CatalogDecisions`
  (the decision guard) and `CatalogSettlement`. `sales.master_data.import`
  (PIC, head) and `sales.master_data.approve` (head); the quotation list also
  needs both price scopes and the LME list `sales.price.read`, for upload and
  preview alike, since the preview shows prices.
- **The catalog DW1 reads** `application/snapshot_catalog.py`:
  `SnapshotSalesCatalog` answers each hand-maintained list from the
  workspace's approved snapshot and from the mock otherwise (wired in
  `build_dw1`); a snapshot replaces its list whole, so a code it lacks is
  None whatever the mock holds. The quotation master list a sent quotation is
  recorded in (`QuotationLedgerPort.record`) stays the mock's.
- **Approval**: `submit` opens a run-less `sales.catalog` approval stamped
  `sales.master_data.approve`, makers the importer and the submitter,
  payload ids, list, file name and sha256, counts and the snapshot compared
  with (never a row). The guard refuses a stamp other than that, a snapshot
  no longer submitted, a maker, and approving one compared with a list
  approved since (`base_changed`). The worker settles
  `sales.catalog.decided`: approved supersedes the list in force.
- **Reading the file**: one outbox event `sales.catalog.imported` in the
  upload's transaction; `dw_worker/consumers/sales_catalog.py` hands it to
  `CatalogParsing`; reader op `table.rows` (`adapters/readers/tables.py`):
  `.xlsx` (sheet "Dữ liệu", else the first visible), `.xls` converted first,
  CSV in UTF-8 or UTF-16 with `,` `;` or tab; under the order rules' caps,
  5000 rows, 60 columns. The API keeps the bytes (2 MiB) and opens nothing.
- **Migration `511ef1b71dee`** (down_revision `445f93c2ea2a`):
  `sales.catalog_snapshots`, `sales.catalog_import_files`,
  `sales.catalog_rows`; RLS enabled and forced, tenant AND (workspace OR the
  offboarding scope); one approved and one open snapshot per list (partial
  uniques); `ck_catalog_snapshots_checker_not_maker`; composite FK to the
  approval (CASCADE, as `rule_versions`), base snapshot `SET NULL
(base_snapshot_id)`; `ck_approval_requests_sales_catalog_stamped`; grants
  (`catalog_import_files` and `catalog_rows` take no UPDATE); the two scopes.
- **API** `/api/v1/sales/master-data/imports`: `GET` (state per list), `GET
/{list}/template` (xlsx), `POST /{list}` (202, base64 body), `GET
/snapshots/{id}` (preview), `POST /snapshots/{id}/submit`. No route
  decides.
- **Web** `/sales/master-data` ("Dữ liệu chủ" in the nav): per list the
  source badge, "Tải mẫu", "Nhập file", the status while the worker reads
  (polled every 3 s), the preview tables and rejected rows, "Gửi duyệt" and
  the link to `/approvals/{id}`; disabled controls say why; Bravo's tabs say
  they come from the ERP. `/approvals` decides `sales.catalog` in place.

## Tests run (no Docker)

- `tests/unit/test_master_data_import.py` (21): every list reads back from
  its own template rows; tolerant headers; refused file; each bad row's
  row, column and Vietnamese reason, never the value; number groupings; the
  diff; the mock when nothing is approved; the whole flow through the eval
  world (upload reads nothing, the worker parses, preview, submit, the head
  decides on the platform approval, exact lookups after, audit as the lane,
  a second import supersedes and the first stays readable); the proposer
  refused (platform and guard alone); a changed base refused; another tenant
  reads, previews, submits and decides nothing and is served its own source;
  no scope / no price scopes refused; a failed file's reason; a waiting
  import blocks another; unknown customer or item rejected; the template;
  the reader's CSV and refused encodings.
- `apps/api/tests/unit/test_sales_master_data_routes.py` (4),
  `apps/worker/tests/unit/test_sales_catalog_consumer.py` (2),
  `test_sales_support.py` (new routes refused to a support context), web
  `master-data-import.test.tsx` (9) and `approvals.test.ts`.
- Mutations, each red: the guard reading under the approval's scope instead
  of the decider's (another tenant's head found the snapshot); the guard
  without maker-checker; the preview without the price scopes; the guard
  ignoring a changed base; the web's "waiting import" refusal.

## Owed (local Docker)

- `packages/python/dw_sales/tests/integration/test_sales_catalog_imports.py`
  (a snapshot read in its workspace only, through `SqlApprovedLists` and the
  store, the kept list keyed by scope; the file dropped once read; one open
  import per list; the maker refused by the CHECK; a `sales.catalog`
  approval stamped otherwise refused), and the lists extended in
  `test_privileges.py`, `test_sales_schema.py`, `test_sales_roles.py`,
  `test_sales_personas.py`.
- The migration's upgrade and downgrade round trip; `test_rls_coverage.py`
  over the three tables.
- A mutation of `SqlApprovedLists`'s cache key without the tenant, against
  the integration test above.
- The page on the stack (upload a real Proterial list once it arrives), and
  `make demo-reset`: the reset deletes `sales.` approvals, which cascades to
  the demo tenant's submitted and approved snapshots (as rule versions).

## Left open

- A snapshot's rows are kept for ever (superseded ones stay readable by
  design); a retention rule is owed when imports become frequent (an ERP
  sync).
- A quotation DW1 sends is recorded in the mock's in-memory master list,
  not in an imported quotation snapshot; for a workspace on imported
  quotations it reaches the list with the next import.
- A queued import whose outbox event spends its attempts (reader down for
  long) stays "Đang đọc tệp"; uploading again discards it.
- Removing items from the item list leaves convert entries or quotations
  that name them: lookups stay exact (the item is None), the preview does not
  yet warn about it.
- The Bravo adapter: a sync writes a snapshot with `source = 'erp'` and walks
  the same submission and approval; not built.
