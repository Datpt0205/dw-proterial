# 50 — Read Bravo through the gateway, synced into DW, with a drift check

Status: in-progress — the copy by rowversion built offline (2026-11-21): the gateway's reads, the `bravo_sync` lane, DW's copy and its freshness page for the black list, LME and export control. pending: the pages and checks that use the copy (the black list and export-control checks, LME in the quotation, the quotation lookup, "item never produced", Design done), the procedure reads (`ufn_BlackList_Check`, `usp_WarningNewItem_HCV`, `usp_B30BizDocDetailSO_GetSQData_HCV`: called live, not copied), the other read kinds (customer, item, convert), and IT's read login on UAT
Blocked by: 63 (the gateway's read queries)
Category: enhancement

## Why

Thirty-one of the 48 needs are reads: customers, items, converting,
quotations, Base price, LME, export control, the black list, SOs and YCBG
status. Today DW1 reads files that people export, while Bravo's own tables
already hold these facts.

## Shape

- **No views (ADR 0027, 2026-11-21).** The gateway's read login holds
  SELECT on exactly the tables and columns below, granted by FPT's script and
  reviewed by IT. Nothing is created inside Bravo's database. The 11-20
  design's `dw` views are dropped, so there is no object of DW's inside a
  vendor database to survive upgrades and UAT restores.
- **Sync.**
  - A worker lane reads changed rows by each table's `timestamp` (rowversion),
    under SNAPSHOT isolation, every 5–15 minutes in working hours.
  - The first full sync runs 19:00–07:00.
  - Pages read DW's PostgreSQL copy and show when Bravo was last read. If
    Bravo is down, the data is stale, never wrong.
- **Facts read from Bravo, never typed into DW:**
  - black list: `B20BlackList`, `ufn_BlackList_Check`;
  - LME: `B20LME`;
  - export control: `B20ExportControlList`, with its dates and NoNeed flag;
  - quotation validity: the quotation's expiry date, not "one year";
  - "item never produced": `usp_WarningNewItem_HCV`;
  - Design done: the YCBG line's `Status = 'CLOSE'`, set by GetData's trigger.
- **Quotation lookup.**
  - The lookup follows `usp_B30BizDocDetailSO_GetSQData_HCV`: BP code +
    customer + indirect customer, valid on the SO's DocDate, approved, not
    closed and not cancelled.
  - The masterlist is `vB30BizDocDetailSQ_MasterList_HCV`. The Excel
    masterlist is read only when Bravo has no quotation (Đạt, 11-20).
- **Time zone.** Bravo stores UTC; DW shows and compares in Vietnam time.
- **Drift check** (the gateway's fingerprint, ticket 63).
  - It compares Bravo's client version, the hash of the Import templates and
    layouts DW uses (validators included), and the columns of every view.
  - A change stops writes (tickets 51 and 53) and tells a person. Reads go on
    while the views still hold.

## Acceptance

1. Every P1 read's figures match Bravo's screen on UAT.
2. The read login cannot select a column outside its grants (negative test on UAT).
3. A changed layout hash stops writes in a test.

## Done (2026-11-21, offline)

- **Reads through the gateway** served so far: `so.by_number`,
  `user.by_employee_code` (ticket 53), `so.by_customer_po` (ticket 51) and
  `sync.changes`. The others answer 501 until something uses them.
- **The copy by rowversion** (`dw_bravo.sync`): `sync.changes` reads one
  allowlisted table's allowlisted columns past a cursor, in rowversion
  order, a page of at most 1,000 rows; tables and columns come from
  `SYNC_TABLES` only, each named by the 11-20 schema: `B20BlackList`,
  `B20LME`, `B20ExportControlList` (with its dates and `NoNeed`). Values
  are kept as exact text (a float is refused). The read login's grant is
  column by column (`docs/proterial/sql/08`, outside git).
- **The `bravo_sync` lane** (worker, 10 minutes, 07:00-19:00 Vietnam): what
  changed since each table's cursor; once a night a full pass, which is how
  a row Bravo deleted is seen (marked gone, never deleted, unmarked if it
  comes back). Bravo not answering is said per table and moves no cursor.
  Runs only where the gateway and its tenant are configured.
- **DW's copy** (migration `ffd0c95da906`, `bravo.mirror_rows`,
  `bravo.mirror_cursors`, tenant only, RLS forced, DELETE revoked).
- **Freshness** (`GET /sales/bravo/facts`, `sales.case.read`): per table,
  rows held, rows gone, when Bravo was last read and fully read, stale past
  an hour, the last error in words.
- **Not built, and why:** the checks that use the copy. A black list or
  export-control check decides who DW may sell to; its rules (match on
  `KeyWord`? on `CustomerCode`? what `NoNeed` means) are Bravo's own
  routines (`ufn_BlackList_Check`) and the BA's, and are called live rather
  than re-implemented (ADR 0027: no second answer). LME in the quotation
  needs which of `LMEActual` / `LMECenter` the quotation uses.
- Tests: lane 9, gateway route 1, client 1, freshness 2, worker schedule
  1, PostgreSQL 3 (copy, errors, another tenant) + privileges 1, SQL Server
  1 (allowlisted columns, rowversion order, a changed row read again);
  12 mutations red.

## Comments
