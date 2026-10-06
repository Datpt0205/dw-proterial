# 09 — Evals, security review, demo run

Status: built (2026-10-06, uncommitted); eval sales@1.0.0 10/10 in the eval smoke; both security reviews run; demo runbook, make demo-reset, make test-web-sales (11 passed once, 7.2 min; two later runs did not finish green, see Demo)
Blocked by: 08

## What

- `evals/datasets/sales@1.0.0.json` with prompt_injection,
  cross_tenant_attack and missing_evidence cases.
- Graders `sales.extraction_accuracy` and `sales.findings_recall` (G14, G30):
    - `sales.extraction_accuracy` scores PRV code, quantity, unit price and
      requested date against `purchase_orders.json`;
    - `sales.findings_recall` scores against the README's expected findings.

    Both graders live in `dw_sales`, and a composition root injects them into
    the eval runner, so `dw_evals` never imports a context. They run unchanged
    on Proterial's sample set, which is kept outside git.

- Security cases:
    - M12 (injection);
    - tenant B on mocks bound per tenant (red when the binding is removed);
    - missing_evidence on the TOTAL-mismatch and skipped-line fixtures;
    - maker = checker;
    - pricer = approver;
    - price leakage through `GET /audit/events` and notifications.
- Run `reviewing-feature-security`, `reviewing-deployment-security` and the
  mutation check. Each new guard is shown red when removed.
- A full demo rehearsal on the running stack, as the personas. Record the
  steps in the area file.

## As built (2026-10-06)

### Evals

- `evals/datasets/sales@1.0.0.json`, 10 cases, full security coverage, pinned
  by the release manifest (`eval_datasets`, checksum). Fixtures under
  `evals/fixtures/cases/sales_*.json`, expectations under
  `evals/expected/sales_*.json`.
- Seven graders in `dw_sales.evals.graders`, keyed `sales.<gate>`:
    - `sales.extraction_accuracy`: PRV code, quantity, unit price and
      requested date of every PO line against `purchase_orders.json` (516
      fields over 18 documents, accuracy 1.0). A PRV code counts as right when
      the exact mapping equals the sample set's convert list and, for a code
      the list does not hold, when DW1 did not claim an exact mapping (never a
      guess). M15 and M16 must be routed with their reasons.
    - `sales.findings_recall`: disposition and findings of every message
      against the README's "Messages" table (26 findings over 32 messages,
      recall and precision 1.0).
    - `sales.injection_contained` (prompt_injection, M12),
      `sales.scope_binding` (cross_tenant_attack), `sales.never_clean`
      (missing_evidence: M21, M22, M27 refused at `prepare` naming the
      finding; M16 opens no case), `sales.separation_of_duties` (preparer and
      Bravo recorder cannot cross-check; the pricer cannot approve;
      `approvals.decide` approves nothing), `sales.price_confidentiality` (a
      reader without `sales.price.read` finds no price in any answer; nobody
      finds one in the audit rows, case events or notifications; a price
      reader does).
- They run the **real services** in one process (`dw_sales.evals.world`):
  `assemble(...)` as `build_sales` wires it, with an in-memory
  `SalesUnitOfWork` (per scope, copied in and written back on commit,
  refusing what the SQL store refuses). RLS, grants and the store's CHECKs
  stay with the integration suites.
- **Injection, not import.** `dw_evals.runner.run_dataset` takes the graders;
  `compose_graders` refuses a key registered twice. `scripts/run_evals.py` is
  the composition root that adds `dw_sales.evals.GRADERS`; lint-imports keeps
  "Platform does not import contexts". `dw_sales` declares `dw-evals` as an
  extra (`evals`), so no image installs it (`uv export --package dw-api`
  lists no `dw-evals`).
- **Sample set.** A case may name `sample_set: {data_dir, attachments_dir}`;
  Proterial's set, outside git, runs the same graders unchanged
  (`test_a_sample_set_outside_the_package_is_read_from_its_own_directory`).
- One owner for the policy versions: `load_sales_policies` in
  `adapters/policy_files.py`, used by `build_sales` and the eval world.
- **Found:** the README's Design-reply rows (M18, M25, M29, M30
  `attached_to_case`) hold only when Sales recorded the YCBG and sent it to
  Design before the reply arrived. Processed as one batch, they are routed
  `design_reply_unmatched` (and may be processed again later). The findings
  case states those Sales steps (`sales_steps`), and
  `test_findings_recall_fails_when_design_replies_meet_no_waiting_case` keeps
  the dependency visible.

Each grader fails when what it guards breaks (`tests/unit/test_evals.py`).
Production guards were also broken in-process to watch the dataset go red
(a scratch script patched the code in memory, so the developer's `--reload`
API never served a broken guard):

| Guard broken                                         | Cases red                                                                                |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `MockInbox`/`MockSalesCatalog` scope binding removed | `sales-sec-cross-tenant-mocks` (inbox, process-all, M01/M04/M10, every master-data list) |
| `OrderCase._require_not_a_maker` removed             | `sales-exc-maker-checker-order` (the model's own invariant then answers 422, not 409)    |
| `line_total_mismatch` dropped from intake            | `sales-normal-findings`, both `missing_evidence` cases                                   |
| Excel reader reads numbers one decimal short         | `sales-normal-extraction` (125 unit prices), M12 injection, findings, maker-checker      |
| `PriceView.of` shows every amount                    | `sales-exc-price-leakage` (99 prices reached the reader)                                 |

### Demo

- Runbook `sales/dw1-portal-demo/demo.md` (Vietnamese, fictional data), in
  the order of the spec's Done-when.
- `make demo-reset` (`dw_sales.testing.demo_reset`, then
  `scripts/keycloak_dev_users.py`): deletes the Sales rows of the personas'
  tenants only, keeps the audit log, runs the full demo seed. Refuses every
  profile but local/test (`test_demo_reset.py`, red with the guard removed).
- `make test-web-sales`: `apps/web/e2e/sales-demo.spec.ts`, ten stages in
  the runbook's order, every action through the UI where the UI offers it,
  each refusal checked twice (the disabled control with its reason in words,
  and the API's 403/409/404). Runs on 2026-10-06, all on a heavily loaded
  machine (other projects' containers at 130-1200% CPU):
    - 11 passed in 9.8 min, then 11 passed in 7.2 min (cold starts);
    - re-run on the final tree: 9 passed, stage 9 failed, 1 did not run.
      Hà's overview page stayed on the shell's "Loading…" for 60 s; the API
      checks just before it (overview 200, no price, 403 elsewhere) passed.
      Not reproduced or explained; treat as open until a green run on an idle
      machine;
    - a second re-run stopped at stage 3 because the `dw_proterial` infra
      stack (Postgres included) was shut down from outside this session at
      10:51 mid-run. The Playwright
      config now starts a dev-auth API itself unless one answers on
      `E2E_API_URL`, takes both ports from the URLs, and gives its web the build
      directory `.next-e2e` (`NEXT_DIST_DIR`), so it never shares `.next` with a
      developer's running `next dev`.

- **Fixed on the way (product):** the inbox drew "DW xử lý" only for an
  unprocessed message, so a Design reply routed `design_reply_unmatched` by
  "DW xử lý tất cả" could never be matched from the UI, although the API
  takes a routed message again. `inbox/page.tsx` now offers "DW xử lý lại" on
  exactly those messages; stages 6 and 8 of the walk press it (red without
  it).
- The walk processes M04 alone and sends it back to the customer before
  "DW xử lý tất cả": processed as one batch, Rev.1 (M07) joins M04's case
  before anyone asked for it.

### Security review (`reviewing-feature-security`, whole DW1 feature)

1. **Tenant isolation:** RLS FORCEd on every `sales` table and partition
   (`verify_invariants`, `test_rls_coverage`); object keys
   `{tenant}/{workspace}/sales/...`; mocks bound to one scope. Negative
   tests: `test_sales_isolation.py`,
   `test_sales_api_access.py::test_another_tenants_pic_sees_an_empty_mailbox_and_none_of_alphas_cases`,
   eval `sales-sec-cross-tenant-mocks`. Mutation: binding removed, red.
2. **Authorization:** every route on the verified context, the scope checked
   before reading and again in the service (`test_service_scopes.py`, stores
   that refuse to open); maker/checker and pricer/approver in the case and
   the CHECKs. Negative tests: `test_sales_api_access.py`,
   `test_sales_api_orders.py` (409 "tách nhiệm"), `test_sales_api_quotes.py`
   (403, 409), the evals. Mutation: maker guard removed, red.
3. **Autonomy and approval:** DW1 has no agent tool and no model call
   (decision 13); approval is a case decision until ticket 10 (ADR 0001).
   Nothing in ticket 09 adds reach. Ticket 10 owes the check that a platform
   approval still needs `sales.quote.approve`.
4. **Untrusted content:** attachments are parsed deterministically; M12's
   text changes no value and addresses no draft (`test_order_intake.py`, eval
   `sales-sec-prompt-injection-m12`, which walks M12 to a confirmation draft
   addressed only to the customer's contacts). Mutation: reader broken, red.
5. **Provenance and audit:** the case, its event and the audit row in one
   transaction
   (`test_a_refused_decision_writes_neither_the_case_nor_an_audit_row`);
   audit details are ids and codes (the `allowed` set in the M01 walk); the
   check basis is stamped. The eval scans audit rows, events and
   notifications for prices.
6. **Lifecycle and defaults:** price visibility fails closed (`PriceView`);
   `price_floor_unknown` fails closed; the demo reset refuses deployed
   profiles. Created and not destroyed: artifact bytes after a reset (no
   record points at them; offboarding purges the prefix).

Integration run 2026-10-06: `dw_sales` integration plus the eight `apps/api`
Sales suites, 153 passed.

### Deployment review (`reviewing-deployment-security`)

1. Dev-only surfaces: the Playwright API runs in dev auth mode only as a
   process Playwright starts locally; `validate_for_profile` refuses dev auth
   in uat/production (`test_production_forbids_dev_auth_mode`); the mocks
   answer a deployed profile only with `SALES_DEMO_TENANT_ID` set
   (`test_sales_routes.py`); `demo_reset` refuses deployed profiles.
   `dw_sales.evals` ships in the wheel but imports `dw_evals`, which no image
   installs: imported there, it fails rather than runs.
2. Responses: no new route. Downloads stay `attachment`, `no-store`,
   `nosniff`.
3. Secrets: the Playwright dev secret default is a local HS256 key for a
   process that refuses to start in a deployed profile; no compose or
   `.env.example` change.
4. CORS: the e2e API's origin comes from `DW_PUBLIC_WEB_URL`, local only.
5. Outbound URLs: none added.
6. Images: none added or changed; `uv.lock` adds only the `evals` extra,
   which no image installs.

### Open

- The release manifest pins the dataset file, not the fixtures,
  expectations or the truth files they name (`purchase_orders.json`, the
  README): editing an expectation changes the grade without changing the
  release ref. A platform question (`release_manifest._eval_datasets`), not
  fixed here.
- The approval panel does not refresh after the approver renders the
  document preview from "Tệp và thư nháp DW1 soạn" (`approval.tsx`
  `useLatestPdf` reads the file list on its own): it says "Chưa có bản xem
  trước" until the page is reloaded. The walk and the runbook reload; a fix
  belongs with the page.
- The preview PDF is not rendered at submit: the approver renders it. Whether
  submit should render it is a product question for Đạt.
- CI does not run the browser walk (as for `make test-web`); Đạt owes that
  decision with the web vitest one.
