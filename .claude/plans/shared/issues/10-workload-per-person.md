# 10 — Each person's workload on the head's screen

Status: ready-for-agent
Blocked by: none (ticket 09 hangs its action here)
Category: assignment

## What

§3: "Khối lượng việc từng người trên màn của trưởng phòng". Checked
2026-11-27: not built; the head sees the case lists and the pipeline, not a
count per person.

## Design

- `GET /api/v1/sales/workload` (`sales.case.assign`): per member who works
  cases here (the same candidates as assignment), open orders and quotes by
  status group, how many are late against the server's SLA (the follow-up
  timings `my-work` already uses), how many wait on that person's decision,
  and unassigned in total. Counts only, never an amount.
- Computed by one SQL per kind with an index that leads with `tenant_id` and
  carries `assigned_to, status` (Data model rules: the index carries what
  the query groups by).
- Web: a "Khối lượng việc" table on `/sales/overview` for the head: one row
  per person, the counts as links to the filtered case list
  (`?assignee=<id>&late=1`), and "Giao lại tất cả…" (ticket 09).

## Acceptance

- Unit: late counted from the same SLA function as `my-work` (one owner);
  unassigned separate.
- API: refused without the scope; another tenant's members never counted
  (PostgreSQL).
- Web: every region state; the links carry the filter.

## Owed

- none.
