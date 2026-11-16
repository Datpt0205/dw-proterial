# 14 — Master data read from Bravo, through one port per list

Status: done for the Excel path (2026-11-16); the vendor's API adapter waits on R01/R03/R04 (ADR 0026)
Blocked by: none to start; the vendor API replaces each upload later (ADR 0026)
Category: enhancement

## Why

Every master list DW1 imports today has an owner in Bravo, seen on 11-10:
customers (Danh mục đối tượng), items with the customer's item codes, the
convert list, base prices, LME, delivery term/mode/destination, colour
codes, black list, the export control program. A second copy in DW1 that a
person must import drifts from the first (failure-modes #2), and it is the
reason DW1 needs a master-data import page at all.

## Shape

- A `BravoMasterData` port, one read per list, as of a date. The adapter
  for the vendor's API (`docs/adr/0026`), and until then an adapter over
  the Excel each Bravo screen exports, uploaded by a person, through the
  same port.
- DW1's catalog snapshot is built from these reads. The existing master-
  data import stays only for a list Bravo does not hold.
- Every check stamps which snapshot it read (check basis, unchanged).

## Acceptance

1. A Bravo export of the convert list maps the same lines as Sales' own
   workbook on B43's sample.
2. A list that fails to read leaves the previous snapshot in force and
   says so. It never becomes an empty list that passes everything.
3. No connection to Bravo's database anywhere (`verify_architecture` keeps
   SQL Server drivers out).

## Comments

## Done (2026-11-16, Excel path)

- **One reader of every Bravo export** (`domain/bravo_exports.py`,
  `find_header`): the header is the row among the first ten that titles the
  most of the columns asked for, by title, never by position; a required
  column missing is refused by name (`MissingColumnsError`), a column nothing
  asked for is listed (`Header.extra`), a column titled twice refused unless
  its cells add up. `header_key` now drops Excel's `_x000D_` (B07, B16 and B21
  write it inside titles). The header is not always on row 2 as first
  assumed: B07's is on row 3 under block labels, B16's on row 4. The master
  lists (`parse_rows`, which used a shape rule before) and Design's result on
  a YCBG (ticket 16) both read through it; ticket 03's sales orders will.
- **`BravoMasterDataPort`** (`application/catalog_imports.py`): one read per
  list. `ExportedMasterList` answers it over the export a person uploaded;
  `CatalogParsing` reads every list through it, so the vendor's API adapter
  replaces the file without touching what follows (snapshot, preview,
  second-person approval, in force).
- **Acceptance 2:** a list that fails to read (a column missing, titles and
  no row, no usable row) leaves the approved snapshot in force; the list's
  state says the newest read failed and why (`test_bravo_master_data.py`,
  mutation-checked: letting an empty read through turns it red).
- **Acceptance 3:** `verify_architecture.py` refuses a SQL Server driver
  imported, declared, locked or named in a `mssql+` URL anywhere, tests
  included (`apps/api/tests/unit/test_no_bravo_database.py`).
- **Acceptance 1, measured outside git (counts only).** B43's `Form PO (new
  format)` as received is the **empty template**: `PRV vs PRL`, where Bravo's
  codes are pasted, has no row; `hk & cable` holds one real line (its other
  259 formulas resolve to 0). So it cannot show which code Sales' workbook
  gives. Measured instead against what Bravo itself holds: B02's 93 sales-order
  lines, each looked up in B04 (read through the port: 11,423 records, 100
  rows refused) by its direct customer and the customer's code or words:
  **93 / 93 the same PRV code** (56 by "All customer code", 37 by "Other
  information1"). B43 filled for one PO is asked of Proterial (below).

Owed:

- B43 filled for one real PO (the `PRV vs PRL` sheet with Bravo's rows
  pasted), to measure acceptance 1 as written.
- The new lists Bravo holds land with their tickets: Base price (11), the
  convert list's approval states and colour codes (04), the quotation master
  list (12); black list, LME screen and export control program after them.
- Running two sessions side by side: the integration harnesses read their
  database name from `DW_TEST_SALES_DB` / `DW_TEST_SALES_API_DB`.
