# 10 — Changes Proterial makes itself: overcapacity, NG, short stock

Status: ready-for-agent
Blocked by: none (an example notice to the customer improves it)
Category: enhancement

## Why

Drawio 2b (6.1B): after confirmation, PC may move or split the dates of
many lines at once, or cancel lines. DW1 handles a customer's revision
(`change_review`), not a change that starts inside Proterial.

## Shape

- "Thay đổi nội bộ" on a confirmed order takes the reason (overcapacity,
  NG, short stock, other) and the lines with their new dates or quantities,
  pasted from PC's mail and read the way item 7 reads.
- It produces the change list to apply in Bravo ("Thay đổi chi tiết") and a
  drafted notice to the customer, and sends the case back to cross-check.

## Acceptance

1. A bulk split of 20 lines makes one change list and one notice.
2. Nothing on the case changes before a person applies it.

## Comments
