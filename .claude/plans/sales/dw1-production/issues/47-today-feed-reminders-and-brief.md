# 47 — "Hôm nay": one feed per person for the morning brief and reminders, learning what matters

Status: in progress (slice built 2026-11-15, built with 48; what is left is under "Done")
Blocked by: 43 (labelled cases), 44 (tiers)
Category: enhancement

## Why

Đạt, 2026-11-17: the reminder agent and the morning brief should not add
sessions or noise either. Today the brief (`morning_brief`), customer
reminders and follow-ups (`sales_followups`, the worker's lanes) reach a
person as separate notifications.

## Shape

- **One feed per person, "Hôm nay"**: the morning brief at the tenant's
  time opens the day; reminders through the day join the same feed, newest
  on top, each one line with the case, why now, and one action (open, the
  draft, "Đã xử lý"), plus "Nhắc lại sau" and "Không cần". The bell shows
  the count; there is no second place to look.
- **Ranked, not just listed**: what is due, blocking someone else, or about
  to breach a customer's term comes first; the model words each item from
  facts code built (figures checked), code ranks by due time and tier.
- **Learns what matters (ADR 0015)**: "Không cần" and "Nhắc lại sau" are
  labelled cases; similar items are ranked down or batched for that person,
  never dropped when a term or a customer's deadline is at stake (a
  floor code enforces).
- **Reminders are T0**: they apply themselves; nothing is sent outside.
- **Latency**: built in the worker, ready before the person opens it.

## Acceptance

1. A reminder whose deadline is a customer's term is never hidden by
   learning, however often it was dismissed.
2. The brief and the reminders of one day are one feed, not two places.
3. Every figure in an item is a fact; an item that fails the check is shown
   in code's own sentence.
4. One person's feed and feedback never reach another's.

## Done (2026-11-15, one slice with ticket 48)

- **One feed, one page.** `/sales` ("Việc cần làm") is the place: today's
  brief on top, the work list (48), then "Nhắc việc". The brief is the one
  the `sales_followups` lane delivered to the person today, read back from
  the inbox (`GET /sales/today`, `dw_sales.application.today`), so nothing
  slow runs when the page opens; its model-written opening (already
  figure-checked in the worker) shows tagged "DW1 viết", the counts behind
  "Xem số liệu". Reminders are the person's follow-up notifications of the
  last 7 days in this workspace, but "your turn" (the work list holds that
  work) and the brief.
- **"Đã xử lý", "Nhắc lại sau" (1 h, 4 h, ngày mai), "Không cần"**, stored
  per person in `sales.reminder_marks` (migration `4bcfa82060fc`; RLS
  tenant + workspace + user, read scope for offboarding; gone with its
  notification by cascade, so 90 days like the inbox).
- **Learns, never drops a term.** A follow-up kind the person dismissed more
  often ranks lower for them; a customer's term (`CUSTOMER_TERM`:
  `quote_deadline`, `implied_acceptance`) is first, takes "Đã xử lý" only,
  and is never hidden by a dismiss or a snooze: the service refuses (409),
  `ck_reminder_marks_customer_term` refuses the row, and a mark that exists
  anyway is read as nothing (acceptance 1).
- **One person's** (acceptance 4): the inbox read is the caller's own, marks
  are RLS-narrowed to the person, a mark on someone else's notification is
  404 (unit and integration tests).
- Decided: a dismissal is stored as a reminder mark, not in
  `sales.labelled_cases` (that table holds a model step's proposed and kept
  values, ADR 0015 decision 5; a reminder carries neither).

**Left:** the model wording each reminder line (reminders are still code's
sentences as the lane writes them; acceptance 3 holds because no model text
is in them); batching similar reminders for a person (only ranking down);
the bell still lists the inbox beside the page.

