---
status: Accepted
date: 2026-10-30
accepted: 2026-10-30 (Đạt: "làm hỏi đáp có session ... mục tiêu là trả lời theo ngữ cảnh tốt", the design left to the implementer)
amends: the AI list's item 9 (a read-only assistant over cases), deferred on 2026-10-30 and brought back by the contract
---

# Status questions are answered from live data: the model reads the question, code answers it

## Context

The contract's DW01 acceptance criterion 6 ("Báo cáo và trả lời") asks that
questions on an agreed list (a PO's status, a quotation's status, the work
waiting, the work overdue) be answered right from the data in the system, over
the connected channel, and that anything outside the list or without enough
data be said plainly, never guessed. Item 9 of the AI list had recorded a
platform agent with read-only Sales tools for this; Đạt deferred it on
2026-10-30, and the contract brought it back.

Đạt asked for sessions, short- and long-term memory "so context is not lost",
and raised two techniques: compacting context into images, and keeping past
context in Qdrant to retrieve when needed. The goal he set is answers that are
right in context.

## Decision

1. **A catalog, not a chat.** Four kinds of question (`QuestionKind`):
   `order_status`, `quote_status`, `my_work`, `overdue`, and
   `out_of_scope` for everything else, which is answered with the list of
   what DW1 can answer. No question is answered from the model's own
   knowledge.
2. **The model understands, code decides** (the operator's rule 6). One call,
   `sales.question_intent@1.0.0`, turns the question into a `QuestionIntent`
   (kind, the PO or request number written, whether it refers to the case
   just discussed). Code resolves it against the cases **the caller may see**,
   through the same query services the portal reads (`OrderQueries`,
   `QuoteQueries`, `OverviewService.my_work`): the assistant can never show
   what the page would not. A number that matches nothing is "not found among
   the cases you can see"; a model that is down or answers nonsense is "DW1
   did not understand", never a guessed case.
3. **Facts are code's, and carry no amount.** Status, whose turn, the next
   step, dates, counts of open flags; never a price. That keeps every answer
   safe for any channel and every role.
4. **The wording is the model's, checked; the fallback is code's.** A second
   call, `sales.assistant_answer@1.0.0`, writes the answer from the facts.
   Code keeps it only when every figure is among the facts and it names no
   amount (`figure_check`); otherwise the answer is code's own sentence from
   the same facts. Each answer lists the cases it rests on, as links.
5. **Sessions and short-term memory live in PostgreSQL**
   (`sales.assistant_sessions`, `sales.assistant_turns`): a person's own,
   by RLS (`tenant AND ((workspace AND user) OR scope)`), and by the service.
   The last turns of the session go to the intent call as untrusted history;
   the case the conversation is about is carried as **structured state** (its
   kind and id, the `focus`), so "PO đó giao chưa?" resolves to the case code
   resolved last time, re-checked against what the caller may see on every
   turn, instead of an id the model restates.
6. **Thirty days**, then a session goes (`sales.prune_assistant_sessions()`,
   the worker's `sales_assistant_retention` lane): a technical bound on a
   working conversation, like the in-app inbox's, not a legal term.
7. **The core is channel-agnostic.** The portal is the first channel (on
   premises, "kênh tương tác khác"). Zalo or Teams is an adapter over the same
   service once Proterial accepts that questions and answers pass through the
   provider and the host reaches out to it; the channel's account must be
   bound to a verified member first, as `dw_platform`'s channel links are.

## Not chosen

- **Compacting the context into images.** Rendering text as an image to save
  tokens is lossy exactly where a status answer cannot be: PO numbers, dates,
  item codes. The on-premises model reads text, and a session here is a few
  short turns, nowhere near a context limit.
- **Retrieving past conversation from Qdrant.** A past turn is a past state:
  "PO X is waiting for Bravo" was true yesterday. The answer must come from
  the case as it is now, which PostgreSQL holds; retrieving old answers is the
  way to state something stale with confidence. What a turn needs from the
  past is which case it is about, and the `focus` carries that exactly.
- **`dw_memory` for long-term memory.** It holds a workspace's facts with
  provenance and a review queue; no status question needs one, and a status
  kept there would be a second copy that drifts (failure-modes #2). It stays
  available for a person's preferences when one is asked for.
- **An agent with tools** (item 9's recorded design). On a 9B model, one
  classification into a closed schema is far more reliable than a tool loop,
  and the contract's criterion is a closed list.

## Consequences

- Every new kind of question is a `QuestionKind`, a resolver and a test, and
  the prompt's list grows with it: the catalog says exactly what DW1 answers.
- Two model calls per turn (about 10 s on Qwen3.5-9B); without a model the
  assistant still says it did not understand rather than guessing.
- Eval `sales_assistant@1.0.0` holds the four kinds, the session's focus,
  out-of-scope, prompt injection, another tenant's PO, and a model down.

## Addendum, 2026-11-06: the answer as it is written

Đạt asked that people see the words arrive, not wait for the whole sentence.
`POST /sales/assistant/ask/stream` (and DW2's) answers in Server-Sent Events;
`/assistant/ask` stays, reading the same stream to its end, so the two cannot
drift.

- **The check moves with the words.** Decision 3 kept a wording only when the
  whole of it passed, which a stream cannot wait for. `released` holds the
  provider's chunks until a word is whole and asks the same check of all the
  text so far before that word leaves, so what a person saw is always a prefix
  that passed. A word that fails stops the call (its one slot is freed) and
  `replace` puts code's sentence in the words' place; that sentence is what the
  turn keeps. Facts hold no amount, so what can flash on a screen is a figure
  the facts hold, never a price.
- **Same prompt, same schema.** The model still answers `{"answer": ...}`;
  `JsonStringField` reads the field as it arrives and the schema validates at
  the end. `sales.assistant_answer@1.0.0` and its eval do not change. The eval
  runs through `interpret`, not the stream; the stream's guards are held by
  unit tests and a mutation of each.
- **One attempt.** No retry and no fallback once words may be on a screen.
  Code's sentence is the fallback.
- **Refusals stay statuses.** The first event is taken before the response
  starts, and everything that refuses happens before it, so a 403 or a 404 is
  never a frame in a 200. After that a failure is one `error` frame in fixed
  words.
- **The spend ceiling still sees it.** Charged after the stream, a call cut
  short included, at an estimate when the provider reports no usage.
- **DW2 streams its steps only.** It words its answers itself, so nothing is
  written word by word there; what arrives as it goes is what it is doing.

Measured 2026-11-06: Qwen3.5-9B on the home lab's LM Studio, first word 0.45 s,
whole answer 1.2 s, warm; the real app and the repository's Caddyfile on
`caddy:2.11.7-alpine`, frames 0.4 s apart as written, and a client leaving
stopped the generator at once. FastAPI 0.141 runs a dependency's exit after a
streamed response, so `Idempotency-Key` is released or recorded when the turn
ends. `request_timing` logs the time to the first event, not the turn.

