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
  - DW performs the writes itself, after the PIC approves on the portal; it
    does not stop at a proposal (Đạt, 11-20);
  - creating a document goes through Bravo's own engine. The ways, in order of
    preference:
    1. a vendor procedure, or Bravo's own automation (ticket 60);
    2. UI automation of the Import button;
    3. DW's runner of Bravo's XML rules (ticket 59);
  - changes to an existing document go through a staging table in `GetData`
    and an Agent job, under the PIC's Bravo user (Đạt, 11-20), after portal
    approval and UAT.
- Constraints the ADR records: DW's logins never hold a right on Bravo's
  tables or an admin role; Bravo's trigger-bypass context value is never used.
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
