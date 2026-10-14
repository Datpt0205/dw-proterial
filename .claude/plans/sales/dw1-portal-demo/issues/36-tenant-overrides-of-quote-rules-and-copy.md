# 36 — A tenant's own quote rules, pricing, copy and upload template

Status: done (2026-10-14; the six keys, their readers and stamps; built, mutation-checked and reviewed by the agent, Đạt away; not committed; integration tests written and owed while Docker is down, see Owed)
Blocked by: —
Category: enhancement

Split from ticket 19 on 2026-10-13 (agent, Đạt away).

## What

Ticket 19 built the mechanism: `sales.rule_versions`, the propose and
approve routes, `TenantRuleBook` resolving through `TenantOverlay`, and the
stamp read back by a recheck. It made two keys overridable, `sales_order_rules`
and `sales_kpi`, because their readers already took the tenant's scope. The
other Sales policy and copy files are still read as one platform object at the
composition root, so a tenant version of them would be stored and applied by
nothing:

- `sales_quote_rules` and `sales_pricing`: `QuotationService.rules` and
  `.pricing`; the Design mailboxes are also copied into `ArtifactCopy` from
  the platform's quote rules (`load_artifact_copy`), so the drafting of a
  YCBG must read the tenant's too, or the two disagree.
- `sales_emails`, `sales_documents`, `sales_bravo_upload`: `ArtifactCopy` in
  `ArtifactService` and the drafting.
- `sales_handoffs`: `InboxQueries` and the hand-off drafts.

## Acceptance

1. Each reader resolves its key per tenant through `TenantRuleBook` (the
   service asks with the scope it already has); the composition root hands
   the book, not the loaded object.
2. Each key is added to `RuleKey`, `OVERRIDABLE` and the migration's
   `ck_rule_versions_key` in one change, with its reader.
3. Where a case or an artifact stamps the version it used (a quotation's
   `rules_version` and pricing version, an artifact's `template_ref`), a later
   read uses the stamp, as ticket 19 does for order rules.
4. Tests as ticket 19's: another tenant never sees the version; a stamped
   version is read back; a mutation making resolution fall back to any tenant
   goes red.

## Sources (as of 2026-10-13)

- `dw_sales/application/rules.py`, `adapters/policy_files.py`
  (`load_artifact_copy`, `rule_book`), `application/quotation.py`,
  `application/drafting.py`, `application/artifacts_service.py`,
  `application/inbox_service.py`; ticket 19's Comments.

## Triage (2026-10-14, agent, Đạt away)

Category: enhancement. State: ready-for-agent. Đạt asked on 2026-10-14 for
35 and 36 to be triaged and done now.

Claims checked against the code (as of 2026-10-14):

- `QuotationService.rules` and `.pricing` are the platform's loaded objects,
  handed in at `adapters/assembly.py` (`policies.quote_rules`,
  `policies.pricing`). **True.**
- `ArtifactCopy.design_mailboxes` is copied from the platform's quote rules
  in `load_artifact_copy`, while `QuotationService._from_design` reads
  `rules.design_mailboxes`: once the quote rules resolve per tenant, the YCBG
  draft and the reply check must read the same tenant's. **True.**
- `sales_emails`, `sales_documents`, `sales_bravo_upload` are one
  `ArtifactCopy` given to `ArtifactService` at assembly. **True.**
- `sales_handoffs`: `InboxQueries.handoffs`, rendered on every read of the
  inbox (`_draft`). The hand-off reader itself reads no copy. **True.**
- Stamps (acceptance 3):
    - `QuoteCase.rules_version` is stamped at `open_case` and **read by
      nothing**: `price_evidence` (reference price), `decide_price` (copper
      basis, the finding's stamp) and `quotation_document` (validity) read
      whatever this process loaded (failure-modes #1). They read the stamp.
    - Pricing has **no case stamp**: each `PriceEvidence.pricing_policy` and
      each price finding's `rule_versions` carry the version they were
      computed under, and nothing computes them again later. So pricing
      resolves to the tenant's current version at each computation, and the
      result carries it; there is no later read to bind.
    - An artifact's `template_ref` is stored with its bytes, and a render at
      the same case version returns the stored file. The one later read is
      `send_draft`, which renders the final quotation again to attach it
      "byte for byte the stored ones": that holds only while the documents
      copy is the version `quotation_final` recorded. A render reads the
      copy at the version the case's artifacts at that case version stamped.
- Found in triage (security): `HandoffCopy` is filled with `str.format`.
  Once a tenant can propose its own, a placeholder such as
  `{customer:>999999999}` allocates a gigabyte on every read of the inbox,
  and `{customer.__class__}` reaches attributes. The copy is validated to
  name only the known placeholders, plain, before it is overridable.

Redundancy: none; ticket 19 split this out. dw_sales ADR 0004 (checker
decisions as platform approvals) is still Proposed and Đạt has not decided
whether rule decisions move onto platform approvals.

- **Decided by the agent (Đạt away), 2026-10-14: ticket 19's route shape
  stays** (`POST /sales/rules/{key}/versions`, `POST
/sales/rules/versions/{id}/decision`, `GET /sales/rules`); the six keys
  join the same `RuleKey` path parameter. If Đạt accepts ADR 0004's
  amendment for rules, the decision route moves to a `sales.rules` platform
  approval, as `sales.layout` did, for all eight keys at once. (Đạt chose
  that on 2026-10-14: ticket 38.)
- **Decided by the agent (Đạt away), 2026-10-14: Design's mailboxes are the
  tenant's current quote rules', in both readers** (the reply check and the
  YCBG/Design drafts), not a case's stamp: where Design is now is not a rule
  a case was checked under, and a stamp would draft to a mailbox the reply
  check no longer trusts.
- **Decided by the agent (Đạt away), 2026-10-14: a stamp of a platform version
  this process no longer ships is refused (409)**, as ticket 19 does for
  order rules, for the quote rules a case was opened under and for a copy an
  artifact at the same case version recorded. Open for Đạt: holding every
  shipped platform version in the platform layer would keep such cases
  workable across a deploy. (Đạt chose that on 2026-10-14: ticket 37.)

Brief: `RuleKey`/`OVERRIDABLE`/`ck_rule_versions_key` gain the six keys in
one change (new migration; `ck_rule_versions_document` also reads a copy's
`copy_id`/`version`); `TenantRuleBook` resolves them (`quote_rules`,
`quote_rules_at`, `pricing`, `artifact_copy`, `handoff_copy`), every policy
compared by its `ref`; `QuotationService`, `ArtifactService` and
`InboxQueries` each take a narrow port the book satisfies, and the
composition roots hand the book. Tests as ticket 19's, per reader.

## As built (2026-10-14, agent, Đạt away; not committed)

- `application/rules.py`: `RuleKey` and `OVERRIDABLE` gain
  `sales_quote_rules`, `sales_pricing`, `sales_emails`, `sales_documents`,
  `sales_bravo_upload`, `sales_handoffs`; every policy is compared by its
  `ref` (a `ref` property on `OrderRules`, `SalesKpi`, `SalesPricing`,
  `QuoteRules`, `BravoUploadLayout`; the copy models had one).
  `TenantRuleBook` answers each reader's port: `quote_rules`,
  `quote_rules_at`, `pricing`, `handoff_copy`, `artifact_copy(scope,
stamps)`.
- `QuotationService` takes `policies: QuotePoliciesPort` (in
  `quotation.py`) for `rules`/`pricing`: `open_case` stamps the tenant's
  quote rules; `price_evidence` (reference rule), `decide_price` (copper
  basis, the finding's stamp) and `quotation_document` (validity) read the
  case's stamp (`_rules_of`; 409 `rules_version_gone` for a version this
  process does not hold); pricing is the tenant's current at each
  computation and each evidence and finding carries it; the reply check
  reads the tenant's current Design mailboxes.
- `ArtifactService.copy: ArtifactCopyPort` (in `drafting.py`): each render
  asks the book with the template refs of the case version's files already
  drawn, so `send_draft` attaches byte for byte the final files drawn
  before a new documents version; a stamp no longer held is 409
  `template_version_gone`; Design's mailboxes are the tenant's current ones.
- `InboxQueries.handoffs: HandoffCopyPort` (in `handoffs.py`), read once
  per list when any message carries a hand-off.
- Copy hardened before it became tenant-proposable: `HandoffCopy` names only
  its own placeholders, bare (`str.format`: a format spec, an attribute, an
  index or a conversion is refused); `EmailTemplate.subject` is one line
  (the mail writer refuses a line break, which would otherwise surface as a
  render error).
- Composition: `services.assemble` hands the book to `InboxQueries` and
  `ArtifactService` (no `artifact_copy`/`handoff_copy` parameters);
  `adapters/assembly.py`, `evals/world.py`, `evals/requests.py` hand the book
  to `QuotationService`. `SalesPolicies` holds `emails`, `documents`,
  `upload` instead of a pre-built `ArtifactCopy` (`load_artifact_copy` gone;
  the platform layer is the book's). `memory_rules.platform_book` and a
  general `seed_approved` for tests and evals.
- Migration `26a5276840ba`: `ck_rule_versions_key` names the eight keys;
  `ck_rule_versions_document` reads `policy_id`/`policy_version` or
  `copy_id`/`version`, wrapped in `COALESCE(..., false)` (found in review:
  `57a241ea182b`'s check passed a document naming no `policy_id`, because a
  CHECK evaluating to NULL passes). Downgrade fails while a version of the
  six is stored. `test_sales_schema.py` holds the key list to `RuleKey`.
- `contracts/openapi/openapi.json`, `generated/sales.d.ts` (`RuleKey`),
  release manifest regenerated.
- Tests: `test_rules.py` (each of the six proposed, approved, in force for
  alpha, platform for beta, never read by stamp from beta; another key's
  document refused); `test_quotation.py` (stamp read by every later step and
  the next case takes the newer version; another tenant; a stamp no longer
  held refused; pricing per tenant on evidence and findings; Design
  mailboxes current); `test_artifacts.py` (drafts in the tenant's copy,
  recorded; send draft keeps the final files; stamp no longer held; Design
  drafts to the tenant's mailboxes; subject line break refused);
  `test_handoffs.py` (the inbox writes in the tenant's copy through the
  propose/approve service; seven placeholder shapes refused). API
  integration `test_sales_api_rules.py`: quote case stamped and its
  quotation valid for the stamped days after a newer approval, beta on the
  platform's; a tenant e-mail copy writes and names the draft; a hand-off
  copy with a format spec 422; the table refuses a document naming no key
  or another key's version.

Mutation checks (each against a green baseline, restored): resolution
falls back to any tenant's approved version (acceptance 4) and a stamp read
from any tenant: `test_rules.py`, `test_quotation.py` and `test_artifacts.py`
red; later quote steps reading the rules in force, not the stamp; a case
opened under the platform's rules; the reply check on the platform's
mailboxes; files of one case version ignoring each other's stamps; Design
drafts to the platform's mailboxes; any hand-off placeholder accepted; the
inbox resolving another tenant's hand-off copy; a subject line break
accepted; a stamp no longer held falling back to the version in force. All
red.

`reviewing-feature-security`: tenant isolation (every lookup is the
existing `SqlRuleVersionLookup`, a tenant session per call; stamps are read
from the tenant's own artifact rows and resolved under its scope; beta
resolves the platform's for every key, tested per key and mutated);
authorization (same scopes and maker/checker as ticket 19 for all eight
keys; the rules list shows documents, pricing included, only to
`sales.rules.propose`, which today only `sales_pic` and `sales_head` hold,
both with `sales.price.read`); autonomy (no new agent reach; a tenant's
quote rules decide which verified mailbox is Design's, a trust decision now
behind the head's approval); untrusted content (a proposed copy is
validated by its schema: hand-off placeholders bare, subjects one line,
`string.Template` everywhere else, PDF text escaped, cells written as text);
audit (proposal and decision audited in their transaction, unchanged;
artifacts record the copy version); defaults (no tenant version: the
platform's; a stamp not held: refused, never the version in force).

## Owed when Docker is back (WSL hung since 2026-10-13 22:01)

```sh
set -a; . ./.env; set +a
uv run alembic -c db/alembic.ini heads          # one head (0a78ca5e96d3 on 2026-10-14, ticket 25 on top of 26a5276840ba)
uv run pytest -m integration apps/api/tests/integration/test_sales_api_rules.py \
  packages/python/dw_sales/tests/integration/test_sales_schema.py \
  packages/python/dw_platform/tests/integration/test_rls_coverage.py \
  packages/python/dw_platform/tests/integration/test_privileges.py
uv run pytest -m integration packages/python/dw_sales apps/api/tests/integration -k sales
```

Then: remove `COALESCE` from `ck_rule_versions_document` in a scratch
database and watch `test_the_table_refuses_a_document_naming_no_key_or_another_keys_version`
go red; `alembic downgrade b2afb906fbf2` must fail while a quote-rules
version is stored.

## Open for Đạt

- dw_sales ADR 0004 for rules: if accepted, the decision route moves to a
  `sales.rules` platform approval for all eight keys at once.
- A deploy that ships a new platform version of a key strands the cases
  stamped with the old one (409), as order rules already do (ticket 19).
  Holding every shipped version in the platform layer would keep them
  workable; not done without a decision.
- Whether a viewer of the rules list should see a pricing document without
  `sales.price.read`: moot while only PIC and head can list.

## Comments

- 2026-10-14, CI run 38513561151 (agent):
  `test_a_tenants_email_copy_writes_its_drafts_and_the_file_names_it`
  unpacked the render's response as a list, but it is `{"artifacts": [...]}`
  (`RenderedView`), so the one key came back as `view` and indexing it
  raised `TypeError`. A test bug; it now reads `["artifacts"]`. Re-run on CI
  owed.
