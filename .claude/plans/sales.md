# Sales (Proterial Vietnam) — DW1 Đơn hàng & Báo giá

This repo became the Proterial product repo on 2026-10-02: `origin` is
`github.com/Datpt0205/dw-proterial` (public; Đạt keeps it public for now).
The platform seed stays in `Datpt0205/codebase`. DW01 (procurement) keeps
running in `C:\Users\phung\dw` and gets no new features; it moves here when a
Purchasing DW for Proterial is signed (estimated 30–51 person-days).

## State

- Context `dw_sales` scaffolded with `scripts/new_context.py` (14 seams).
- Feature in progress: `sales/dw1-portal-demo/` — DW1 end to end on mock data
  behind real ports. Spec: `sales/dw1-portal-demo/spec.md`. Tickets 01–27 in
  `sales/dw1-portal-demo/issues/`.
- 2026-10-12, ticket 12 triaged: what needs nothing from Proterial became
  17 and 19–27 (rule overrides, legacy encodings, delivery schedules,
  support without prices, telemetry, SQL overview, ClamAV and worker
  parsing, public-repo guard, legacy Office and OCR), all ready-for-agent;
  12 keeps what waits on the requirements doc (needs-info). Đạt sent the
  requirements doc to Proterial (confirmed 2026-10-12). Order agreed with Đạt:
  13 → 14 → 17, then 19–27.
- 2026-10-12, ticket 15 built (uncommitted; "As built" in the ticket): a
  `value_uncertain` is corrected per field with a typed value
  (`POST /orders/{id}/findings/{key}/corrections`), kept beside the value as
  read (migration `33f444c15062`), and the upload file, the cross-check sheet
  (`sales_documents@1.1.0`) and the drafts print the entered value; the
  corrected line's checks (header: PO-level checks) run again and a finding
  whose values did not change keeps its decision. Reviewed the same day: a
  revised order's change list now carries the corrected value, and the
  findings card offers the sheet note only when the case would take it.
- 2026-10-12, tickets 13, 14 and 17 built (uncommitted; each ticket's "As
  built" has the detail and its mutation checks):
    - 13: the quote page reads the artifact list once (`useCaseArtifacts`)
      and hands it to the files panel and the approval panel, so a rendered
      preview shows without a reload; the walk's `page.reload()` is gone
      (the walk itself was not run);
    - 14: a cross-check decision the run cannot apply is recorded on the
      order (`unapplied_decision`, migration `58184771c541`) and in the
      audit (run, approval, reason code), and "Gửi kiểm chéo lại"
      (`POST /orders/{id}/resend-cross-check`; the Bravo recorder, or the
      head with the new `sales.order.resend_cross_check`) raises a new
      approval; `bravo-entry` on an order already in Bravo no longer
      withdraws its pending cross-check. The platform's resume payload now
      names the approval (`approval_id`), and its in-memory run store has
      `active_since`: both are platform code changed in this repo, owed
      upstream;
    - 17: the head reassigns a case (`PUT /orders|quotes/{id}/assignee`,
      `sales.case.assign`, migration `934101cde272`), eligibility from
      `ScopeHoldersPort.holding`, audit with old and new ids, the new
      assignee notified.
      Found while running the integration suites: `ck_approval_requests_sales_stamped`
      (`a64b918fc1f2`) lets a `sales.` approval with a NULL `required_scope`
      through, because `false OR NULL` is NULL and a NULL CHECK passes; its two
      tests fail (`test_sales_constraints.py`, `[sales.quote-None]`,
      `[sales.order.cross_check-None]`). **Closed 2026-10-12 by migration
      `d9e73228e7d7`**: the constraint, same name, now reads
      `coalesce(required_scope, '') LIKE 'sales.%'`; validated on ADD, so an
      unstamped Sales row already in the table stops the upgrade (measured on
      a scratch database: "violated by some row"); downgrade restores
      `a64b918fc1f2`'s definition. Both tests red before, green after.
- 2026-10-12, the gaps left in the demo flow became tickets 13–18, each
  checked against the code that day (the Open items below point at them):
    - 13 the quote approval panel sees a new preview without a reload
      (ready-for-agent);
    - 14 an order whose cross-check decision failed to apply can be
      cross-checked again (ready-for-agent; wider than the race noted under
      ticket 10: any version bump between decide and apply strands it);
    - 15 `value_uncertain` corrected per field, and the upload file prints the
      correction (done 2026-10-12, uncommitted, reviewed; re-run the corrected line's checks, plus the total check);
    - 16 a worker lane processes new mail (done 2026-10-12, uncommitted:
      the worker's `sales_inbox` lane acts as DW1's service account per
      tenant, role `sales_dw1` = `sales.inbox.process` only, migration
      `af154486381e`, resolved by `SqlMembershipLookup.find_service_access`
      and cut to that one scope; one run per message, oldest first; the
      message log's (workspace, message_id) key refuses a second disposition
      on a case; pause state only; 60 s tick; the lane audits as
      `system:sales_inbox`. DW1 is built for both processes by
      `dw_sales.adapters.assembly.build_dw1`. The lane is on by default;
      `DW_WORKER_SALES_INBOX_LANE=false` for the walk-through by button,
      which demo.md now says. Reviewed 2026-10-12: the lane re-reads each
      message and the pause just before its run, so it never re-processes
      one a person routed mid-tick nor spends a run a pause would refuse;
      worker image not yet scanned);
    - 17 the head reassigns a case (G22, moved out of 12; ready-for-agent);
    - 18 CI runs vitest and the DW1 walk (ready-for-agent 2026-10-12: vitest on
      every push; the walk on `main` and nightly, blocking after three green
      runs in a row). Built and adversarially reviewed 2026-10-12, not
      committed; not yet seen on a runner (the ticket's "Still to prove").
- Tickets 01 and 07 committed 2026-10-03; 01 follow-up (fixtures M13–M32,
  mock Bravo history, open YCBG list, snapshot as_of, one SourceAnchor) and
  02/03 reworked to the amended spec, adversarially reviewed and committed
  2026-10-05 (dw_sales 683 unit tests; import contracts 9 kept).
- 2026-10-03, conformance review done. The review itself stays outside git
  because it quotes Proterial's survey. The plan gets the mechanics right
  (reading, mapping, checks) but not the process:
    - WIV-03-012 steps 9–10 are missing: no cross-check by a second Sales
      member, no joint confirmation. One PIC can approve and confirm alone.
    - The revised-PO loop dead-ends: a correction request plus Rev.1 never
      yields an upload file.
    - The confirmation carries no delivery date, and the short-LT rule counts
      from the PO date, not the date the PO was received.
    - Quotation steps 2, 5, 6, 8, 9, 11 and 12 have no state or artifact.
    - Roles are three generic scopes, so the walk-through only works as
      platform_admin.
    - ADR 0008, 0009 and 0010 decisions are not followed, nor recorded as
      exceptions.
- 2026-10-03, spec and tickets amended per the review: the process map, the
  actor/role/scope table, maker/checker, price visibility, per-finding and
  per-message dispositions, check basis, the ADR 0009 source gate and the
  interim behaviour per open decision are in the spec. 02/03 are amendment
  tickets, 01 has a fixture follow-up, 11 seeds the personas, and 12 holds
  the production-only gaps. Context glossary and ADRs 0001–0003 are under
  `packages/python/dw_sales/`.
- 2026-10-03, a second pass checked the amendments against the survey and
  the requirements doc. It corrected three process facts: the short-LT
  rule uses the standard lead time; the PIC still compares the Bravo entry
  with the PO when recording the order number; NOC/ESF blocks confirmation,
  not preparation. The cross-checker must also differ from the Bravo
  recorder. The quotation approval matrix waits for Proterial (ticket 12).
- 2026-10-05, ticket 05 built (`3557de8`): 42 routes under
  `/api/v1/sales`, each on the verified access context, scope before the
  idempotency key, amounts left out by one mapper per resource, ids-only
  mutation answers. The items owed into 05 landed: the case carries every
  earlier maker and refuses the cross-check itself (409 "tách nhiệm"), quote
  cases stamp rules version and catalog `as_of` (the parser is the
  request's), one actor id type (principal uuid, migration `075dca5a6168`),
  audit rows in the same transaction, the Design mailbox in
  `sales_quote_rules@1.1.0`, and `price_floor_unknown` (fail closed, Đạt did
  not object). `sales_kpi@1.0.0` shipped. Details in the ticket's "As built".
- 2026-10-05, ticket 06 built (`2f737ca`): every artifact in the table
  rendered from the case by `POST /orders|quotes/{id}/artifacts`, listed by
  `GET .../artifacts`, stored under `{tenant}/{workspace}/sales/{case}/{id}`
  with template `id@version`, case version and sha256, downloaded only in its
  state and at the case's current version (409 `stale_artifact` after an
  edit). Copy `sales_emails@1.0.0`, `sales_documents@1.0.0` and policy
  `sales_bravo_upload@1.0.0` (MOCK) are pinned by the manifest. reportlab
  stays a runtime dependency (G38). The confirmation draft opens at
  `confirmed`, not `cross_checked`; details in the ticket's "As built".
- 2026-10-06, ticket 09 built (`2284d3c`): eval dataset `sales@1.0.0`
  (10 cases, full security coverage) graded by seven `sales.*` graders that
  live in `dw_sales.evals` and run the real Sales services in one process
  over an in-memory store; `scripts/run_evals.py` is the composition root
  that injects them, so `dw_evals` imports no context. Pinned in the release
  manifest. Demo runbook `sales/dw1-portal-demo/demo.md` (Vietnamese),
  `make demo-reset` (start state), `make test-web-sales` (Playwright walk).
  Security reviews (feature and deployment) recorded in ticket 09.
- **What "done" means for the demo:** the personas walk the spec's Done-when
  on the local stack from `make demo-reset`, the walk is automated
  (`make test-web-sales`), and `make eval-smoke` scores extraction and
  findings on the mock set. It is a demo on fictional data, and nothing
  production-only exists. What remains is ticket 12 (production hardening:
  sandboxed parsing, support access, tenant overrides, rules approval, DW1's
  service principal, Proterial's real inputs).
- 2026-10-06, ticket 10 committed (`8d098b3`): DW1 runs on the agent runtime
  (dw_sales ADR 0004, Proposed, supersedes ADR 0001; spec decision 5
  amended). "DW xử lý", submit and the Bravo entry are each a DW1 run
  (`configs/workers/sales.yaml`, graph 1.0.0, pinned), counted by the
  runner's `RunAllowancePort` check. Submit and the Bravo entry pause on a
  platform approval (`sales.quote`, `sales.order.cross_check`) stamped with
  its decide scope (`sales.quote.approve`, `sales.order.cross_check`, never
  `approvals.decide`) and naming every maker; `sales.` is strict and has a
  Sales decision guard; the run applies the decision. The context decide
  routes are gone; the pages decide on `decision.approval_id` with a
  required comment. Platform gained: stamped decide scope, makers, decision
  guard, inbox audience filter, withdraw by subject, an in-memory runtime
  the eval world uses. Walk: 11/11 passed on the third run (`make demo-reset`, `make test-web-sales`); the two before timed out at different steps under machine load (a draft render at stage 1; M29's reprocess at stage 8, whose run row shows 107 s against 0.2 s measured idle). Details and open items in the ticket's
  "As built".
- 2026-10-07, platform `96f95ad` merged (`chore/platform-merge-2`): Sales
  approvals moved onto the platform's approval model (dw_sales ADR 0004
  amendment). The stamp is the `required_scope` column (migration
  `ac31ff0f2087` copies a payload `decide_scope` into it and renames the
  key; `DecisionAsked` still reads `decide_scope` from runs paused before);
  deciding asks `approvals.decide` AND the stamp, so `sales_pic`,
  `sales_head` and `sales_quote_approver` gained `approvals.decide`; seeing
  is the platform's `ApprovalAudience` (the product's own filter and its
  `test_approval_audience.py` are gone). The purchasing manager now gets
  404, not 403, on a Sales request. Kept: makers, `CaseDecisions.check`
  (async guard, longest-prefix keyed), withdrawal (reads the approval as
  the run's requester). Platform ADR 0004 is `docs/adr/0011` here.
- 2026-10-08, platform `ab33703` merged: the antd-only web (see
  `web-ui.md`), decision audit (one `approval.decided` row per decision, the
  platform's; Sales writes none of its own), append-only decisions, 401 for
  a missing bearer (`test_sales_routes.py` follows), `ScopeHoldersPort.holding`
  takes the tenant id as the platform's does, Sales role labels in the one
  role-label table, `/approvals` links a Sales approval to its case. DW1
  renders no prompt (spec decision 13), so the platform's prompt containment
  versions no Sales prompt and `sales@1.0.0` is unchanged.
  **Owed from that merge (Docker became unavailable mid-pass):** the
  integration suites ran once before it stopped (729 passed, 6 failed: the
  five new `ck_approval_requests_sales_stamped` cases on a test bug, and
  `test_sales_api_access.py` still expecting 403 for a missing bearer); both
  are fixed and NOT re-run. Playwright (sales spec, platform specs) and
  `make check-rerank` were NOT run. `make db-migrate` did run on the dev DB
  (head `a64b918fc1f2`) before the stop.
- Next: 12 (needs-triage). Owed by the API to the pages:
  the PO-read attributes for the candidate picker, order due dates in
  my-work, Vietnamese refusal messages, server time. (Role names and
  permission-set scopes landed in `/auth/bootstrap` on 2026-10-05; the web
  stopgap roster is gone.)
- Offboarding export reads a partitioned parent and its partitions, so audit
  and event rows come out twice (pre-existing; platform).
- Open from the 02/03 pass: routing reasons (complaint, sample request,
  delivery change) are keyword tables, against operator guideline §6,
  accepted by the spec for the demo; ticket 03 added the ledger to the mock
  catalog; the sales policy files stayed at 1.0.0 (never released).

- 2026-10-05, UI compared with the E-HSDT v3 prototype (screenshots in the
  session scratchpad): the Sales pages are antd v6 but keep the platform's
  navy theme and system font, the header shows the platform menus in
  English, and lists are plain tables. The prototype uses Be Vietnam Pro
  (JetBrains Mono for codes), a bright primary, a Sales-only header with
  counts, a "Cần xử lý" panel, Segmented tabs with counts, search/sort and
  two-line rows. Primary decided `#0071e3` by Đạt 2026-10-05.
- 2026-10-05, restyle built (`92b155a`): theme from the prototype
  (`web-ui.md` has the mapping and the nearest-passing values); Sales-only
  bar for a PIC/head/viewer with counts (my-work, unprocessed mail) and the
  Vietnamese role name; the four lists on the prototype's list pattern
  (breadcrumb, summary line, "Cần xử lý", Segmented tabs with counts,
  diacritics-insensitive search, `Intl.Collator('vi')` sort, two-line rows,
  `StatusTag`s, red "còn X giờ" inside a day, assignee avatar; tab/q/sort in
  the URL); order and quote detail with the 4-fact summary strip, the
  procedure card and findings as severity-barred rows. API: bootstrap
  returns `role_names` and the effective scopes (roles + permission sets,
  via `effective_scopes`); OpenAPI and TS types regenerated.
  Left different from the prototype: lists on white tables; no command
  palette; the bar overflows "…" between 992 and ~1250px; customer names come
  from the mock master data (a code it lacks shows the code).
- Dev: realm redirect URIs allow port 3300 only; `.env` sets
  `DW_WEB_PORT=3300`, but `scripts/dev.sh` defaults to 3000, so a run
  without the env var cannot sign in.

## Inputs owed by Proterial

The requirements doc `DW1_Don-hang-Bao-gia_Nhung-gi-can-co_30-09-2026_v1.2.docx`
(kept outside git) lists them: convert list, item master, quotation master
list and LME rule, Bravo upload template, sample POs with their Bravo orders,
mailbox access, AI/data approval, WIV-03-012/023 texts. Sent by Đạt
(confirmed 2026-10-12); answers awaited.

## Slice log

| Ticket | Commit    | What                                                                                                     |
| ------ | --------- | -------------------------------------------------------------------------------------------------------- |
| 07     | `78af2bd` | antd v6 shell: registry on the `antd` layer, theme owns tokens, top navbar, dates/money                  |
| 01     | `b5f990b` | Mock catalog and inbox behind `SalesCatalogPort`/`InboxPort`; 12 fictional emails M01–M12                |
| 02, 03 | `ad467dd` | Amended to WIV steps: maker/checker, dispositions, revised PO, quote steps 1–12; fixtures M13–M32        |
| review | `077d54b` | Security review of the core: Design mailbox, decided_by, scope-bound mocks, confirm_mapping              |
| 04     | `5ed607b` | `sales` schema, RLS by tenant+workspace, maker/checker across revisions, roles, offboarding              |
| 11     | `87ab107` | Demo personas: `dw_sales.testing.seed_personas`, `khoa.lam`/`tam.ngo` in the platform seed, roster fixed |
| 05     | `3557de8` | API routes and scopes, overview/my-work, source gate, pause/resume, actor uuids, `sales_kpi@1.0.0`       |
| 06     | `2f737ca` | Artifacts: upload file, cross-check, drafts, quotation xlsx+PDF; copy pinned; download gates             |
| 08     | `88fb7b6` | Sales pages on the E-HSDT v3 visual language; walked in a browser as every persona, refusals shown       |
| 09     | `2284d3c` | Evals `sales@1.0.0` + graders injected; security reviews; demo runbook, `demo-reset`, Playwright walk    |
| 10     | (pending) | DW1 on the runtime: checker decisions are platform approvals, decide scope stamped, makers refused       |

## Open

- **Sales roles decide unstamped approvals** (owed, Đạt; from
  `ac31ff0f2087`). Every Sales approval type is stamped, and since the
  platform merge of 2026-10-08 the database says so
  (`ck_approval_requests_sales_stamped`, migration `a64b918fc1f2`, NULL
  refused since `d9e73228e7d7`: a `sales.` approval carries a `sales.`
  scope or is not written). That does
  not close the widening: the platform decides on `approvals.decide` AND the
  stamp (`docs/adr/0011`), so `sales_pic`, `sales_head` and
  `sales_quote_approver` keep `approvals.decide` and with it every
  UNSTAMPED request in their workspace (`memory.review` today). Closing it
  needs a platform decision, not a product patch: either a stamp stands in
  for `approvals.decide` (then the three drop it), or the platform stamps
  its own types (`memory.review`).
- From ticket 09 (2026-10-06): the approval panel needed a page reload after
  the approver rendered the preview (closed by ticket 13); whether submit should render the preview
  itself (Đạt); the release manifest pins an eval dataset file but not the
  fixtures and truth files it names (platform); the mock README's
  Design-reply dispositions assume Sales recorded the YCBG first (the eval
  states those steps); CI does not run `make test-web-sales` (ticket 18); the walk passed
  11/11 once, then a re-run timed out on Hà's overview ("Loading…", 60 s)
  under heavy machine load: unexplained until a green run on an idle machine.

- From ticket 06 (2026-10-05): a `value_uncertain` correction is one value
  for a whole region, so the upload file carries the values as read
  (closed by ticket 15, 2026-10-12); an object written before its record commits can be orphaned
  (purged by offboarding); rendering is not stopped by the pause (Đạt to
  decide); the web client types need `pnpm run generate:api-types`.

- From ticket 05 (2026-10-05):
    - The overview loads every case of the workspace; SQL aggregates before
      real volume (ticket 12).
    - The A3 shadow count uses interim conditions (no finding, every line
      exact, an original) until Proterial defines A3.
    - Ticket 08 must render a served PDF page with pdf.js scripting off and
      a sheet grid's cell text as text; a download's file name needs
      `Content-Disposition` in the CORS `expose_headers` if the browser is
      to read it.
    - A pause commits before its notification: a delivery failure answers
      500 while DW1 is paused (a retry answers 409 "đã tạm dừng").
    - The committed OpenAPI snapshot was stale on `main` before 05 (the
      contract test failed); 05 regenerated it, platform drift included.
- Ticket 11 (2026-10-05): the full demo seed is
  `uv run python -m dw_sales.testing.seed_personas` (platform seed, then the
  Sales keys). The new personas sign in through Keycloak via
  `scripts/keycloak_dev_users.py`, which links by email; the realm file was
  not changed. The platform seed resets roles, so a full re-run rewrites the
  Sales keys (same end state); the Sales seed alone writes nothing on a
  re-run. (The `approver_boost` item owed to ticket 10 is closed: a Sales
  approval requires its stamped `sales.quote.approve`, so Diệu's
  `approvals.decide` decides none; tested in the API suite, the unit suite,
  the eval and the walk.)
- From ticket 10 (2026-10-06): the generic Approvals page sends no case
  version, so deciding a Sales approval there would be refused. Closed by the
  platform's `approval-inbox-link` (merged 2026-10-08): `salesApprovalHost`
  in `apps/web/app/sales/_meta/approvals.ts` makes `/approvals` show "Mở hồ
  sơ để quyết định", linking to the case page, instead of the decide
  buttons. An order whose decision passed the guard and then failed in its
  run had no step that raises its cross-check again: closed by ticket 14. Processing's
  audit rows do not name the run (decision rows do). No mailbox consumer
  exists, and one must start a DW1 run to be counted: ticket 16 (built
  2026-10-12; each message is its own counted run).
- Public repo: the repo name and these plan files name Proterial and its
  procedure codes (WIV-03-0xx). Đạt decided on 2026-10-05 to keep the repo
  public and not alias them. Mock data, people and figures stay fictional,
  and Proterial's documents stay outside git.
- Defaults adopted until Proterial answers, taken from the requirements
  doc's own interim answers (Đạt may overrule); the spec's "Interim
  behaviour" table names the policy key or role each answer changes:
    - the cross-check is kept;
    - the signed hard copy stays the quotation approval of record, and portal
      approval is shown as the proposal;
    - only the quotation PIC and the head see other customers' prices;
    - NOC/ESF warns, and the export-control PIC must acknowledge it;
    - quotation steps 11–12 are built on mock data.
- Quotation-time target: under 1 day (Đạt, 2026-10-05).
- UI reference (2026-10-05): Đạt's E-HSDT v3 prototype in `docs/design/`
  (untracked, another product's handoff) is the visual language for ticket
  08; the screen mapping is in ticket 08. `docs/design/` is in `.gitignore` (Đạt, 2026-10-05)
