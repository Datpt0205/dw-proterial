# 56 — The case's assistant: chat first, tools for every effect, few refusals

Status: needs-triage
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

## Comments
