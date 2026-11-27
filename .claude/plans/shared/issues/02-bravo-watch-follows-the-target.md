# 02 — The Bravo change watch guards the Bravo in use, and has a page

Status: ready-for-agent
Blocked by: none (Sales ticket 85 built the target)
Category: Bravo gateway

## What

`docs/dev/viec-chung-dw1-dw2.md` §6: "Replay hằng đêm các lần lưu đã ghi
lại; trang theo dõi; thêm màn DW2 (ticket 65)" — the page part here, plus
the gap Sales ticket 85 left ("a ticket for the watch to follow the target
is owed"). ⚑ for DW1's UAT run: the watch fingerprints and baselines
`production` only (`packages/python/dw_bravo/src/dw_bravo/watch_lane.py:95-102`),
so a gateway holding only UAT logins cannot fingerprint, every kind pauses
once the age limit passes (fail closed), and nobody can accept a baseline.
Today a UAT run needs production logins or pauses lifted by hand.

The nightly replay is ticket 26; DW2's screens join the watch in ticket 31.

## Design

- **The guarded Bravo is the tenant's target now** (`SqlSwitches.target`,
  ticket 85), the same answer the gateway routes writes by. The lane
  fingerprints that target; when the target is `production` and UAT is
  configured, UAT stays the early warning it is today.
- **Baselines per target:** `bravo.watch_baselines`, `watch_fingerprints`,
  `watch_reads` gain `target` (migration, `NOT NULL`, CHECK
  `uat|production`, rows stored backfilled `production`, which is what the
  lane read). `BravoWatchService.accept` takes the latest fingerprint of the
  target in use only. A switch of target with no baseline for the new one
  pauses every kind until a person accepts (fail closed, as today).
- **The page:** `/sales/bravo/watch` (the API is there:
  `GET /api/v1/sales/bravo/watch`, `POST .../baseline`, scopes
  `sales.bravo.watch.read`/`.accept`): the target tag ("Bravo UAT"/"Bravo
  thật", `bravo-target.tsx`), each write kind paused or not and why, what
  changed (layout, column, trigger, routine) since the baseline, when Bravo
  was last read, and "Chấp nhận thay đổi" disabled with its reason without
  `.accept`. Linked from the rules page's Bravo card.

## Acceptance

- Unit: target UAT → UAT fingerprinted and baselined; switch to production
  with no production baseline → every kind paused; accept takes the target's
  latest only; the early warning only when the target is production.
- PostgreSQL: CHECK on `target`; another tenant sees and accepts nothing;
  history append-only (existing tests extended).
- Web: page states (loading, error, forbidden, a pause, nothing paused); the
  accept button refused by the server without the scope (test against the
  route, not the hidden button).
- Mutation: the lane reading `production` regardless of target turns a test red.

## Owed

- none for the code; running it live needs the UAT read login (Proterial IT,
  Sales ticket 63/85).
