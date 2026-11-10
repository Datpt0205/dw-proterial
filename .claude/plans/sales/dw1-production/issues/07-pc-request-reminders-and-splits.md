# 07 — The request to PC, its reminders, and lines split by PC's dates

Status: ready-for-agent
Blocked by: none (PC's own request form, if any, improves it)
Category: enhancement

## Why

Drawio 2a: Sales asks PC for delivery dates and chases them, and PC's reply
may split a line into several dates. DW1 reads PC's dates from a pasted
mail (item 7) but drafts no request and sends no reminder.

## Shape

- "Hỏi PC" drafts the request (lines, quantities, requested dates). The
  case waits on PC, with a follow-up from `sales_followups`.
- PC's dates that split a line become delivery schedules (ticket 21), each
  one a row of the paste sheet (ticket 02). Bravo keeps both the first and
  the current confirmed date, so a re-confirmation by PC keeps the first.

## Acceptance

1. A line PC splits in two becomes two schedules whose quantities sum to
   the line's.
2. A re-confirmation keeps the first confirmed date.

## Comments
