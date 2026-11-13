# 19 — One mail or one file with several POs opens one case per PO

Status: ready-for-agent
Blocked by: none
Category: enhancement

## Why

Customer 1 sends nine POs in one mail; customer 3 sends two; customer 2's
CSV holds one PO number per line. Today a mail is one case.

## Shape

- Grouping by PO number after reading: each PO number's lines become one
  case, each linked to the same stored message and file, with the lines'
  sources kept.
- A PO number repeated across files of the mail is one PO; the
  disagreement rule is ticket 22.
- The inbox shows the mail once with its cases listed.

## Acceptance

1. A fixture mail with three POs opens three cases whose lines sum to the
   file's lines.
2. Reprocessing the mail opens no second set.
