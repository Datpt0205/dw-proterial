# 49 — ADR 0026 amended: Bravo read through a `dw` schema, written by Import or a staged job

Status: needs-info (waits on Proterial IT's and the Bravo vendor's review of the design)
Blocked by: none in code; the review of `docs/proterial/Thiet-ke-ket-noi-DW-Bravo_2026-11-20.docx`
Category: architecture decision

## Why

ADR 0026 says "no database access, ever", and `apps/api/tests/unit/test_no_bravo_database.py`
(through `scripts/verify_architecture.py` `bravo_database_violations`) refuses
any SQL Server driver. The 11-19/20 survey (`ops-hardening.md`, 11-20 entry)
showed the 48 needs can be met from what Bravo's SQL Server already has, with
no vendor API. Tickets 50–53 cannot start before the decision changes.

## Shape

- Amend ADR 0026, or supersede it with a new ADR:
  - reads go through views in a `dw` schema inside Bravo's database, with a
    SELECT-only login and snapshot isolation;
  - phase-1 writes use Bravo's own Import, pressed by a person;
  - phase-2 writes go through a staging table in `GetData` and an Agent job,
    under the PIC's Bravo user (Đạt, 11-20), after portal approval and UAT.
- Constraints the ADR records: DW's logins never hold a right on Bravo's
  tables or an admin role; `CONTEXT_INFO 0x55555` (Bravo's trigger bypass) is
  never used.
- Narrow the architecture test instead of deleting it. Only the Bravo adapter
  package may import the SQL Server driver; every other package still fails
  the test. A mutation (an import in `dw_sales.application`) turns it red.

## Acceptance

1. The ADR states:
   - the decision;
   - the rejected options: a vendor API, writing Bravo's tables directly, DW
     holding sysadmin;
   - the conditions.
2. The test refuses a driver outside the adapter package, shown red then green.

## Comments
