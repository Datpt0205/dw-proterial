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
| Ops hardening                      | `.claude/plans/ops-hardening.md`    | Done; numbers owed            |
| Agent runtime and memory (Mốc 0–6) | `.claude/plans/platform-runtime.md` | Done but for named gaps       |
| Web UI shell (Ant Design v6)       | `.claude/plans/web-ui.md`           | antd only; product theme; CSP |
| Sales — Proterial DW1              | `.claude/plans/sales.md`            | 13–38 built; 39 needs-info    |
| Chat channels (Zalo)               | `.claude/plans/channels.md`         | Upstreamed; live run owed     |

After working in an area, update its file. Update this index only when an
area's state, the next step or a decision owed changes. A new area gets its
own file and a row here.

## Now (2026-10-17)

- **Proterial product repo** (`origin` `Datpt0205/dw-proterial`; platform
  seed in `Datpt0205/codebase`). DW1 (Đơn hàng & Báo giá) on mock data:
  `sales.md`, spec and tickets under `sales/dw1-portal-demo/`; demo runbook
  `demo.md`, `make demo-reset`, `make test-web-sales`, eval `sales@1.3.0`.
- 2026-10-17: Đạt (proposal of 2026-10-13): DW1 and DW2 (Mua hàng: Yêu cầu
  mua & PO) both on premises, UAT first on mock values; DW2's process
  documents to come. Closed: `supported_channels` enforced, one
  `awaits_cross_check`, the picker as entered (`b65956a`, `2b23a1b`).
- **Next:** Đạt runs the Docker/CI suites and pushes; then DW2 as a new
  context (`make new-context NAME=purchasing`) once its documents arrive.

## Decisions Đạt owes

- **Runtime:**
    - sales roles decide UNSTAMPED approvals via `approvals.decide`
      (`sales.md` Open: a stamp standing in for it, or stamped platform types);
    - a plan quota on direct model calls (`runs_per_day`/`spend_usd_per_day`
      are enforced only in the runner);
    - on premises: `DW_API_MODEL_PROFILE=onprem` and no external key or
      reranker for uat/production (recommended 2026-10-17; `luna` and FPT
      Cloud rerank stay local-only);
- **Ops:** spend guard dollar thresholds per plan; a retention term for
  offboarding export bundles; how many superseded document versions to keep.
- **Platform:**
    - upstream `953086f` (offboarding) and `5452299`+`26d97dd` (manifest
      pins) to `Datpt0205/codebase`; offboard tenant service users (sales 16);
    - ADR 0024's support masking clause; backfill ADRs with a status
      (`docs/agents/domain.md`): 46 citations of ADR-001..003 point at
      documents this repo never had.
- **Sales:**
    - the interim defaults listed in `sales.md` Open;
    - whether pausing DW1 also stops rendering drafts and files;
    - the Sales bar layout (ticket 39: two rows, a submenu, or the drawer
      below `xl`); allow Actions to open PRs (ClamAV bump, ticket 25);
    - restart WSL (admin): 25/27's image, trivy and integration runs wait.

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
