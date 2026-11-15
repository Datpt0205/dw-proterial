# 43 — Every correction becomes an example; prompts and skills re-optimised on them

Status: ready-for-agent (after 40 and the research note)
Blocked by: 40
Category: enhancement

## Why

dw_sales ADR 0015 decision 5 (Đạt, 2026-11-16). Method:
`docs/research/2026-11-16-less-human-review.md`.

## Shape

- **A corrections store**: per tenant (and customer where the case is a
  customer's), per step: the input (or a reference to it), the model's
  answer, the right answer, who decided and when. Written wherever a person
  confirms, corrects or rejects a model's result today (one writer per step,
  through the step's existing service); RLS, FORCE, grants; retention set.
- **Dynamic few-shot**: a step's reading retrieves the most similar
  corrected cases of the same tenant (and customer) and passes them as
  examples, wrapped as untrusted input like every interpolated value; never
  another tenant's.
- **Optimisation on a schedule**: a worker lane re-optimises a step's prompt
  or skill on its corrected cases (the method the research note picks),
  replays it on every labelled case, and proposes a new version only if it is
  better and breaks no security case; the head approves, never applied
  directly.
- The labelled cases are the ones ticket 44 sets thresholds on.

## Acceptance

1. A correction on one tenant never appears as an example for another
   (negative test).
2. A step reading a case like a corrected one gets that correction as an
   example, and the eval shows the gain on held-out cases.
3. An optimised version that is worse on any labelled case or fails a
   security case is never proposed.
4. No code change is needed for a step to learn from new corrections.
