# 73 — Gateway: split an SO line (`so.line.split`)

Status: in-progress — the split's statements and checks built offline 2026-11-27 (`e37b19d2`, `2c0d8fb3`); `so.line.split@1` stays `pending`; ready-for-human (the UAT split, script 08 rerun)
Blocked by: 70, 72 (the grid layout 8213's item binding on a new line), 75 (whether a grid line needs the New right), 52 (a clean UAT split)
Category: enhancement (tickets 53, 63)

## Why

`02-trace-3.csv` 11-25 17:28:58 shows a split's statements, inside a mixed
save (an empty line deleted, a quantity set on an unsaved line, then 135 + 115)
on a roller item, unit Pc.

## What

- Original line UPDATE: `Quantity`, `Quantity9`, amounts, `BoxQuantity`
  (= `Quantity9 / (QuantityBox * Length)`, 8212's `Eval_BoxQuantity_SetValue`),
  `QuantityBox`, `QuantityGroup` = the total, `GroupDivi`, `Divide` = 1.
- New line INSERT: copied columns plus `OriginalQuantity`, `GroupDivi`,
  `POLine` 0; header totals, `TotalQuantity`, `LMEFixed`.
- Switch stays off until the UAT session (ticket 52) traces a clean split of a
  saved quantity on a cable item (SO2609-000335 was proposed).

## Acceptance

- The 17:28:58 split part replays; the clean UAT split replays column for
  column before the switch's `uat_proof` is written.

## Comments

**2026-11-27, built offline (unattended, decided by recommendation).**
Plan and its adversarial critique from workflow `wf_c5489c26-ef9`; each of
the critique's points checked against the code, the layout and the schema
dump, and taken where it held.

What a split does now, through every check of the pipeline:
- Typed as the layout allows: on the line `Divide` = 1 first (so
  `Eval_QuantityGroup_GetVaule` takes the whole quantity, and the line is a
  head before its label: `Eval_Detail_Divi_GetData` would copy NULLs onto a
  labelled line without `Divide`), then `GroupDivi`, then the first part's
  `Quantity9`; per further part a grid line is added, its `GroupDivi` typed
  (the layout's copy rule brings the head's item, description, POLine,
  price, Length, carton, dates…: POLine is the head's, not 0; 11-20 copied
  POLine 1), then its `Quantity9` (`OriginalQuantity` follows, `Id < 0`).
  The parts' total is `CheckDivide`'s, not code's.
- `RuleRunner.add_row`: the relation key from the layout's own
  `<ParentKey>/<ChildKey>` (`BizDocId`), a negative `Id` (never written), every
  view column NULL, then `RowAdded`.
- The client's INSERT (five traced INSERTs read against the schema dump's
  defaults): the view's columns the table stores, in the table's order, each
  non-NULL one plus each NULL one with no default (`ParentRowId`, the dates,
  `GhiChu2/3` listed NULL; `TaxCode`, `ParentId` not; `PCNote`, not in the
  view, never), `RowId` '' (Bravo's `DML_B30BizDocDetailSO_InsertUpdate_RowId`
  fills it), read-back `WHERE Id=SCOPE_IDENTITY()`. A save is header UPDATE,
  then INSERTs, then line UPDATEs (11-20 10:30:07, 11-25 16:56:07, 17:28:58).
  INSERT is granted table-wide, so `render_insert` refusing a column outside
  that list, or an unread list, is the only column guard.
- `so.line.split@1`'s operation is `update` (the trace's context is
  `EDIT_BizDocSO|Edit`); the watch's import-template rule no longer pauses
  it (a split uses no import template). Contract fields unchanged; at most
  ten parts, added while pending. Schema regenerated.
- Refused before the approval is spent, as unmeasured: a line already in a
  group (it, or a line sharing its label, holds `Divide`), a line other lines
  follow (where Bravo puts the new line and renumbers is untraced), a
  confirmed date on any part (no traced split typed one), a cancelled line
  (as before), a new line whose view or table columns were not read.
- Rights: both the Edit and the New command right are asked until ticket 75
  says which a grid line needs (fail closed); column rights use `NoAddNew` on
  the new line and `NoEdit` on the line. The lock is checked on the line, not
  on the new one.
- Reconcile: the new lines are the lines Bravo holds that it did not, in
  order; each column compared; `RowId` must read back filled (an empty one
  would block every later line: `IX_B30BizDocDetailSO_RowId_Unique`); a line
  nobody planned (a colleague's, meanwhile) is a difference.
- The group label is the smallest positive number no other line uses; the
  line's own stale label is not kept (11-25: '2' became '1').

Measured: 31 new unit cases (26 in `test_gateway_split.py`, 3 runner, 2
trace reading), green with and without the trace; 23 mutations, each red,
each restored (order Divide/GroupDivi, `RowAdded`, the negative Id, each refusal,
updates before inserts, the lock skip, reconcile of inserts, RowId filled,
`NoAddNew`, the New right, the own label, NULL-without-default, validators
on new rows, the unknown column, the unread list, the parts bound, the
unplanned line, the generated columns on SQL Server, the agreeing-rows
answer, the INSERT exclusion in `before_after`). SQL Server 2017
(`test_gateway_sqlserver.py`, 21/22; the failing one is not this ticket's,
below): the read login reads defaults and generated columns from
`sys.columns` and the view's columns; the write login with INSERT on the
line table only inserts the client's statement and the row count is 1 under
a trigger in Bravo's `SET NOCOUNT ON` shape, which keys `RowId`; INSERT on
the header is denied.

Replay (`test_a_traced_split_is_held_back_where_the_layout_is_not_measured`,
both traced splits; 17:28:58's deleted empty line dropped against its one
DELETE): neither replays to the client yet, and the test says why.
- Copying the head changes the new line's `CustomerDescription`, whose rule
  `Eval_Detail_B20ItemCustomerDescription_Convert_ItemCode` holds when
  `ISNULL(GroupDivi,0) = 0`: a text label compared with a number. The runner
  refuses that comparison as unmeasured, so the gateway holds every split
  back on the real layout. Every reading consistent with the traces (the
  client saved labels '1' and 'A'; the convert procedure is never called in
  `02-trace-3.csv`) makes it false for a positive-number label, but how the
  client compares is not measured, so it stays refused.
- The client's copy raises the copied columns' rules (10:27:41: the special
  note, the base price and the MP check were called right after the copy),
  as the runner does. The 17:28:58 new line's `QuantityBox` 0 is no rule of
  8212's (its one rule writes 1 for a '-' carton): the grid layout 8213's item
  binding, ticket 72's, which a split's new line needs as a created line's
  does. Until it lands a gateway split would write `QuantityBox` and
  `BoxQuantity` the client does not.
- The ECP check a new line runs (`RowAdded`) has no result in a trace;
  answered UNKNOWN in the replay, so what reads it is undecided.

Script 08 (outside git) gains: VIEW DEFINITION on `vB30BizDocDetailSO_Edit`
(read), INSERT on `B30BizDocDetailSO`, UPDATE on `QuantityBox`, `GroupDivi`
and header `LMEFixed` (write), and the note that `DML_..._ChangeLog` fires
AFTER INSERT too, so section 3's Log-DB user is needed for a split as for an
update. The RowId trigger needs no grant (same owner, same database).

Left, and why:
- `pending` stays until a clean UAT split is traced (ticket 52), ticket 72's
  grid binding lands, and the label comparison is measured.
- DW1 proposing a split (ticket 53: `SplitChange` in `bravo_line_writes`, a
  CHECK migration admitting 'split' and `so.line.split@1`), not started: no
  point before the gateway can run one.
- Live, the header's `usp_B20BizProcessGroup`/`LMEFixed` and the item rules'
  procedures are ticket 50's, as for quantity and cancel.

Owed by Đạt / Proterial:
- The UAT split (ticket 52): a PIC, in an Edit window, splits a saved
  quantity on a cable item (SO2609-000335), the line having lines after it,
  and types a confirmed date on the second part.
- Whether PICs type `Length` again per part on a cable split (11-20 did
  not; 11-25 13:44:43 did).
- Proterial's `GroupDivi` label convention, and whether any report reads it
  (PICs typed 'A' and '1'/'2'; the gateway uses the smallest unused number).
- Script 10 (ticket 75): does a user with Edit but not New get to add a grid
  line?
- IT reruns script 08 with the grants above; script 07 for the Log DB.

Found, not caused here: `test_gateway_sqlserver.py::test_an_so_is_read_by_
its_number_in_the_clients_line_order` fails on SQL Server because its schema
has no `IsCancel`, which `c81fc553` added to the read; `test_bravo_so_layout`
and `test_bravo_rq_layout` count the 11-20 trace's saves and fail on
`02-trace-3.csv` (known since ticket 71).
