# Plan — index

`.claude/hooks/session-start.sh` reads this file whole at session start and
warns past 80 lines, because an index that grows stops being read. It holds
four things: where each area stands, what is next, what Đạt still owes, and
how a feature is checked. Detail lives in the area file. History lives in
git: every slice's commit message, and the pre-split narrative at
`git show 84e3f6a:.claude/PLAN.md`.

## Areas

| Area                               | File                                | State                         |
| ---------------------------------- | ----------------------------------- | ----------------------------- |
| Ops hardening, on premises         | `.claude/plans/ops-hardening.md`    | Done; on-prem stack unrun     |
| Agent runtime and memory (Mốc 0–6) | `.claude/plans/platform-runtime.md` | Done but for named gaps       |
| Web UI shell (Ant Design v6)       | `.claude/plans/web-ui.md`           | antd only; product theme; CSP |
| Sales — Proterial DW1              | `.claude/plans/sales.md`            | 13–42 built                   |
| Chat channels (Zalo)               | `.claude/plans/channels.md`         | Upstreamed; live run owed     |

After working in an area, update its file. Update this index only when an
area's state, the next step or a decision owed changes. A new area gets its
own file and a row here.

## Now (2026-10-19)

- **Proterial product repo** (`origin` `Datpt0205/dw-proterial`; platform
  seed in `Datpt0205/codebase`). DW1 on mock data: `sales.md`, tickets
  under `sales/dw1-portal-demo/`, runbook `demo.md`, eval `sales@1.3.0`.
- **On premises** (Đạt, 2026-10-18), DW1 and DW2: Qwen3.5-9B, bge-m3 and
  bge-reranker-v2-m3 on the plant's host, no API called;
  `infra/onprem/README.md` (`make onprem-models`, `make onprem-up`).
- 2026-10-19, so users change DW1 themselves (Đạt): rules edited in a form
  drawn from each key's schema with a diff before approval (ticket 40);
  master data imported from Excel, previewed, approved, mock until then
  (41); follow-ups and the 07:30 brief, every timing in `sales_followups`
  (42). Migrations `d2b1394c67b1` -> `511ef1b71dee`.
- **CI on main:** Prettier fixed (`63fe6b3`); the public-repo guard fails
  until the `PUBLIC_REPO_DENYLIST` secret exists; integration tests red
  since 2026-10-14, cause unread (logs need sign-in, no Docker here).
- **Next:** on a machine with Docker and a GPU: the integration suites
  (why red since 10-14 first), the migration round trips, `onprem-up`,
  `check-rerank`, the live eval, `make web-screens` (pages of 39-42 never
  looked at). Then DW2 when its documents arrive.

## Decisions Đạt owes

- **Platform:** upstream `953086f`, `5452299`+`26d97dd` and this batch to
  `Datpt0205/codebase`; 46 citations of ADR-001..003 point at documents this
  repo never had; renumbering duplicate ADRs (left as they are).
- **Runtime:** a plan quota on direct model calls (the runner's only).
- **Ops:** the `PUBLIC_REPO_DENYLIST` secret; allow Actions to open PRs
  (ClamAV bump, ticket 25); restart WSL for 25/27's checks.
- **On premises:** Proterial's AD details for LDAP federation, and whether
  the plant keeps internet (M365, Exchange Online) or none.
- **Sales:** Proterial's real data replaces the mock (`sales.md` Inputs
  owed); the interim defaults in `sales.md` Open.

## How a feature is checked here

1. `scripts/verify_invariants.py`: mechanical checks, run in CI and in the
   commit hook.
2. `.claude/hooks/pre-commit-gate.sh`: runs layer 1, then asks only the
   questions this diff earns.
3. `.claude/skills/reviewing-feature-security/`:
    - six trust boundaries, with a negative test at each;
    - a mutation check;
    - run before calling a feature done, without being asked.
4. `.claude/skills/reviewing-deployment-security/`: deployed-profile exposure,
   secrets, CORS, outbound URLs, and a scan of every new image.
5. `mattpocock-skills` (`/ask-matt` routes): the flow from grilling to
   `/implement` and `/code-review`; `CLAUDE.md` "Agent skills" places
   layers 1–4 inside it.

`.claude/rules/failure-modes.md` holds the counts behind layers 1–3. Layer 2
guarantees the questions get raised, not that they get answered truthfully.
No layer replaces running the thing.
