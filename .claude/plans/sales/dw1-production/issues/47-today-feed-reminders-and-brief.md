# 47 — "Hôm nay": one feed per person for the morning brief and reminders, learning what matters

Status: ready-for-agent (after 43–44)
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
