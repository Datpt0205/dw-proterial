# 56 — The case's assistant: chat first, tools for every effect, few refusals

Status: in-progress — slice 1 done 2026-11-21 (a flag decided in the case chat, confirmed by hash); left: the other effects as tools (a reversible step with undo, a mail to the customer, a Bravo write once ticket 49/51 allow), the short system prompt with retrieved examples (ticket 57), a quote's flags
Blocked by: 46 (a conversation per case), 40/41 (skills, tools)
Category: enhancement

## Why

Đạt, 11-20:

- pressing buttons on the portal feels worse than chatting;
- the chat must feel like AI and not refuse often, while guardrails and
  prompt-injection defences stay strict;
- upgrades must not depend on ever-longer prompts.

Each case already has its own conversation (ticket 46), which keeps the
context small.

## Shape

- **Free talk, bound effects.** The model talks freely: it answers, explains,
  summarises and drafts. Every effect is a tool call on that case only. Code
  binds the case, customer, tenant and approver; the model never chooses them.
- **Risk tiers (ADR 0015).**
  - Reads are free.
  - Small reversible steps apply with a one-line note and an undo.
  - Bravo writes, mail to a customer and exceptions are stated by the model
    and confirmed by the PIC in the chat, by a sentence or one tap on an
    in-chat suggestion. The confirmation is bound to the content hash.
- **When unsure,** the model asks one natural question with its best guess.
  It never gives a bare refusal. It refuses only what is not allowed: another
  case, another customer, another tenant, or a right the PIC lacks.
- **Short system prompt:** role, tone, "act through tools, ask when unsure".
  Everything else lives elsewhere:
  - rules and thresholds in tool code and Bravo's data;
  - how-to in skills, loaded only for the step at hand;
  - the case's state in a short card that code builds;
  - 2–3 examples picked from corrected real replies (ticket 57);
  - the shape of the output in tool schemas.
- **Untrusted content** is wrapped (ADR 0010), and text is released only after
  its check.

## Acceptance

1. The eval (ticket 57) passes its bar, including the injection and wrong-case
   attacks.
2. No tool can reach another case (negative test).

## Done: slice 1, a flag's decision confirmed in the case chat (2026-11-21)

The first effect through the chat, chosen because Đạt's 11-20 rule sends
every exception to the case's PIC in the case chat: a decision on one of
the case's open flags (accept with a reason, or ask the customer to correct
the PO).

- **The model reads, code binds.** `sales.question_intent@1.2.0` adds
  `decide_finding` with `finding_code`, `decision` and `reason`; it is shown
  FLAGS, the bound case's open flags (codes and lines only, wrapped as data).
  Code resolves the code among those open flags; a code the case does not
  hold open, two of a kind, a decision the flag does not allow, or an accept
  with no reason is answered with the one question that lets DW1 go on
  (copy `sales_assistant@1.2.0`), never a bare refusal and never a guess.
- **Said, then confirmed.** The turn keeps a `ProposedDecision` (case,
  version, flag key, decision, reason) and its SHA-256 over those; the chat
  shows the sentence, the case's version and the hash's head, and a
  "Xác nhận" button. `POST /assistant/cases/{kind}/{case_id}/turns/{seq}/confirm`
  takes only the hash: the decision recorded is the stored turn's, through
  `OrderCommands.dispose` (the page's own command, scope and version check),
  as the confirming person. A wrong hash, a case moved since, a flag no
  longer open, another person's turn, another case's route, another tenant:
  nothing recorded. A person who may not prepare the order is stated nothing.
- **Store:** migration `3187714cd75c` admits `decide_finding` and adds
  `assistant_turns.proposal` (jsonb), CHECKed to an object on a
  `decide_finding` turn only; the CHECK caught JSON `null` written for "no
  proposal", fixed with `none_as_null`.
- **Web:** the chat draws the confirmation under the turn
  (`ProposalConfirm`); once recorded, the button is disabled and the order
  page reloads (`useCaseChatDecided`).
- **Another PO named in this case's chat** (found writing ticket 57's
  wrong-case set): DW1 points to that case and states nothing, rather than
  take this case's flag.
- **Tests:** `test_case_decisions.py` (11, the negatives above), the DB
  round trip and CHECK in `test_assistant_sessions_db.py`, `case-chat.test.tsx`
  (nothing sent before the press, the hash sent, the page reloaded, not sent
  twice). Mutation check: the hash binding, the scope gate, the open-flag
  resolution and the reason rule each broken, each red.
- **Security review** (`reviewing-feature-security`): tenant isolation and
  the person's own conversation (RLS, `_held`, negative tests); authority
  stays the command's; the new reach is "a PIC records a flag decision from
  the chat after confirming DW1's exact statement"; model output never names
  the case or the flag; the decision and its audit are the command's one
  transaction. Not yet measured live on a model: ticket 57.

## Comments
