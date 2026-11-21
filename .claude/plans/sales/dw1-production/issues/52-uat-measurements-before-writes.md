# 52 — Measure on UAT what the writes depend on

Status: ready-for-human (Đạt at Proterial: the 02a/02b trace, then scripts 05, 03c, 06 and 07, and the IT questions in item 8)
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

**Added 2026-11-21 (ADR 0027 rests on these; `docs/proterial/sql/06` and `07`).**

6. **Script 06: users and rights, as counts only.**
   - Are employee codes filled, and unique, for active Bravo users?
   - Are employee e-mails filled?
   - How many users are mapped to Windows accounts?
   - Which permission rows exist for the SO, YCBG, quotation, PR and PO
     commands?
7. **Script 07, on UAT, inside a rolled-back transaction.** Does an SO line
   UPDATE, with its triggers, succeed under a login holding only column
   grants? Does `SET CONTEXT_INFO` work under it? Does a SNAPSHOT read work
   under the read login?
8. **Questions for IT, not scripts.**
   - Can the DW host reach the AD over LDAPS, or through their federation
     service (AD FS or Entra ID)?
   - Can DW have a read-only AD account?
   - Is the AD's `employeeID` filled?

## Acceptance

- The trace CSV and the document numbers are in `Downloads/DB-Bravo`.
- Each question above has its answer recorded in this ticket.

## Comments
