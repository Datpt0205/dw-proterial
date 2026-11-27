# 68 — DW enters the YCBG and the quotation into Bravo, not only the SO

Status: needs-info (2026-11-25): waiting on a 10-minute UAT trace of what the 11-20 trace lacks (quotation, an existing SO's save, a cancel, a split on another packing), then script 08 widened and run by IT

## Why

Đạt, 2026-11-25: DW enters everything Sales entered in Bravo; Sales only
approves before the entry (ADR 0027 addendum). Only the SO's 5 write kinds
existed, all off.

## What

New write kinds on the gateway's pipeline (token, PIC's user, rights,
runner, column grants, audit), each off until measured:

- `rq.create@1`, `rq.line.update@1` (YCBG): from the draft ticket 16 builds.
- `sq.create@1`, `sq.line.update@1` (quotation): from Design's QUOTE and the
  base price; the price computed by the SQ screen's rules (runner, ticket
  59), never written by DW.
- The SO's 5 (tickets 51, 53).

## Already traced (11-20, `02-trace-uat-bo-sung.csv`, local only)

Read again 2026-11-25 (Bravo writes `UPDATE TOP (1)`): an SO created by
typing (header + 2 lines), a line's quantity, a line's dates (CDDate,
EstimatedTimeDelivery, SalesAccountingDate), a split (a line INSERTed,
Divide/GroupDivi/QuantityGroup set), the header's POCustomer, a YCBG created
by NewAsCopy, Design's result on a YCBG line (20 columns). Every SO edit was
on the SO just created, in the window still open (context `EDIT_BizDocSO|New`).

## Needs, in order

0. **Settled from the schema, 2026-11-25:** the context's event word (`New`
   for the traced edits) is only copied by `DML_*_ChangeLog` into Bravo's
   change log (`__$CommandKey0`); the user id is read apart
   (`ufn_sys_GetUserIdFromContext_Info`). So an existing SO's save carries
   `Edit` (the screen's permission command of that name), checked once at
   the UAT acceptance against Bravo's log row; no trace needed. The user's
   Edit/Save right is read by a read-only script (to write), not traced.
   **Still needs a Sales person, about 5 minutes**: a quotation created and
   edited (none traced); a real cancel, both ways; and a split on a bobbin
   or drum item, unless the vendor says how `QuantityBox` is set. Import is
   not needed: DW creates an SO as the typed create does.

1. One UAT session traced by 02a/02b (Đạt, with a Sales person): each entry
   once, times and document numbers noted.
2. From the trace: each kind's columns, event word, rights checked, the
   client-set columns of a new line; script 08 widened to exactly those.
3. IT runs 07 and 08 on UAT; the acceptance per kind.
4. Asked of the vendor: how a new SO line's `QuantityBox` is set (two traced
   lines both 1, the column's default 0, ticket 59).

**2026-11-25, the one UAT session handed to Đạt (02a/02b, about 25 minutes,
with a Sales person; times and document numbers noted):** A. a YCBG made by
New (not a copy), then one of its lines edited before Design answers; B. a
quotation made the way Sales makes one from Design's QUOTE (pulled from the
YCBG if that is how), then one non-price cell edited; C. an SO made the way
Sales usually makes one (pulled from the quotation if that is how); D. an
existing SO opened from the list (window closed first), a line's date
changed and saved, then a quantity changed and saved; E. a line split on a
bobbin or drum item; F. a line cancelled by its tick, and one through
"Cancelled order information". What each answers: the INSERT/UPDATE column
sets and the procedures each save calls in order (A, B, C), the event word
and the permission calls of an existing document's open and save (D),
`QuantityBox` (E), what a cancel writes (F). IT, apart: scripts 07 and 08.
Added the same day from the change log (ticket 69): C2. an SO made by
Import with the template Sales uses (305 of 2,608 recent SO saves); G. a
line's unit price changed to the PO's (about 120 recent saves; a new write
kind, `so.line.set_price`, the price only ever the PO's, ADR 0008).


**2026-11-25, what the UAT session traced (`02-trace-2.csv`, 13:28–14:00,
local only):** A done (a YCBG by New, one line; then Edit: 4 line columns),
B done (a quotation by New with its line pulled from that YCBG line,
`RowId_RQ`; the prices `PriceLME1..15`, `OriginalPriceLME*`, `MaterialCost`
from Bravo's own `usp_B30BizDocDetailSQ_Check_B20BasePrice` and `_LME`; then
Edit: header delivery mode/term, the line's item and price columns), D done
(an existing SO opened from the list: context `EDIT_BizDocSO|Edit`, the word
settled in Needs 0 now seen; a date save of 3 columns; a quantity save on a
split pair: Quantity, Quantity9, amounts, Length, QuantityGroup, Divide, and
the header's totals). Not traced: C (an SO pulled from a quotation), C2
(the Import dialog opened, `B00ImportSetting` read, nothing imported), E, F,
G. Every save ends in `usp_B30BizDocProcess_CreateProcess` and touches the
header (`ModifiedBy`).

Read from the layouts and today's rows instead of a trace:
- **Cancel (F)** is not a tick and not the "Cancelled order information"
  screen (`MasrerList_Cancel` is a list whose row opens the SO): on the SO
  line, column "Order status" (`IsCancel`, a lookup of `B20Class`
  `SOCancel`, value `Cancel`) sets Cancelled date (today), Cancelled
  quantity (`Quantity_Edit`), Cancel price (`UnitCost`), amount, and
  `CancelPRS` (`ufn_B30BizdocRelationSO_PRS`); the person types the reason.
  114 lines carry `Cancel` today; their logged saves set quantity, price,
  amounts and `BoxQuantity` to 0. Whether the 0s are typed or computed is
  the one thing a 2-minute trace of F settles.
- **What may be edited** is in the grid layout (8213), not the data layout
  the runner reads: 35 `Editor/Expr` conditions. A line on a completed or
  pending delivery (`CheckEdit` = `ufn_Prevent_Edit`) takes no edit; a saved
  line's quantity changes only through a split or a cancel; the unit price
  only while `RowId_Price` is empty; `UnitCost` never. The runner does not
  read these yet: a write kind must, or DW writes what the screen forbids.
- **Import (C2)** is 305 of 1,090 SO creates in the log, one person, each a
  one-line SO, and it skips screen rules the typed create runs
  (`BasePriceCode` on 6% of imported lines, 74% of typed). DW creates as the
  typed create does; the paste sheet (ADR 0026) stays the way back.
- **The quotation screen** (8375) holds 2 rule kinds the runner refuses
  (`BravoNullValidator` ×2, `BravoCommandKey` ×3) and calls two writing
  procedures as server constraints (`usp_B30BizDocDetailSQ_ExpiryDate_Update`,
  `usp_B30BizDocSQ_ExpiryDate_Update`), which the runner must never call
  while it plans. The YCBG screen (11766) has nothing it refuses.

**2026-11-25, later:** none of the three trace files (11-20 and 11-25) holds
a save touching a cancel or a unit price; the only split is the 11-20 one on
an item of `QuantityBox` 1. The UAT machine has no network and takes no
file, so C2 (Import) is dropped: DW does not need it. A cancel's price going
to 0 is the screen's own rule (`Eval_Ct0_OriginalUnitCost_ResetWhenQuantityZero`
on `Quantity9`). Handed to Đạt: one session, E/F/G on UAT's SO2609-000335
(lines of `QuantityBox` 5 and 3, 610 m), each saved apart.

**2026-11-25, Đạt:** no SO is ever made from a quotation; Sales makes every
SO from the SO file. C is dropped, and the SO screen's pull from a quotation
(`RowId_SQ`, `usp_B30BizDocDetailSO_GetSQData_HCV`) is not a path DW writes
by. The trace still owed is E, F, G only.
