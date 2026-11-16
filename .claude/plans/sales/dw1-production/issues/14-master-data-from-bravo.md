# 14 — Master data read from Bravo, through one port per list

Status: ready-for-agent (2026-11-16: the Excel stand-in; B04, B05, B06, B07, B09, B21 are Bravo's own exports, all with the title row 1 / header row 2 shape)
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
