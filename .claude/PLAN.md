# Plan

The first 40 lines are injected into context at session start by
`.claude/hooks/session-start.sh`. Keep what matters inside them, and keep them
true — a stale plan is worse than none, because it is believed.

Here rather than `docs/`: this repository deliberately ships no documentation
directory, and this is tooling state, not a product document.

## Now — ops hardening is done; picking the first bounded context is next

A platform status review (2026-09-22) found six gaps an enterprise buyer would
ask about. Đạt chose to close five of them first — backup/restore, retention
enforcement, a spend guard, tenant offboarding/export, minimal alerting —
before picking the first bounded context. Five phases, dependency-ordered
(backup/restore gates retention enforcement). **All five done and verified:
Phase 0** (this file's own stale retention paragraph), **Phase 1** (backup
off-box copy + a restore drill that actually ran against live infra),
**Phase 2** (`retention@1.4.0.yaml`: `audit.enforced` is now `true`),
**Phase 3** (spend guard, mechanism only — **quotas still unset, needs Đạt's
dollar thresholds**), **Phase 4** (tenant offboarding + export, end to end —
**the export bundle itself has no retention term yet, same open shape as
audit's before Phase 2**) **and Phase 5** (Prometheus + Alertmanager,
verified against real running containers, not just config syntax — **alert
thresholds are provisional starting points, and one metric/alert pair
(reaper) can't fire yet because no bounded context has registered a queue for
it to watch**). Full phase detail in "Ops hardening" below.

Ops hardening has landed: `build_agent` and `MemoryService.propose` still have no
production caller because a bounded context is what calls them, and this repo
deliberately ships none. Adding one here to make the wiring look complete would
break the boundary the whole repo is built on.

The next-after-that step is still a decision, not a task: **pick one business
context** (sales chat, research, lead scoring) and plug it in at the seams — a
package under `packages/python/`, its graphs registered on the runtime seam,
its worker YAML, its tool specs, its eval dataset. `CLAUDE.md` lists the seven
plug-in points.

Only then do the numbers this plan leaves blank become measurable: how many live
memories one account really accumulates, whether the GIN index gets chosen with
real data, what a day of runs actually costs.

**Done and pinned by tests:** Mốc 0, 1a, 1b, 2, 3, 4, 5, 6. Details below.

**Decided AND enforced.** `configs/policies/retention@1.4.0.yaml` carries a
chosen, cited term for audit — `audit.tables.audit_events.days: 1095`
(Commercial Law Art. 319's 2-year limitation period plus a review-cycle
margin; Decree 13/2023 requires deletion once purpose ends, since the table
carries `actor_id`) — and `audit.enforced: true` as of Ops hardening Phase 2
below, gated on the restore drill in Phase 1 actually having run. The old
"usage ledger" half of this note no longer applies —
`platform.model_usage_ledger` was dropped entirely (migration
`aefe7c1f5d9b`); it never had a real reader.

A second language (Go) for the application tier was asked about and answered in
`CLAUDE.md` — allowed, provided it never re-implements tenant isolation, and the
four conditions there are tested by `test_rls_coverage.py` rather than trusted.

**Next, in the order they would be asked for in an enterprise review:**

1. ~~Data lifecycle~~ — **done: memory, knowledge, audit and usage.**
   `configs/policies/retention@1.4.0.yaml` is the versioned answer to "how long
   do you keep our data", it is in the release manifest with a checksum so the
   question can be asked about the past, and ONE file feeds all three sweeps on
   the worker's hourly lanes. Deletes, never closes a window: `valid_until` says a
   fact stopped being true, retention says we may no longer hold it.
   `legal_hold` has no term and is never swept; a class this build does not know
   is kept, not guessed.

    What closing knowledge actually took, beyond the obvious sweep:
    - **Evidence had no lifecycle at all.** `evidence -> documents` is RESTRICT,
      and deleting a memory only cascades `memory.item_evidence` — the evidence
      row survived for ever, pinning its document for ever. So a document cited
      once could never be hard deleted and the grace period was a promise the
      schema could not keep. `SqlMemoryRetention` now removes evidence nothing
      cites, which is what makes the chain drain. It lives in memory, not
      knowledge, because `item_evidence` is a memory table.
    - **A cited document is held back, not crashed on.** The citation test is in
      the SELECT, and again inside the deleting transaction — the vector deletes
      sit between the two, so a memory proposed in that gap would otherwise fail
      the whole batch and stall every document behind it.
    - **Both stores, points first.** Rows without points is a pass the next hour
      finishes; points without rows is the text of a deleted document in the only
      store that can still return it.
    - `KnowledgeGateway.purge_soft_deleted` was deleted. It was this feature,
      written earlier, never called from anywhere, crash-prone on any cited
      document — the duplicate is what would have drifted.

    **And done for audit and usage too.** The baseline said in a comment that "an
    operational job creates real monthly partitions ahead of time"; it never
    existed, every row was in the `_default` partition, and a default partition
    cannot be dropped — so "audit retention is DROP PARTITION" could not execute
    at all. The job exists now as a worker lane, and building it turned up two
    holes of the family migration 0009 found:

    - **The audit log was not append-only.** `0001_platform_grants.sql` revoked
      UPDATE and DELETE on `platform.audit_events` and says in prose that this is
      "enforced by the grant rather than by convention". It never revoked them on
      `audit_events_default`, which had taken them from the blanket grant one
      statement earlier. As `dw_app`, both `DELETE FROM audit_events_default` and
      `UPDATE ... SET action = 'rewritten'` succeeded. `ALTER DEFAULT PRIVILEGES`
      means every future partition would have arrived the same way, so the revoke
      is now part of creating one.
    - **A partition created later inherits no RLS**, which is 0009 again — a
      monthly job would have re-opened that leak every month. Creating, policing
      and revoking are one function, and `test_partition_maintenance.py` asks the
      catalog rather than reading the DDL.

    Two more things the work itself taught:
    - Creation is **self-healing**. A row for a month with no partition lands in
      the default, and Postgres then refuses to create that month's partition.
      Without relocation that state is terminal — one missed window and the month
      can never be partitioned, so never dropped. Found by running the whole
      integration suite, not this one file.
    - **Nothing is dropped by default until `enforced` says so.** The pass
      creates partitions ahead unconditionally, which is pure gain; dropping is
      gated. **Đạt chose the number** (`audit_events.days: 1095`,
      `retention@1.4.0.yaml`) and, as of Ops hardening Phase 2, `enforced` is
      `true` — gated on the rehearsed restore from Phase 1 actually having run
      first. DROP PARTITION on an expired audit month can now really happen on
      the worker's next hourly pass.

    Still open, and named rather than silently included: **superseded documents**
    — how many versions back to keep is a different question from how long a
    deletion takes to become final.

2. ~~Backup and restore: no procedure, never rehearsed.~~ — **Phase 1 below,
   done.** A rehearsed restore is what unblocks flipping `audit.enforced`.
3. ~~Tenant offboarding and data export~~ — **Phase 4 below, done.**
4. ~~SLO, alerting, on-call~~ — **Phase 5 below, done.**

## Ops hardening (in progress, started 2026-09-22)

Five phases, dependency-ordered — backup/restore must exist and be proven
before retention enforcement can turn on; the rest are independent of each
other. Landing as separate commits, tests run after each. Design detail
(exact files, migrations, port signatures) lived in a plan-mode file for the
session that wrote it; what follows is the durable summary.

- **Phase 0 — done.** This file's stale retention paragraph (`1.2.0`, "two
  numbers") corrected to match what the real policy file shipped.
- **Phase 1 — done, verified against real infra.**
  `scripts/backup_postgres.sh`'s off-box copy (to a new `dw-pg-backups` MinIO
  bucket) now fails the whole run if it can't upload, rather than quietly
  finishing local-only. New `scripts/restore_postgres.sh`. New
  `packages/python/dw_platform/tests/integration/test_restore_drill.py` — runs
  `pg_dump`/`pg_restore` for real via `docker exec` (the same mechanism the
  scripts use, not a logical row-copy) against the live stack: dumps the
  migrated test database, restores into a scratch one, confirms a single
  alembic head and that a seeded row survived. Ran, passes.
  Scope, stated honestly: this rehearses restore *within the same running
  cluster* — the dump carries no `CREATE ROLE`, so GRANTs resolve against
  roles that already exist. A from-scratch disaster-recovery drill (new host,
  roles provisioned from zero via `scripts/create_agent_role.py` etc.) is a
  separate, larger exercise, not yet done.
- **Phase 2 — done, verified.** `configs/policies/retention@1.4.0.yaml` (renamed
  from `1.3.0`) ships `audit.enforced: true`. Release manifest regenerated and
  `--check`-clean; `verify_invariants.py`/`verify_architecture.py` and the full
  `dw_platform` integration suite (`test_partition_maintenance.py` included)
  re-ran green under the flipped flag. `apps/worker/src/dw_worker/main.py`'s
  hardcoded load path updated to match the new filename — the one place a
  rename like this actually breaks something if missed.
- **Phase 3 — done, verified, mutation-checked.** Spend guard, mechanism
  only — no admin UI, no route, no usage-stats service (Đạt's call: the old
  `platform.model_usage_ledger` was removed, commit `142a0db`, for looking
  like invoicing evidence it never was — nothing here invoices anybody). New
  narrow table `platform.tenant_daily_spend_guard` (one row per tenant per
  day, a running total — not a per-call event log, on purpose), migrations
  `2b5ff2bceb06` + `c3ec03bd6fd1` (table + RLS; the worker-drain policy its
  own housekeeping sweep needs). `RunAllowancePort.spend_usd_per_day` mirrors
  the existing `runs_per_day` gate in
  `dw_agent_runtime/adapters/langgraph_runner.py` — same "before the
  expensive part" placement, same fail-closed shape when the dependency
  errors (a lookup failure refuses the run; a *recording* failure does not,
  because by then the model has already answered — asymmetric on purpose,
  both halves have a test).
  **Ships with the three plans' quotas unset (`None` = unmetered) — this
  needs Đạt's actual dollar thresholds before it protects anything. Not
  decided yet**, same deferral shape `legal_hold.days: null` uses elsewhere
  in this file: ship the
  mechanism, decide the number later, never guess it into a config.
  What the mutation check actually caught: the first tenant-isolation test
  (`test_another_tenant_neither_sees_nor_increments_the_spend`) still passed
  with the RLS policy replaced by `USING (true)`, because
  `SqlSpendGuardStore` filters by `tenant_id` in its own WHERE clause and
  never needed RLS to do it — the test exercised the application filter, not
  the database one. Added `test_rls_hides_the_row_even_from_a_query_with_no_tenant_filter`,
  a raw query with no WHERE at all, and confirmed *that one* goes red under
  the same mutation. Failure-modes.md's "a test that cannot fail" (found 4×)
  — this is the shape, caught before merge instead of after.
- **Phase 4 — done, verified end to end, mutation-checked.** Tenant
  offboarding + data export. Landed as three pieces:
  - **Postgres** (`SqlTenantOffboarding`, `dw_platform`): `export_rows`/
    `purge_rows` are catalog-discovered, not a hand-maintained table list —
    `pg_policies` filtered to `tenant_isolation_%`, the same query
    `test_migration_and_rls.py` already used to prove RLS coverage. Real
    count found by asking the catalog, not assumed: 23 tenant-scoped tables
    today, not the 17 first estimated. Two catalog surprises the tests now
    pin: `platform.tenants` carries a `tenant_isolation_%` policy but no
    `tenant_id` column (excluded by checking the column exists, not a
    special case); `platform.audit_events` is exportable but not purgeable
    (`dw_app` has no DELETE there — append-only, governed by
    `retention@1.4.0.yaml`, not by offboarding). Purge order for the one
    real FK chain (`memory.items → knowledge.evidence →
    knowledge.{chunks,documents} → platform.worker_runs`) is hand-ordered
    from the actual constraint graph, not guessed; everything else purges in
    any order, checked to have no FK between them. `claim_requested` runs
    under `app.worker_drain` for exactly one query (nothing else tells the
    worker which tenant has work waiting); a stale claim (`updated_at` >30
    minutes old at `'exporting'`/`'purging'`) is reclaimed rather than stuck
    forever, safe because every step is naturally idempotent.
  - **Provisioning** (`dw_platform.application.provisioning`):
    `initiate_offboarding`/`get_offboarding_status`/`finalize_offboarding` +
    3 routes under `RequireProvisioningContext`. Real bug caught before it
    shipped: the request must be filed *before* the tenant status flips, or
    a `ConflictError` rollback on a second concurrent `initiate` clobbers a
    still-in-flight first request's `"offboarding"` status — regression-
    tested.
  - **Worker lane** (`dw_worker.consumers.offboarding`): claims, exports
    (Postgres rows + knowledge artifacts + feedback attachments, zipped),
    uploads to `dw-exports`, purges (rows + both buckets + Qdrant), reports
    back. Real bug caught before it shipped: feedback attachment keys are
    `feedback/{tenant_id}/...`, not `{tenant_id}/...` like knowledge
    artifacts — a wrong prefix would have silently exported and purged
    nothing from that bucket. One tenant failing does not stop another
    claimed the same tick (mutation-checked: removing the try/except turns
    the isolation test red).
  **Known gap, named rather than silently shipped:** the export bundle in
  `dw-exports` has nothing that ever deletes it. A tenant's full data
  (PII included) sits there indefinitely once offboarding completes — the
  same shape of gap `retention@1.4.0.yaml` closed for audit/memory/knowledge,
  not yet closed here. Needs a retention term from Đạt, the same way audit's
  did; not guessed into a config.
- **Phase 5 — done, verified end to end against real running containers, not
  just config syntax.** Minimal-but-real alerting. Confirmed by survey: zero
  alerting infra existed (no Prometheus/Grafana/Alertmanager, no scrape
  endpoint; `/api/v1/ready` only probed Postgres; outbox/reaper were log-only).
  Đạt chose the fuller option over a bash+webhook script.

  **The metrics pipeline itself was silently broken before any of this could
  work, found by running it rather than reading it:** `metrics.get_meter(...)`
  was never backed by a real `MeterProvider` anywhere in the codebase —
  `metrics.get_meter_provider()` returned OTel's own `_ProxyMeterProvider`
  whether Langfuse was configured or not, so every `add_metric` call ever made
  (`dw_run_total` included) was a silent no-op. `dw_observability/otel.py` now
  always installs a `PrometheusMetricReader`-backed provider — metrics no
  longer share tracing's "only if an OTLP endpoint is set" gate, since
  Prometheus is pull-based and needs no destination configured to be worth
  turning on. Two more instances of the same bug class, found while fixing the
  first: `apps/api/src/dw_api/bootstrap/telemetry.py` was a second,
  divergent reimplementation that never called the shared builder, so
  `dw-api` specifically would have stayed broken even after the fix; and
  `apps/worker/src/dw_worker/main.py` built a `TelemetryPort` and then
  discarded it (`_ = _build_worker_telemetry(settings)`) — never passed to
  anything, so outbox/reaper metrics had nowhere to go until this was fixed
  too.

  **What's live now:**
  - `TelemetryPort` gained `set_gauge` (`dw_observability/telemetry.py` +
    `otel.py`) — `add_metric` is a Counter only, and using it for "how many
    are pending right now" would have summed each tick's reading into a
    number nobody asked for. Mutation-checked: swapping `set_gauge`'s body
    for `add_metric`'s turns the new gauge test red.
  - `/api/v1/ready` (`apps/api`) now probes Redis and Qdrant, not just
    Postgres — `dw_api/health.py`'s `redis_probe`/`qdrant_probe`, wired in
    `bootstrap/wiring.py` from resources built once and shared with the rest
    of the container (the Qdrant client is dedicated to the probe and disposed
    on shutdown, same lifecycle discipline as the SQL engines).
  - `dw-api` serves `/metrics` at root (not `/api/v1` — a scrape target isn't
    a versioned API route), a plain route rather than mounting
    `prometheus_client`'s ASGI app (the latter 307-redirects a bare
    `GET /metrics` to `/metrics/`, which is not what a scrape config expects
    — found by testing the mount, not by reading `prometheus_client`'s docs).
  - `dw-worker` runs `prometheus_client`'s own HTTP server on a dedicated port
    (`WorkerSettings.metrics_port`, default 9464 — the OTel/Prometheus
    exporter's own convention), since this process has no HTTP server of its
    own to mount a route on.
  - Outbox backlog: `OutboxDrainPort.backlog()` (new, catalog-free — same
    filter `claim_batch` already uses) returns pending count + oldest
    pending timestamp; the consumer reports both as gauges every tick
    (`dw_outbox_backlog_size`, `dw_outbox_oldest_pending_age_seconds`). This
    is live traffic today, not a metric waiting for a future context: the
    memory-formation handler already dispatches through this same outbox.
  - Reaper: `dw_reaper_reaped_total{queue}` increments whenever a sweep
    actually settles an abandoned row. **Cannot fire in this deployment
    yet** — the reaper lane only registers once a bounded context appends a
    `ReapTarget` (`apps/worker/src/dw_worker/main.py`), and this repo ships
    none. The metric and its alert are both real; there is nothing to trip
    them until the first context lands. Named here rather than left to be
    discovered as "why does this alert never fire."
  - Prometheus + Alertmanager join the `observability` compose profile
    (`infra/prometheus/`, `infra/alertmanager/`), run alongside `full`. Six
    alert rules, each against a metric this codebase actually emits: API
    down, worker down, Postgres connections >80% of `max_connections` (a new
    `postgres-exporter` service, reusing the existing `dw_app` role — no new
    migration, verified against a live Postgres that the catalog views it
    reads are world-readable regardless of RLS), outbox backlog above a
    threshold, reaper repeatedly reaping, and a run-failure-rate spike. That
    last one uses `dw_run_total{status="failed"}`, not
    `dw_node_failure_total` — the finer-grained per-node metric is declared
    in `dw_observability/metrics.py` and **emitted by nothing anywhere in
    the codebase**, a pre-existing gap found while writing this rule, not
    introduced by it. Writing a rule against a metric nobody emits would have
    been exactly this repo's failure-modes.md #1 ("declared, and nobody
    reads it") in the alerting direction — decoration, not a safeguard.
  - All six rules and both configs were validated with the real tools
    (`promtool check config`, `amtool check-config`), and the whole pipeline
    was run for real: `docker compose --profile observability up`, watched
    `DwApiDown`/`DwWorkerDown` go `pending` → `firing` in Prometheus after the
    real 2-minute window, and confirmed Alertmanager received both. Two real
    bugs only this caught: Alertmanager's config has no env-var substitution,
    so the first version of the render step left the literal placeholder text
    in the rendered file (a single-quoted `sed` replacement, never shell-
    expanded); and the *default*, no-webhook-configured state
    (`ALERTMANAGER_WEBHOOK_URL=` empty, what `.env.example` ships) made
    Alertmanager refuse to start at all (`unsupported scheme "" for URL`,
    crash-looping) — fixed by rendering a receiver with zero configured
    integrations when the URL is unset, rather than one `webhook_configs`
    entry with an empty url.
  - No OTel Collector: simplified away from the original plan. Prometheus is
    pull-based, so `dw-api`/`dw-worker` expose `/metrics`/a scrape port
    directly rather than through a bridging collector; Langfuse's OTLP trace
    export is unchanged and separate.
  - No new CI job: the existing `contracts` job already runs
    `docker compose --profile full --profile observability config -q`, which
    picks up the four new services automatically.

  **Left open, named rather than silently guessed:** every alert threshold
  (outbox backlog 500, reaper 20/hour, run-failure rate 0.2/s, DB connections
  80%) is a starting point, not a measured number — there is no bounded
  context yet generating real traffic to measure against, the same shape as
  Phase 3's unset spend quotas. No Grafana dashboards — polish, not the gap
  this phase closed.

  **Follow-up, 2026-09-22: the three new images, actually scanned.** The
  `reviewing-feature-security` trivy reminder reads narrowly as "the image
  this change produces" — none of Phase 5's four new images are built by
  this repo, so the first pass scanned nothing. Ran it properly, and the
  first read of the results (reported as "a few CVEs") was itself wrong —
  a `tail`-truncated table hid most of the table's rows. The real,
  deduplicated count with `--severity HIGH,CRITICAL --ignore-unfixed`:
  `postgres-exporter:v0.15.0` 45 (2 CRITICAL), `prometheus:v3.6.0` 44 (2
  CRITICAL), `alertmanager:v0.27.0` 46 (2 CRITICAL), `alpine:3.20` (the
  `alertmanager-config` init image) 0. Overwhelmingly Go stdlib /
  `golang.org/x/*` transitive DoS-class bugs baked into the binary
  regardless of whether the vulnerable function is ever called, plus one
  shared CRITICAL on all three (`CVE-2025-68121`, a `crypto/tls` certificate-
  validation issue) and, on `prometheus` only, `CVE-2026-33186` (gRPC-Go
  authz DoS — not reachable here, this deployment uses no remote-write/
  federation). Real-world exposure is lower than the raw count: all three
  run on `dw-internal`/`dw-edge` bound to `127.0.0.1`, never the public
  internet, the same network posture this compose file already gives
  Qdrant and Valkey.

  Checked whether a newer tag helps rather than assumed it: `prometheus`
  latest (`v3.7.3`) carries the identical 44/2-CRITICAL — an upstream
  release-cadence gap this repo bumping its pin cannot close, so it stays on
  `v3.6.0`. `postgres-exporter` and `alertmanager` newer tags each drop one
  CRITICAL and several dozen HIGH for free; bumped to `v0.17.1` /
  `v0.28.1` respectively, each re-verified live (config still parses, the
  exact metric names `DwPostgresConnectionsNearLimit` reads are still
  populated, Alertmanager still loads the rendered config and Prometheus
  still discovers it) before the pin changed — a version bump gets the same
  "run it, don't trust the changelog" treatment as any other dependency
  change. The remaining ~39–44 per image are accepted, written down here
  rather than left silent, per `reviewing-deployment-security` §6.

Every phase touching tenancy/authorization/data lifecycle (2–4) runs
`.claude/skills/reviewing-feature-security/` before being called done — this
repo's standing rule, not re-asked for.

## Mốc 3 — nhớ được giữa các lượt (chi tiết)

**Done in this slice.** `MemoryService.recall` + `RecalledMemoryMiddleware`, in
`platform_middleware` behind `AgentSpec.recall`. A run carrying a `subject_ref`
now gets what this worker already learned about that record, framed as data by
`runtime@1.5.0`. Four conditions narrow it and each has a negative test that a
mutation proved: tenant, workspace, worker, clearance.

Two honest limits to keep in view:

- `build_agent` still has **no production caller** — this is a skeleton, and a
  bounded context is what builds an agent. "Wired" here means wired into
  `platform_middleware`, the same sense in which the other middlewares are.
- The ranker has a real implementation now: `dw_memory/adapters/qdrant_ranker.py`,
  its own Qdrant collection, tested against a running Qdrant (tenant and worker
  filters discriminate; a width mismatch refuses rather than dropping everyone's
  vectors). Indexing runs on the worker after the memory is committed and never
  raises; both composition roots build it only when `QDRANT_URL` is set, measured.
- Measured, and NOT tuned on: the GIN index on `subject_refs` does serve `?|`
  (Bitmap Index Scan), but in the full recall query the planner prefers
  `ix_items_page` and applies `?|` as a filter. That is a reasonable choice on an
  empty table and says nothing about production. Left alone deliberately — index
  tuning against no data is guessing.
- Recall matches on `subject_refs` overlap. Similarity now decides the ORDER of
  that set when a ranker is wired (`dw_memory/ranking.py`) — it never decides the
  SET. An index that is empty, stale or poisoned can only produce a worse order,
  never a wrong answer, and a memory written before the index existed still
  surfaces. A ranker that is down degrades to confidence order, which is what
  every run did before. Still true: a run about no record recalls nothing.

**Also done: supersession (migration `62a9aaba6b16`).** Memory was append-only —
nothing ever wrote `valid_until`, so two facts that disagreed both stayed live
and recall returned both by confidence. A `fact_key` names WHAT a memory asserts,
so two live memories sharing a key and a subject are two answers to one question
and the later one closes the earlier. Closed, never deleted: the row, its
provenance and its audit entry stay, and the audit says which memories were
closed and under what key. A memory with no key still accumulates, which is
correct for episodes.

This is the one SOTA idea taken so far that changes correctness rather than
quality. Not taken, deliberately: vector/graph recall (needs embedding
infrastructure; subject-keyed matching is explainable and enough while a run is
about one record), and LLM-decided merging (the model proposes, code decides).

**Also done: the async write path.** `propose` has a production caller — the
worker's outbox handler for `memory.candidate_proposed`, wired in
`dw_worker.main`. Remembering runs after the answer, not during it. The outbox
delivers at least once, so `propose` took an `idempotency_key`: the event's own
id becomes the candidate row's primary key, and a redelivery returns the first
decision instead of writing a second memory. Tenancy comes off the event
envelope, never the payload — what produces the payload is a model's output one
layer up. The context supplies a plan the catalog does not contain, so anything
that starts reading the plan on this path refuses rather than grants.

What a bounded context still owns: EMITTING the event. The platform ships the
schema, the handler, the idempotency and the audit; deciding what is worth
remembering is a workflow's judgement, not the platform's.

**Still open, and the heavy half:**

- ~~Route the builtin file tools through `ToolExecutor`~~ — **checked, and not a
  task.** It was inherited from the blueprint, which assumed memory would be a
  `MEMORY.md` the model edits with `edit_file`. `build_agent` is built on
  `create_agent`, which installs no tools at all; `create_deep_agent` is what
  ships the eight file/shell tools and it is deliberately not used. The only
  always-allowed name is `write_todos`, which writes to graph state and reaches
  nothing outside the run. `OfferedToolsOnlyMiddleware` remains as the guard for
  a context that reaches for the deep variant anyway.
- So the `AGENTS.md` route is not needed either: structured items in Postgres
  carry provenance, supersession, audit and RLS, and a file in tmpfs carries
  none of those. Reopen this only if a context has a real need for a
  model-editable file, and then it is new capability, not a hole to close.
- Left for the write side: vector-ranked recall (Qdrant and `EmbeddingPort` are
  already wired for knowledge), and a context that actually emits
  `memory.candidate_proposed`.

## Next after that

- ~~**Mốc 5 sub-agents**~~ — **done**, `adapters/sub_agents.py`. Two things were
  measured on the pinned deepagents rather than assumed. Inheriting tenancy is
  already safe: the context is graph level, so a child sees the caller's tenant,
  workspace, scopes and autonomy, and a `SubAgent` spec has no field that could
  replace them. What is NOT safe by default is spend — with a probe middleware on
  both, the order is parent, child, parent, so the parent's ceiling never sees a
  token the child burns. `sub_agent_spec` rebuilds the gates inside the child and
  hands it the SAME ledger object. Its tools are built from DEFINITIONS through
  `platform_tools`, never passed in ready-made, and a child may not offer a tool
  its caller lacks. The `task` tool exists only when a context names something to
  delegate to.
- **Mốc 6 running many customers** — half done.
    - Retry on the agent path: **done** (`adapters/model_retry.py`). Provider
      FALLBACK is deliberately not built: the chat factory points at a LiteLLM
      proxy where failover is configuration the application never sees.
    - Per-tenant daily spend cap: **built, then removed on request.** It read
      `platform.model_usage_ledger`, and that whole table went with it
      (migration `aefe7c1f5d9b`) — nothing in this repo invoices anybody, so a
      per-tenant cost ledger had two readers and no purpose behind them. What
      that costs is stated plainly because it is a real gap: `runs_per_day`
      still bounds HOW MANY runs a tenant starts and the per-run ceiling from
      Mốc 1a still bounds one loop, but **a day of expensive runs now has no
      ceiling**. Cost still reaches telemetry.
    - `cancel_thread` over HTTP: **done**. The runner's method takes a thread id
      and nothing else — it reads an in-process dict, safe while the only caller
      is a run that started it, a cross-tenant cancel the moment it is a route.
      Ownership is established in the endpoint via `run_store.thread_belongs_to`,
      under the caller's own tenant and therefore under RLS; a thread that is not
      yours is a 404, the same answer as one that never existed.
    - Provider fixtures: **done**. The mechanism existed and was wired at
      `bootstrap/models.py`, the directory was empty, and nothing had ever read a
      fixture back — configured and unexercised. Now tested: found by prompt id
      AND version, a missing recording is refused loudly rather than invented, a
      non-object file is refused, and a registered builder still wins.

## Decisions still open (asked, not yet answered)

None. The three that stood here were answered and closed — see the last row of
Done. What they turned into:

- `never` was not collapsed into `conditional`; it was given the only meaning a
  tool's author may safely carry — a claim, checked where a tool is declared,
  that the tool does nothing needing a person. A `never` on anything reaching
  outside is now refused instead of silently read as `conditional`.
- The `record_visibility` cache no longer invents a value. An entry written by an
  older release is a miss and is re-read. That also retired the fail-closed guess
  for `max_autonomy_level`, which was safe but still wrong for seconds per deploy.
- `approval_policy_version` is in the release manifest, read from the constant a
  run is actually stamped with rather than copied.

## Done

| Mốc | Commit    | What it changed                                                            |
| --- | --------- | -------------------------------------------------------------------------- |
| 0   | `4d45cf5` | `build_agent()` — one place a platform agent is assembled                  |
| 1a  | `1cda019` | Spend ceiling on the agent loop; ledger no longer leaks                    |
| 1b  | `b3b556f` | Context compaction that is recorded, bounded and fails open                |
| 2   | `eb25931` | Autonomy A0–A4 decides approval; tenant ceiling; policy stamped on the run |
| 4   | `80d849f` | Provenance as a chain the database enforces                                |
| —   | `643236f` | Invariant checker + commit gate + the security-review skill                |
| —   | (below)   | The three open decisions, answered: `never`, the cache, the manifest       |

Mốc 3 is deliberately out of order: Mốc 4 was cheaper and is what an audited
buyer asks for first.

## How a feature is checked here

Four layers, in decreasing order of how much they can be skipped:

1. `scripts/verify_invariants.py` — mechanical, runs in CI and in the commit
   hook. Exemptions live in `RLS_EXEMPT` / `UNREAD_EXEMPT` and each needs a
   written reason.
2. `.claude/hooks/pre-commit-gate.sh` — blocks `git commit`, runs layer 1, then
   asks only the questions this diff's file paths earn. Once per diff, not once
   per attempt. Disable with `touch .claude/no-commit-gate`.
3. `.claude/skills/reviewing-feature-security/` — six trust boundaries
   (business logic: tenant, authz, autonomy, untrusted content, provenance,
   resource lifecycle), a negative test at each, and a mutation check. Run
   before calling a feature done, without being asked.
4. `.claude/skills/reviewing-deployment-security/` — added 2026-09-22 after
   Ops hardening Phase 5 shipped four new container images that nothing
   scanned (none were "built," so the existing trivy reminder in layer 3
   didn't obviously cover them). OWASP-shaped deployment/config exposure —
   dev/mock surfaces reaching a deployed profile, response leakage, secrets
   and defaults, CORS, outbound URLs, and scanning EVERY new image whether
   built or pulled. Preventive, not yet backed by an incident count the way
   `failure-modes.md` is.

`.claude/rules/failure-modes.md` holds the counts layers 1–3 are derived from.
The honest limit: layer 2 guarantees the questions are raised, not that they
were answered truthfully, and no layer replaces running the thing.
