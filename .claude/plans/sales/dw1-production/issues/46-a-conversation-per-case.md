# 46 — One conversation per case, on the case page; one general one per person

Status: ready-for-agent (after 43–44; the Qdrant review of 2026-11-17 first)
Blocked by: 40 (skills), 44 (tiers)
Category: enhancement

## Why

Đạt, 2026-11-17: an internal chat where each PO thread is one session, with
an experience that does not confuse people with too many sessions. Today
the assistant (dw_sales ADR 0007) keeps free sessions per person on its own
page, and its focus case is state inside a session.

## Shape

- **The case is the conversation.** A chat panel on the order and quote
  case pages (`@dw/ui`'s `AssistantChat`, Ant Design X, the one chat frame),
  bound by code to that case: its focus is fixed, never inferred, and its
  tools (ticket 31's, bound to the case's customer) see only that case's
  customer. Opening the case opens its conversation; there is no "new
  session" to make and no list of sessions to manage.
- **One general conversation per person** on the assistant page, for
  questions across cases; a case it names is offered as a link to that
  case's conversation, never answered with another customer's data.
- **Private per person**, kept like today's sessions (RLS by tenant,
  workspace and user, pruned after 30 days); what DW itself did on a case is
  in the case's shared activity, not in anyone's chat.
- **Found from the work, not from a list**: the case list and "your turn"
  show a small mark on cases with an unread answer; the assistant page shows
  at most the ten cases most recently talked about.
- **What it may do**: answer and explain (status, findings, the thread,
  the PO as read), and start a T0 action through the case's own buttons
  (a draft, a reminder). Never a T2 effect (ADR 0015): a Bravo write,
  anything sent, a price.
- Streamed through `released` (every word held until it passes its check),
  as today.

## Acceptance

1. A case's conversation never answers from another case's or customer's
   data, whatever is asked (negative test, also by injection in a mail).
2. Opening a case shows its conversation; nothing else needs creating.
3. A question in the general conversation about a case links to it and
   reads it with the caller's own permissions.
4. Another person's conversation on the same case is not found.
