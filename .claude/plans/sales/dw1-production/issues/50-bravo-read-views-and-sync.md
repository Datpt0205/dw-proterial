# 50 — Read Bravo through `dw` views, synced into DW, with a daily drift check

Status: needs-info (IT creates the `dw` schema and `dw_read` on UAT from FPT's script)
Blocked by: 49
Category: enhancement

## Why

Thirty-one of the 48 needs are reads: customers, items, converting,
quotations, Base price, LME, export control, the black list, SOs and YCBG
status. Today DW1 reads files that people export, while Bravo's own tables
already hold these facts.

## Shape

- **Views and login.**
  - FPT writes the view script (`dw.v_*`, only the columns DW needs). IT
    reviews it and creates it on UAT, then on production.
  - `dw_read` holds CONNECT and `SELECT ON SCHEMA::dw` only.
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
- **Daily drift check.**
  - It compares Bravo's client version, the hash of the Import templates and
    layouts DW uses (validators included), and the columns of every view.
  - A change stops writes (tickets 51 and 53) and tells a person. Reads go on
    while the views still hold.

## Acceptance

1. Every P1 read's figures match Bravo's screen on UAT.
2. `dw_read` cannot select a Bravo table (negative test on UAT).
3. A changed layout hash stops writes in a test.

## Comments
