# Ops hardening

A platform status review on 2026-09-22 found six gaps an enterprise buyer would
ask about. Đạt chose to close five of them before picking the first bounded
context. All five are done and on `main`. The full narrative is at
`git show 84e3f6a:.claude/PLAN.md`, sections "Ops hardening".

| Phase | Commit    | What                                                                        |
| ----- | --------- | --------------------------------------------------------------------------- |
| 1     | `091eb35` | Backup off-box copy (the run fails if upload fails); restore drill run live |
| 2     | `c97ee4e` | `retention@1.4.0.yaml`: `audit.enforced: true`, gated on phase 1            |
| 3     | `061267b` | Spend guard, mechanism only (`platform.tenant_daily_spend_guard`)           |
| 4     | `89b00b5` | Tenant offboarding + data export, end to end                                |
| 5     | `8cbbee6` | Prometheus + Alertmanager, verified against running containers              |
| —     | `2a87f58` | Image pins bumped; real CVE counts recorded                                 |

## What holds, and where it lives

- **One retention file.** `configs/policies/retention@1.8.0.yaml` feeds the
  memory, knowledge, audit, checkpoint (since 1.6.0), channel-delivery
  (since 1.7.0), offboarding-export and superseded-version (since 1.8.0)
  sweeps on the worker's hourly lanes.
    - Audit keeps 1095 days: Commercial Law Art. 319's two-year limitation plus a
      review margin. Decree 13/2023 requires deletion once the purpose ends.
    - Since 1.5.0 the only memory class is `default`; `legal_hold` left the
      file. A row still carrying it, like any class this build does not know,
      is kept and never swept.
- **Partition creation is one function**, `platform.ensure_time_partitions`
  (CLAUDE.md, Data model rules). A partition created later inherits neither
  RLS nor the audit revoke.
- **Offboarding discovers tables from the catalog** (`pg_policies`), not from a
  hand list.
    - `platform.audit_events` is exported but never purged.
    - The one FK chain is purged in hand-checked order.
    - Stale claims older than 30 minutes are reclaimed.
    - Feedback attachments live under the `feedback/{tenant_id}/` prefix.
- **Metrics:**
    - a Prometheus reader is always installed;
    - `dw-api` serves `/metrics` at the root;
    - `dw-worker` serves its own scrape port (9464);
    - seven alert rules, each against a metric the code really emits
      (`DwNodeRepeatedlyFailing` since 2026-10-15).
- **Object storage is SeaweedFS** (`chrislusf/seaweedfs:4.48`, `weed mini`;
  compose service `s3`), since 2026-09-29.
    - MinIO withdrew its images from Docker Hub and then quay.io. Đạt chose
      replacing it over mirroring the old image.
    - The code speaks plain S3, so the swap was compose-only.
    - Buckets and the backup scripts use `rclone/rclone:1.75.1`, a generic
      client, so the next swap touches neither.
    - A replacement must first pass
      `dw_knowledge/tests/integration/test_object_storage_contract.py`
      (5 tests). The last of them refuses unsigned requests: without
      credentials SeaweedFS allows everything, measured at 200 on an unsigned
      PUT.
    - The earlier `SignatureDoesNotMatch` failures in the `dw_knowledge`
      suite no longer reproduce: 37/37 passed on MinIO and on SeaweedFS.

## Open

- **The plant's hosts (Đạt, 2026-11-09, corrected the same day).** DW runs
  on its own Ubuntu Server, as designed. Bravo runs on-prem on a separate
  Windows Server (it has a desktop and can reach wifi). VPN will likely be
  refused; staff use desktop PCs only, no laptops.
    - DW never connects to Bravo: a person imports the file DW drafts. No
      network path between the two hosts is needed for that.
    - Falls with no VPN: support over VPN (ADR 0024 open item 3), Grafana
      over an SSH tunnel from home, and question 49 (access from outside).
      Updates go in as an image bundle on site.
    - FPT proposes rather than asks (Đạt, 11-09): the host as sized; FPT
      installs Ubuntu 24.04, the driver and Docker on site; wired LAN, a
      fixed IP, 443 from the PC subnet and 22 from IT only; **no internet**
      for the host, updates as a monthly USB bundle; DW's own CA, its root
      put on the PCs; a separate plant PC for the OneDrive mail drop, never
      the Bravo server; DW accounts first, AD later; NTP from AD; the
      BIOS set to power on when power returns (no UPS asked for); backups
      on the host only, as built (Đạt, 11-09: a lost machine loses DW's own
      data, not Bravo's or the mail; the hand-over states UPS and off-host
      backup are Proterial's, so they do not count against the 99%); Grafana in the browser behind Keycloak (to build); alerts by
      internal SMTP; FPT on site for UAT and go-live week, Teams after;
      a step-by-step runbook and two training sessions.
    - Asked of Proterial (7, drafted, not yet in the workbook): IP, names
      and the PC subnet; domain-joined PCs; an SMTP relay;
      the screen-share tool; AD or not (q3); a security agent (q47).
      No longer asked: UPS, a backup share.
    - **Risk found 11-09, to test on UAT day 1:** `proterial.com` is on
      Exchange Online with SPF `-all`, DKIM and DMARC `p=none` (public DNS).
      DW2 reads a request only from a sender `Authentication-Results`
      verifies, unknown being unverified (`dw_platform.domain.messages`). A
      mail inside the tenant may carry no such header, which would send
      every internal request to a person. Measured so far only with outside
      senders (11-02). If it holds, the fix is to accept Exchange's own
      intra-org stamp, a change to the trust boundary that needs its own
      review and tests.
    - **UAT and production, drafted 11-09 for Proterial IT (not yet in the
      workbook):** Power Automate and Teams allowed or blocked by DLP (the
      mail drop's precondition, measured only on FPT's tenant); internal
      mail verification (above); a Bravo account on the test company and
      which Bravo role may import a file; software brought in on an
      encrypted SSD (no internet on the host); where FPT's engineer works on
      site; real-data defects fixed on site only; key-user accounts. At go-
      live on the same host: keep accounts, rules, master data and learned
      layouts, delete cases, mail and history. Master data re-exported from
      Bravo monthly by each department's admin; IT onboards and offboards
      people by runbook; cutover at a week's start, away from month-end
      close, two weeks in parallel; one Teams group for support.
    - **Bravo integration (11-09), first proposed as a read-only sync:** today
      DW neither reads nor writes Bravo; people move files both ways and
      type Bravo's numbers back. Proposed: read Bravo's database through
      views the vendor makes, with a read-only login, on a schedule (every
      15 min for order numbers and receipts, nightly for master data).
      Gains: DW1 compares the Bravo entry with the PO itself (O7/O9), DW2
      takes Bravo's PO number and received quantities, and master data stays
      current. Still no writes: Bravo is the ledger. Needs: the database
      kind, views and a read-only login from the vendor, port 1433 from the
      DW host to the Bravo server. Owed: whether a synced master-data change
      applies at once (proposed, with a change log) or waits for the second
      person's approval DW2 asks today. UAT keeps the manual path; build
      after go-live.
      **Confirmed by Proterial IT (11-09):** Bravo is two-tier, a client
      app on each PC talking straight to SQL Server on the Windows Server,
      no firewall between, roles inside Bravo; one database, nothing to
      sync. **Superseded the same day:** Proterial gives no database login;
      the Bravo vendor builds an API over its own stored procedures, so the
      business logic stays theirs. DW calls it through a Bravo port and
      adapter, no database access at all. FPT's part: the list of endpoints
      DW needs. Reads first (DW1: customers, items, conversions, valid
      prices, sales orders by the customer's PO; DW2: items, suppliers with
      email, prices paid, budgets left, POs and goods receipts). Writes
      later and only if Proterial wants them: create a sales order or a PO
      from DW's draft, called when a person presses, with an idempotency
      key. Plus: a DW-only key with least rights, HTTPS on the LAN, coded
      errors, the Bravo test company first, docs and versions. UAT keeps
      the manual path until the API exists.
      **The request, 11-09:** `docs/proterial/Danh-sach-bieu-mau-va-API-Bravo_DW1-DW2.xlsx`
      (gitignored, like the questions workbook): 40 forms and documents to
      ask for at once, 38 APIs (15 P1 before UAT: reads; validate-only
      calls P2; writes P3, each on a person's press, with an idempotency
      key) and 16 common requirements; yellow cells for Proterial and the
      vendor. Fields come from the import sheets and Bravo layouts in code.
      It supersedes the workbook's "Tài liệu cần gửi" sheet (10 rows).
    - **Cato (SASE) on the plant's PCs, heard 11-09:** DW is unaffected in
      principle. The API's rate limit keys on the bearer token and
      Keycloak's lockout on the account, so one shared plant IP throttles
      no one. IT to configure: PC-to-DW traffic bypassed locally (else DW
      depends on the internet), DW's three names in Cato's DNS, no TLS
      inspection on them (it may buffer the chat's frames and break the
      certificate). Proposed: a Cato account for FPT that reaches only the
      DW host, as the sanctioned way to support without a VPN.
      Close q49.

- **Offline install of the DW host (given to Đạt 11-10, not yet written into
  the README):** Ubuntu Server 24.04 LTS from USB (Rufus, GPT/UEFI), RAID 1
  in the installer, OpenSSH ticked, no snaps; the BIOS powers on after an
  outage. Driver (Blackwell needs 570+, `-open`, with Ubuntu's signed
  modules), Docker and the NVIDIA Container Toolkit as `.deb`s downloaded
  on a VM from the same ISO and installed with `apt-get install ./*.deb`;
  images by `docker save $(compose config --images)`; models by
  `fetch-models.sh --export/--import`; the repo by `git archive`. Not run
  end to end anywhere. Offered: `make onprem-bundle` to do the export.
  **Qwen3.8-Flash-Next** fits a disk (about 35–50 GB, to check) and needs
  the 64 GB of RAM, but runs on Strata, not Ollama: packaging Strata for
  offline use, its licence and a measurement on the RTX PRO 4000 are owed
  before it replaces Qwen3.5-9B, which ships first.
  **Đạt's chosen path (11-10):** install from USB, then fetch everything
  over the plant's guest wifi before the LAN is plugged in. Checks owed on
  site: a wifi card or a phone's USB tethering, no captive portal, IT's
  consent to wifi then LAN, wifi off before the LAN. The code must still
  come by USB (`git bundle`): `main` is 184 commits past GitHub. An SSD of
  saved images and models goes along as the fallback.

- **Contract baseline (11-10, for Linh's tracking tool):** `Downloads/proterial/Baseline_Proterial_DW1-DW2.xlsx`,
  outside the repo. Dates count working days from a kick-off cell set to
  11-09 (the rollout plan says 11-03; Đạt to confirm). Hardware ready by
  11-13 (contract 5.1); DW02 go-live 11-30–12-04 and DW01 12-14–12-18 by
  the contract (the rollout plan puts DW02 in week 6).

- **Chat that streams, and models kept loaded (2026-11-06, Đạt).**
    - **Built:** `POST /{sales,purchasing}/assistant/ask/stream` (SSE over
      `fetch`, because `EventSource` sends no bearer token). `/assistant/ask`
      reads the same stream to its end. `dw_agent_runtime.model.streaming`:
      `released` holds each word until the text so far passes the figure and
      amount check; `replace` puts code's sentence over words that stopped
      passing. Decisions: `dw_sales` ADR 0007 addendum, a rule in `CLAUDE.md`.
      The chat frame shows the step in progress, the words, and a stop button.
      This is the existing question list, streamed. It is **not** the agent
      with tools proposed below.
    - **Built:** `scripts/warm_model.py`, the `model-warm` service in the
      on-prem overlay (every 300 s), `make onprem-warm`; `make onprem-up`
      returns once the models are loaded. It fails on a model held on CPU.
    - **Ran:** Qwen3.5-9B on local Ollama behind a real browser: DW1 step at
      0.1 s, first word 3.9 s, whole 6.2 s (the intent call is 2.4 s of it);
      DW2 answer at 2.2 s; stop keeps the question, stores no turn, releases
      the key. LM Studio: first word 0.45 s, whole 1.2 s. The real app and
      the repository's Caddyfile on `caddy:2.11.7-alpine`: frames arrive as
      written, a client leaving stops the generator. Cold load by the script:
      110 s, fully on the GPU. The script also ran in `dw-worker:local`.
    - **Mutation:** 23 guards, each red. Three survived at first: two were
      missing tests, one a condition that did nothing (removed).
    - **Integration, 2026-11-06** (both DWs, platform, API, worker; run on the
      code before streaming): 2 not green, both old and neither the chat's.
      `test_sales_personas` read the roster's Purchasing roles against Sales'
      seed since 11-01 (fixed). `test_offboarding_memory_vectors` timed out:
      creating a Qdrant collection takes 7.6 s on this Docker volume, past the
      client's default 5 s (fixed in the test). The same default stands in the
      composition roots (`AsyncQdrantClient(url=..., api_key=...)`), so a slow
      plant disk could fail `ensure_ready` at start: measure it there.
      On the streaming code, the assistant integration files
      (`test_assistant_sessions_db`, `test_purchasing_assistant_db`,
      `test_sales_api_access`) passed 13 before the run outlived its session;
      a whole rerun is owed. The chat's unit, route and web tests passed, and
      the browser walk wrote through real Postgres.
    - **Open:** `sales_assistant` evals run through `interpret`, not the
      stream. DW1's `my_work` wording was replaced on its one live run, so
      that kind flashes words and then code's list; if it does so at the
      plant, skip the wording for lists. `model-warm` has not run inside the
      compose stack, nor anything here on the plant's host or on Qwen3.8.
      `request_timing` measures to the first event, so `route_latency.py`
      reads a stream as fast. The intent call has no words to show, so a
      cold or queued model still shows only the step.

- **Process deck for Proterial (2026-11-06, outside the repo).**
  `Downloads/proterial/DW1-DW2_Quy-trinh-va-luong-nghiep-vu_Proterial.pptx`,
  31 slides: as is, with DW and who stays, every status and move of orders,
  quotes and purchasing. Built by `DW-decks-src/build_flows.py` from
  `flow.json`, dumped from `process_settings.EDGES` and `STATUS_BUCKETS`; the
  build stops on a DW1 move not drawn. DW2's moves are read by hand from the
  application services (no move table in code). DW2's as-is is still assumed.
  The 11-05 survey deck's slide 4 promises a hand-off drawing it does not
  have; master deck slide 21 still lacks the plant GPU.

- **Reaching the portal on premises (2026-11-06, answered for Đạt).**
    - Staff open `https://<DW_WEB_HOST>` on the plant's network only; Caddy
      (ADR 0009) is the one door, no Cloudflare or CDN (a third party would
      see decrypted traffic). Outside the plant: the company VPN, not a
      published port. Mail is unaffected (Exchange Online, the flows run in
      Microsoft's cloud); only portal actions need the network.
    - Fixed: the README said `DW_CADDY_LOCAL_CERTS=1`; the Caddyfile pastes
      the value as a global option, so it is `local_certs` (`949472a9`).
    - Still not run: `make onprem-up` behind Caddy in the `uat` profile.
      Certificates from Proterial's own CA need a Caddyfile `tls` change.
    - Asked of Proterial (questions 48–50, `docs/proterial/`): the three DNS
      names and which CA; who needs access from outside and whether a VPN
      exists; whether email reminders are wanted (the process does not
      require them; the bell carries them today).
    - **Agent chat (Đạt, 2026-11-06):** Đạt plans a larger model at the
      plant (2-bit). Proposed, not built: measure it on the existing evals
      against 9B first (ADR 0007 rejected a tool loop because of 9B), then
      read-only tools, then drafts, then HITL cards in the chat that call
      the same approval API. The model never approves. The plant GPU is
      known: an RTX PRO 4000 Blackwell, 24 GB (`sales.md` State), so nothing
      is owed there; asking for it on 11-06 was a mistake.
    - **Measuring on Giang's home lab (2026-11-06):** keys in the local
      `.env` only (`GIANG_*`). The live lane now sends
      `DW_ONPREM_MODEL_API_KEY` (`d3621fda`). LM Studio
      (`qwen3.5-9b-mtp`, gemma-4-12b) answers and honours
      `reasoning_effort: none`; through it `sales_assistant` and
      `purchasing_assistant` were 5/5 each (DW1 p50 0.8 s). Strata, where
      Đạt expects the qwen3.8 model, answered Cloudflare 1033/530 (the
      tunnel is down; still down after 2 h of polling).
    - **Already measured, found 11-06 and missing from these plans:**
      Qwen3.8-Flash-Next 125B on Strata (RTX 3090 24 GB), 26/10, six DW1
      golden sets, `Downloads/DW1_Qwen3.8-Flash-Next-IQ3XXS_Strata_ket-qua-test_2026-10-26.xlsx`.
      Against 9B: PRV-code hints 0.978 vs 0.711, mail intent 1.0 vs 0.898,
      RFQ 0.917 vs 0.946; 0 dangerous errors; all six bars passed; p50
      3.3–19.8 s. Q2_0: same bars, about half the time. Not measured:
      DW2's sets, the Q&A sets, security cases, tool calling, the plant's
      GPU. Next, when Giang's tunnel is up: those, through the scratch
      runner, field by field against the 9B reports.
    - **Content guardrails (2026-11-06, asked by Đạt):** today's holds by
      allow-list, not by topic: a closed intent schema (`out_of_scope` gets
      the fixed catalog), ADR 0010 input framing, code-written or
      figure-checked answers, no tools. Open: no content classifier on the
      two free-text surfaces (DW1's worded answer, drafted mails); no eval
      case for sexual, political, abusive or chit-chat jailbreak questions
      (offered to Đạt, not added). A free agent chat needs an on-prem guard
      model (e.g. Qwen3Guard, measured in VI/EN/JA first), failing closed.

- **Logs, traces, Grafana (2026-11-05, Đạt: everything on Proterial's
  server, no cloud).**
    - **Built:** `observability` is now Prometheus (with a volume, 30 days)
      + Alertmanager + Loki 3.7.9 + Alloy v1.21.3 + Tempo 2.10.10 + Grafana
      13.2.5. Langfuse moved to its own `langfuse` profile, for UAT or
      debugging only.
        - Four provisioned dashboards (`infra/grafana/dashboards`).
        - New metrics `dw_model_calls_total` and `dw_model_call_seconds_total`
          by prompt and model.
        - Alert `DwTelemetryStoreDown`, the 8th rule.
        - Every service uses json-file rotation (5 × 10 MB) with its service
          label; Alloy reads the files, not the socket.
        - `make onprem-up` runs the profile. README: "Watching it run".
    - **Ran on Docker Desktop:**
        - Loki labels only this project's lines.
        - Real `dw.model.call` spans from the worker reached Tempo with
          metadata only.
        - `sales.morning_brief` calls showed on the AI dashboard.
        - Every panel query returned `success`.
        - Stopping Tempo put the alert in `pending`.
        - Grafana took 4.5 minutes on its first start and 39 s after that.
        - postgres-exporter's WAL collector failed on every scrape
          (`pg_ls_waldir`); it is now off.
    - **Log audit before shipping:** the API runs without uvicorn's access
      log, every runtime engine sets `hide_parameters` (invariant check 4),
      a refused outbox payload names fields not values, and the reader
      mismatch is no longer chained.
        - **Still open:**
            - Postgres's own error text can quote one value (a bad cast, a
              unique-key DETAIL), measured with `hide_parameters` on. A
              formatter that reduces a DB error to its SQLSTATE is owed.
            - Model output chained under `ModelOutputInvalidError`.
            - `str(refused)` used as a reader refusal reason.
            - OSError paths naming a mailbox address or attachment.
            - The knowledge parser's filename.
            - docgen's document name.
        - The API configures no logging (only uvicorn's).
    - **trivy 0.74.0, HIGH, fixed upstream:**
        - Loki 0; Tempo 1 (go-jose); Alloy 2 (apt).
        - Grafana 35, almost all Go stdlib/x/net in bundled datasource
          plugins; 13.3.0 has 39 and Tempo 3.1.1 still has 1, so the pins
          stay.
        - Grafana is on loopback and reads only internal stores.
    - **Owed:**
        - Grafana behind Caddy with Keycloak sign-in; today it is loopback
          plus an SSH tunnel.
        - Retention per store (question 40).
        - AGPL of Grafana, Loki and Tempo for FPT legal.
        - DW1's accepted vs to-a-person rate stays on the portal, read from
          `sales.step_outcomes`; DW2 records no per-step outcome.
        - Model call failures are not counted, only answered calls.
        - No link yet from an alert to the same run's log lines.
- **On premises (2026-10-18, `7eabeb4`, `2338aec`).** `infra/onprem/README.md`
  and `docker-compose.onprem.yml`: Ollama 0.34.4 (qwen3.5-9b-dw, bge-m3) and
  llama.cpp b11146 (bge-reranker-v2-m3) on dw-internal, pinned by digest;
  the deployed check takes `onprem` as a real provider; embeddings follow the
  route's provider; a keyless reranker over http only as an allow-listed
  host; realm: 5-minute access tokens, lockout, password floor (the host
  overlay had counted on a brute-force detection nobody enabled); the web
  manifest.
    - **Ran locally on 2026-10-19.** `onprem-models`, plus the compose files in the `local` profile: rerank through `build_reranker`, bge-m3 through `build_embeddings`, and chat with 32/33 layers on the GPU.
    - **trivy:** llama.cpp has 2 HIGH, Ollama 0.34.4 has 50 HIGH, all fixable; moving the pin is Đạt's call.
    - **Measured problems:** GPU discovery can time out to CPU behind a healthy check; the first load takes minutes; qwen35 takes no parallel slots. All in `infra/onprem/README.md`.
    - **Still owed:** `onprem-up` in `uat` behind Caddy, and the realm applied to an existing Keycloak by hand.

- **Offboarding exported each row of a partitioned table twice** (fixed
  2026-10-15, `953086f`). Every partition carries its own tenant policy, so
  the catalog query listed it beside its parent, and the export (and purge)
  read the audit log and the ledger through both. Partitions are left out;
  `test_export_holds_each_row_of_a_partitioned_table_once`. Platform code:
  owed upstream to `Datpt0205/codebase`.
- **Offboarding loses in-app notifications unexported** (measured 2026-10-03,
  `workspace-scope-offboarding/01` step 4; fixed 2026-10-15, `fb3fefb`,
  migration `2e0354b50d10`: the notifications SELECT policy is tenant AND
  (recipient OR `app.workspace_scope`), only SELECT widened; reusing
  `app.workspace_scope` rather than a second lane setting was decided by the
  agent, Đạt: làm luôn, and `CLAUDE.md` Tenancy records it. Owed on
  Docker/CI: `test_offboarding.py`, `test_rls_coverage.py`,
  `test_privileges.py`, `test_notifications.py`, the round trip, and the
  mutation run: downgrade the revision, then
  `test_export_holds_every_persons_notifications_of_the_tenant` and
  `test_a_narrowed_table_lets_offboarding_read_every_row_of_the_tenant` go
  red). `platform.notifications` is read
  only by its recipient (`app.user_id`), so the lane's export lists the table
  with 0 rows and its purge deletes none; the purge of `platform.workspaces`
  then CASCADEs them away. Measured on the test database: a tenant with one
  notification exported `[0]` rows and kept none after purge. The workspace
  scope does not help, since the policy narrows by user, not workspace. Needs
  an export path that reads them (a scope the lane sets, like the workspace
  one, under the same tenant-clause rule) before a real offboarding.
- **Spend guard quotas are unset.** Every plan's `spend_usd_per_day` is `None`,
  so nothing is metered until Đạt gives dollar thresholds.
- **Offboarding export bundles in `dw-exports` are never deleted.** Closed
  2026-10-18 (`981f3a1`; decided by Đạt: 30 days after they are written).
  `offboarding_exports.retain_days: 30` in retention 1.8.0 (required,
  1..365). Lane `offboarding_exports_retention` (hourly, only with object
  storage) lists the bucket through the port, reads tenant and write time
  from the key (`export_key_for`/`export_written`), keeps keys of any other
  shape, and deletes inside the transaction that writes its lane audit row
  (`SqlOffboardingExportAudit`, in the workspace the purge record names; no
  row, no deletion). Owed on Docker/CI: 3 tests in `test_offboarding.py`
  (`test_an_export_deletion_is_on_its_tenants_log_as_the_lane_beside_the_purge`,
  `test_a_deletion_that_fails_leaves_no_audit_row`,
  `test_a_tenant_with_nothing_to_record_against_keeps_its_bundle`). Still open:
  the request row keeps `export_key` after the bundle is gone, so the operator's
  status read names a deleted object; the audit row is the record.
- **Superseded documents: keep the newest five.** Closed 2026-10-18
  (`981f3a1`; decided by Đạt). `knowledge.superseded_versions_kept: 5`
  (required, 1..100). `SqlSupersededVersionRetention`, lane
  `retention_knowledge_versions` (only with object storage): ranks superseded
  versions per (tenant, workspace, `doc_key`) by `effective_to`, deletes points,
  the stored text (`document_storage_key`, shared with ingest), then rows
  (chunks cascade), re-checked in the deleting transaction; cited versions held
  and counted; one lane audit row each. Owed on Docker/CI: 5 tests in
  `test_knowledge_retention_db.py`, and a SQL-level mutation (drop `tenant_id`
  from the window partition, see
  `test_another_tenants_versions_are_ranked_apart_and_untouched` go red); the
  window scans every superseded row each hour (no index carries it; fine at
  today's sizes, measure before a large library). Still open: the
  deleted-document sweep removes rows and points but not the stored text, and
  no sweep removes staged uploads (`{tenant}/{workspace}/uploads/{job}/...`).
- **The restore drill is same-cluster only.** A from-scratch DR drill (new
  host, roles provisioned from zero) has not been done.
- **Alert thresholds are starting points, not measurements:** outbox backlog
  500, reaper 20/hour, run failure rate 0.2/s, DB connections 80%.
- **The reaper alert can fire only where DW1 is mounted.** None was registered
  on 2026-09-29. Since `8adbe08` Sales registers a `ReapTarget` for its
  processing lane (`dw_worker/main.py`), but only when `s3_endpoint_url` is
  set and `SALES_DEMO_*` mounts DW1; a deployed profile without it still
  registers none. The header of `infra/prometheus/alerts.yml` says so since
  `5f59855` (2026-10-17).
- **`dw_node_failure_total` is declared and emitted by nothing**
  (`dw_observability/metrics.py`), so no rule uses it. Closed 2026-10-15
  (`fbe99ac`, `c732366`): the runner counts it once per failed run (not a
  cancellation), with the worker-graph node read from LangGraph's exception
  note (`test_node_failure_metric.py` pins it against the real library),
  after the run is settled, so a raising sink cannot leave a run RUNNING;
  alert `DwNodeRepeatedlyFailing` reads it. Owed: promtool on
  `infra/prometheus/alerts.yml` (or the file loaded in the observability
  profile), and the series on a live `/metrics` after a failing run.
- **No Grafana dashboards.**
- **Image pins (2026-10-15, `f14490f`).** Every third-party compose image is
  exact-pinned (postgres `16.15-alpine`, valkey `8.1.10-alpine`, clickhouse
  `24.8.14.39-alpine`, langfuse and langfuse-worker `3.225.11`, alpine
  `3.20.10`), each the version its floating tag resolved to that day. Still
  open: no check stops a floating tag coming back (a `verify_invariants.py`
  check would be its own item); the Dockerfile bases float
  (`python:3.12-slim-bookworm` in api/docgen/worker, `node:22-alpine` in
  web). Owed on Docker: pull the pinned images and run trivy; re-measure the
  Vietnamese collation (Đ after D, measured on 16.14) on 16.15, which CI has
  run since 2026-09-21, ideally as an integration test. The worker image
  drops docling and torch (`e0f8ed3`): rebuild, trivy, compose smoke owed.
  ClamAV's pin moves by a weekly workflow (`clamav-bump.yml`, sales ticket
  25), built, not yet run: Đạt allows Actions to create pull requests.
- **Accepted CVEs.** About 39–44 HIGH/CRITICAL remain per image, mostly
  transitive Go stdlib/x code. Pins: `prometheus:v3.6.0` (a newer tag did not
  help), `postgres-exporter:v0.17.1`, `alertmanager:v0.28.1`. Re-scan on every
  bump.
    - `chrislusf/seaweedfs:4.48`: none (trivy 0.74.0, 2026-09-29).
    - `rclone/rclone:1.75.1` carries 3 fixable HIGH, all denial of service:
      CVE-2026-14456 in libcrypto3 (twice) and CVE-2026-84445 in grpc.
      Accepted: rclone runs as a one-shot client on the internal network and
      opens no listener. Move to the next rclone release that clears them.
