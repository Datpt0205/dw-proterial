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

## Method (from the research note, 2026-11-16)

`docs/research/2026-11-16-less-human-review.md`: the threshold is set by
conformal risk control on the tenant's labelled results, so the error rate
among what applies itself stays at or below α even if the model's
confidence is poorly calibrated (a weak score only lowers the share that
applies itself). Confidence from token probabilities and agreement across
samples (Strata returns both cheaply, measured). Three tiers: T0 reading,
classifying, linking, unsent drafts; T1 an internal hand-off or a move into
someone's queue, at a stricter α; T2 anything sent, any Bravo write, prices,
dates, approvals, never automatic. Certifying α with no errors takes about
59 accepted cases for 5%, 149 for 2%, 299 for 1%; until a step has them it
runs in shadow mode (decides and logs, applies nothing). Any new model,
prompt, skill or example set turns automatic application off until
re-measured. The missing data today is the model's proposal stored beside
what the person kept: ticket 43 starts there.

## Decided 2026-11-16 (Đạt: "cứ làm theo đề xuất")

With his conditions: DW must take work off people, never add errors for
people to catch; follow the state of the art; let the model improve itself
from real runs where it can; keep latency.

1. **α per tier** as the note suggests, tenant configuration with these
   platform defaults: T0 5%, T1 2%, T2 never automatic. A tenant may only
   tighten them on the head's screen; loosening is a platform change.
2. **Tiers**: T0 reading, classifying, linking a mail to a case, unsent
   drafts, reminders; T1 an internal hand-off (PC, QA, Design) or a move into
   someone's queue; T2 anything sent, any Bravo write, prices, dates given to
   a customer, approvals.
3. **Audits**: a 3% blind sample of what applied itself (more while a step
   is new), audited by the PIC who owns the case; an audited error rate above
   α stops the step.
4. **Shadow mode** until a step has the labelled cases its α needs (59 at
   5%, 149 at 2%): it decides and logs, applies nothing.
5. **The skill is chosen by one constrained, scored call** (a JSON-schema
   enum of the tenant's skills, with the token probabilities as its score),
   not by the agent's free choice: amends ADR 0014 decision 1. Tools stay
   for the facts a reading lacks.
6. **Self-improvement from real runs**: every confirmation and correction
   is a labelled case (ticket 43); similar corrected cases are retrieved as
   examples; an offline optimiser (GEPA/MIPROv2 class) proposes new
   prompt/skill versions weekly, replayed on every labelled case and approved
   by the head; thresholds are re-set nightly from the labelled cases.
7. **Latency**: nothing slow sits on the path a mail takes. Retrieval of
   examples is one vector search, top few, in the tenant's own collection;
   extra samples are drawn only for a borderline result (adaptive), in
   parallel (Strata serves concurrent requests, measured); optimisation and
   threshold setting run in the worker, off the request path. A step whose
   p95 grows beyond its budget is reported like a failed bar.

## Open

- Decided above. Left: the latency budget per step (proposed: p95 at most
  twice its measured one-call p95 on Strata).

## Addendum 2026-11-24: shadow for a step that is off (ticket 67)

Đạt, 2026-11-24: "làm theo đề xuất, bắt đầu cơ chế shadow dùng chung đi".
Decision 4's shadow mode existed only inside a step that was on (a result
cleared its threshold while the step was stopped). A step that is off, or on
and not yet attested, never ran, so no person's decision ever labelled it,
and the plant's real mail measured nothing. 18 of 19 steps sat there.

Decided:

1. **A third state per step**: `model_assist.shadow` lists the steps that
   read while they are not on and passing, wherever a model is configured
   for them. A reading in shadow is kept (`sales.shadow_readings`) and
   applied nowhere, shown nowhere. The tenant chooses: it costs model calls.
2. **The person's decision labels it**: where the person makes the decision
   the step would have proposed, the step's own service takes the reading
   (deleted as it is labelled) and writes a labelled case gated ``shadow``
   in the decision's transaction. Those labels count toward the step's
   threshold and the head's view like any gated result's, so a step can
   earn its threshold on real work before it is ever turned on.
3. **One engine, two lines per step**: where it reads, and where the person
   decides. A step is listed as shadow-capable (`SHADOW_STEPS`) only with
   both; the rules refuse any other.
4. **Bounded**: a reading no one decides is dropped after `SHADOW_KEPT_FOR`
   (60 days) by the `sales_shadow_retention` lane.

First step: `description_attributes`. Next: reply reading (two readers on
the same message, labelled by the step Sales takes), `message_intent`,
`po_body_extraction`.
