# 16 — The quote request to Design is numbered outside Bravo

Status: needs-info
Blocked by: Q-B11 (where the request is made and how it is numbered); B16 (the form in use)
Category: enhancement

## Why

Bravo's "Phiếu yêu cầu báo giá" screen was opened on 11-10 and holds
nothing. DW1's quote lane records `ycbg_recorded` with "the Bravo YCBG
number" and matches Design's reply by that number only (CONTEXT.md, YCBG).
In production the number has no Bravo to come from.

## Shape (to settle once Q-B11 answers)

- If Sales numbers the request in its own form (`RFQ2611…` on the board),
  DW1 drafts the form with the next number in the form's own pattern.
  Sales confirms the number, and Design's reply is matched by it, as today.
- If Design numbers it, DW1 records Design's number from the reply and
  matches by the customer, the item and the open request.
- Bravo's RFQ List and the request block of "Master list báo giá" are read
  (API R13) to follow a request, never to number it.

## Acceptance

1. A Design reply naming a number no open request holds stays unmatched
   and goes to Sales. It is never guessed onto a case.
2. Two open requests can never share a number (constraint, mutation-checked).

## Comments
