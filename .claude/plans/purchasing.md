# Purchasing (Proterial Vietnam) — DW2 Mua hàng

DW02 (the contract's Phụ lục 02, `sales.md` State 2026-10-30): six functions,
PR intake (email, Bravo, form, scanned paper) → cross-check (quotes, purchase
history, budget, approval limits) → supplier RFQ and comparison → draft PO
(Bravo import file) → supplier confirmation and delivery tracking → brief and
Q&A. Built per `docs/adr/0013` on mock data until Proterial's purchasing
samples arrive. The model on premises only reads and writes; code checks and
decides (dw_sales ADR 0005/0006/0007, as DW2 applies them).

## State

- 2026-11-01, **ADR 0013 decision 1 done**, one commit each, behaviour unchanged,
  unit suite green after the five (4037 passed), lint-imports kept:
  malware port + clamd → `dw_platform` (`0c75ddb`); figure/amount check →
  `dw_agent_runtime.model.figure_check`, the names `DW1`/`DW2` now the
  caller's (`a5f75ac`); the one-call model door (`caller_run`,
  `InterpretationPort`, `GatewayInterpretation`) → `dw_agent_runtime`
  (`9485f97`); `InboundMessage`/`AttachmentContent`/`mail_parts` →
  `dw_platform.domain` (`a0be24d`); outbox folder → `dw_platform` (`43908c2`).
- 2026-11-01, **scaffold** (`e0fb115`): `make new-context NAME=purchasing`, all
  generated seams; the first `independence` contract (Sales ↔ Purchasing).
- 2026-11-01, **slice 1 — PR intake (DW02 function 1), done**:
    - Form: `POST /api/v1/purchasing/requests` (`purchasing.request.intake`,
      Idempotency-Key) held to the tenant's form rules (422 naming
      `missing:<field>`, `too_many_lines`, `currency_not_allowed`), a case
      `received`, stamped `rules_ref`, audited `purchasing.request.received`.
    - Mail: `POST /mail/{id}/read` — the sender must be one of the rules'
      `internal_domains` and pass SPF/DKIM/DMARC, else a person reads it
      unread by any model; then `purchasing.pr_mail_reading@1.0.0` returns
      spans only, code finds each as a whole token run in the newest part,
      parses quantity/date/currency, refuses the whole request on any span it
      cannot find; requester = the verified sender. Settled once
      (`purchasing.mail_outcomes`, append-only). No model / no answer: 503,
      nothing recorded.
    - Reads: `GET /requests` (keyset), `/requests/{id}`, `/mail`
      (`purchasing.request.read`).
    - Rules: `configs/policies/purchasing_rules@1.0.0.yaml` (platform layer);
      a tenant's version from the platform's `PolicyOverridePort`, validated,
      refused (409) when unreadable or reusing a platform version — never a
      fallback.
    - Data: migration `2d0c58dc3806` (schema `purchasing`, `cases` with the
      aggregate in `body`, `mail_outcomes`; RLS tenant AND (workspace OR
      scope); roles `purchasing_buyer`, `purchasing_viewer`).
    - Checks: unit 50 + API routes 11; integration 8 on Postgres (RLS by
      tenant/workspace with no WHERE, unscoped session reads 0, no
      UPDATE/DELETE on outcomes, CHECKs = enums, roles, service end to end
      with a tenant override); `test_rls_coverage`, `test_privileges`,
      offboarding, migration round trip green. Eval
      `purchasing_pr_intake@1.0.0` 5/5 with full security coverage (red with
      the span check off). Mutations, each red: internal sender, verified
      sender, form rules, mail rules, intake gate, read gate, route guards,
      settled-once, requester from sender, header spans, line quantity,
      token boundary, duplicate line, tenant-rules fallback, platform-version
      reuse, mock inbox scope.
    - Found on the way: the date parser read `20/11/2026` as 2020 (unit
      test); the outcome was written before its case (FK, integration test;
      the in-memory store now refuses it too); Sales' route walks lacked
      `session_id` since `22da090` (`4031bc8`).

- 2026-11-01, **slice 2 — cross-check + approval limits (DW02 function 2), done**:
    - `GET /requests/{id}/check` (read) and `POST /requests/{id}/submit`
      (`purchasing.request.submit`, `case_version`, Idempotency-Key).
      `domain.checks.cross_check` over master data behind `MasterDataPort`
      (mock `data/master.json`, demo scope only): reference price = lowest
      valid quotation, else last price paid, else the estimate; amount
      unknown when a line has none; findings as codes.
    - `purchasing_rules@1.1.0` adds `approval`: bands (`up_to` inclusive, the
      last open), the scope each is decided by
      (`purchasing.approve.tier1..3`, the migration's), a label, the price
      tolerance and the findings that escalate to the last tier. Unknown
      amount or another currency → the last tier. Rules without `approval`
      send nothing (409 `no_limits`).
    - Sending stamps the check and `ApprovalAsked` (approval id, scope,
      label, version, sender) on the case and opens a run-less platform
      approval `purchasing.request` in the same transaction, `required_scope`
      the tier's, makers = receiver + sender. The API makes `purchasing.`
      strict and registers `RequestDecisions` (refuses another approval of
      the case or a stale `subject_version`); the worker settles
      `purchasing.request.decided` (`RequestSettlement`: outcome from the
      approval row, read with the stamped scope, idempotent).
    - Migration `911fdfb96d5e`: statuses, generated `approval_id` (unique per
      tenant), `ck_cases_sent`; buyer + submit; role `purchasing_head`
      (tier1, tier2); permission set `purchasing_director_approver` (tier3).
    - Checks: unit 75 + API routes 14 + worker handler; integration 10 (the
      platform's own approval flow: maker refused, empty reason refused,
      another tier's holder finds nothing, stale version refused by the
      guard, outbox event, settlement idempotent, another tenant finds
      nothing; `ck_cases_sent`; roles and permission sets cover every
      approve scope); eval `purchasing_pr_approval@1.0.0` 4/4 (red with
      escalation off). Mutations, each red: expired quote, highest quote,
      partial-sum amount, other-currency price, tolerance, over budget,
      unknown-amount escalation, escalation, inclusive limit, tier shape,
      submit gate, stale version, sent twice, tier scope stamp, makers, guard
      version, guard approval id, idempotent settle, pending settle, stamp
      not rules at settle, master-data scope, API strict prefix, API guard,
      worker handler. One guard (status beside version) was redundant and
      removed: every write moves the version.

- 2026-11-01, **slice 3 — RFQ + offers + comparison + choice (DW02 function 3), done**:
    - `POST /requests/{id}/rfq` (approved only): suppliers per line from the
      master data (`suppliers_for`: supplies it, quoted it, was paid for it;
      known suppliers only; at most `rfq.max_suppliers_per_line`, rules
      `1.2.0`), reply date `rfq.reply_days`, recipients the supplier's
      contacts. `purchasing.rfq_mail@1.0.0` words it from code's facts (dates
      day first, as the mail writes them); kept only when `figure_check`
      finds no figure outside the facts and `names_amount` none, else the
      template. Nothing is sent.
    - Offers: `POST /requests/{id}/offers` (typed; known supplier, a line of
      the request) and `/offers/from-mail/{message_id}` (verified sender of an
      asked supplier's domain; `purchasing.supplier_quote_reading@1.0.0`
      spans; tied by item code to the lines asked; an unasked item is left
      out; read once).
    - `GET /requests/{id}/comparison`: valid offers in the request's
      currency, cheapest first, totals, need-by met. `POST /selection`: one
      offer per line, total held to the stamped tier `limit` (409
      `exceeds_approved_limit`).
    - Migration `0e9a49b7a6f8`: statuses `rfq_drafted`,
      `supplier_selected`; `ck_cases_sent` rewritten; `ck_cases_sourced`
      (absent jsonb keys read as absent, not NULL); buyer gets
      `purchasing.rfq.prepare`.
    - Checks: unit 95 + API routes 15; integration 11 (the whole flow on the
      SQL store, `ck_cases_sourced` refusals, another workspace finds
      nothing); eval `purchasing_sourcing@1.0.0` 4/4 (red with the comparison
      reversed or unasked items kept). Mutations, each red: supplier cap,
      unknown supplier, RFQ figure check, RFQ amount check, RFQ before
      approval, rfq gate, reply read twice, unverified reply, any sender,
      unknown typed supplier, unknown line, one per line, choice without
      offer, approved limit, expired and foreign offers compared, dearest
      first, offer price span, unasked item recorded, sourcing-state
      validator.

- 2026-11-01, **lift: the spreadsheet cell writer** (`599682d`): DW2's
  Bravo file is the second writer of a workbook a person opens, so Sales'
  G29 cell rule (text never a formula) is `dw_platform.adapters.spreadsheet.put`.
- 2026-11-01, **slice 4 — draft PO + Bravo import file (DW02 function 4), done**:
    - `POST /requests/{id}/po` (`purchasing.po.prepare`; suppliers chosen):
      one order per chosen supplier (`<pr_no>-NN`), lines at the chosen
      offers' prices, names from the master data; refused when the rules
      have no `bravo_po`, a chosen supplier left the master data, or the
      orders' total is not the selection's. The layout and its rules ref are
      stamped beside the orders.
    - `GET /requests/{id}/po/bravo.xlsx` (`purchasing.po.prepare`; the file
      holds prices): drawn from the stamp, byte for byte the same each time
      (openpyxl dates the workbook at save, measured; the date is pinned),
      `no-store`, file name cleaned of `/`. DW2 records nothing in Bravo.
    - `purchasing_rules@1.3.0` adds `bravo_po` (sheet, date format, columns
      from a fixed field set; headers MOCK). Migration `126b205278ad`:
      `po_drafted`, `ck_cases_sent`/`ck_cases_sourced` rewritten,
      `ck_cases_po`; buyer gets `purchasing.po.prepare`.
    - Checks: unit 112 + API routes 16 (the download through the app);
      integration 11 (orders and file on the SQL store, `ck_cases_po`,
      another tenant finds nothing); eval `purchasing_po@1.0.0` 4/4 (red
      with the formula guard bypassed or a gone supplier accepted); the
      other three datasets green. Mutations, each red: po gate (draft,
      file), draft without a choice, stale version, file from the rules in
      force, no-layout rules, price from the first offer, byte stability,
      formula guard, header uniqueness, column order, po validator,
      supplier gone, total mismatch. Two first mutations were too weak or
      unmatched by a test and were redone or closed with one.

## Plan of the unattended run (Đạt, 2026-11-01: DW2 is a real product)

Product rules, the three-level switch per step and the 12-step defaults are
in `CONTEXT.md` ("Automation"). Order, each lift one commit, Sales unchanged:

- Phase 1, the lifts (ADR 0013 decisions 2–3). Reordered against the brief
  for one dependency: learning a template from a file and the master-data
  import both read Excel through the reader, so the reader's split comes
  before them.
    1. rule versions → `dw_platform.application.rule_versions` (+ table
       `platform.rule_versions`, moved with `ALTER TABLE … SET SCHEMA`, rows
       kept); rule words' `apply_changes` generic;
    2. rule drafts (words, file) → platform, worker lane generic;
    3. reader split (wire, transport, generic ops to the platform);
    4. template learning generic (DW2's Bravo PO layout from its file);
    5. model readiness + measurements → platform; DW2's three-level switch;
    6. master-data import; 7. mail drop (`DW_PURCHASING_MAILBOX`);
    8. outbox (sent from the buyer's own mailbox).
- Phase 2: functions 1–4 automated (requester role, auto-submit, re-approval
  past the tier, notices, retention). Phase 3: web pages; then stop and report.

## State of the unattended run

- **Lift 1, rule versions** (`b28a0773`): the engine and
  `platform.rule_versions` (moved by `SET SCHEMA`, rows kept); Sales on it,
  behaviour unchanged, whole unit suite green.
- **ADR 0014** (`0fd851fd`): a lift moves the decisions and their tables;
  each context keeps its queue (drafts, imports, mailbox, outbound).
- **Lift 2, changes in words** (`4a146c58`): `dw_platform.application.rule_words`.
- **Reader split: deferred, on purpose.** DW2 reads attachments through
  ports it declares, satisfied at the composition root by the reader client
  that exists (ADR 0013 decision 2's own interim); the split moves DW1's
  parsers and is its own change, not needed for DW2 to read a file.
- **DW2 rules editor (API)**: `purchasing_rules` registered with the engine
  (migration `633993a6d8b4`: key admitted, `purchasing_configurer`, head
  proposes and approves); `GET /rules`, `GET /rules/{key}/schema`,
  `POST /rules/{key}/versions` (ids only answered); `purchasing.rules` guard
  in the API, settlement in the worker. Policy overrides no longer read.
- **Lift 3, model readiness** (`f29142f8`): `dw_agent_runtime.model.readiness`,
  `platform.model_step_measurements` (moved, rows kept).
- **DW2 switches, three levels** (`purchasing_automation@1.0.0`, migration
  `82cc61f87d6c`): five steps code reads (mail sorting, opening a request from
  a mail, submission, RFQ drafting, PO drafting); ceilings in code; `ai_auto`
  on a step with a model reading waits for a passing measurement
  (`purchasing_pr_mail_reading`, bar 0.9 proposed), else runs `ai_review`;
  a version raising a step unmeasured is refused (409) at proposal, decision
  and settlement. `GET /purchasing/automation`. The lanes that read the
  switches come with Phase 2; the DW2 attest lane (`--attest` for DW2
  datasets, a golden grader with `bar` details) is not built: no step can be
  measured yet, so `ai_auto` on a model step cannot take effect (fail-closed).
- **Requester, "Tôi cần mua…"** (migration `e823f9c57e5a`): role
  `purchasing_requester` (create, read own); `POST /requests/mine/draft`
  (`purchasing.pr_from_words@1.0.0`, spans; nothing stored),
  `POST /requests/mine` (number by code, name and department from the
  directory, `requested_by` stamped); `GET /requests[/{id}]` narrowed to
  the requester's own in SQL (`ix_cases_tenant_id_requested_by_received_at`).
  Eval `purchasing_pr_words@1.0.0` 5/5; 8 mutations red.
- **Retention** (`retention@1.10.0` `tables`, migration `6cbb8581e01e`):
  `purchasing.cases` 3650 days, `purchasing.mail_outcomes` 365 days, **chờ
  kế toán Proterial xác nhận**; lane `purchasing_retention` (hourly) through
  `purchasing.prune_expired` (SECURITY DEFINER, NULL keeps all).
- **Deployed Bravo guard** (rules `1.4.0`, `bravo_po.mock: true`): a
  deployed profile drafts no order with the platform's stand-in layout
  (409 `mock_layout`); a tenant layout of its own drafts.
- **Automation lane + notices** (migration `6971b41fcdf6`): DW2's service
  account (`purchasing_dw2`, registered with provisioning; demo seed owed),
  lane `purchasing_automation` (60 s) reading the five switches: mail read or
  told, cases opened for review at `ai_review`, sent at `ai_auto`, RFQs
  drafted after approval, orders drafted after selection; supplier mail
  (verified, known domain) never read as a PR; approver told at submission
  (makers excluded), requester and sender at decision. A deployed profile
  refuses DW2's mocks (API 503, no lane) until the stored mailbox and master
  data land. Eval `purchasing_automation@1.0.0` 5/5; 8 mutations red (one
  not a guard: `break` on the model down only saves calls).
- **Reapproval past the tier** (rules `1.5.0`, migration `b60b5a0a4c91`):
  a choice above the stamped limit (+ tolerance, default 0) waits on a
  strict `purchasing.reapproval` at its tier (`awaiting_reapproval`), the
  reason worded by `purchasing.reapproval_reason@1.0.0` and kept only when
  every figure is a fact; guard in the API, settlement in the worker,
  approver/requester told. Eval `purchasing_reapproval@1.0.0` 5/5; 8
  mutations red (two first green, closed with tests).
- **Rules changed in words** (`POST /purchasing/rules/{key}/words`,
  `purchasing.rule_change_in_words@1.0.0`): synchronous, nothing stored; the
  platform's `apply_changes` decides, the draft carries an unused number;
  the person sends it through the one door. Eval
  `purchasing_rule_words@1.0.0` 5/5; 3 mutations red.
- **Phase 3, the web pages** (2026-11-01): `apps/web/app/purchasing` on
  the `@dw/ui` shell, its own bar ("DW2 Mua hàng"): "Việc của tôi" (one
  press to decide after the reason the strict approvals require; the
  request shown beside it), "Tôi cần mua…" (model draft, or the hand form
  when DW2 cannot read), "Hộp thư", "Hồ sơ mua hàng" and the case (next
  step, lines, check, RFQ drafts, offers by hand or read from mail, code's
  comparison with the cheapest-in-time pre-chosen, PO + Bravo download,
  history with "Máy đọc"/"Máy viết"/"Mẫu cố định"/"Người nhập"), "Cài đặt
  DW2" (switches by press, rules in words, every change read as words,
  decided by a second person; no code, JSON or YAML shown). Words are
  `CONTEXT.md` "Screen words", tested both ways (web labels, Python mail
  reasons). `PurchasingApi` typed from `generated/purchasing.d.ts`.
  Walked per role with Playwright (requester, buyer, head, director,
  configurer, 360 px) on the demo tenant; `e2e/purchasing.spec.ts` 5/5.
  Defects the walk found, fixed with tests: the director was asked to decide
  a request they could not read (an approver now reads the one case its
  stamped scope decides, 404 for any other); a switch change reused the
  number in force (409; an unnumbered proposal is now numbered by the
  platform); every requester's number was the same for hours (uuid7 head;
  now its random tail, `DW2-<yymmdd>-<8 hex>`); the hand form did not open
  when the model was down; a requester was shown a buyer's button; the
  Bravo file lost its name (CORS now exposes `Content-Disposition`).
  Demo personas: `uv run python -m dw_purchasing.testing.seed_personas`
  (Bình head, Khoa buyer, An requester, Tâm configurer, Giang last tier;
  Dung buyer in Beta).
- **Second pass (Đạt, 2026-11-01: "làm hết những gì làm được")**:
  `50d9cf53` who downloads (`purchasing.po.download`), who reads every
  request, who decides a rule change are permission sets an admin grants;
  retention is each tenant's rule (`purchasing_rules@1.6.0`, `retention`),
  pruned per workspace (`191b591d4ef1`). `8a2bb9d7` DW1 and DW2 pages show
  what a person acts on, how a page works behind "?" (`@dw/ui` `InfoTip`,
  `PageHeader.help`; ui-quality §2). `949ccf35` a buyer names suppliers for
  a line the catalogue lists nobody for. `90576acc` a buyer's paper-request
  page. `46bf5ba0` an RFQ DW2 cannot word waits for the buyer (`pending`),
  never a template. The question list for Proterial:
  `docs/proterial/Cau-hoi-Proterial-DW1-DW2.xlsx` (not in git: repo public).

- 2026-11-02, **stored mailbox + mail drop (Phase 1 step 7), done**:
    - Lift (`e5448863`): `DroppedFile`/`DropFolderPort` →
      `dw_platform.application.drop_folder`, `LocalDropFolder` →
      `dw_platform.adapters.drop_folder` (its first test of its own; the
      path guard mutated red). Sales unchanged.
    - Migration `32c1f04b76d6`: `purchasing.mailbox_messages`,
      `mailbox_attachments`, `mailbox_files` (`stored|duplicate|refused`,
      reason), monthly partitions + DEFAULT, RLS ENABLE/FORCE and the
      tenant AND (workspace OR scope) policy on all six, SELECT+INSERT only
      (UPDATE/DELETE REVOKEd by name: the schema's default privileges give
      them), named by `platform.ensure_time_partitions`; offboarding finds
      them in the catalog (export) and the tenant's purge cascades them;
      `purchasing.prune_mailbox_in` (SECURITY DEFINER) and
      `retention_scopes()` naming mail-only workspaces.
    - `dw_purchasing.application.mail_drop`: lane `purchasing_mail_drop`
      (60 s), audits as `system:purchasing_mail_drop`; waits on a file
      written < 30 s ago or empty; refuses > 20 MB unread or a file the
      reader refuses (recorded, told once to `purchasing.request.intake`
      holders); a folder it cannot list told once a day; a file written
      before the mailbox term is not read (its mail would be pruned, and
      its name is forgotten with it); logs names and code's reasons only.
    - Reader: DW2's own `MailFileReaderPort`; the worker adapts Sales'
      `ClientMailReader` (`dw_worker.purchasing_reader`, ADR 0013
      decision 2's interim). The API reads the store, never the folder, so
      only the worker builds the reader and names the folder.
    - `SqlPurchasingMailbox` is `InboxPort` with `DW_PURCHASING_MAILBOX=stored`
      (API and worker, one variable, tested); `DW_PURCHASING_MAIL_DROP_DIR`
      (worker only; compose on-prem mounts `/purchasing-mail-drop:ro`).
      Missing either, no lane; a folder that is not a directory stops the
      worker. The lane runs where deployed (no mock in it).
    - Retention: `purchasing_rules@1.7.0` `retention.mailbox_days` (30–3650,
      365); the term used is never past `mail_outcome_days` (a mail whose
      outcome is gone reads as unread and would open a second case). Not a
      refusal: a version written before 1.7.0 reads the platform's 365 by
      `read_over`, and refusing it would leave the tenant without rules.
    - **Deployed DW2 still 503**: the mock mailbox is refused there, and
      the stored one is real but the master data is still the mock; the
      second check goes with the master-data import (prompt 2).
    - Checks: unit (drop lane 15, retention, settings, worker wiring and
      reader adapter, API mount); integration 15 (stored once + audit
      actor, copy/twin stored once, refused recorded, oldest first, other
      tenant/workspace reads nothing, unscoped reads nothing by partition
      name, foreign insert refused by policy, no UPDATE/DELETE, partitions
      policed, retention per workspace, offboarding export + purge);
      `test_privileges` (every partition SELECT+INSERT), `test_rls_coverage`,
      offboarding. Mutations, each red: see the commit.

- 2026-11-02, **one inbound flow for DW1 and DW2** (Đạt: "code theo luồng
  như bạn mô tả"): one drop folder (`DW_MAIL_DROP_DIR`, worker only; the two
  `*_MAIL_DROP_DIR` are gone; on-prem mounts `/srv/dw/mail-drop` read-only),
  a subfolder per person named by their sign-in address, written by the one
  flow everyone runs. Each lane reads the subfolders of the members holding
  its scope (`OwnedFolders` over `HolderMailboxes`, i.e. the platform's
  `holding` plus their addresses): DW1 `sales.inbox.process`, DW2
  `purchasing.request.intake`, the same people each lane tells of a refused
  file. A file in the root or in anyone else's folder is not listed, and a
  read of one is refused. Each context still stores into its own tables.
  Checks: unit (OwnedFolders 4; both lanes' wiring), integration
  (`addresses_holding`: holders' addresses lowercase, nobody else's);
  mutations red: unfiltered listing, root files, case, unchecked read,
  every member, address case, each lane's scope, DW2 unfiltered. Assumed,
  to check at the plant: the folder name is the address the person signs in
  to DW with (`platform.users.email`), not an alias.

- 2026-11-02, **the folder in a Teams/SharePoint site, run end to end on
  FPT's tenant** (Đạt and a colleague): a private Team "DW - chuyen thu"
  made by Đạt, no admin and no new licence; `DW-mail/<address>` in its
  library, each folder shared (edit) with its person, the colleague not a
  member of the Team; each person's flow writes there (Site Address
  `…/sites/DW-chuyenthu`, Folder Path `/Shared Documents/DW/DW-mail/<address>`);
  Đạt's PC synced `DW-mail` through "Add shortcut to OneDrive → My files".
  The local worker read it: DW1 stored Đạt's 2 mails (he holds
  `sales.inbox.process`) and not the colleague's; DW2 stored all 3 (both hold
  `purchasing.request.intake`); a second run stored nothing again. Found
  two flow pitfalls: a stale Outlook connection (re-added) and a stray
  character before the Message Id token ("Id is malformed"). Found and fixed
  a deadlock between `ensure_time_partitions` and `prune_mailbox_in` on the
  worker's first tick (`394419a5ebbd`, see the commit). The guides still
  describe the DW account's OneDrive: switching them is Đạt's go-ahead.

- 2026-11-03, **master data loaded from one workbook** (Đạt: "cho upload
  file, đừng input từng cái"): `/purchasing/master-data`. Who configures DW2
  downloads the template (a guide and one sheet per list), fills it in Excel
  and uploads it whole; the `purchasing_master_import` lane scans it and reads
  it in the reader sandbox; the page shows what changes list by list and the
  rows refused (sheet, row, why); "Gửi duyệt" proposes it as the tenant's
  version of `purchasing_master_data` (the head's own applies at once). A
  sheet left out keeps its list. Where deployed, checks read only the
  tenant's lists (the 503 is gone). `dw_purchasing/docs/adr/0001`; migration
  `cf783456f739`; the rule-version store now takes `keys`/`statuses` so no
  settings page loads a master-data document. Checks: unit (domain 10,
  service and lane 16, API 4, worker reader 3, web 3), integration 13
  (RLS both ways, unscoped, constraints, grants, the version applied, the
  settings list); 22 mutations, each red (two tests tightened until red).

- 2026-11-03, **an RFQ sent from the buyer's own mailbox** ("Gửi từ hộp thư
  của tôi" on each supplier's RFQ): `application.rfq_mail`, table
  `purchasing.rfq_mails` (migration da6950544c81), worker lane
  `purchasing_outbound` (30 s). The server refuses an RFQ with no words, a
  recipient no longer the supplier's contact in the master data, a caller
  with no sign-in address, a deployment with no outbox share
  (`DW_OUTBOX_ENABLED`), and a second active mail per supplier. The job goes
  into the same `DW-outbox/<address>` folder and flow DW1 uses: the flow's
  job format is the platform's now (`flow_job`), and DW1's lane leaves the
  receipts of jobs not its own. Failed, unconnected or stalled (30 min) mails
  tell who pressed; a failed one may be sent again. Checks: unit 10 (service
  and lane), API 2, integration 7 (found and fixed a CHECK a NULL error
  passed), web 2; mutations, each red (one test added until red).

- 2026-11-03, **a supplier's reply tied to its RFQ by code**
  (`application.sourcing.reply_case`): the one case still asking that asked
  the sender's supplier (sender verified by the mail system) and whose PR
  number the mail names (the RFQ's subject carries it; a reply keeps it). The
  automation lane's notice now names the PR and links its case; the case's
  offer card lists the tied mails first ("Trả lời hỏi giá này") and picks the
  one when alone (`GET /requests/{id}/rfq/replies`). A mail naming no PR,
  another PR, or two is a buyer's to place, as before. Reading the quote
  stays a buyer's press. Checks: unit 5 new; mutations, each red (two tests
  added until red).

- 2026-11-03, **a PR read from its Excel form or its scanned paper**
  (DW02 function 1, the two sources left): the `purchasing_mail_drop` lane
  now reads every attachment as it stores the mail: ClamAV first (scanner
  down: the tick ends, nothing stored unscanned; infected: never read, bytes
  not kept), an image not read as a form, at most 5 documents per mail, then
  the reader sandbox's new `text.document` op (Sales' reader, ADR 0013
  decision 2's interim): visible cells, a PDF's text layer, a page with no
  text layer by OCR (Tesseract, flagged), `.xls`/`.doc` converted first. The
  text is kept beside the attachment (`mailbox_attachments.reading`,
  migration `2ba8d9cc436c`, CHECKs on its shape and on an infected file's
  bytes); nothing after the lane parses a file. `pr_mail_reading@1.1.0`
  shows the model the mail and the one document; code takes every line from
  one place (mail or file), and a value only a scan holds marks the case
  `read_from.scanned`: it waits for a person (`Review`) whatever the switch,
  in the domain too. To a person, unread: an infected file, several
  documents, one too long to show whole; no PR beside an unreadable document
  is `attachment_unreadable`. The case page says which file and "Bản scan".
  Demo mails P07 (Excel) and P08 (scan). Checks: unit (domain 5, intake 12,
  lane 6, worker adapter 8, reader op 9), integration (reading stored and
  read back, infected bytes absent, CHECK shapes, other tenant/workspace
  reads none), eval `purchasing_pr_intake@1.1.0` 7/7 (an attachment case and
  an attachment prompt-injection case), automation expectations moved for
  the two mails; ~40 mutations, each red (two first green, closed with
  tests). Run live: the rebuilt reader OCRed the fixture scan (2 pages,
  5–7 s, table rows as `|` cells like a sheet's, diacritics partly lost:
  "DON" for "ĐƠN"). Fixed on the way: `test_purchasing_rfq_mails_db` tied on
  `queued_at` and failed by uuid order about half the runs.
- 2026-11-04, **the DW2 attest lane, and the first DW2 step measured**:
  `BARS` named a grader nobody registered (`purchasing.pr_intake_golden`)
  and a metric no grader reported, so `--attest` could measure nothing
  (failure-modes #1). Now the golden grade (`purchasing.pr_mail_golden`)
  reports `golden.right`: the share of the golden mails that reach the model
  settled exactly, each opened request checked line by line (code,
  quantity, unit, date: `expected.golden_lines`), mails settled by their
  sender not counted; the replay must settle all. `run_evals.py --attest`
  finds a dataset's step in either context (`measured_step`) and records
  it as that context's lane (`purchasing.automation.ModelAttestation`,
  `system:purchasing_model_attest`). Dataset `purchasing_pr_intake@1.2.0`.
  **Run live on Qwen3.5-9B (`qwen3.5-9b-dw`), demo tenant: 1.0 (6/6 mails,
  Excel and OCR'd scan included), bar 0.9, passed and recorded**; both
  prompt-injection cases held on the live model. So "Mở hồ sơ từ thư" may
  now be set to "AI tự làm" for the demo tenant (it reads the measurement;
  a scan still waits for a person). On a host, run from the host with
  `DW_ONPREM_MODEL_BASE_URL` at `localhost` (`.env` names the containers'
  `host.docker.internal`). Mutations, each red: bar's grader, bar's metric,
  lines compared, sender mails excluded, replay strict, DW2 dispatch, DW2's
  lane. Found on the way and fixed first (`e95b996b`): the SQL store wrote
  the case body from a hand list that lacked `read_from`.
- 2026-11-04, **function 5a — each drafted order followed** (DW02 function
  5, a buyer's presses; the lane comes in 5b): `domain.tracking` +
  `application.follow_up`, per `po_ref` in the case body (`tracking`,
  migration `13bff35b038b`: `ck_cases_tracking`, a list, only at
  `po_drafted`). Bravo's number typed once by the buyer; a supplier's
  confirmation found by code (verified mail of the order's own supplier
  naming Bravo's number or the `po_ref`: `named_order`, listed by
  `GET .../po/confirmations`), read by spans
  (`purchasing.order_confirmation_reading@1.0.0`,
  `domain.confirmation_reading`), held line by line to the order
  (`differences`: quantity, unit price, a later date, a missing line, a line
  not ordered), kept unaccepted until a buyer accepts it; receipts never
  past what is owed; `GET /orders/late` (a line past the confirmed date,
  else its need-by, less arrived than ordered). All `purchasing.po.prepare`.
  Case page: Bravo's number, the confirmation tag and its differences, "DW2
  đọc xác nhận" per listed mail, "Ghi nhận hàng". Demo mails C01 (Kimura,
  matches) and C02 (Bảo Hộ: 40 of 50 gloves, 22/11, and an injected note).
  Eval `purchasing_follow_up@1.0.0` 5/5 with full security coverage, **and
  5/5 live on Qwen3.5-9B** (golden 1.0; the injected note ignored). Checks:
  domain 17, service 13, routes (403 before the body on all six), DB flow on
  Postgres with the CHECK; 16 mutations, each red (three first green or
  mistyped, closed with tests). Found on the way: a confirmation naming the
  `po_ref` also names the PR number, so it listed as an RFQ reply; demo
  confirmations name Bravo's number, as a supplier's real ones would.
  Not yet seen on a browser (owed with the chat frame's walk).
- 2026-11-04, **function 6 (Q&A) — Hỏi đáp DW2**, DW1's design (dw_sales
  ADR 0007) in DW2's own code: `purchasing.question_intent@1.0.0` reads a
  question (and the session's last 6 turns, both untrusted) into
  `request_status` / `my_work` / `late_orders` / `out_of_scope`; code
  answers through `PurchaseRequests.cases` (the list page's query, a
  requester's own only), never an amount; a PR number the question does
  not write is dropped (`written_in`), part of a number names nothing, two
  matches are not guessed between. `steps` (how the question was read, what
  was looked up) go with each answer: the chat frame's "DW2 đã làm gì".
  Sessions `purchasing.assistant_sessions/_turns` (migration `63b96e56db85`,
  RLS by user, append-only, `prune_assistant_sessions()` at 30 days by the
  `purchasing_assistant_retention` lane). Routes `/assistant/ask`,
  `/assistant/sessions[/{id}]` (any reader). Page "Hỏi đáp DW2" on
  `AssistantChat`. Eval `purchasing_assistant@1.0.0` 5/5, **5/5 live on
  Qwen3.5-9B**. Unit 15, integration 2 (round trip, other person /
  workspace / tenant read none, no UPDATE/DELETE, CHECK, prune), platform
  RLS/privileges/offboarding green; 7 mutations each red (three first
  green, closed with tests). Found on the way: DW2's models named like
  DW1's (`TurnView`, `QuestionKind`, `AskBody`) made FastAPI rename both and
  broke DW1's TypeScript; renamed, and a contract test now fails on any
  `<module>__<Name>` schema. The morning brief (step 12's other half) is
  not built.
- 2026-11-04, **function 5b — DW2 reads supplier mail on its own** (Đạt:
  "tự khớp đơn nếu bước không quan trọng, bước quan trọng người xác nhận"):
  two switch steps, `quote_reading` and `confirmation_reading`, each waiting
  on its own model reading (`purchasing_supplier_quote_reading` on
  `purchasing_sourcing`, `purchasing_order_confirmation_reading` on
  `purchasing_follow_up`, bars 0.9 on `golden.right`), in
  `purchasing_automation@1.1.0` at `ai_auto`; a tenant version written
  before them, in force, is read over the platform's (`read_over`) and
  takes its level, still waiting on the tenant's measurement; read on its
  own (a released file) the two are `person` (corrected 11-04: the 5b
  commit said a tenant version reads them as `person`). The lane ties a
  verified supplier's mail by code to the one order it names
  (`named_order`, the oldest 500 drafted cases) or the one case asking
  (`reply_case`): at "AI tự làm" a quote is read into its offers (the
  buyer told to compare and choose) and a confirmation that differs in
  nothing is accepted (`only_if_same`); one that differs goes to the buyer
  at every level. Handled there, the mail is settled `supplier` with its
  case (migration `ad62389cc25d`: the disposition, its shape, the two
  steps in the measurements CHECK); a mail about nothing waiting is told
  once and left unread, and no longer takes a slot of the 20 reads a tick.
  **Live on Qwen3.5-9B, demo tenant: both 1.0, passed and recorded**, so
  both run on their own there. The live grader had run the scripted
  "invented price" case on the real model, which reads well, so it failed
  for the wrong reason: scripted cases now keep their script live. The
  confirmation's prompt-injection case also runs the lane at "AI tự làm"
  (never accepted, the buyer told). Also: DW2's lane now runs where
  deployed, on the stored mailbox (the mock refused, as the API refuses
  it); before, every DW2 switch did nothing on UAT and production.
  Mutations: see the commit.
- 2026-11-04, **5b's rest and the morning brief** (Đạt: "ok làm đi"):
  - `delivered` (Đã nhận đủ hàng): the receipt that completes every line of
    every order moves the case there, code's, audited
    `purchasing.case.delivered`; the case refuses more receipts and is never
    late. The domain refuses a delivered case with anything owed.
  - Late lines told: the lane tells the buyers each line past its date
    (confirmed, else need-by) once per (order, line, date). `late` now
    counts in the plant's day (it counted UTC's, a day behind from 00:00
    to 07:00). `automation_scopes_due()` also returns a workspace with
    orders still followed. Migration `e13dd31820b5`.
  - The brief (`domain.brief`): each working day from `brief.at` at the
    plant (`purchasing_rules@1.8.0`: 07:30, Monday to Saturday, as DW1's;
    Proterial's to set), counts only: the buyers their states and late
    lines, whoever reviews what DW2 read their queue, each approver the
    requests stamped with their own scope. Once per person and day by its
    source key; nothing sent to someone with nothing waiting. No switch
    for either: they tell, they decide nothing.
  - Corrected on the way: the 5b commit said a tenant's older automation
    version reads the new steps as `person`; in force it is read over the
    platform's (`read_over`) and takes its level. Tests now cover both
    paths. Mutations, each red: closing, "in full", the domain's refusal,
    the plant's day, the lane's late step, the web's disabled receipt;
    the brief's time, days, zone, an approver's own tier, late lines.
- 2026-11-04, **walked on a browser** (local stack, Qwen on Ollama, as the
  buyer `khoa.lam`): home, a case with orders, recording the last receipt
  (the case turns "Đã nhận đủ hàng", the form locks), Hỏi đáp DW2 (status,
  my work, late lines, answered from live data), the notices. Fixed from
  what it showed: the brief came as one notice per role, so a buyer who
  also reviews got two; it is one per person now (the lane asks the
  platform who holds each scope, `HoldersPort`, DW2's own account left
  out). A supplier's mail tied to nothing yet was told as a quote to read;
  it now says nothing ties it yet and that recording Bravo's number lets
  DW2 recognise a confirmation. The case history never showed Bravo's
  number, the confirmation or receipts (since 5a); it does, and "Đã nhận đủ
  hàng". The chat frame showed nothing while a first answer was coming (a
  cold model takes about a minute): it shows the question and "DW2 đang trả
  lời…" (`@dw/ui`, DW1's too). Not walked: DW1's "Xác nhận cả dòng" (the
  demo reads no request by model); its web tests cover it.

## Next

1. Đạt reviews Phases 1–3 (this report), the pages on a browser.
2. The rest of Phase 1, each its own session: the Bravo layout learned from
   Proterial's file. The case page of a scan-read request walked in a
   browser with the local model. Measured on mock mail only (11-04): re-run
   `--attest` on Proterial's real PRs once they arrive.
3. The plant's flow (Đạt, 2026-11-02: set up and integrated later, prepared
   now): the one flow for every person, `DW-mail/<address>` in a private
   Team's SharePoint library (measured 2026-11-02), the plant PC's share at
   `/srv/dw/mail-drop`
   (`infra/onprem/README.md`; the two Word guides updated to it). Then a
   live run as ticket 43's, with a buyer's folder and a PIC's. Which mailboxes it exports (the shared purchasing one
   or each buyer's) is settled then. Code and compose are ready
   (`DW_PURCHASING_MAILBOX=stored`); then a live run as ticket 43's.
4. A reminder to a late supplier, worded by the model for a buyer to send
   (step 11's other half); only the buyer's notice is built.
5. Whether the brief and Hỏi đáp are used: count questions and their
   `out_of_scope` share after a few weeks live, and drop what nobody uses.
6. Bars and live measurements for DW2's other model steps (a sentence to a
   PR, an RFQ's wording): the PR mail, the quote and the confirmation
   readings have theirs (11-04).
7. A sent request cannot be withdrawn (a question on the Proterial list).

## Not done, on purpose

- Bravo's number is typed: nothing reads it back (Bravo has no connection).
  `late` and the brief read the 500 oldest open cases and log at that
  bound; a case leaves `po_drafted` once everything arrived. Both run each
  lane tick (60 s); the notices' keys keep them once per day or date.

- A purchase approval is decided on the web only: no subject version is
  registered for the Zalo decision command.
- A sent request cannot be withdrawn or edited yet; a rejected one stays
  rejected (a new request is a new case).
- RFQ drafts are not sent: the outbox folder (`dw_platform`) can carry them
  from the buyer's mailbox, as DW1's mails go; wiring it is the next step
  after the pages.
- A supplier's reply is tied to its RFQ by the PR number it names, not by
  thread headers (the flow sends, so DW2 never holds the sent Message-ID).
- The Excel PR form and scanned paper are read through Sales' reader until
  it is split (ADR 0013 decision 2). Bravo as a source: no connection.
- A phone photo of a paper request (JPEG/PNG) is not read: only a PDF scan
  is OCRed. A scanner's own text layer (a "searchable PDF") is read as text,
  not flagged as OCR, so such a case is not held for review by that rule.
- A mail with two documents is a person's, even when one is a drawing.
- A mail stored before 2026-11-03 has no reading: it is read from its words.
- No offsets kept for a mail's spans (DW1 keeps anchors): the mailbox is the
  mock; anchors come with the mail drop's move (ADR 0013 decision 3).

## Decisions Đạt owes (Purchasing)

- **A confirmation dearer than the order** (2026-11-04): a buyer may accept
  it; the difference stays recorded and shown, and nothing in DW2 or Bravo
  changes the order's price. Whether a higher confirmed price must go back
  for approval at its tier (as a choice past the tier does) is Đạt's or
  Proterial's call.

- ~~**Internal mail in DW's store**~~ Decided by Đạt 2026-11-02: kept and read,
  since the model runs on the plant's own host and nothing leaves it; not a
  question for Proterial.

- **Who configures DW2**: built as `purchasing_configurer` (proposes) and
  the head (decides, and applies their own at once, as a Sales head). Whether
  Proterial wants the director, not the head, to decide limit changes.
- **Retention**: now the tenant's own setting (10 years / 365 days by
  default, `purchasing_rules@1.6.0`); Proterial's accountant sets it.
- **Who requests**: built as `purchasing_requester` (own requests only).
  Proterial to say how a request DW2 opens is numbered (code's
  `DW2-<yymmdd>-<8 hex>` today) and whether Bravo's PR number replaces it.
- **Who reads a request to decide it**: built as the holder of the scope
  the approval stamped, that one case only while it waits (the director
  reads nothing else). Whether directors should read every request.
- **Bravo import template**: the real column headers, sheet and date format
  of Proterial's Bravo PO import (the mock's are invented), and whether one
  file per PR or one per supplier. A tenant rule, so no deploy when it lands.
- **Who may download the PO file**: a permission set the tenant's admin
  grants (`purchasing_po_downloader`); the buyer holds it by role.
- **Stored mail**: kept 365 days by default (`retention.mailbox_days`),
  never past the mail outcomes'; Proterial's accountant sets it.
- **Re-approval past the tier**: built (goes back at the tier its total
  names, tolerance 0 by default). Proterial to give the tolerance, if any.
- **Paper requests** (2026-11-03): built as a PDF scan mailed to the buyer
  (or the plant's copier mailing it), read by OCR and always held for a
  person. Proterial to say how paper reaches Purchasing (copier to mail?
  which sender: the copier's address must be the company's and pass
  SPF/DKIM, else every scan goes to a person), whether phone photos must be
  read, and a sample of their PR form (Excel and paper) to measure OCR on.
  Read by a model from 11-12 (`sales.md` State, "Scans and handwriting"):
  Qwen3.8's vision, else PaddleOCR-VL or a small CPU model, Tesseract kept.
  The requester of a forwarded scan is the forwarder (the verified sender),
  not the name printed on the paper. Asked as questions 28–31 (and 20) of
  `docs/proterial/Cau-hoi-Proterial-DW1-DW2.xlsx` (2026-11-04).
