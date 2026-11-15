# 43 — Every correction becomes an example; prompts and skills re-optimised on them

Status: in progress (2026-11-15): part 1, the labelled-cases store and its writers, done; parts 2 (dynamic few-shot) and 3 (scheduled optimisation) open
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

## Done

Part 1, the corrections store (2026-11-15). Parts 2 and 3 are open: the
retrieval waits on the Qdrant review, and the optimiser after it.

- **`sales.labelled_cases`** (migration `eac4fabdb31a`): one row per item a
  person decided on a model step's proposal: the step, lane, case, customer,
  message, attachment, line and field (the input by reference, never the
  mail's text), the proposal and the value kept as JSON (at most 16 KB each),
  the verdict, the prompt / model profile / rules versions, who and when.
  Tenant AND workspace RLS with the offboarding scope, ENABLEd and FORCEd on
  parent and DEFAULT; append-only for `dw_app` (UPDATE/DELETE revoked);
  range-partitioned by month, named last in `ensure_time_partitions`;
  retention 365 days (`retention@1.12.0`, `sales.drop_expired_labelled_cases`,
  worker lane `sales_labelled_cases_retention`); FKs to tenant and workspace
  `ON DELETE CASCADE`; indexes led by `tenant_id` for a step's newest and one
  customer's.
- **Not a column of `sales.step_outcomes`**: that row is written when the
  step runs, in the intake's transaction, holds no value by design
  (`ck_step_outcomes_refusals`) and takes no UPDATE; a decision comes later in
  another transaction and its point is the two values.
- **One rule for the verdict**: `dw_sales.domain.labelled_cases.verdict_of`
  (nothing kept = rejected, the proposal kept = confirmed, else corrected),
  and `ck_labelled_cases_verdict` holds the table to the same rule.
- **One writer per step**, each in the transaction of the decision, after its
  case event and audit rows: `OrderCommands.confirm_mapping`
  (`description_attributes`: candidates from a model reading vs the code
  kept), `OrderCommands.correct_value` (`po_body_extraction`, a `model_read`
  value vs the one typed, compared as the field's type),
  `QuoteCommands.answer_finding` (`rfq_extraction`, each value confirmed, "as
  read" one case per value), `ChangeRequests.confirm` / `.reject`
  (`change_request`, a line the model read), `LayoutService.propose`
  (`layout_proposal`, the pre-filled mapping vs the one proposed). A value a
  code reader gave, a convert-list line, a table's or a person's change line
  writes none.
- **Read port** `LabelledCaseReadPort` (`latest` per step, newest first, one
  customer's; `counts` per step by verdict): `SqlLabelledCaseReader`, and
  `MemoryStore` in the eval world.
- **Head's view**: `GET /api/v1/sales/activity/labels` (the activity
  summary's gate), "Kết quả người đã kiểm" on the activity page: per checked
  step the count and the share kept as proposed; the split on click.
- Not stored: a confidence. No adapter asks Strata for `logprobs` yet, so the
  column comes with the change that does (ticket 44). No shadow-decision
  field: ticket 44 adds it with its writer.
- Not labelled yet, each a gap for a later pass: reply intents
  (`reply_intent`/`thread_agent`/`skill_intents`: no person confirms a
  reading today, only the step they take), `message_intent` and
  `request_handoff` (no decision on them), the design reply, sender customer
  and PC dates readings (not `ModelStep`s, and their proposal is never
  stored), reply drafts (nothing records used or discarded), and a person
  superseding a layout DW1 learned by itself.
