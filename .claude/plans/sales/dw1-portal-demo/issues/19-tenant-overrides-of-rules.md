# 19 — Tenant overrides of Sales rules and templates, proposed and approved (G15)

Status: done (2026-10-13; the mechanism, the routes, sales_order_rules and sales_kpi; the other five keys are ticket 36. Built and adversarially reviewed by the agent, Đạt away; committed in 399920d)
Blocked by: —
Category: enhancement

Split from ticket 12 on 2026-10-12.

## What

Sales rules and templates ship as platform-layer files:
`configs/policies/sales_order_rules`, `sales_quote_rules`, `sales_pricing`,
`sales_kpi`, `sales_bravo_upload`, and `configs/copy/sales_emails`,
`sales_documents`. Proterial's own values (lead-time table, LME rule, email
wording, upload template) must arrive as a tenant override at runtime, not as
an edit to the checkout (`CLAUDE.md`, "Per-tenant artifacts").

`dw_kernel.overlay.TenantOverlay` and `dw_platform`'s `PolicyOverridePort`
exist; Sales does not use them yet (verified 2026-10-12).

## Acceptance

1. Every Sales policy and copy file resolves through `TenantOverlay`: the
   tenant's approved version if one exists, the platform's otherwise. The
   tenant comes from the run or the access context, never from the request.
2. A case keeps stamping the `id@version` it was processed under, and the
   stamp says which layer it came from; later reads use the stamp, not a
   fresh lookup.
3. Routes under `/api/v1/sales/rules`:
    - propose a new version of one key (body validated by that key's schema;
      a schema failure → 422), needs `sales.rules.propose`, granted to
      `sales_pic` and `sales_head` (maker/checker, as in the rest of DW1);
    - approve or reject a proposal, needs `sales.rules.approve`, granted to
      `sales_head` only;
    - both scopes declared in one new migration, with this route;
    - the proposer cannot approve their own proposal (409);
    - list versions, with who proposed and approved each.
4. Each proposal and decision is audited in its transaction.
5. Inventory answers (the release manifest) still read the platform layer
   only.
6. Negative tests: an override never resolves for another tenant; a
   `sales_pic` cannot approve; a support context cannot propose or approve;
   a proposal for an unknown key → 422.
7. Mutation check: make resolution fall back to any tenant's override and
   watch the cross-tenant test go red.

## Out of scope

- A web editor for rule files (the API and an audit trail are the slice);
  a read-only "rules in force" view is welcome if small.
- Proterial's actual values (they wait on the requirements doc).

## Sources (as of 2026-10-12)

- `dw_kernel/overlay.py`, `dw_platform/application/ports.py`
  (`PolicyOverridePort`), `test_tenant_overlay.py`.
- Spec decision 14; `configs/policies/sales_*`, `configs/copy/sales_*`.

## Comments

- Decided by the agent (Đạt away), 2026-10-13: **a Sales table, not
  `platform.policy_overrides`.** That table holds one document per tenant and
  policy, with no version, no proposal and no decision; this ticket needs
  versions proposed by one person and approved by another, listed with both.
  `sales.rule_versions` (migration `57a241ea182b`) keeps them; Sales never
  wrote to `policy_overrides`, so no fact has two homes.
- Decided by the agent (Đạt away), 2026-10-13: **narrowed by tenant only.** A
  rule applies to the whole tenant, whichever workspace it was proposed in
  (`workspace_id` records which). It is the first Sales table not narrowed by
  workspace: `test_sales_schema.py` names it in `_TENANT_WIDE` with the reason,
  and still requires every other Sales table to be.
- Decided by the agent (Đạt away), 2026-10-13: **routes on Sales, as the
  ticket says, not a platform approval.** `POST /sales/rules/{key}/versions`
  (`sales.rules.propose`, PIC and head), `POST
/sales/rules/versions/{id}/decision` (`sales.rules.approve`, the head; the
  proposer gets 409 `maker_checker`, and `ck_rule_versions_checker_not_maker`
  refuses it whatever writes the row), `GET /sales/rules` (what is in force
  per key and from which layer, the platform's refs, every version with who
  proposed and decided it). dw_sales ADR 0004 (checker decisions as platform
  approvals) is still Proposed; if Đạt accepts it, the decision route moves
  to `sales.rules` approvals like `sales.layout`. (Đạt accepted it on
  2026-10-14; ticket 38 moved the route.)
- Decided by the agent (Đạt away), 2026-10-13: **only keys whose readers
  resolve per tenant are overridable: `sales_order_rules` and `sales_kpi`.**
  `RuleKey` and `OVERRIDABLE` in `dw_sales.application.rules` are the one
  list; any other key is not a path of the router (422). The quote rules,
  the pricing policy, the e-mail and document copy, the Bravo upload template
  and the hand-off copy are read as one platform object at the composition
  root (`QuotationService.rules/pricing`, `ArtifactCopy`, `HandoffCopy`);
  accepting a version of them before their readers resolve it would store a
  rule nothing applies (failure-modes #1). Ticket 36 owns them.
- Decided by the agent (Đạt away), 2026-10-13: **the stamp names one document,
  and later reads use it.** A tenant version may not take the number the
  platform ships (409 `platform_version_reused`, at proposal and again at
  approval), so `sales_order_rules@x.y.z` on a case means one document. A
  recheck reads the stamped version (`OrderRulesPort.rules_at`): a version the
  tenant approved since does not reach a case checked before it, and a
  version this process no longer holds is refused as before. `GET
/sales/rules` says which layer each version is.
- Decided by the agent (Đạt away), 2026-10-13: **the demo tenant's version
  goes through the route.** `dw_sales.testing.seed_rules.seed_demo_rules`
  proposes the sample set's `sales_order_rules@1.5.1` as An (PIC) and approves
  it as Giang (head) through `SalesRulesService`, each with the access context
  their membership resolves to; `make demo-reset` (`seed_demo`) and the API's
  integration suite run it. The API's composition root no longer reads the
  sample set's policies directory. The eval world (no database) holds the
  version as approved in memory (`MemoryRuleVersions.seed_approved`).

### As built (2026-10-13)

- `packages/python/dw_sales/src/dw_sales/application/rules.py` (new):
  `RuleKey`, `OVERRIDABLE`, `RuleVersion`, `TenantRuleBook` (resolution
  through `TenantOverlay`, `at` by stamp), `RuleBookOrderRules`,
  `SalesRulesService`, the views.
- `application/order_ports.py` (`rules_at`), `order_intake.py` (a recheck
  reads the stamp), `overview_service.py` (`KpiPort`), `services.py`
  (`rules`, the book), `access.py` (`RULES_PROPOSE`, `RULES_APPROVE`),
  `case_store.py` (`rule_versions` on the unit of work).
- `adapters/persistence/rule_versions.py` (new), `tables.py`, `uow.py`;
  `adapters/memory_rules.py` (new); `adapters/order_rules.py`
  (`TenantOrderRules` gone, `rules_at`), `adapters/policy_files.py`
  (`rule_book`), `adapters/assembly.py`; `evals/world.py`, `evals/graders.py`
  (the callers hold the new scopes as the roles do);
  `testing/seed_rules.py` (new), `testing/seed_personas.py`.
- `presentation/routes.py`: the three routes.
- `db/migrations/versions/57a241ea182b_sales_rule_versions_proposed_and_.py`.
- Tests: `packages/python/dw_sales/tests/unit/test_rules.py` (new, nine),
  `test_order_rules.py`; `apps/api/tests/integration/test_sales_api_rules.py`
  (new, five), `conftest.py` (the seed), `test_sales_api_access.py` and
  `apps/api/tests/unit/test_sales_support.py` (route parameters);
  `test_sales_roles.py`, `test_sales_schema.py`, `test_privileges.py`.
- `contracts/openapi/openapi.json`, `generated/sales.d.ts`.

Mutation checks (each against the passing tree, then restored):

- resolution falls back to any tenant's version (memory store): the
  cross-tenant and the KPI tests red; the policy of `sales.rule_versions`
  made `USING (true)`: the API's cross-tenant test red (tenant beta listed
  alpha's 1.5.1). Acceptance 7.
- the service's maker/checker refusal removed: red (the version's own
  validator refuses it too); the database's check removed: the API test that
  writes around the service red.
- a stamp read for a rejected version: red.

`reviewing-feature-security`: tenant isolation (RLS by tenant, FORCEd; the
lookup is bound to the scope's tenant; beta reads nothing of alpha's and
cannot decide it); authorization (scopes at the route and again in the
service; a PIC cannot approve, a viewer cannot list or propose, a support
context is refused on every route not opened to it, which the route walks
in `test_sales_api_support.py` and `test_sales_support.py` now cover);
untrusted content (a document is validated by its key's schema; a refusal
names fields, never values); audit (`sales.rules.proposed`, `.approved`,
`.rejected` in the write's transaction, key, version and status only);
defaults (no approved version: the platform's; a stamp this process cannot
read: refused). `reviewing-deployment-security`: three routes behind the
existing auth and CORS; the sample set's policies are no longer read by the
API in any profile; the seed runs only where `seed_demo` runs (local, test).
Acceptance 5: the release manifest is built from `configs/` at build time
and reads no database; `release_manifest.py --check` unchanged.

- **Owed, 13/10/2026 (Docker down).** Run green before the crash: the five
  rules API tests, `test_sales_overview_sql.py`, `test_sales_roles.py`,
  `test_sales_schema.py` (with `_TENANT_WIDE`), `test_sales_offboarding.py`,
  `test_privileges.py`, `test_rls_coverage.py`, and every mutation above.
  Not re-run after the last changes, because Docker Desktop (WSL) stopped
  answering at 22:00: the whole Sales integration suite with the seed in the
  API conftest (every API test now resolves the demo tenant's rules from the
  database, not the sample set), and `test_sales_personas.py`, whose
  expected scopes were brought up to the two new ones after the crashed run
  showed it red. Run `uv run pytest -m integration packages/python/dw_sales
apps/api/tests/integration -k sales` when Docker is back. Run since on CI:
  the Integration job (`uv run pytest -m integration`, which collects both,
  `test_sales_personas.py` included) passed on 1621cbc and on 99cb905 after
  ticket 38 (844 passed).
