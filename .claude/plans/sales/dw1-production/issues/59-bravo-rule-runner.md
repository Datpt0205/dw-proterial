# 59 — A Bravo rule runner: execute the screen's own XML rules, not a copy of them

Status: ready-for-agent (the SO screen's layout, its 22 procedures and the UAT save trace are in hand; the shared templates come with script 03c)
Blocked by: 49 before anything runs against Bravo; none for building it offline
Category: enhancement

## Why

Bravo's form logic (the SO screen: 404 field rules, 27 validators) is not
executed by SQL Server.

- It is stored as XML in `B00LayoutData` and `B00ImportSetting`.
- It is run by the Bravo client on each PC: `B00Command` maps `EDIT_BizDocSO`
  to the `DataEditor` module.

A write through the database therefore skips every rule. Copying the 404 rules
by hand would create a second copy that drifts. The rules are data, though,
and the vocabulary is small:

- 11 rule component kinds;
- about 20 expression functions;
- 22 Bravo procedures and functions, whose code we have.

So DW can run Bravo's own definitions, read at run time, and follow Proterial's
configuration as it changes.

## Shape

- Parse the screen's XML at run time:
  - evaluators per column on `ColumnChanging` / `ColumnChanged`;
  - validators, separated into blocking and warning by `bValidateWarning`;
  - server constraints with their procedures and parameters.
- An expression evaluator for Bravo's language:
  - EMPTY, ISNULL, IIF, CHILD, SUM, SUMIF, VLOOKUP, EXISTS, IN, DATEADD,
    CHARINDEX, CONVERT, UPDATEDCOLUMN, USER, GETDATE;
  - `Parent.<col>` for the header and `Exists(Detail)` for the lines.
  - Unknown syntax refuses the run; it never guesses.
- Server constraints call the same procedures, read-only, under `dw_read`'s
  sibling login.
- Output: the exact column set the client would `INSERT`/`UPDATE`, the warnings
  for the PIC, and the blocking reasons.
- Scope order: SO lines (dates, split, cancel, quantity), then SO creation,
  then YCBG, quotation, PR, PO.

## Acceptance

1. Replayed on the 11-20 UAT trace, the runner produces the same columns and
   values the client sent, for every saved SO and YCBG operation.
2. Each validator in the SO layout has a test that fires it.
3. A layout changed in Bravo changes the runner's behaviour with no code change
   (test with an edited copy).

## Comments

Measured facts and file locations: `docs/proterial/bravo/BRAVO-NOI-BO.md`
(gitignored).
