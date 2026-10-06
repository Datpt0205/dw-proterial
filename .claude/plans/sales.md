# Sales (Proterial Vietnam) — DW1 Đơn hàng & Báo giá

This repo became the Proterial product repo on 2026-10-02: `origin` is
`github.com/Datpt0205/dw-proterial` (public; Đạt keeps it public for now).
The platform seed stays in `Datpt0205/codebase`. DW01 (procurement) keeps
running in `C:\Users\phung\dw` and gets no new features; it moves here when a
Purchasing DW for Proterial is signed (estimated 30–51 person-days).

## State

- Context `dw_sales` scaffolded with `scripts/new_context.py` (14 seams).
- Feature in progress: `sales/dw1-portal-demo/` — DW1 end to end on mock data
  behind real ports. Spec: `sales/dw1-portal-demo/spec.md`. Tickets 01–12 in
  `sales/dw1-portal-demo/issues/`.
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
mailbox access, AI/data approval, WIV-03-012/023 texts. Not sent yet
(2026-10-02).

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

- From ticket 09 (2026-10-06): the approval panel needs a page reload after
  the approver renders the preview; whether submit should render the preview
  itself (Đạt); the release manifest pins an eval dataset file but not the
  fixtures and truth files it names (platform); the mock README's
  Design-reply dispositions assume Sales recorded the YCBG first (the eval
  states those steps); CI does not run `make test-web-sales`; the walk passed
  11/11 once, then a re-run timed out on Hà's overview ("Loading…", 60 s)
  under heavy machine load: unexplained until a green run on an idle machine.

- From ticket 06 (2026-10-05): a `value_uncertain` correction is one value
  for a whole region, so the upload file carries the values as read (domain
  follow-up); an object written before its record commits can be orphaned
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
- From ticket 10 (2026-10-06): the platform's generic Approvals page lists
  Sales approvals to their deciders but sends no case version, so deciding
  there is refused (the page is shadcn and moves to antd first); an order
  whose decision passed the guard and then failed in its run (a one-request
  race) has no step that raises its cross-check again; processing's audit
  rows do not name the run (decision rows do); no mailbox consumer exists, and
  one must start a DW1 run to be counted.
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
