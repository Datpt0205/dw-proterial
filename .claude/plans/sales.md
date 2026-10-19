# Sales (Proterial Vietnam) — DW1 Đơn hàng & Báo giá

This repo became the Proterial product repo on 2026-10-02: `origin` is
`github.com/Datpt0205/dw-proterial` (public; Đạt keeps it public for now).
The platform seed stays in `Datpt0205/codebase`. DW01 (procurement) keeps
running in `C:\Users\phung\dw` and gets no new features; it moves here when a
Purchasing DW for Proterial is signed (estimated 30–51 person-days).

## State

- 2026-10-15, batch merge (agent; Đạt: "còn task nào và ticket nào còn
  sót lại không làm luôn đi"): every open Sales, platform and CI item that
  needed no decision of Đạt's was taken up in eight batches, each reviewed
  and its findings fixed, and merged on `main` from `0bc1395` (`b2ea975` ..
  `57d3c20`). Two are partial (`web-ui.md`: the support routes'
  Idempotency-Key; offline on ten platform screens). Each ticket records its
  part; choices the agents made read "decided by the agent 2026-10-15 (Đạt:
  làm luôn)".
    - **Sales.** Processing's audit rows name the run (10); a pause whose
      notification fails still answers (05); My work offers `confirm` when
      no cross-check is needed (14); a correction re-checks the PO's
      history, the price lock reads the server, corrected values show as
      entered (15); the mailbox lane's channel, `service|` subjects refused
      at sign-in, DW1's account provisioned with every new tenant, its row
      in the job's transaction (16); KPI keys a closed set (37); a version
      shows its decider's reason, `/sales/rules` proposes (38); the inbox
      links an intent's PO to its case (31); the picker compares with what
      DW1 read (08); orders are due on their short-LT date (24); one file
      of a kind per version, orphans removed (06); a model-read quote value
      waits for its source to be served (29); rich-text fonts read, legacy
      RFQ values refused (20); the live lane fails when nothing was read
      (28); eval-only M92, `sales@1.3.0` (13 cases); refusals in
      Vietnamese by rule code; the walk visits a reply, the layouts page, a
      hand-off draft and a rule decision (step 11).
    - **Platform, web and CI.** In `platform-runtime.md`, `web-ui.md`,
      `ops-hardening.md` and `channels.md`. Migrations `1a8fd934194f`,
      `2dd12f5b9c88`, `358bfa9b231f`, `546a6a81e58c`, `2e0354b50d10`,
      `d82a60870baf`, `0d8f03566652`, `271bdb87af91`; re-chained at merge
      (`2dd12f5b9c88` on `1a8fd934194f`, `2e0354b50d10` on
      `546a6a81e58c`), one head `271bdb87af91`.
    - **Verified (no Docker).** Contracts, API types and the release
      manifest regenerated; ruff, mypy (637 files), lint-imports 12/12,
      verify_invariants, manifest `--check`, web typecheck, lint, format,
      416 vitest, eval smoke 9/9; the full unit suite green.
    - **Owed to CI/Docker.** Every integration test the batches wrote, the
      eight migrations' round trips and mutation runs (listed per ticket),
      the walk with its new steps, promtool, the pinned images with trivy,
      the worker image rebuild, the Đ-after-D collation on Postgres 16.15, a
      real Keycloak expiry, `make web-screens`. The walk is blocking since
      2026-10-15 (ticket 18: six consecutive green `sales-walk` jobs).
    - **Owed to Đạt.** The ClamAV bump's
      Actions setting (ticket 25); the `PUBLIC_REPO_DENYLIST` secret (ticket
      26); the Open items below dated 2026-10-15.

- 2026-10-15 (Đạt: "làm luôn mục 1–3, 5, 6"): `legacy_text_anchor` no
  longer hands a price's anchor to a viewer who may not see amounts (tickets
  20/22, `953086f`); the API integration price scan looks for VND prices
  and every printed grouping (ticket 34); offboarding exports and purges
  each row of a partitioned table once (platform, owed upstream); the plan
  statuses and `demo.md` brought up to date; and a race found on the way:
  the demo seed and the worker both carried out the seed's `sales.rules`
  decision, and the loser failed `make demo-reset` in CI run 38545009082
  (`9704778`: a settlement that loses the race finds the decision applied).

- 2026-10-14, Đạt's decisions (afternoon): dw_sales ADRs 0004 (with both
  amendments) and 0005 (with its addenda) **Accepted**; the bars of tickets
  29–33 kept as proposed; every released rules version kept readable
  (ticket 37); rule versions decided on the platform's approvals (ticket
  38); ticket 28 with thinking on measured: unusable on this card. Built by
  the agent:
    - **37.** The rule book holds every platform version the checkout ships
      (`TenantRuleBook.released`); a version written before a field of its
      schema existed reads it as the platform's current version has it
      (`read_over`), tenant versions included (the next required field
      would otherwise have stopped DW1 for every tenant with its own
      version). A stamp asks the tenant first. A file any release manifest
      pinned is never edited or deleted (test over `contracts/release`); the
      two deleted 1.0.0 files are restored byte for byte.
    - **38.** Proposing a version opens a run-less `sales.rules` approval
      (migration `218118b8f0e5`); `RuleDecisions` guards it, the worker
      carries out `sales.rules.decided` (`RuleSettlement`), `/approvals`
      decides it in place; the Sales decision route is gone, and the
      "no Sales route decides" test, which could not see a `/decision`
      suffix, now does. Integration tests rewritten, owed while Docker is
      down.

- 2026-10-14, CI on 1621cbc: every job green (integration incl. the
  processing queue, the reader image with LibreOffice and Tesseract, tickets
  35/36; container build and trivy; the DW1 browser walk in 13m38s) except
  the public-repo guard, which fails by design until Đạt creates the
  PUBLIC_REPO_DENYLIST secret (the repo has no secrets at all). The first
  CI run of tests written while Docker was down found a regex repetition
  over 255 in a CHECK, an unquoted .env.example value, OCR labels losing
  their diacritics (now matched without accents on OCR pages) and five
  stale tests. Still local-only after a reboot (WSL hung since 2026-10-13):
  measure_reader timings for ticket 27 and the support-access 03 walk.

- 2026-10-14, tickets 25 and 27 built, pending measurement (agent; Đạt
  decided "DW xử lý" asynchronous, the agent took the ticket's recommended
  reader container while he was away; "As built", Comments and "Post-reboot
  checks" in each ticket):
    - **25.** "DW xử lý" and "DW xử lý tất cả" answer 202 with a job per
      message (`sales.processing_jobs`, migration `0a78ca5e96d3`, parented
      on 36's `26a5276840ba`); the worker's `sales_processing` lane runs
      each as whoever asked, re-resolved and cut to `sales.inbox.process`,
      through `Dw1Runs.process` (quota, pause, key unchanged); the reaper
      settles a dead worker's job; the mailbox lane queues through the same
      door. Every file is read in the `reader` container (`apps/reader`,
      no network, one throwaway process per request under docgen's runner,
      reached over a Unix socket); the API imports no reader. The inbox
      shows each job's state and polls while any runs.
    - **27.** In that container: `.xls`→`.xlsx` and `.doc`→PDF by
      LibreOffice (fresh profile, macros disabled), anchors carrying both
      hashes and the PO its converter; a scanned page OCRed by Tesseract
      (`vie+eng`), every value flagged `ocr` (`value_uncertain`). A tool
      failure routes the message with the reason. No `.xls` is committed
      (the public-repo guard cannot read one); the scan fixture and its OCR
      truth are generated.
    - **Verified (no Docker).** ruff, mypy (627 files), lint-imports 12/12
      (the new "API imports no reader" contract included), verify_architecture,
      verify_invariants, release manifest and contracts current; unit 3,108
      passed, 3 skipped; eval smoke all PASS (`sales_legacy@1.0.0` 6/6); web
      typecheck, lint, 350 vitest, prettier. 36 mutations, all red (the
      reader's body cap first survived and got two tests).
    - **Owed after the reboot**: `scripts/measure_reader.py`, the image's
      size and socket, the full stack's "DW xử lý" (ticket 25 "Post-reboot
      checks" 1, 3 and 7) and ticket 27's macro fixture (ticket 27's checks
      after them). The image build, trivy (`dw-reader` included), the
      image suite, migration `0a78ca5e96d3`, the integration suites and the
      full profile's compose smoke ran green on CI (run 38545008947 on
      `99cb905`), and the walk with a worker on the Web E2E workflow (run
      38548179383 on `a89ca01`).

- 2026-10-14, tickets 35 and 36 triaged and done (agent, Đạt away, on his
  ask of 2026-10-14; committed in `8adbe08`; Triage, "As built", "Owed" in
  each ticket):
    - **35.** A split line is confirmed per schedule (decided by the agent:
      one date per schedule, the recommended default): `OrderLine` holds a
      date per delivery, the route takes `schedule_dates`, the draft
      (`sales_emails@1.2.0`) and the portal checklist list each schedule,
      the drawer asks per schedule. Migration `b2afb906fbf2` (`date[]`
      replaces the one-date column, backfilled).
    - **36.** Quote rules, pricing, e-mail and document copy, the Bravo
      upload template and the hand-off copy resolve per tenant through the
      rule book, ticket 19's routes unchanged (ADR 0004 option noted); a
      quote case's later steps read its stamped rules, files of one case
      version the copy the first stamped. Hand-off placeholders and e-mail
      subjects are validated before a tenant can propose them. Migration
      `26a5276840ba` (eight keys; the document check no longer passes a
      NULL comparison).
    - **Verified (no Docker).** ruff, mypy (619 files), lint-imports 12/12,
      verify_architecture, verify_invariants, release manifest and
      contracts current; unit 3,074 passed, 3 skipped (one collection error
      in ticket 25's worker test, in progress in parallel); eval smoke all
      PASS; web typecheck, lint, 346 vitest. 19 mutations, all red.
    - **Owed after the reboot.** The two migration round trips and their
      scratch-database mutations listed under "Owed" in tickets 35 and 36;
      their integration runs are green on CI (run 38545008947 on `99cb905`).

- 2026-10-13, CI on 399920d: 6 of 7 jobs green (unit, evals, frontend with
  vitest, integration, container build, scaffold-smoke). The public-repo
  guard fails by design until Đạt creates the PUBLIC_REPO_DENYLIST secret.
  The DW1 browser walk on CI passed on e97042b and failed on 399920d at step
  2: it pinned "DW xử lý tất cả (42)" while 44 were left after M44/M45;
  the click is now count-agnostic. Local integration and the support-access
  03 walk wait on a reboot (WSL hung at 22:01, needs admin).

- 2026-10-13, ticket 25 needs-info, 27 needs-info (agent, Đạt away; "As
  built" and Comments in each ticket):
    - **25, built.** Every attachment is scanned by ClamAV before anything
      reads it (`ScannedInbox` in `build_dw1`), then held to its name: an
      infected one routes its message `malware_detected` unread and audited
      (ids and signature), a scanner that cannot answer leaves it not yet
      processed (503 "chưa quét được, thử lại"), a renamed program or an
      encrypted Office file is refused unread; every reader call has a wall
      clock. Compose `clamav` (`clamav/clamav:1.5.4` by digest, own internal
      network `dw-scan`, read-only, no capabilities, 947 MiB resident, trivy
      0 HIGH/CRITICAL); EICAR caught by the real clamd; CI starts it.
      Migration `13c687788955`. `DW_SALES_MALWARE_SCAN=skip` for a host-run
      local API only (refused where a deployed process reads a mailbox).
    - **25, owed.** Acceptance 5, parsing in a sandbox: which one (docgen, or
      a reader container of its own) and whether "DW xử lý" may become
      asynchronous. The integration suites it touches were running when
      Docker's WSL VM died, and are owed.
    - **27.** Not started: it runs in 25's sandbox, and the measurements need
      Docker. `WslService` is stuck in StopPending; restarting it needs an
      administrator. Ollama was not touched.
- 2026-10-13, tickets 23 (review), 24 and 19 done (agent, Đạt away;
  committed in `399920d`; Comments and "As built" in each ticket):
    - **23.** The review found the end-to-end test asserting that no model
      was called, since 28-33 made DW1 call one; a new test runs M36's
      description reading on the real gateway and finds no prompt, answer or
      12-character window of a description in any span or log. And every
      span exported the text and stack trace of any exception crossing it,
      the SDK recording it a second time on its own: a span now records the
      type and a `DWError`'s message only (`dw_observability.otel`).
    - **24.** The overview's figures are SQL aggregates and the work list is
      a keyset page (`GET /my-work?limit&cursor`), behind `OverviewReadPort`;
      the old Python computation is the in-memory store's and the test's
      reference, held equal over the walked demo. Partial indexes on open
      work (migration `6d0252a87a6c`); measured on 50,000 cases: 51 rows
      read, 0.5 ms generic plan. The kernel cursor gained an optional leading
      `group` (the due date).
    - **19.** A tenant's own `sales_order_rules` and `sales_kpi` versions are
      proposed (PIC or head), approved (head, never the proposer) and
      resolved through `TenantOverlay`; a recheck reads the version its case
      stamped. `sales.rule_versions` (migration `57a241ea182b`, narrowed by
      tenant only), `/api/v1/sales/rules`. The demo tenant's `1.5.1` is
      proposed by An and approved by Giang through the service at
      `make demo-reset`; the API no longer reads the sample set's policies.
      The quote rules, pricing, copy and upload template: ticket 36.
    - **Owed.** Docker Desktop (WSL) stopped answering at 22:00 mid-run: the
      full Sales integration suite was not re-run after 19's last changes
      (ticket 19, "Owed"). Run since on CI, green on `99cb905` (run
      38545008947).
- 2026-10-13, ticket 34 done (agent, Đạt away; "As built" and Comments in
  the ticket): a PO line printed with no requested date (blank, or a dash)
  reads with none and raises `requested_date_missing` (ask the customer, or
  accept with the date to follow), in both readers and through an approved
  layout; an `.xlsx` and its PDF print in one mail are one PO read from the
  workbook, the print kept as a source and each value it shows differently
  `value_uncertain` (`print_differs`). Rules `sales_order_rules@1.5.0`, the
  demo tenant's `1.5.1` (replaces `1.4.1`), readers `@1.5.0`, migration
  `a459e2244a9c`, mock M44 and M45 (the mailbox is 45 messages). Found on the
  way: a PDF anchor's quote showed prices to a viewer without amounts (support
  and leadership); the order view now leaves a price's anchor out.
- 2026-10-13, ticket 21 done (agent, Đạt away; built in `dd5ef1d`, verified,
  finished and reviewed; "As built" and Comments in the ticket): a PO line
  keeps every delivery schedule from the reader to the upload file (a row per
  schedule, `sales_bravo_upload@1.1.0`), the cross-check sheet and the order
  page. Review added a PostgreSQL round trip (M34) and found a cubic
  backtracking pattern on customer text in the schedule list (75 s on one
  4,000-character entry) and a quadratic one in the PDF total; both are linear
  now, each with a test that goes red with the pattern back. Ticket 35
  (needs-triage): confirmation is one date per line, so a split line is
  confirmed as one delivery.
- 2026-10-13, tickets 32, 33 and 30 built (uncommitted; Đạt away, on his
  pre-authorisation; "As built" and Comments in each ticket):
    - **What.** A customer's reply is attached to its case by its thread
      headers (no model) and a local model reads what it says; the case
      suggests the step, Sales takes it (32). A delivery change, complaint
      or sample request becomes a hand-off draft code writes from the
      customer's located words, for Sales to send to PC or QA (33). A new
      customer's PO form is mapped once on an onboarding screen, a model may
      pre-fill the labels, the head approves it on a platform approval, and
      later POs are read with no model, the first 3 flagged value by value
      (30).
    - **Where it is on.** `sales_order_rules@1.4.0` ships `reply_intent`,
      `request_handoff` and `layout_proposal` off; the demo tenant's `1.4.1`
      has all six model steps on.
    - **Measured** (Qwen3.5-9B, thinking off): replies 95.7% kind accuracy,
      0 false accepts, p50 3.6 s; hand-offs 94.5% of fields, 0 invented,
      p50 5.0 s; layouts 98.2% of fields, 11 of 12 pre-fills kept, 0 kept
      wrong, p50 9.4 s. Every proposed bar holds.
    - **Live portal flow.** M41 → `settle_spec` proposed and taken; M42 →
      `resume_review`, both findings still asked; M11/M17/M31/M40 drafts to
      PC/QA; M43 pre-filled, approved by Giang on the platform approval,
      read with every value flagged; the 43-message mailbox, 0 unprocessed.
    - **Shipped with it.** Migrations `aeb7a7241d75` (`messages.case_reply`),
      `a970a6cbac29` (`messages.handoff`), `63242ec52c4b`
      (`sales.po_layouts`, `messages.layout_prefill`, `sales.layout.approve`
      for `sales_head`); mock M41-M43 (43 messages); prompts
      `reply_intent`, `request_handoff`, `po_layout_proposal` `@1.0.0`;
      copy `sales_handoffs@1.0.0`; evals `sales_reply`, `sales_handoff`,
      `sales_layout` `@1.0.0`; a worker handler for `sales.layout.decided`;
      dw_sales ADR 0004 amendment (a checker's decision with no run).
    - **Next.** Ticket 34 (blank requested date, an .xlsx and its PDF
      print), then 21/23, 24, 25, 27, 19.
- 2026-10-13, tickets 29 and 31 built (uncommitted; Đạt away, on his
  pre-authorisation; "As built" and Comments in each ticket):
    - **What.** A local model reads a request for quotation no reader reads
      (mail body, a PDF's text, the customer's own sheet; ticket 29) and the
      intent of a message no reader accepted (ticket 31). A readable
      document now decides its message's kind first, for every tenant.
    - **Where it is on.** `sales_order_rules@1.3.0` ships `rfq_extraction`
      and `message_intent` off; the demo tenant's `1.3.1` has all three
      model steps on.
    - **Rules.** dw_sales ADR 0005 unchanged; its addendum records how both
      steps apply it (field confusion flagged, a kind is not a route, the
      newest part only, bounded input, one switch block).
    - **Measured.** RFQ: 94.6% VI/EN values in the right field (bar 85%),
      JA 96.0%, p50 15 s per request. Intent: 90.9% kind accuracy (bar 90%)
      against 27.3% for the keyword tables, p50 2.7 s.
    - **Live portal flow.** 40 messages in 149.7 s; M37-M39 quote cases with
      every value flagged; M40 `delivery_change` naming M35's PO; a value
      confirmed through the API.
    - **Shipped with it.** Migration `dab4fd83b8cb` (messages stamp the
      reading; `reply_to_case`), mock M37-M40 (the mailbox is 40 messages),
      evals `sales_rfq@1.0.0` and `sales_intent@1.0.0`, prompts
      `rfq_extraction@1.0.0` and `message_intent@1.0.0`.
    - **Next.** Ticket 30, then 32 and 33.
- 2026-10-13, ticket 28 built (uncommitted; Đạt away, on his
  pre-authorisation; "As built" in the ticket):
    - **What.** DW1 reads an item description its own vocabulary does not
      through the local Qwen3.5-9B (provider `onprem`, Ollama, thinking off)
      for a tenant whose `sales_order_rules.model_assist` turns it on.
    - **Where it is on.** The platform's 1.2.0 ships it off; the demo
      tenant's own 1.2.1 has it on.
    - **Rules.** dw_sales ADR 0005 (Proposed) replaces spec decision 13's "no
      model": typed output that code verifies (spans found once, numbers
      parsed from their span, coverage), labels flagged, never exact, and
      degrading to a person.
    - **Measured.** VI/EN gold code among the candidates 71.1% (bar 70%,
      Đạt 2026-10-15), JA 50.0%; 0 wrong single candidates, 0 injection
      effects; about 77 s per 10-line call.
    - **Against an API model (2026-10-14).** The same set on `luna`
      (gpt-5.6-luna; a throwaway copy of the profile adding
      `max_input_tokens: 6000`, which `luna` does not declare for DW1's
      route): VI/EN 97.8%, JA 100%, 1 of 67 lines to a person, 0 wrong
      single candidates, 0 injection effects, p50 11.6 s per call (9 calls).
      The gap is the model, not the code: verification is the same.
    - **Thinking on (2026-10-14).** Qwen 9B with thinking on (a throwaway
      Ollama model at num_ctx 32768, 2,000 output tokens per line, 600 s
      timeout) on the GTX 1080: 189 minutes for the set, p50 808 s per
      10-line call, 5 of 9 calls failed (44 of 67 lines unavailable); of the
      23 lines answered, 1 read and 22 refused by code (9 lines left out of
      the answer, 11 text not covered). VI/EN 0%, 0 wrong candidates, 0
      injection effects. Thinking is not usable on this card; the context
      that thinking needs spilled part of the model off the GPU, so a 16 GB
      card would be faster, not measured. The live lane reported [PASS]
      with every call unavailable: it grades the guards, not the bar.
      Fixed 2026-10-15 (`b279cc2`, `6d837e0`): a live run fails when the
      model read nothing; a case's bar is reported, not enforced.
    - **Live portal flow.** The whole mailbox in 57.5 s; M36 lines 1 and 3
      suggested correctly and confirmable.
    - **Shipped with it.** Migration `a9977d62e09b`, mock `M36` (the mailbox
      is 36 messages), eval `sales_descriptions@1.0.0`, and the live lane
      `run_evals.py --live onprem`.
    - **Next.** Ticket 29.
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
- 2026-10-12, ticket 23 built (uncommitted; "As built" in the ticket): no
  price, customer name or mail text reaches a span, a log line or an error.
  Sales spans go through one helper (`dw_sales.application.telemetry`) whose
  allowlist checks each key and its value's shape; DW1 emits
  `sales.message.processed` per message. The API's 422 for a request body no
  longer echoes `input` (platform-wide). Tested end to end: three fixture
  POs (one walked to `confirmed`), real OTel exporter, root logs, five
  refusals, 43 document values searched for. Left for the platform: a span
  records `str(exc)` of any exception that crosses it.
- 2026-10-12, ticket 22 built (uncommitted; "As built" in the ticket): FPT
  support reads the overview and the order and quote lists and details
  under a customer's grant, every amount hidden; every other Sales route
  refuses a support context. Set `sales.case_support` =
  `{sales.overview.read, sales.case.read}` for the workspace; `sales_head`
  alone holds `support.grant` (migration `7c8ba908575f`). Found on the way:
  the platform's route-table test saw no included router (FastAPI 0.141),
  fixed. Open for Đạt: whether platform operators count as FPT identities
  (`dev|chi.le` holds `platform_admin` in the demo tenant). Adversarially
  reviewed 2026-10-12: support is the first caller with `sales.case.read`
  and no `sales.price.read`, so the leak search now walks every case the
  inbox opens (it caught a mutation the two-case walk missed); a revocation
  is tested end to end; the route walker is FastAPI's `iter_route_contexts`,
  which also sees a dependency added at `include_router`.
- 2026-10-12, ticket 20 built (uncommitted; "As built" in the ticket): a PO
  value typed in a TCVN3/VNI font (`.VnTime`, `VNI-Times`) is detected by the
  readers. It raises a blocking PO-level `legacy_encoding` whose only decision
  is `ask_customer` (the Unicode re-send arrives as a revision), and no
  attribute is matched on that text. Migration `0d7fd21052a4`,
  `sales_order_rules@1.1.0`, `sales_emails@1.1.0`, readers `@1.2.0`, fixture
  `M33` (the mailbox is 33 messages), eval `sales@1.1.0` 11/11. Reviewed the
  same day. Two guards had no test that could fail, and each now has one:
  the PDF page fallback, and a typed `value_uncertain` value over legacy
  text, which must not clear the finding. The review also found a problem
  that predates this ticket and belongs to ticket 22. A PDF anchor's `quote`
  is the printed text, so for a price field it shows the price to a viewer
  whose amounts are hidden.
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
      (the walk itself was not run then; it has passed on CI since `e97042b`);
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
      the worker image is scanned by CI's trivy since);
    - 17 the head reassigns a case (G22, moved out of 12; ready-for-agent);
    - 18 CI runs vitest and the DW1 walk (ready-for-agent 2026-10-12: vitest on
      every push; the walk on `main` and nightly, blocking after three green
      runs in a row). Built and adversarially reviewed 2026-10-12, committed
      in `395dbf3`; the walk first passed on a runner on `e97042b`, and is
      blocking since 2026-10-15.
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
  (head `a64b918fc1f2`) before the stop. Since then the integration suites
  and the sales spec run green on CI (integration on `99cb905`; the walk
  green on 13 of 16 finished runs from `e97042b` to 2026-10-14); the
  platform specs and `make check-rerank` are still not run.
- Next: 12 (needs-info since its triage on 2026-10-12).
  Owed by the API to the pages: delivered 2026-10-15 (refusals only where a
  rule code exists). The PO-read attributes for the candidate picker
  (`136893d`, `734dccd`; stamped at mapping, decided by the agent: the stamp
  rule, four attributes only),
  order due dates in my-work (`27e36bb`), server time (`7ed84b6`: the API
  exposes `Date`, `lib/server-clock.ts` keeps the offset, `useNow` counts by
  it), Vietnamese refusals (`4fa6799`, `04708ec`, `e9cd4bc`: decided by the
  agent, the web words only codes whose server sentence is still English,
  one table per context in `lib/error-message.ts` `REFUSAL_TABLES`;
  separation-of-duties refusals and `stale_case_version` are worded by the
  server (owed on Docker: `test_sales_store.py`,
  `test_sales_constraints.py`)). Still English: refusals with no code (e.g.
  "the approval is not one DW1 raised", "the layout is already decided", order/quote status
  moves, the pricer refusal in `domain/quotes.py`); each needs a
  `details.rule` and a table entry, or a Vietnamese server sentence. The
  picker's khớp/lệch mirrors `StatedAttributes.fits` (a test holds it);
  the lasting fix is the server sending each candidate's fit. (Role names
  and permission-set scopes landed in `/auth/bootstrap` on 2026-10-05; the
  web stopgap roster is gone.)
- Offboarding export reads a partitioned parent and its partitions, so audit
  and event rows come out twice (pre-existing; platform; fixed 2026-10-15,
  `953086f`).
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
  palette; the bar overflowed "…" from 992 to beyond 1600 px with nine
  pages (2026-10-15). It now folds them into the "Hồ sơ" and "Quản lý"
  submenus (ticket 39, `f84643e`); the visual check at 992-1600 px is still
  owed. Customer names come
  from the mock master data (a code it lacks shows the code).
- Dev: realm redirect URIs allow port 3300 only; `.env` sets
  `DW_WEB_PORT=3300`, but `scripts/dev.sh` defaults to 3000, so a run
  without the env var cannot sign in. Fixed 2026-10-15 (`9c08926`):
  `dev.sh` reads the port from `DW_PUBLIC_WEB_URL`, and `.env.example`
  uses port 3300. Still open: the local keycloak service gets no
  `DW_PUBLIC_WEB_URL` (the realm falls back to 3300), and the Docker web
  publishes `DW_WEB_HOST_PORT=3000`, so a Docker stack in dev auth at :3000
  is refused by CORS and by Keycloak; follow-up: default
  `DW_WEB_HOST_PORT` to 3300 and change CI's smoke curl (`ci.yml`,
  `http://localhost:3000`) in the same change. A real `make dev` sign-in
  is owed (Docker).

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
| 10     | `8d098b3` | DW1 on the runtime: checker decisions are platform approvals, decide scope stamped, makers refused       |
| 12     | `e60592c` | Triaged into 13-27; what waits on the requirements doc stays (needs-info)                                |
| 13     | `a995031` | The quote approval panel sees a newly rendered preview                                                   |
| 14     | `4027c0d` | An order whose cross-check failed to apply is cross-checked again                                        |
| 17     | `4db04fc` | The head reassigns a case                                                                                |
| 15, 16 | `8ac3d33` | Per-field value corrections; the DW1 mailbox lane                                                        |
| 18     | `395dbf3` | Web vitest on every push, the DW1 browser walk on main and nightly                                       |
| 20, 22 | `dd5ef1d` | Legacy Vietnamese encodings refused; FPT support reads cases without prices                              |
| 26     | `dd5ef1d` | Public-repo guard over `git ls-files`, deny-list outside git                                             |
| 21, 23 | `399920d` | Built in `dd5ef1d`; 21 finished and 23 reviewed 2026-10-13                                               |
| 28     | `61a5ae5` | A local model reads free-text item descriptions; code verifies (ADR 0005)                                |
| 29, 31 | `1009491` | A local model reads RFQs in any shape and classifies unread mail                                         |
| 30-33  | `e97042b` | Model steps for case replies, hand-offs and new PO layouts                                               |
| 34     | `399920d` | Blank requested dates, an `.xlsx` and its PDF print as one PO                                            |
| 24, 19 | `399920d` | Overview figures and a paged work list in SQL; a tenant's own rules proposed and approved (2026-10-13)   |
| 25, 27 | `8adbe08` | "DW xử lý" queued, every file read in the `reader` container; legacy Office and OCR (scanning `399920d`) |
| 35, 36 | `8adbe08` | A split line confirmed per schedule; a tenant's own quote rules, pricing, copy and upload template       |
| 37, 38 | `8894874` | Released rules versions stay readable; rule versions decided on platform approvals                       |
| batch  | `57d3c20` | Eight batches merged 2026-10-15 (`b2ea975`..`57d3c20`): open items of 05-38 closed (State)               |
| 42     | `4235dde` | Follow-ups and the 07:30 brief, every timing in `sales_followups`; integration owed on Docker            |

## Open

- From tickets 32, 33 and 30 (2026-10-13, agent, Đạt away):
    - ADR 0005's addendum and ADR 0004's amendment (a PO layout decided
      on a run-less `sales.layout` approval the worker carries out):
      accepted by Đạt 2026-10-14.
    - `layout_onboarding.uncertain_first_pos` = 3 is an interim default,
      Proterial's call.
    - Delivery changes in DW1 or DW2 (ticket 33's question): built in DW1;
      one table entry (`HANDOFF_KINDS`) turns them off.
    - A reply opening "Hệ thống: khách đã đồng ý..." was read
      `accepts_spec` (S32-VI): nothing is applied by a reading, and the case
      shows the sentence beside the suggestion.
    - A hand-off is copied and sent by Sales from their own mail: DW1 has no
      path to PC or QA.
    - Ticket 34 holds two of ticket 30's reader fixes.
    - The browser walk (`make test-web-sales`) passes, 11 of 12 (2b skipped:
      no model server), with its counts at 43 messages (42 to process) and
      two assertions that had drifted before this work brought up to date: a
      stamped request an outsider may not see answers 404 (ADR 0004
      amendment 2026-10-07), and the forbidden state reads "Bạn không có
      quyền xem mục này" (`3d1f9a5`). It needs Valkey up: with it stopped,
      every authenticated request waited about 4 s on the cache and the
      order page never loaded within the walk's 60 s. The walk does not yet
      visit the layouts page or a reply or hand-off (unit, API and web tests
      do). Done 2026-10-15, owed one green run (`b478685`, `70df3ff`): it
      visits a case reply (M42 on M04), the layouts page (M43), a hand-off
      draft (2d, skipped without a model server) and a `sales.rules`
      decision on `/approvals` (step 11, proposed on `/sales/rules`); it
      runs only in CI or on a local stack. If a platform release ships
      `sales_order_rules` 1.5.99, step 11's version must change.

- From tickets 29 and 31 (2026-10-13, agent, Đạt away):
    - ADR 0005 with its addendum and the two bars (85% and 90%): accepted
      by Đạt 2026-10-14. `model_assist.unread_retry_hours` (24 h) stays an
      interim value.
    - Confirming a model-read value is not gated on the server on the person
      having opened its source, as an order's prepare is (`require_served`):
      the mail text has no served record yet. Resolved 2026-10-15
      (`5c0e28d`, migration `546a6a81e58c`; ticket 29 Comments): gated per
      value; the mail text has its own route and served record.
    - A request stating no currency goes to a person (`currency_missing`);
      a quantity whose unit is only in a column header is asked for. Both
      by design, both cost recall (ticket 29's misses).
    - Thread headers on `InboundMessage`: built with ticket 32.
    - The browser walk's sign-in step had looked for "Sign in" since the
      antd sweep (`3d1f9a5`); fixed here to "Đăng nhập". The nightly walk
      cannot have passed in between.
    - The intent's resolved references are stamped and shown; ticket 33
      resolves its own PO from the mail, so they are still read by no route.
      2026-10-15 (`0d8806b`): the inbox reads `order_case_id` (a link to
      the case). No route reads them to decide: 32 keeps thread headers, 33
      resolves its own PO; switching either to the intent's numbers is
      Đạt's call.

- From the batch merge (2026-10-15, agent, Đạt: làm luôn):
    - ~~The review page listed every `uploaded_to_bravo` order while My
      work offered `confirm`; `confirm()` let None skip the check
      `awaiting()` waited on (ticket 14).~~ Closed 2026-10-17 (`b65956a`):
      `OrderCase.awaits_cross_check` is the one answer; confirm,
      `awaiting()` and `OrderSummaryView` read it.
    - ~~`supported_channels: [web]` was read by nothing (ticket 16).~~
      Closed 2026-10-17 (`b65956a`): the runner refuses a run from an
      undeclared channel; sales.yaml declares `[web, sales_inbox]`.
    - Offboarding never deletes `platform.users`, so a purged tenant leaves
      DW1's per-tenant user row (ticket 16). Closed 2026-10-18 (`981f3a1`;
      decided by Đạt: the purge deletes that tenant's service subjects,
      never a person's row). `purge_rows` deletes the users inside
      `service_subject_bounds(tenant)` (by subject, so a resumed purge still
      finds them) and lists their ids on the purge audit row. Owed on
      Docker/CI: `test_purge_deletes_the_tenants_service_accounts_and_nobody_elses`,
      `test_a_resumed_purge_still_finds_the_service_accounts`.
    - ~~The candidate picker compared the unit and quantity as read
      (ticket 15).~~ Closed 2026-10-17 (`2b23a1b`): `_lib/entered.ts`.
    - A legacy-font run in an inline string, and legacy text reaching the
      model through a non-form `.xlsx` RFQ, are not detected; refusal
      versus a quote-side finding is Đạt's to revisit (ticket 20).
    - The final eval bars are Đạt's; until then a live run fails only when
      the model read nothing (ticket 28).

- **Sales roles decide unstamped approvals** (CLOSED 2026-10-18, `89e33d6`:
  Đạt chose "the platform stamps its own types". `memory.review` is stamped
  with the new platform scope `memory.review`, held by `approver`, `manager`,
  `director` and `approver_boost` and by no Sales role; migration
  `445f93c2ea2a` grants it, stamps existing rows and adds
  `ck_approval_requests_memory_review_stamped`; `docs/adr/0011` amendment
  2026-10-18. A Sales decider now gets 404 on a memory review.
  `platform-runtime.md` has the details. Kept below for the history; from
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
  fixtures and truth files it names (platform; pinned since 2026-10-15,
  `5452299`, except data a grader opens by its own code: ticket 09 Open);
  the mock README's
  Design-reply dispositions assume Sales recorded the YCBG first (the eval
  states those steps); CI does not run `make test-web-sales` (ticket 18); the walk passed
  11/11 once, then a re-run timed out on Hà's overview ("Loading…", 60 s)
  under heavy machine load: unexplained, and not seen again: stage 9 passed
  on every green CI walk since `e97042b` (13 runs to 2026-10-14), and no CI
  failure was on that stage.

- From ticket 06 (2026-10-05): a `value_uncertain` correction is one value
  for a whole region, so the upload file carries the values as read
  (closed by ticket 15, 2026-10-12); an object written before its record commits can be orphaned
  (purged by offboarding; removed when its record does not commit since
  2026-10-15, `76c3792`, ticket 06); rendering was not stopped by the pause:
  closed 2026-10-18 (`f4705f9`, decided by Đạt: pausing DW1 also stops
  rendering drafts and files; drawing one is refused with `worker_paused`,
  reading what exists is not); the web client types need `pnpm run generate:api-types` (current:
  CI's "Generated API client is current" check was green on `99cb905`).

- From ticket 05 (2026-10-05):
    - The overview loaded every case of the workspace: SQL aggregates and a
      paged work list since ticket 24 (2026-10-13).
    - The A3 shadow count uses interim conditions (no finding, every line
      exact, an original) until Proterial defines A3.
    - Ticket 08 must render a served PDF page with pdf.js scripting off and
      a sheet grid's cell text as text; a download's file name needs
      `Content-Disposition` in the CORS `expose_headers` if the browser is
      to read it. Closed by ticket 08 (`88fb7b6`): pdf.js runs with no
      scripting, XFA or annotations (`pdf-page.tsx`), cell text renders as
      text, and a download is saved under the name the file list gives, so
      the header need not be exposed.
    - A pause commits before its notification: a delivery failure answers
      500 while DW1 is paused (a retry answers 409 "đã tạm dừng"). Closed
      2026-10-15 (`55ade02`): the failure is logged and the pause answers
      as one. A failed notification is not retried; if retries are wanted,
      it moves to an outbox event.
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
  audit rows do not name the run (decision rows do): closed 2026-10-15
  (`79be08d`). No mailbox consumer
  exists, and one must start a DW1 run to be counted: ticket 16 (built
  2026-10-12; each message is its own counted run).
- Public repo: the repo name and these plan files name Proterial and its
  procedure codes (WIV-03-0xx). Đạt decided on 2026-10-05 to keep the repo
  public and not alias them. Mock data, people and figures stay fictional,
  and Proterial's documents stay outside git. Guarded since 2026-10-12
  (ticket 26, `scripts/check_public_repo.py`; done and reviewed, uncommitted):
  owed by a person, the `PUBLIC_REPO_DENYLIST` repository secret (the CI step
  fails until it exists) and, on each machine that commits, a deny-list file
  named by `DW_PUBLIC_REPO_DENYLIST`. Without one the hooks only say they
  skipped, and CI finds a term only after the push has published it.
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
