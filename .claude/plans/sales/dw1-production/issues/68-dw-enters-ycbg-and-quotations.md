# 68 — DW enters the YCBG and the quotation into Bravo, not only the SO

Status: needs-info (2026-11-25): waiting on one UAT trace of every entry (ticket 52's session, widened), then script 08 widened and run by IT

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

## Needs, in order

1. One UAT session traced by 02a/02b (Đạt, with a Sales person): each entry
   once, times and document numbers noted.
2. From the trace: each kind's columns, event word, rights checked, the
   client-set columns of a new line; script 08 widened to exactly those.
3. IT runs 07 and 08 on UAT; the acceptance per kind.
4. Asked of the vendor: how a new SO line's `QuantityBox` is set (two traced
   lines both 1, the column's default 0, ticket 59).
