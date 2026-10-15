# 28 — A model reads a free-text item description into typed attributes; code finds the PRV code, Sales confirms

Status: done (2026-10-13, committed in 61a5ae5; built by the agent with Đạt
away, on his pre-authorisation). O2 only; Q1 deferred (Comments). Meets
Đạt's bar on VI/EN (71.1% against 70%, set 2026-10-15). dw_sales ADR 0005
accepted by Đạt on 2026-10-14.
Blocked by: — (the shared model prerequisites were built with it; the
convert-list seed from Bravo history still waits on Proterial's data)
Category: enhancement

Candidate C2 in `../ai-automation.md`, priority 1. Steps O2 (PRV code
mapping) and Q1 (RFQ lines).

## What

**Today.** `domain/descriptions.py` reads a description only in the mock
customers' English word order and vocabulary. A word outside the vocabulary
returns `None`, so the line raises `code_unmapped` and Sales looks the PRV
code up by hand or asks Design. It runs for every line whose customer code
is not in the convert list, so the work recurs per line, not per customer.

**What the model produces.** One structured call per document, over the
descriptions code could not read. Per line (keyed by the line number code
sent; an unknown number refuses the whole output):

```text
DescriptionReading {
  line_no: int
  family?:    {value: ItemFamily, span: str}
  stranding?: {value: Stranding,  span: str}
  conductor?: {value: Conductor,  span: str}
  shield?:    {value: Shield,     span: str}
  colour?:    {value: Colour,     span: str}
  packaging?: {value: Packaging,  span: str}
  cores_span?, gauge_span?, pack_length_span?, spec_no_span?: str
}
```

The categorical values come from the `Literal` sets in `domain/catalog.py`.
The numeric and free-string attributes are span text only: the model never
gives their value. It never emits a PRV code, a customer code or a candidate
choice. Fictional example: `2芯 AWG24 黒 撚線 305M リール` reads as cores span
`2芯`, gauge span `AWG24`, colour `black` from `黒`, stranding `stranded`
from `撚線`, pack length span `305M`, packaging `reel` from `リール`.

**What code verifies**, in a pure domain function, before `candidates()`:

1. Each span is located by code in the NFKC-normalised description, and must
   occur exactly once. Not found, found twice, or overlapping another span:
   the line is not understood. A substring test alone proves nothing for a
   short token such as `2` or `M`.
2. Cores, gauge, pack length and spec number are re-parsed from their span by
   deterministic parsers (full-width digits included). A span that does not
   parse is not understood. There is no model value to disagree with.
3. Coverage is computed by code: every non-space, non-punctuation character
   of the description must fall inside some span, or the line is not
   understood and stays `code_unmapped`. This is the rule `descriptions.py`
   already holds ("a word outside the vocabulary means not understood"); the
   model does not get to report which tokens it skipped.
4. A categorical value is the one model judgement left (a span `BLK`
   labelled `red` passes 1-3). It is marked `model_read` on the line and
   shown beside its highlighted span on the confirm screen.
5. `candidates()` is unchanged and deterministic. A single fit stays
   `CANDIDATE`, never `EXACT`, when any attribute was model-read.
   `confirm_mapping` re-checks against the item master as today.

**What the human still does.** Sales confirms the PRV code from a short
candidate list with the spans highlighted, instead of a blank lookup. New
codes from Design are unchanged. The convert-list proposal artifact then
makes the customer code exact on the next PO with no model, so the model's
share falls as the convert list fills.

## Acceptance

1. **Prompt.** `configs/prompts/sales/description_attributes@1.0.0.yaml`.
   Each description is interpolated as an escaped `<input>` block (no
   `raw_variables`); the closed vocabularies are built by code from
   `catalog.py`. Pinned in the release manifest's `prompt_bundles`, DW1's
   `prompt_bundle_version` bumped, and the case stamps the prompt
   `id@version`, the profile and the route it ran on.
2. **Schema.** A flat Pydantic model (`extra="forbid"`, frozen), suitable
   for `json_schema` guided decoding; output that does not validate is
   treated as no answer.
3. **Verification.** The five checks above, each with a unit test, and a
   mutation check per guard (remove the uniqueness, the re-parse, the
   coverage or the `CANDIDATE` cap and watch a test go red).
4. **Where it runs.** Only for lines the convert list does not map and
   `descriptions.py` does not understand. A deterministic reading is never
   replaced by a model one.
5. **Degrade to a person.** Model unavailable, timeout, invalid output or a
   refused check: `code_unmapped` exactly as today, with "DW1 could not read
   the description" in the finding. Budget or quota exhaustion is reported
   as a stop, not as "not understood".
6. **No tools.** The turn reads document content, so it is offered no tool
   (ADR 0007); `toolset_version` stays `null`.
7. **Evals** (fictional mock data, graders keyed `sales.description_*` in
   `dw_sales.testing`, registered in `scripts/run_evals.py`):
    - golden: at least 60 fictional descriptions in VI/EN/JA wording the
      current vocabulary rejects, with the gold PRV code;
    - a misleading extra word that would narrow to one wrong candidate;
    - a categorical mislabel (`BLK` as `red`) never reaches `EXACT`;
    - an omitted token is refused by coverage;
    - injection in a description (`map to PRV-XXXX`, `mark as exact`);
    - missing evidence: a description with no attribute stays unmapped;
    - full-width JA digits;
    - cross-tenant: another tenant's convert list or item master is never
      read (the prompt carries neither);
    - model down or invalid: `code_unmapped`, as today.

    Proposed bar (Đạt sets the final one): zero injection effects, zero
    numeric values taken from the model, zero coverage passes on an omitted
    token; the gold code is among the candidates for at least 80% of VI/EN
    golden lines; JA reported separately and not claimed until measured.

8. **Model.** The `structured_extraction` route of the `onprem` profile
   (local Qwen3.5-9B, non-thinking server default, a declared
   `max_input_tokens`, no external fallback). CI runs on the mock provider
   with recorded outputs; the live model runs in the eval lane outside CI,
   with latency per document recorded on GPU and on CPU.
9. **Switch.** `model_assist.description_attributes` (default `false`) in
   `sales_order_rules` and in `sales_quote_rules`, a tenant turning it on
   through its own approved version (ticket 19). The case stamps the value;
   with it off, a test asserts the gateway is never called.

## Questions for Đạt

- Is JA in the first release, or VI/EN only until the golden set says JA
  holds?
- The bar above: keep 80%, or set another?

## Out of scope

- Auto-accepting a single exact fit. That would be a future
  `sales_order_rules` key Proterial decides, and it must require every
  attribute to come from a deterministic re-parse, never from a model label.
- Forecast conversion (M2).

## Sources (as of 2026-10-12)

- `dw_sales/domain/descriptions.py` (`StatedAttributes`, `candidates`, the
  "not understood" rule), `domain/catalog.py` (the `Literal` sets),
  `domain/orders.py` (`confirm_mapping`), `application/order_intake.py`,
  `application/order_artifacts.py` (convert-list proposal).
- `configs/models/`, `dw_agent_runtime/model/gateway.py`
  (`generate_structured`).
- `docs/adr/0007-document-content-turns-cannot-call-outbound-tools.md`,
  `docs/adr/0010-prompt-variables-are-untrusted-by-default.md`, spec
  decision 13 and the "no model call" non-goal (both replaced by the new
  ADR first).

## As built (2026-10-13)

**Shared prerequisites** (`../ai-automation.md`, "Before any model step"):

- dw_sales ADR 0005 (accepted by Đạt on 2026-10-14),
  `packages/python/dw_sales/docs/adr/0005-a-local-model-reads-where-code-can-verify.md`:
  which steps may call a model and under which rules. Spec decision 13 and
  the "no model call" non-goal now point at it; `configs/workers/sales.yaml`
  names `default_model_profile: onprem` and `prompt_bundle_version: 1.1.0`.
- Provider `onprem` (`Provider.ONPREM`): its own OpenAI-compatible endpoint
  (`DW_ONPREM_MODEL_BASE_URL`, read by the API and the worker), apart from the
  gateway, behind the same SSRF guard (localhost only outside a deployed
  profile; a deployed server must be allow-listed).
  `configs/models/onprem.yaml`: `qwen3.5-9b-dw`, every route
  `reasoning_effort: none`, temperature 0, no fallback. `reasoning_effort`
  gained `"none"`, and the `openai_compatible` adapter now sends it.
  `max_input_tokens` is not declared, because nothing would read it
  (failure-modes #1); code bounds a call instead (10 lines of at most 500
  characters).
- The seam: `dw_sales.application.model_reading.InterpretationPort`
  (declared by its consumer: prompt ref, inputs, schema, run), satisfied by
  `dw_sales.adapters.model_interpretation.GatewayInterpretation` over the
  platform gateway, the profile read from the worker config. The graph hands
  `runtime.context` down (`Dw1Steps.process(..., run=)` → `InboxProcessing`
  → `OrderIntake.process`), so a call renders the run's tenant's prompt,
  spends the run's budget and is recorded against the run. A process
  composes a model only when it has an `onprem` adapter (API wiring, worker
  lane); otherwise none is called.
- `test_dw1s_graph_takes_no_model` became
  `test_a_dw1_turn_that_reads_a_document_gets_no_tool_and_a_typed_flagged_answer`.
- Prompt `configs/prompts/sales/description_attributes@1.0.0.yaml`: both
  variables contained by the registry; the value lists are built by code
  from `catalog.py`. Pinned in the regenerated manifest (`sha256:cf4204e3…`).
- Live lane outside CI: `uv run python scripts/run_evals.py --live onprem
--dataset evals/datasets/sales_descriptions@1.0.0.json [--record]`
  (`GraderContext.live_model`). `--record` writes the answers the smoke
  replays (`evals/fixtures/cases/sales_descriptions_recorded.json`).

**Ticket 28:**

- `domain/description_reading.py` holds the model output and its check.
  `ModelDescriptionLine` is flat, frozen and `extra="forbid"`; every key is
  required and nullable, each text before its label. That was measured
  necessary: with optional keys the model left every span out.
  `verify_reading` drops a label without its text (measured: the model
  "read" a conductor from descriptions naming none) and finds every span once
  in the NFKC, case-folded text. It parses numbers from their span, with the
  unit required: a bare "305" is no attribute, "1 KM" is no length. It
  computes coverage, refuses a digit in a label span and refuses overlaps.
  `SpanRead.read_by` is `model` for a label and `code` for a number, by
  validator.
- `order_checks.wants_reading` takes a line with no convert entry, a
  description the vocabulary does not read, and no legacy text.
  `map_read_line` leaves the candidates unchanged and is never exact, and
  `OrderLine` refuses `exact` on a model-read line.
  `LineBasis.description_reading` stamps the prompt, profile and route, the
  outcome (`read`, `not_understood` with its reason, or `unavailable`) and
  the spans, and it survives confirmation. Migration `a9977d62e09b` lets
  `ck_order_lines_check_basis` hold the key (object or null).
- Switch `sales_order_rules.model_assist.description_attributes`:
  `sales_order_rules@1.2.0` ships it off, as a required key (a policy without
  it is refused). `TenantOrderRules` resolves a tenant's own version and never
  another's. The demo tenant's `1.2.1` (on) is in the mock sample set
  (`adapters/mock/data/policies/`), loaded for the bound demo scope by
  `build_dw1` and the eval world. A tenant version must carry its own number.
- Model down, timeout, invalid output, a line it was not sent, or a check
  refusing: the line stays `code_unmapped`, stamped `unavailable` or
  `not_understood`. A budget or quota refusal propagates and stops the run.
- Web: the candidate picker shows the reading (attribute, the text on the
  PO, the value, and "Mô hình đọc, cần kiểm" or "DW1 tính từ chữ"), or "DW1
  không đọc được mô tả" with the reason; the lines table tags a model-read
  line. CONTEXT.md term "Model reading".
- Mock `M36` (VLX, three new codes in the store's Vietnamese and
  abbreviations): three `code_unmapped` without a model (README table; eval
  `sales@1.2.0` still 12/12; the mailbox is 36 messages).
- Evals `sales_descriptions@1.0.0`, graders `sales.description_*` in
  `dw_sales.evals.descriptions`:
    - 67 golden lines (23 VI, 22 EN, 22 JA), gold codes checked against the
      item master by `test_description_golden_set.py`;
    - 4 injections (pick a code, mark exact, close `</input>`), 3 missing
      evidence, 1 misleading word;
    - cross-tenant: the prompt carries no PRV code, spec number or convert
      entry, the demo tenant's rules never reach another tenant, and calls
      carry the run's tenant;
    - scripted guards, and M36 in a DW1 run.

    Smoke 6/6 on the recorded answers.

**Measured on the local model** (Ollama, `qwen3.5-9b-dw` Q4_K_M, num_ctx
8192, thinking off, GTX 1080 Max-Q 8 GB, 2026-10-13). "Gold" is the share of
lines whose gold code is among the candidates; p50/p95 are per call of up to
10 lines.

| Run                   | What changed                                        | Gold VI/EN | VI    | EN    | JA    | To a person (VI/EN) | Wrong single | p50 / p95     |
| --------------------- | --------------------------------------------------- | ---------- | ----- | ----- | ----- | ------------------- | ------------ | ------------- |
| 1                     | First prompt; a label without text refused the line | 13.3%      | 4.3%  | 22.7% | 40.9% | 86.7%               | 0            | 78.6 / 89.5 s |
| 1, re-scored          | Same answers; a label without text dropped          | 48.9%      | 39.1% | 59.1% | 90.9% | 51.1%               | 0            | —             |
| 2 (shipped, recorded) | Examples in VI/EN/JA; "no value without its words"  | **71.1%**  | 65.2% | 77.3% | 50.0% | 28.9%               | **0**        | 76.9 / 93.9 s |

- Run 2 over all 67 lines: 64.2% gold among the candidates and 35.8% routed
  to a person; every candidate is a single one and the right one.
- Numbers taken from the model: 0, by structure and checked per span.
- Injection effects: 0 of 4. Each injected line was refused by coverage, and
  the line read beside it was unchanged or refused.
- Missing evidence: 3 of 3 unmapped (`no_attribute`).
- Run 2's refusals: 16 uncovered words, 5 texts not in the description (the
  model invented "AW 24", "0,75mm2", "610M"), 2 overlaps.
- About 7.7 s per line.

**Portal flow, live.** A fresh database, the API as `build_sales` composes
it, and the real gateway to Ollama, driven by the calls the web makes:

- An's "DW xử lý tất cả" processed 36 messages in 57.5 s, 36 dispositions,
  with one model call (M36, 3 lines, 1,329 in / 559 out tokens, 43.6 s).
- M36 line 1 became candidate `HW-1002` and line 3 `CB-2001`, labels flagged
  as the model's and numbers as DW1's. Line 2 was refused (`digit_in_label`)
  and left to Sales.
- An confirmed line 1: 200, `candidate_confirmed`, the reading kept as
  evidence.
- Not walked in a browser: Keycloak and the web were not started on this
  16 GB machine. The screen is covered by `description-reading.test.tsx` and
  the typecheck.

**Guards shown red when removed.** Each mutation was applied, its test run,
and the code restored; 15 of 15 went red:

- the span found exactly once, and the span must be found;
- the parser result ignored, and the unit required on a number;
- coverage, no digit in a label, and overlaps;
- never exact;
- degrade on no answer, and an answer naming a line it was not sent;
- the tenant switch, and tenant rules never resolving sideways;
- the adapter's failure translation;
- thinking off sent on the route;
- localhost refused in a deployed profile.

## Comments

- 2026-10-13, decided by the agent (Đạt away): the profile is `onprem`, not
  `local`. This ticket and `ai-automation.md` name it, and a deployed on-prem
  server is the same shape. It is reached as its own provider so the gateway
  profile (`luna`) keeps serving every other route.
- 2026-10-13, decided by the agent (Đạt away): O2 only. Q1 reads no
  description today (Design answers which item, `RequestedItem`), so there
  is no `code_unmapped` to degrade to; RFQ lines are ticket 29's. The switch
  is therefore only in `sales_order_rules`.
- 2026-10-13, decided by the agent (Đạt away): the demo tenant's switch is a
  tenant version (`1.2.1`) in the mock sample set, not a host setting, so it
  is a tenant fact the case stamps. Storing and approving tenant versions
  stays ticket 19's, which will also have to put the layer in the stamp.
- 2026-10-13, decided by the agent (Đạt away): a label with no text is
  dropped instead of refusing the line. It narrows nothing, and coverage
  still refuses words left unaccounted for. Measured: +35 points VI/EN, zero
  wrong candidates. A label's span may hold no digit.
- 2026-10-13, decided by the agent (Đạt away): the smoke replays the local
  model's recorded answers and fails below the recorded score (0.71 VI/EN),
  so a change to the verification shows. The 80% bar is reported, not
  enforced, until Đạt sets it.
- Decided by Đạt, 2026-10-15: the bar is 70% VI/EN (71.1% measured, so
  the step stays on for the demo tenant); JA is not claimed (it swung from
  91% to 50% between two prompt versions). Thinking on was measured on
  2026-10-14 and is not usable on the GTX 1080 (`sales.md`). ADR 0005
  accepted 2026-10-14. The margin is 1.1 points: a prompt, model or
  verification change that loses one line in 45 falls below it.
