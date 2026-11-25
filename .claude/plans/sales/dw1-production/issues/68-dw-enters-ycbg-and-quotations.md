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

