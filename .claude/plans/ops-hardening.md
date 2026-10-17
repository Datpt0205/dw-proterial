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
  registers none. The header of `infra/prometheus/alerts.yml` still says no
  context registers one (checked 2026-10-15).
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
