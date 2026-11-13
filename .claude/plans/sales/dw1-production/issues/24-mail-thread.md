# 24 — The mail thread: a key on every stored message; thread to case many to many

Status: ready-for-agent
Blocked by: none
Category: enhancement

## Why

dw_sales ADR 0009 decisions 1–2. `ThreadLinks` links a reply only when its
headers name exactly one case; once ticket 19 opens a case per PO, every
reply in a multi-PO mail's thread names several and links nowhere.

## Shape

- A thread key on each stored message, computed when stored from
  Message-ID / In-Reply-To / References (the earliest known message of the
  chain), never from the subject or a model.
- `ThreadLinks` returns every case of the sender's customer the thread
  holds, not only one. One: attached as today. Several: the numbers the
  message names (`message_intent.resolve`, or a document's PO number)
  choose; none named: routed `reply_to_case` with the candidate cases for
  Sales to pick ("Chọn hồ sơ").
- A case shows its thread(s), including the messages before its PO.

## Acceptance

1. A reply in a thread with three cases naming one PO number attaches to
   that case only.
2. The same reply naming none is routed with the three cases offered.
3. A reply whose References name another customer's message links nothing
   (negative test).
4. A message whose References name messages of two threads joins the
   earliest; the key never changes once stored.
