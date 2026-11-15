# 44 — Reversible steps apply themselves under a measured error rate, with sampling audits

Status: ready-for-agent (after 43 has labelled cases; the method from the research note)
Blocked by: 40, 43
Category: enhancement

## Why

dw_sales ADR 0015 decisions 1–4 (Đạt, 2026-11-16): reduce people's work;
irreversible effects keep a person.

## Shape

- **Tiers in code**: every step declares its tier, `applies_itself`
  (reading, classifying, linking, drafting, reminders, legal state moves) or
  `person_approves` (Bravo writes, anything sent, price, approvals). A step
  with no tier is `person_approves` (fail closed).
- **Confidence and threshold** per step by the research note's method, set
  from the labelled cases (ticket 43) for the tenant's target error rate; too
  few cases, no threshold, nothing applies itself.
- **Applying**: a result whose code checks pass and whose confidence clears
  the threshold is applied, recorded as applied by DW (the lane audits as
  itself, ADR 0011), shown, and undoable by a person; otherwise it goes to a
  person as today.
- **Audits**: a share of applied results goes to a person to confirm; each
  confirmation or correction is a labelled case (ticket 43). The audited error
  rate per step is tracked; above its target the step stops applying itself
  until re-measured.
- **Settings**: the target error rate per tier and the audit share are tenant
  config on the head's screen with one sentence each (ticket 35).
- **Web**: "DW đã tự làm" with undo; the audit queue; per step, applied vs
  sent to a person and the audited error rate. Less text, detail on click.

## Acceptance

1. A `person_approves` step never applies itself, whatever its confidence
   (negative test at the effect, not only the router).
2. A step without enough labelled cases applies nothing by itself.
3. A step whose audited error rate exceeds its target stops applying itself.
4. Every applied result can be undone, and the undo is a labelled case.
5. Cross-tenant: one tenant's thresholds, cases and audits never read
   another's.
