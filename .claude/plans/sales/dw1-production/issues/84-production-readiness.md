# 84 — Production readiness for DW1

Status: needs-info (codeable parts built 2026-11-27; Đạt's mailbox term and keep rule owed; the drills wait for 83)
Blocked by: 83
Category: operations

## What

- Backup restore drill on the plant's host (Postgres, object store), timed.
- Monitoring and alerts reach a person (Alertmanager route), including the
  mail-folder watchdog and the gateway's `in_doubt` ledger entries.
- DW1 mail retention lane (Đạt decides the number of days; DW2 has
  `retention.py`).
- CI green on `main`; a runner for `deploy.yml`; GitHub billing (Actions
  started no job since 11-24); the branch ruleset enforced.
- Every switch that is on names its measurement (rules) or UAT proof
  (gateway); a release manifest pinned for the go-live.

## Acceptance

- A checklist in `sales.md` with each item ticked by a run, not by reading.

## Comments

### 2026-11-27, codeable parts built (unattended workflow)

Built from the plan and its adversarial critique; each critique point was
checked against the code first.

- **Lane health** (`821ce89e`). `run_worker` seeds
  `dw_lane_last_ok_timestamp_seconds{lane}` with the start time and moves it
  after each clean tick; `dw_lane_interval_seconds{lane}` is the lane's own
  cadence from `ConsumerRegistry.interval_for`. `DwLaneStale` fires when a
  lane has had no clean tick for three of its intervals, and never under 30
  minutes. That catches a lane that fails, hangs (an `await` that never
  returns), or never once succeeded. The critique was right that a tick
  counter would have been blind: `build_retention_consumer` swallowed every
  failure (the `partitions` lane among them), and every per-workspace loop
  swallowed its scope's. Those loops now count what they caught and raise
  `ScopesFailedError` after the last scope (`consumers/scope_failures.py`),
  so the other scopes are still served. Covered: sales inbox, followups,
  auto-apply, skill replay, rule drafts, examples, prompt optimiser, pairs
  and shadow retention, purchasing automation, reaper, channel and web push
  delivery. Not changed: offboarding records a failed tenant in its own
  status; ingest, zalo and outbox record per-item failures.
- **Alerts** (`c9c062ea`).
  - `DwOutboxEventStuck`: the oldest pending event is over 1800 s for 10
    minutes. The gauge existed and no rule read it.
  - `DwDeliveryExhausted`: `dw_channel_delivery_exhausted_total{channel}`
    counts `attempts_exhausted` only, after the claim's transaction ends. It
    starts at 0 per channel, because `increase()` misses a series' first
    sample. Recipient-side ends (unlinked, unreachable, no device) are
    routine and not counted.
  - `DwBravoWriteNeedsAPerson`: reads `bravo.writes_needing_a_person()`
    (migration `fc8d358317fe`). That is SECURITY DEFINER, a count only, of the
    ledger's `in_doubt`, `reconcile_failed` and stale `claimed` rows across
    tenants; `dw_app` EXECUTE only. The `bravo_ledger_health` lane samples it
    every 5 minutes. The rule fires on a rise, because those ledger states
    are final.
  - `Watchdog`: always firing, routed to no receiver.
  - `alerts.test.yml` (promtool) tests every rule.
  - `test_alert_rules_read_emitted_metrics.py` replaces the plan's
    `ALL_METRICS` membership idea. That tuple declares names no code emits
    (`dw_task_success_rate`, `dw_human_intervention_rate`,
    `dw_retrieval_hit_rate`), so the test asks for an `add_metric` or
    `set_gauge` call on the constant instead.
- **Relay to a person** (`4901f0b3`). `15-alert-relay.sh` installs a 2-minute
  timer that writes `B:\DW-Backup\status\alerts.json` only from an answer
  `jq` parsed, through a rename. `host-watchdog.ps1` section 5d mails one
  check per alert and the lane or channel it names. It fails `alert-relay`
  when the file is 15 minutes old or lacks `Watchdog`, and leaves alert
  checks unjudged while the relay is down.

**Measured.**

- promtool: SUCCESS. Red under two mutations.
- Exporter names: read in-process.
- Relay: run against a real Alertmanager 0.28.1. Unreachable Alertmanager:
  exit 6, nothing written.
- `amtool check-config`: passes, with and without a webhook.
- Watchdog section: eight cases in PowerShell 5.1.
- Unit: worker, observability.
- Integration: `test_bravo_ledger_health_db.py` on Postgres.
- Every new guard has a mutation that turns its test red (listed in
  `sales.md`, "Production readiness").

**Not built: DW1 mailbox retention.** The plan would ship a delete of
customers' mail while its keep rule is still Đạt's to decide. The critique
showed that the plan's rule (keep while a linked case was touched within the
term) deletes evidence of live cases. A safe v1 must keep any mail named
anywhere: 10 `message_id` columns, and ids inside 20 JSONB columns
(`order_cases.confirmation/agreement/pc_reply/...`, `quote_cases.body`,
`po_layouts.body`, `salesorder_pairs.document`, `assistant_turns.cites`, ...).
It must also keep open inbox rows, leave `mailbox_files` alone (or a pruned
mail is read again from the folder), and lock `platform.audit_events` before
`sales.mailbox_*` (the `394419a5ebbd` deadlock order). With no term the
platform deletes nothing either way, so leaving it unbuilt changes no
behaviour.

**Owed.**

- Đạt: the term in days.
- Đạt: confirm the keep rule (only mail nothing references; mail of a case
  waits for a case term).
- Đạt: GitHub Actions billing, a runner for `deploy.yml`, and Pro/Team so
  the ruleset is enforced.
- Proterial: how long Prometheus, Loki and Tempo keep data (question 40).
- Plant (after 83): the relay drill (stop a lane or Tempo, mail, "OK
  again"); a timed backup restore with PITR; the first from-scratch DR
  drill; each gateway switch's UAT proof; a go-live tag from `main`.
- Plant: read the new metrics on the live worker's `:9464/metrics`; measure
  the thresholds on real traffic.

