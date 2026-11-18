# 46 — One conversation per case, on the case page; one general one per person

Status: in progress (slice built 2026-11-16, looked at in a browser 2026-11-18; left: T0 buttons from the chat, explaining the thread; see "Done")
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

## Done

Slice built 2026-11-16 (recorded in dw_sales ADR 0007, addendum of
2026-11-16; glossary "Assistant session").

- **Store, one owner** (`sales.assistant_sessions`, migration `bfe2d1aeadcd`
  from 44's `efc46a50e75e`): `case_kind`/`case_id` (both or neither,
  CHECKed), `last_read_at` (`dw_app` may UPDATE it and `last_turn_at` only);
  partial unique indexes `uq_assistant_sessions_one_per_case` and
  `uq_assistant_sessions_one_general`; each person's older free sessions
  deleted, their latest kept as the general one. RLS, retention (30 days)
  and the turns are unchanged.
- **Service** (`application/assistant.py`): `CaseKey` from the route;
  `_bound` finds the case among the order or quote list's own reads (gate and
  record visibility) on every read and turn, else not found before the first
  event; a case conversation answers from its case's facts only and points
  another number or the person's work to the general one (`ELSEWHERE`); the
  general conversation answers a named case with a link only (`_linked`);
  `recent` (ten, re-checked as readable), `unread` (one indexed read); seen
  after the stream's last frame and on reading the case's conversation;
  `_held` refuses a store's row of another person or case.
- **Routes**: `GET /assistant/conversation`, `POST /assistant/ask[/stream]`
  (general), `GET /assistant/cases/{kind}/{case_id}`,
  `POST /assistant/cases/{kind}/{case_id}/ask[/stream]`,
  `GET /assistant/cases` (recent), `GET /assistant/unread`. The session
  routes and `session_id` are gone.
- **Web**: `_components/assistant-conversation.tsx` (the one chat, on
  `AssistantChat`), `_components/case-chat.tsx` (`WithCaseChat` on the order
  and quote case pages: open beside the case from `lg`, a button and a bottom
  sheet below, read only once opened), the assistant page (general
  conversation, ten recent cases with the unread mark), the mark on
  `RowTitle` in the order and quote lists and "Việc cần làm"
  (`_lib/unread.ts`, one read per list).
- **Tests**: `test_assistant.py` (acceptance 1 by a pasted instruction a
  model obeys and by a wording naming another PO; 2: an empty conversation
  shown, nothing created; 3: the link, and a restricted caller told not
  found; 4: another person sees none of it; another tenant, a restricted
  caller, a missing case and a wrong kind are not found before the first
  event; unread until read), `test_assistant_sessions_db.py` (uniqueness,
  CHECK, unread query, `case_id` never updated, prune), the eval graders
  (`sales_assistant@1.0.0` unchanged as data, its injection grader now words
  in the PO's own conversation), web `assistant-page`, `case-chat`,
  `my-work-owner` (the mark).

Left:

- Starting a T0 action from the chat through the case's own buttons is not
  built: the chat starts nothing (the buttons sit beside it on the page).
- The answers stay ADR 0007's catalog for the bound case (status, dates,
  flags); "explain the thread / the PO as read" through ticket 31's tools is
  not wired (those steps are off on the plant's model).
- 2026-11-18, **looked at in a browser** (local stack, dev sign-in, the
  Sales head; screenshots in `.playwright-mcp/t46-*.png`, not committed):
  the order and quote case pages at 1440 px (the conversation open beside
  the case), the order page at 390 px (the button bottom right, the bottom
  sheet showing the same conversation asked on the desktop, Esc closing it
  with focus back on the button) and at 320 px (no sideways scroll), the
  assistant page (general conversation, the recent case a real link to its
  page). With no model reachable the answer was the "DW1 chưa hiểu" sentence,
  as designed. Fixed on the way: three `Space direction=` (deprecated in
  antd 6) printed a console error on the quote page. Seen, not changed:
  antd 6.6 deprecates `List` for `Listy` (the assistant page warns).
- The unread mark only shows when a turn is kept and its answer never
  delivered; it matters once an answer can arrive while the person is away.
