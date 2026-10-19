# 40 — Business users edit DW1's rules in a form, not in JSON

Status: done (2026-10-19; Đạt asked 2026-10-18: "business users change DW1's rules, thresholds, deadlines and templates themselves through a good UI"; built and mutation-checked by the agent, committed in `8de9456`, `a42fca3`, `82bb48c`, `6659d14`. The rendered page is not looked at yet, see Owed)
Blocked by: —
Category: enhancement

## What

`/sales/rules` (ticket 38's follow-up `bd666a7`) proposes a version of a key
by typing the whole document as JSON in a `TextArea`, and starts it from the
company's own version only, because the platform's documents were not
served. A PIC or head cannot be expected to write JSON, and the head
approving it on `/approvals` saw the key and the number, not what changed.

## Acceptance

1. Each key's JSON Schema (`model_json_schema` of its `OVERRIDABLE` model)
   is served by a read route beside the rules routes, under
   `sales.rules.propose`; an unknown key is not found (404).
2. One renderer draws a form for every key from its schema: numbers with
   their bounds and units, switches, choices in words, single- and
   multi-line text, nested sections, lists (add, remove, reorder) and maps
   (key/value rows). Checks on blur, "bắt buộc" on submit only, the
   server's 422 put back on the fields it names, one error summary
   (ui-quality §9). A "JSON nâng cao" editor stays for experts.
3. Every field of the eight schemas has Vietnamese words, from one table;
   a field added later fails CI until labelled.
4. Before sending, the proposer reads a field-by-field diff against the
   version in force; the head reads the same diff where the approval is
   decided (`/approvals`, `/approvals/<id>`).
5. A proposal may start from any released version, the company's or the
   platform's ("Dùng lại phiên bản này"), and is a proposal like any other.
6. Template fields list the placeholders they may use where the models
   define them; a live preview only if the filling code is reusable.

## As built

- **API** (`application/rules.py`, `presentation/routes.py`):
  `GET /sales/rules/{key}/schema` → `RuleSchemaView` (`rule_schema(key)`,
  the model's own `model_json_schema(by_alias=True)`), and
  `GET /sales/rules/{key}/platform` → every version of the key the
  platform layer holds (`TenantRuleBook.platform` and `.released`, ticket
  37), newest first, whole. Both: `sales.rules.propose` at the route and
  again in `SalesRulesService`, the scope asked before the key is looked at,
  an unknown key `NotFoundError` (404). The path parameter is a plain
  string so a key that is not a `RuleKey` is a 404, not FastAPI's 422.
  Serving the platform's documents is new (ticket 38 noted they were "not
  served"): they are the platform layer, the same for every tenant, and go
  to the same holders who already read the tenant's own documents (pricing
  included; both roles hold `sales.price.read`).
- **Placeholders in the schema** (`application/handoffs.py`): the hand-off
  copy's fields carry `x-placeholders`, built from the same frozensets its
  validator checks (`_named`), so the editor lists them from the one owner.
  The e-mail and document copy (`string.Template`) declare no set: the code
  that draws each kind decides which values exist. The editor shows what the
  version in force uses in the same field, and only warns on another one.
  **No live preview:** the filling code is Python and no endpoint renders a
  template with a sample case.
- **Contracts**: `scripts/generate_contracts.py` also writes
  `contracts/jsonschema/sales_rules.json` (a `JSON_SCHEMAS` seam), checked
  by `--check` in CI like the OpenAPI snapshot. OpenAPI types the route's
  `json_schema` as an object, so the web's label test reads this file.
  `openapi.json`, `generated/sales.d.ts`; `SalesApi.ruleSchema`,
  `.rulePlatformDocuments`.
- **Web**:
    - `_lib/rule-schema.ts`: the schema read into eight shapes (object, map,
      list, text, number, switch, choice, fixed; nullable on any), `toForm`
      / `fromForm` (a map as key/value rows, a nullable section as
      `{ on, value }`, a decimal kept as text), `problem` (bounds, lengths,
      patterns in words), `formName` (a server `loc` to the form field,
      through maps and lists), `fieldPaths` / `enumValues` for the label
      test.
    - `_components/rule-form.tsx`: the renderer. Segmented for a short
      choice, Select (Vietnamese folding search) for a long one; InputNumber
      without `min`/`max`/`precision`, which would change what was typed on
      blur without a word, so the schema's check says it instead; the
      required check is a validator, because async-validator's own reads a
      number as a string and refuses it.
    - `_lib/rule-labels.ts`: `RULE_FIELDS` (key + label path, `*` for a map
      key and `[]` for a list item) with label, help, unit and item words;
      the common fields once; value words for every enum value (finding
      codes, languages and fields reused from `labels.ts`, steps generated);
      a humanised fallback; `pathLabel`, `describeValue`.
    - `_lib/rule-diff.ts`: field by field; lists aligned by content (LCS),
      an edited item compared field by field; `"0.10"` equals `0.1`.
      `_components/rule-diff-view.tsx` draws it with Đổi/Thêm/Bỏ tags.
    - `rules/page.tsx`: the drawer loads the schema and the platform's
      versions, opens "Bắt đầu từ phiên bản" on what applies (or the row's
      version from "Dùng lại phiên bản này"), offers the next free number
      (`nextVersion`), "Xem thay đổi" → diff → "Gửi duyệt"; a 422 returns
      to the form with each named field marked and the rest listed in the
      summary.
    - Approvals: `ApprovalHost.detail` (one lookup, `approvalDetail`, drawn
      by `ApprovalHostDetail` on `/approvals` and `/approvals/<id>`); Sales
      draws `RuleApprovalChanges` for `sales.rules`, which reads through the
      rules routes, so a decider without `sales.rules.propose` is told why
      it is not shown and reads nothing.

## Checked

- Python: `test_rules.py` (+3: each key's schema is the model's, the
  hand-off placeholders; platform documents newest first, each valid; the
  scope before the key, unknown key), `apps/api/tests/unit/test_sales_rule_schemas.py`
  (new, 13: each key 200, platform documents, 403 without the scope on both
  routes and for an unknown key, 404 for three unknown keys). The support
  and route-walk tests cover the two new routes unchanged. ruff, mypy, the
  contracts `--check`.
- Web: `rule-schema.test.ts` (8), `rule-labels.test.ts` (6),
  `rule-form.test.tsx` (5), `rules.test.tsx` (11, rewritten),
  `_meta/__tests__/rule-approval.test.tsx` (3). Whole suite, tsc, lint.
- Mutations, each red then restored: one label removed
  (`intake.max_cells`): the label test; the service's scope check removed:
  the service test (the route's guard keeps the API test green, both layers
  tested); the unknown key as a 422: the API and service tests; the schema
  checks disabled: the renderer's min/max test; "bắt buộc" asked on blur:
  red only after the test was rewritten to wait for the blur's check (it
  was green both ways first, failure-modes #3); server errors not put on
  the fields: the page's 422 test; list alignment ignoring equal items: two
  diff tests.

`reviewing-feature-security`: tenant isolation (the two routes read no
tenant row; the platform layer is the same for every tenant; the approval
detail reads through `GET /sales/rules`, unchanged and RLS-bound);
authorization (the scope at the route and in the service, asked before the
key; a decider without it reads nothing, tested); autonomy (no agent
reach); untrusted content (the schema is code-built; documents are drawn as
text; placeholder checks in the browser are hints, the server's validators
still decide); audit (reads only; proposals unchanged); defaults (an
unknown key 404, a missing scope 403 first). `reviewing-deployment-security`:
two read routes behind the existing auth and CORS, no profile-dependent
path.

## Owed

- A look at the rendered drawer and the approval diff on the stack, at
  phone width and at `lg`: nothing here was seen in a browser. The e-mail
  copy is long (eight kinds × three languages); whether a Card per kind
  reads well or wants a narrower first view is a judgement for the screen.
- The step-11 walk (`e2e/sales-demo.spec.ts`) now proposes through the form
  (fills "Số phiên bản mới", reads the diff, sends): written, not run
  (Playwright was not run in this session).

## Left open

- E-mail and document templates name no placeholder set in their models;
  declaring one per kind (and validating it at proposal, as the hand-off
  copy does) would turn the warning into a refusal and catch a placeholder
  that makes a draft fail to render later.
- A preview with a sample case needs an endpoint that renders a template;
  none exists.
