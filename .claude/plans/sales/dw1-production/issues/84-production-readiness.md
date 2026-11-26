# 84 — Production readiness for DW1

Status: needs-info (several of Đạt's decisions)
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
