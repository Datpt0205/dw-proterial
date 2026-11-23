# 43 — Every correction becomes an example; prompts and skills re-optimised on them

Status: in progress (2026-11-22): parts 1, 2 (dynamic few-shot, `description_attributes`), 3 (the optimiser, smallest version), the head's page, and a measured gain on Strata (examples as confirmed readings, prompt 1.2.0: 3/8 → 8/8 held-out lines) built; the second step (`po_body_extraction`) shown the customer's decided values (2026-11-22; no gain measurable on Strata, which reads every trap without them); which decided lines a reading saw stamped on it (2026-11-23). pending: re-attesting both steps on their new prompts on the plant (`--attest`, on the plant's Strata)
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

### A measured gain: examples as confirmed readings (2026-11-22)

- **The form**: a decided line whose reading code accepted, and whose kept
  item fits what that reading states, is shown as the reading itself, in
  the answer's own shape (`"read"`: each label with its span, each number
  as its span only; `description_reading.answer_of`). Every other decided
  line is shown as before, the kept item's attributes (`"item"`). Never a
  code. `model_reading.shown_lines` decides which, with `candidates`, the
  same function the reading's own candidates come from.
- **Where the reading comes from**: the order line's check basis
  (`description_reading`, stamped at intake), read with the labelled case
  under the same RLS (`SqlDescriptionExamples`); a reading code refused,
  or none, gives none. A tenant prompt version's demonstrations keep the
  reading too (`StoredDemonstration.spans`); the head's page lists them as
  before (`Demonstration`, without spans: the API contract is unchanged).
- **Prompt** `sales.description_attributes@1.2.0` (bundle 1.5.0): an example
  with `read` is the right answer for its words; one with `item` only says
  what the person chose. Its readings are stamped 1.2.0, so no threshold
  set on 1.1.0 gates them (ADR 0015).
- **Found by measuring, fixed**: a one-letter label inside a longer word
  ("R" beside "RL") was refused as `span_repeated`. A label's span found
  more than once now counts where exactly one place is a whole word; a
  number's never does (`verify_reading`).
- **Eval** `sales_description_examples@1.1.0`: decided lines carry the
  reading a person confirmed (verified by code when the fixture loads; d04
  stays item-only), plus two customers whose words no list holds (C005
  "TV ... MD TT CR", C006 "CNL ... LUOI DEN CR"); 8 held-out lines.
- **Measured on Strata** (Giang's home lab, `qwen3.8-flash-next-q2_0`, not
  attested), gold code among the candidates, no wrong single code anywhere:

  | Shown                         | Held-out lines right |
  | ----------------------------- | -------------------- |
  | no example                    | 3/8 (0.375)          |
  | examples as items (1.1.0 form)| 5/8 (0.625)          |
  | examples as readings (1.2.0)  | 8/8 (1.0), twice     |

  The item-only row is the same run with the `read` form switched off in
  code. Security cases held in every run (injection, missing evidence,
  cross tenant). Retrieval p95 under 1 ms (memory index). The recorded
  answers (`sales_desc_examples_recorded.json`) are the 1.2.0 run; the
  smoke's floor is the recorded gain, 0.625.
- **Mutation check**: 8 guards broken one at a time, each red: the whole-word
  rule (labels only; whole words only), the `read` form, its fit to the
  kept item, a number's field, a label's value, the adapter's reading (on
  PostgreSQL), the optimiser's spans.

### The second step: a PO in a mail (2026-11-22)

- **What an example is** (`application.po_body_examples`): one value Sales
  checked in the same customer's earlier mail PO, cut by code from that
  stored mail by its anchors (`domain.po_body_reading.written`), never from
  what the person typed: the text line, the field, and the words, `right`
  where the person kept the value as read, `wrong` where they corrected it
  (where the right words are, the person did not say, and DW does not
  guess). A value the mail never wrote (rule 4: the amount at the price, the
  date at the PO number, the unit at the quantity) is no example.
- **Which**: the sender's customer's newest decided values, at most six,
  newest decision per value only (`SqlPoBodyExamples`, PostgreSQL under the
  scope's RLS, the revision's mail with that one line from `order_lines`).
  No index: a customer's mails share how they are written, not what they
  are about.
- **The reading** (`PoBodyReader`, prompt `po_body_extraction@1.2.0`, bundle
  1.6.0): shown as untrusted `examples` beside the mail. Any failure reads
  without them; a mail that fits its room only without them is read without
  them, never refused for them.
- **Found and fixed (a defect of AI item 4, not of this ticket)**: a PO read
  from a mail body could never be stored on PostgreSQL. The baseline's
  `ck_order_revisions_attachment_id` required an attachment id, and a body
  PO has none, so intake's transaction was refused and the mail never became
  a case. Every earlier test ran on the memory store. Migration
  `4b3f44f30356` admits no id exactly when the document carries the mail it
  was read from; an integration test stores one and reads it back.
- **Eval** `sales_po_body_examples@1.0.0`: four mails of one customer written
  around the point (an apology, an earlier order's shortfall, a stock-take,
  an invoice question), with the traps the customer's own decided values
  settle: a reel length beside the quantity, the order day beside the day
  wanted in one line, an earlier PO's number first, rows in the customer's
  own unlabelled order (code / reels / metres / price / date). Plus an
  injection in an example's words, a mail with no price beside examples with
  prices, another tenant's values that teach the traps backwards.
- **Measured on Strata** (not attested): every value in the right field,
  without examples 1.0 and with them 1.0: **no gain, no loss**. Strata reads
  every trap here unaided; the mechanism ships for the cases production
  labels will show, and the eval's floor stays 0. Security cases held.
- **Seen in the run**: a mail whose two dates are both ≤ 12 ("10/11/2026",
  "01/12/2026") reads neither: the mail does not settle the order, and with
  no notation record for the customer the requested date goes to a person,
  as decided in the 11-13 audit. The fixture was changed to test its own
  trap instead.
- **Mutation check**: 9 guards broken one at a time, each red (an implied
  value, a failure, the room, one per line and field, at most six, a
  correction shown wrong, the newest decision, kept vs corrected, one
  customer's only).

### Which decided lines a reading saw (2026-11-23)

- **The stamp**: `DescriptionReading.examples`, the labelled case ids of
  the decided lines the call showed beside the line, in the order shown, at
  most `MAX_EXAMPLES_SHOWN` (12, owned by the domain; `examples.MAX_SHOWN`
  reads it) and each once. Only what the search found **and** the prompt
  showed: a line whose item left the list, or whose words were shown
  already, never reached the model and is not named; the tenant's prompt
  version's demonstrations are named by `prompt` already and are not
  repeated. An unavailable or refused reading is stamped too: the call
  carried them whatever came back. A quote's items are read by the same
  reader and stamped the same way.
- **Ids, not `examples_as_of`** (the research note's word): the search is
  by similarity, so a time alone does not say which lines came back, while
  the ids do, and stay true when the index or the embedder changes. The
  PO-in-mail step needs no stamp of its own: it is shown the customer's
  newest decided values, which the time of the reading already determines.
- **Who reads it**: the line's trail (ticket 62) says "đã xem N dòng đã
  quyết" on the model-reading step; the ids stay on the line's check basis
  for whoever asks why a line read as it did. The labelled case reaches
  them by its case and line, not by a copy.
- **Old cases**: a basis stored before the stamp has no key and reads as
  shown none (tested), though readings from 11-16 on did see examples.
- **API**: `TrailStepView.examples` (a count) and the quote item's
  `description_reading.examples` (ids: opaque, and nothing outside the
  head's page resolves a labelled case) are added; snapshot and TS types
  regenerated.
- **Deploy note**: `DescriptionReading` forbids unknown keys, so code from
  before this change cannot read a line stamped by it: rolling back past it
  needs the key stripped, as for `confidence` and `gate` before it.
- **Mutation check**: 8 guards broken one at a time, each red (no stamp,
  found but not shown, demonstrations named, a duplicate, no bound, no
  default for old rows, the trail's count, the page's words).

### Left

- **After deploy**: a step's bar is per prompt version, so
  `description_attributes` (1.2.0) and `po_body_extraction` (1.2.0) are not
  ready until the live lane is attested again on the plant model
  (`run_evals.py --dataset <the step's set> --live onprem --attest`).

