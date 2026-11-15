# 44 — Reversible steps apply themselves under a measured error rate, with sampling audits

Status: in progress (2026-11-16): the slice for `description_attributes` done end to end; the gaps under "Left" open
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

## Done

The slice, end to end, for one step (2026-11-16; migration `efc46a50e75e`):

- **Tiers in code**: `dw_sales.domain.autonomy.STEP_TIERS`, every `ModelStep`
  named (a test holds it total), `tier_of` returning `person_approves` for
  any step left out. T0: the readings, `po_body_extraction`, `reply_draft`;
  T1: `request_handoff`; T2: `layout_proposal` (an approval) and
  `change_request` (ADR 0010).
- **Targets and audit share are tenant config**: `sales_order_rules`
  `autonomy` (`applies_itself_error` <= 0.05, `hand_off_error` <= 0.02,
  `audit_share` >= 0.03; a tenant may only tighten), on the head's short list
  with one sentence each (`HEAD_SETTINGS_MAX` 10 -> 13), worded in
  `rule-labels.ts`.
- **Confidence from token log-probabilities**: `ModelRoute.logprobs`
  (on for `onprem`'s structured route, `onprem.yaml` 1.4.0), the
  OpenAI-compatible adapter's `complete_json_scored`, the gateway's
  `generate_structured_scored`, `ScoredInterpretationPort` and
  `dw_agent_runtime.model.scoring.value_confidences` (each JSON value's
  probability by path). `DescriptionReader` stamps the least probable label
  code took as `DescriptionReading.confidence`; no logprobs, no confidence,
  nothing applies. Tested on a fixture in Strata's measured response shape;
  no live call was made.
- **Threshold**: `conformal_threshold` (Learn-then-Test, fixed sequence,
  exact Clopper-Pearson bound, delta 0.05; 59/149/299 cases at 5/2/1%),
  `measure` per tenant + workspace, step, prompt and model profile; stored in
  `sales.step_thresholds` (RLS tenant AND workspace, FORCE, `dw_app` no
  DELETE) by the worker lane `sales_auto_apply` (hourly), with a lane audit
  row whenever a threshold or a stop moves.
- **Gate and shadow**: `OrderIntake._gated` stamps `DescriptionReading.gate`
  (`person` / `shadow` / `audit` / `applied`) on a model-read line with one
  candidate; the gate is copied onto the labelled case (with the confidence)
  and the step row (`sales.step_outcomes.gate`). `shadow` is what clears the
  threshold while the step's audits stop it.
- **Applying**: `AutoApply` after the case is opened (or revised), through
  `OrderIntake.confirm_mapping` as `system_actor("sales_auto_apply")`, a DW
  case event and a lane audit row; it refuses a `person_approves` step at the
  effect itself; it does not learn the code into the convert list.
- **Undo**: `POST /orders/{id}/lines/{n}/mapping/undo` ("Hoàn tác",
  `sales.order.prepare`), `OrderCase.undo_applied_mapping`, a labelled case
  `rejected` with gate `applied`.
- **Audits**: a sha256-of-the-item 3% (tenant config) goes to the case's PIC
  as an ordinary candidate (the served view carries no gate); the audited
  error (blind audits and every decision on an applied result) whose exact
  lower bound passes the target stops the step until a new prompt or model
  profile is measured from the start.
- **Web**: "DW đã tự làm" + "Hoàn tác" on the order's lines; "DW tự làm" on
  the activity page (`GET /activity/autonomy`): per step its mode, applied
  and sent-to-a-person counts over 30 days, the threshold, cases, target and
  audited error on click.

## Left

- **A person cannot reject a single candidate today** (the picker only
  confirms it). So for `description_attributes` a person's verdict on a
  one-candidate line is almost always "confirmed", and a blind audit cannot
  find an error either: the measured error is optimistic until the picker
  gets "Không phải mã này" (a labelled case `rejected`). The undo counts
  against the step (fail closed) meanwhile. Decide before a tenant's
  threshold is trusted.
- Every other T0/T1 step: no score, no effect path; each needs the scored
  call and its own `AutoApply` effect (`po_body_extraction` next).
- A live check on Strata of `logprobs` through the adapter.
- The thresholds use the labelled cases' 365-day window whole; once a step
  applies, its high-confidence region gets labels only from audits and
  undos (the research note's "labels for the region"): weighting audits by
  their share is the principled fix if the threshold drifts.
- `order_artifacts`' "who confirmed" line names the lane's id for an applied
  code (no person behind it).
