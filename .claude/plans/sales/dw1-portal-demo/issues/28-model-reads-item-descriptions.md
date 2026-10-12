# 28 — A model reads a free-text item description into typed attributes; code finds the PRV code, Sales confirms

Status: needs-triage
Blocked by: the shared model prerequisites (`../ai-automation.md`, "Before
any model step"). The deterministic convert-list seed from Bravo sales
history comes first (same file, step 1).
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

## Comments
