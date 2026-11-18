# 44 — Reversible steps apply themselves under a measured error rate, with sampling audits

Status: in progress (2026-11-16): the slice for `description_attributes` done end to end, a person can reject a model's candidates; the gaps under "Left" open
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

Follow-up (2026-11-16, uncommitted until reviewed):

- **"Không phải mã này"**: `POST /orders/{id}/lines/{n}/mapping/reject`
  (`sales.order.prepare`, the case version seen, case event
  `order.mapping_rejected`, audit row), `OrderCommands.reject_candidates`,
  `OrderIntake.reject_candidates`, `OrderCase.reject_candidates`. The rule a
  line now follows: candidates a model's reading proposed (`candidate` or
  `ambiguous`, reading `read`) may be rejected, all together; the line is
  then `unmapped` and keeps nothing of the reading (no candidate, no
  reading, no stated attributes), its item findings go and `code_unmapped`
  opens, every other finding keeps its decision; it then takes what any
  unmapped line takes, a PRV code the item master holds, typed by Sales.
  Candidates from DW1's own vocabulary or the convert list are not rejected
  this way, nor is a confirmed code (DW's own is undone first). The
  rejection is a labelled case `rejected` (`mapping_label` with nothing
  kept); the code then typed labels nothing a second time (the line holds no
  reading). Picker button in `candidate-picker.tsx`, which then stays open
  for the typed code; glossary entry "Model reading" in `CONTEXT.md`.
- `apps/api/tests/integration/test_sales_api_access.py` walks every route
  again: the params the router gained since (`request_id`, `seq`,
  `notification_id`, `name`, `example_id`), and tenant IT's reach now lists
  the skills routes (`sales.rules.propose`, ADR 0014).

## Left

- A line undone ("Hoàn tác") and then rejected is labelled twice, both
  `rejected` with gate `applied` (as undo then confirm is two cases): the
  audited error counts that item twice, which can only stop a step sooner.
- "Việc cần làm"'s inline row decides through `OrderActions`, which holds
  no code picker: a line's code is still picked (or rejected) on the case
  page, which the row links to.
- The release manifest is stale and was not regenerated here (ticket 43's
  uncommitted prompt `description_attributes@1.1.0` would be pinned with it).
- Every other T0/T1 step: no score, no effect path; each needs the scored
  call and its own `AutoApply` effect (`po_body_extraction` next).
- A live check on Strata of `logprobs` through the adapter.
- The thresholds use the labelled cases' 365-day window whole; once a step
  applies, its high-confidence region gets labels only from audits and
  undos (the research note's "labels for the region"): weighting audits by
  their share is the principled fix if the threshold drifts.
- `order_artifacts`' "who confirmed" line names the lane's id for an applied
  code (no person behind it).

## Decided: a PO written in the mail (Đạt, 2026-11-18, "1 theo đề xuất")

Which values of `po_body_extraction` may apply themselves, each only when
the gate lets it (its confidence clears the step's certified threshold for
the prompt and model profile, the step is not stopped, the value was not
sampled for the audit), and never before a threshold is measured on Strata:

- **The PO's own values** (`po_no`, `revision`, `po_date`, `currency`,
  `delivery_term`): where code found the value's words in the mail (every
  value read is) and no open finding other than its own `value_uncertain`
  concerns the field (a currency or term the customer's master data
  disagrees with stays a person's).
- **A line's `unit_price` and `quantity`**: only where they equal the linked
  quote's or the master's exactly (no price finding open on the line).
- **Everything else** (a line's code, description, unit, dates; the total):
  a person's, as today (fail closed until decided otherwise).
- Applying a value is DW recording the read value as Sales would (the
  `value_uncertain` finding settled with that value), as the lane, undoable,
  the undo a labelled case.

## Done: a PO in the mail, slice 1, measured before it acts (2026-11-18)

- `PoBodyReader` asks the scored call where the model can score
  (`ScoredInterpretationPort`), as `DescriptionReader` does.
- `read_po_body(confidences=, model_profile=)` stamps each `model_read`
  flag's `FlaggedValue.confidence` with its own span's probability
  (`lines.k.<field>_span`; the revision is the PO number's span, a line's
  number its `line_span`, the total `total_span`), and `PoDocument.model_profile`.
- `po_value_label` carries both, so every value Sales settles from now on is
  a labelled case the step's threshold can be measured on (it had
  `model_profile=None` and no confidence: none of them could have counted).
- Nothing applies itself yet. Tests: `test_po_body.py` (scores by span, none
  without token probabilities, the reader asks the scored call),
  `test_labelled_cases.py` (the label carries the confidence; red with it
  dropped).

Left for slice 2: the eligibility rule above in the domain, the gate per
value at intake (`autonomy.route`, item key per message, line and field),
the `AutoApply` effect (refused at the effect for a person-approved step and
for a field the rule excludes), "Hoàn tác" and "DW đã tự làm" on the order's
values, and a live check that Strata's tokens score these spans (`--live
onprem` on `sales_po_body`).
