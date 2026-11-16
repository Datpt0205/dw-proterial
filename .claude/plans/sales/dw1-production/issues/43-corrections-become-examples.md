# 43 — Every correction becomes an example; prompts and skills re-optimised on them

Status: in progress (2026-11-16): parts 1, 2 (dynamic few-shot, `description_attributes`), 3 (the optimiser, smallest version) and the head's page for a proposed prompt version built; left: a second step, a measured gain (none reliable on the dev model), re-attesting the step on prompt 1.1.0 on the plant
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

### Part 2, dynamic few-shot (2026-11-16)

- **The step**: `description_attributes`. It has the most labelled cases (one
  per line Sales settles, `po_body_extraction` one per field typed over), its
  input is one short line (cheap to embed and to show), and its eval scores
  the gold code per line.
- **The index** (`dw_knowledge.examples.ExampleGateway`, the knowledge
  gateway's second door): one Qdrant collection `dw_examples__<model>__1`
  (`adapters/qdrant_examples.py`; `adapters/memory_examples.py` for tests,
  evals and a worker with no Qdrant). A point is a vector and the filter
  fields only (tenant `is_tenant`, workspace, step, subject = customer,
  group = order case, decided_at): no text. The filter (tenant, workspace,
  step) is built in the gateway from the caller's scope (the run's); the
  customer's cases first, then the tenant's, one batched round trip; a
  held-out order never. Dense only (BM25 needs stored text). Bounded by a 2 s
  timeout; every failure raises to the caller.
- **What an example is** (`dw_sales.application.examples`): a labelled case
  of the step whose newest decision on its line kept a code (confirmed or
  corrected; never a rejection, never an unconfirmed answer), its description
  read back from the order line under RLS (`SqlDescriptionExamples`, joined
  through the revision the case names); a code no longer in the item list is
  not shown. Shown as the description and the kept item's attributes from the
  item master, never the code (`model_reading.shown_lines`), at most 12 per
  call.
- **The reading** (`DescriptionReader`, prompt
  `sales.description_attributes@1.1.0`, variable `examples`, contained like
  `lines`; no `raw_variables`): the order's customer and the tenant's k
  (`sales_order_rules.learning.examples_per_line`, default 3, 0 off; placed
  on the process page). Any failure (embedder, index, read) is a reading
  without examples, logged by error type. `prompt_bundle_version` 1.4.0.
- **Filled by the worker**: lane `sales_examples` (every 5 min, every
  workspace with Sales cases), keyset from the last indexed case, skipping
  what the index holds; then drops points older than the labelled cases'
  retention cutoff. Offboarding deletes a tenant's points
  (`TenantOffboardingLane.example_vectors`). Wired in the worker only (the
  process that reads mail); the API's readings show none.
- **Latency**: one `similar` call for ten lines (20 searches in one batch) on
  the local Qdrant 1.20, 2 x 1,000 points at 1024 wide: p50 32 ms, p95 46 ms,
  max 60 ms (hash embedder: the index's share only; bge-m3's own was not
  measurable here, no server).
- **Eval** `evals/datasets/sales_description_examples@1.0.0.json` (graders in
  `dw_sales.evals.examples`, the index composed at `scripts/run_evals.py`):
  six held-out lines in three customers' own shorthand, read without and with
  examples; every reading shown its customer's decided line (1.0); injection
  inside an example's text (escaped in its block, the named code never a
  candidate); a line stating nothing beside its customer's examples stays
  with a person; another tenant's decided lines (one with the very words of a
  held-out line) never shown, at the index or at the reading. **Gain: none
  reliable.** On the dev model (Ollama qwen3.5-9b-dw, the onprem profile
  pointed at it): gold among candidates 0/6 without examples in every run;
  with them 0/6 on the first wording of 1.1.0, then 1/6 and 0/6 on the
  final one. Shown an item's attributes, the model copied them without spans
  and code refused them (`no_attribute`, `text_uncovered`): no wrong code,
  no gain. The recorded answers (`sales_desc_examples_recorded.json`) are
  the last 0/6 run. The step's own golden set on 1.1.0 (examples empty), same
  dev model, run back to back with 1.0.0: VI/EN gold among candidates
  0.756 on both (34 of 45 read, none wrong; bar 0.70 met), so the new
  wording costs nothing with no example to show. (The 0.933 of the older
  live report was another day's run of the same model.)

### Part 3, the optimiser (2026-11-16)

- **Lane** `sales_prompt_optimiser` (daily, every workspace with Sales cases,
  only where the worker reaches a model server):
  `dw_sales.application.prompt_optimiser.PromptOptimiser`. Runs only where
  the step runs (rules and bar), with the step's eval security cases loaded
  (`evals/fixtures/cases/sales_descriptions_security.json`, shipped in the
  worker image), no proposal waiting, and at least
  `learning.new_cases_to_retrain` (default 50, at least 20) lines decided
  since the last proposal.
- **Method**: MIPROv2's bootstrapped demonstrations only, no instruction
  rewrite (no model writes words a reading then obeys); no DSPy. Two
  candidate sets of at most 6 distinct lines: the newest per customer, and
  the lines the version in force reads wrong. Each replayed on every decided
  line (at most 1,000), one call per order, never shown its own order's
  lines, graded right / listed / missed; and on every security case of the
  step's eval.
- **Proposed only if** no line reads worse, more read right in total, and
  every security case holds; a replay with any unanswered call proposes
  nothing. Proposed as a rule version of `sales_prompt_description_attributes`
  (migration `137ec1972538` widens `ck_rule_versions_key`) on a
  `sales.prompts` approval (`dw_sales.application.prompt_versions`): proposer
  the lane's system actor, decided by a holder of `sales.rules.approve` who is
  not the proposer (`PromptDecisions`, registered in `graph.register`),
  carried out by the worker (`PROMPTS_DECIDED`). The document holds the
  demonstrations (description and kept code) and the replay counts.
- **Resolved per run** (`PromptBook`, `TenantOverlay` through `RuleBook`): the
  tenant's approved demonstrations are shown before the nearest examples. A
  reading under a tenant version is stamped
  `sales.description_attributes.tenant_<version>@1.1.0`, so a threshold set
  under one set of demonstrations never gates another (ADR 0015: re-measure).
- Acceptance 4 holds: a new decided line is indexed and shown, and counts
  towards the next proposal, with no code change.

### The head's page (2026-11-16)

- **`GET /api/v1/sales/prompts`** (`PromptVersionsService`, read only): the
  platform prompt the versions add to, the version in force (layer and the
  decided lines it shows) and every version of the tenant's, newest first,
  with its replay counts, decision and approval. Gated on
  `sales.rules.approve` at the route and in the service (a PIC and tenant IT
  get 403: the lines carry customers' words); rule versions are narrowed by
  tenant RLS, so another tenant's head lists none. No route proposes or
  decides: the decision stays the `sales.prompts` approval on `/approvals`
  (two-person rule, idempotency key, audit `sales.prompts.*`), carried out
  by the worker.
- **Which corrections**: a `Demonstration` now keeps the decided line it was
  taken from (`label_id`, `case_id`, `customer_code`, optional so older
  documents read), filled by the optimiser; never shown to a reading
  (`shown_lines` reads description and code only; a unit test asserts none
  of them reaches the model).
- **Web**: `/sales/rules/prompts` ("Lời nhắc DW1 học", linked from the rules
  page for the head): one row per version, its status, "Đọc đúng a/n dòng
  đã quyết (bản đang dùng: b/n) · Qua cả k ca bảo mật"; opened, a waiting
  one shows the lines it adds, drops and keeps against the version in
  force, each with its customer and a link to the order, and "Mở phê
  duyệt". The same comparison is drawn under the approval on `/approvals`
  (`PromptApprovalChanges`), where the inbox now decides `sales.prompts`
  itself instead of linking to `/sales`. Audit labels for the three
  actions and the lane.
- The "golden set" the score is measured on is the tenant's decided lines
  (the labelled cases) plus the step's eval security cases: the eval's own
  golden set maps against a synthetic item master, where a tenant's
  demonstrations name codes that do not exist.

### Left

- A measured gain: the example form (description + the kept item's
  attributes) taught the dev model little; showing the confirmed reading's
  own spans as the example (a confirmed line's reading is a right answer
  word by word) is the next thing to try, then measure on Strata.
- **After deploy**: the step's bar is per prompt version, so
  `description_attributes` is not ready on 1.1.0 until the live lane is
  attested again on the plant model (`run_evals.py --dataset
  evals/datasets/sales_descriptions@1.0.0.json --live onprem --attest`).
- A second step (`po_body_extraction`), and stamping which examples a
  reading was shown (`examples_as_of`).

