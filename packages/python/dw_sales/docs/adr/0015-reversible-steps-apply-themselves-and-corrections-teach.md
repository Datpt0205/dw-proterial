---
status: Accepted
date: 2026-11-16
accepted: 2026-11-16 (Đạt: "hướng này khá hay nên làm", "đề xuất này làm đi")
supersedes: "HITL at every step" for reversible steps; the 2026-11-04 hold on relaxing HITL before the plant survey
---

# Reversible steps apply themselves under a measured error rate; every correction teaches

## Context

Đạt, 2026-11-16: the goal is to reduce people's work. A design where every
step the model may be unsure of goes to a person does not do that, and he has
no time for the code to keep changing.

Today each model step's output is verified by code (quotes located, figures
matched, schema) and gated per step by a measured bar, but once a step is on,
almost every result is still a proposal a person confirms. A step at 95% still
costs a person 100% of the checks. And a person's correction fixes that one
case only: nothing learns from it.

## Decision

1. **Two tiers, by whether the effect can be undone.**
   - **Applies itself** (reversible, inside DW): reading and classifying a
     mail, linking it to a case, reading a PO or a reply, drafting, reminders,
     moving a case along a move the state machine allows. Each such
     application is recorded, shown, and undoable by a person.
   - **A person approves** (irreversible or outside DW): a Bravo write (ADR
     0026), anything sent outside (DW still never sends mail), money and price
     decisions, approvals.
2. **A result applies itself only when** every code check passes **and** its
   confidence clears the step's threshold, and the threshold is set from
   labelled cases so that the step's error rate on what it applies stays at or
   below the tenant's target (the method is the research note's,
   `docs/research/2026-11-16-less-human-review.md`). Below the threshold, or
   with any check failing, it goes to a person as today. A step with too few
   labelled cases to set a threshold applies nothing by itself.
3. **The target error rate is tenant configuration**, per step tier, with a
   conservative platform default; the head sees it as one sentence on the
   settings screen (ticket 35).
4. **Sampling audits replace checking everything.** A share of what applied
   itself goes to a person to confirm; the observed error rate is tracked per
   step, and a step whose audited error rate exceeds its target stops applying
   itself until re-measured (fail closed).
5. **Every correction teaches, without a code change.** A person's correction
   (or confirmation) is stored with the input, the model's answer and the
   right answer, scoped to the tenant (and the customer where it is the
   customer's). Similar past corrected cases are retrieved as examples for the
   next reading (dynamic few-shot), and on a schedule the step's prompt or
   skill is re-optimised on the corrected cases and proposed as a new version,
   replayed on every labelled case, approved by the head, never applied
   directly. The same labelled cases set and re-check the thresholds in 2.
6. **Guards stay code** (ADR 0014 decision 3): tenant and customer binding,
   authorization, quote/figure/schema checks, the state machine's legal moves.
   A correction or an optimised prompt can change wording and examples, never
   a tool, scope, recipient, number or move.

## Consequences

- People see the residual and the audit sample, not every result.
- Accuracy now rests on the labelled cases being honest and recent: the
  audit is what keeps them so, and it cannot be switched off for a step that
  applies itself.
- Tickets 43 (corrections as examples and optimisation) and 44 (the tiers,
  thresholds and audits) build this after ticket 40, on the research note's
  method.

## Open

- Đạt: the target error rate per tier (proposed default: none applies until
  set; then for example 1% for reading and linking, 2% for drafts).
- The audit share per step (proposed: 10% at first, lower once stable).
