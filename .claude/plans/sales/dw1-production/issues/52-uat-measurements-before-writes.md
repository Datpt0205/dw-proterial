# 52 — Measure on UAT what the writes depend on

Status: ready-for-human (Đạt at Proterial, one 20-minute trace with 02a/02b)
Blocked by: none
Category: research

## Why

Tickets 51 and 53 rest on three assumptions. They are cheap to measure now
and expensive to discover after the code is written (failure-modes #4:
measure, do not trust).

## Shape

With `docs/proterial/sql/02a`/`02b` recording, on Bravo UAT:

1. Import a DWTEST SO file built from template 72, with a PO price that
   differs from the quotation's.
   - Does the SO keep DW's price, or does Bravo's quotation lookup overwrite it?
   - Does Import show the same blocks and warnings as typing?
2. Cancel one line for real (tick, save), and once more through "Cancelled
   order information".
3. Approve ("Duyệt") an SO, and note which columns change.
4. Save a quotation ("Báo giá, chào hàng").
5. Later, for DW2: save a PR, save a PO from it, change the PO's date.

## Acceptance

- The trace CSV and the document numbers are in `Downloads/DB-Bravo`.
- Each question above has its answer recorded in this ticket.

## Comments
