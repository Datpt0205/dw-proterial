# Plan — index

`.claude/hooks/session-start.sh` reads this file whole at session start and
warns past 80 lines, because an index that grows stops being read. It holds
four things: where each area stands, what is next, what Đạt still owes, and
how a feature is checked. Detail lives in the area file. History lives in
git: every slice's commit message, and the pre-split narrative at
`git show 84e3f6a:.claude/PLAN.md`.

## Areas

| Area                               | File                                | State                           |
| ---------------------------------- | ----------------------------------- | ------------------------------- |
| Ops hardening                      | `.claude/plans/ops-hardening.md`    | Done; numbers owed              |
| Agent runtime and memory (Mốc 0–6) | `.claude/plans/platform-runtime.md` | Done but for named gaps         |
| Web UI shell (Ant Design v6)       | `.claude/plans/web-ui.md`           | Prototype theme; Sales restyled |
| Sales — Proterial DW1              | `.claude/plans/sales.md`            | Demo done; 10 built; 12 left    |

After working in an area, update its file. Update this index only when an
area's state, the next step or a decision owed changes. A new area gets its
own file and a row here.

## Now (2026-10-06)

- **This repo is now the Proterial product repo** (`origin`
  `Datpt0205/dw-proterial`; the platform seed stays in `Datpt0205/codebase`).
  Context `dw_sales` is scaffolded; DW1 (Đơn hàng & Báo giá) is being built
  end to end on mock data: `sales.md`, spec and tickets under
  `sales/dw1-portal-demo/`.
- DW1's demo is built (tickets 01–09, 11): eval `sales@1.0.0` in the eval
  smoke, runbook `sales/dw1-portal-demo/demo.md`, `make demo-reset`,
  `make test-web-sales`. All committed and pushed (`2284d3c`).
- Platform pieces still waiting for a first caller: `platform-runtime.md`.
- Sales ticket 10 committed 2026-10-06 (`8d098b3`): DW1 runs on the runtime,
  quotation approval and cross-check are platform approvals (dw_sales ADR
  0004 Proposed, Đạt to review).
- Platform `92a1571` merged 2026-10-06: FCI rerank, six hardening slices.
- **Next:** sales 12 (production hardening, needs-triage).

## Decisions Đạt owes

- **Runtime:**
    - a plan quota on direct model calls (`runs_per_day`/`spend_usd_per_day`
      are enforced only in the runner);
    - the model profile and key for uat/production (local runs on `luna`,
      gpt-5.6-luna, `make check-model`; the key is only in local `.env`);
    - the rerank key for uat/production (local reranks through FPT Cloud,
      `make check-rerank`; the key is only in local `.env`);
    - whether CI runs the web vitest suite.
- **Ops:**
    - spend guard dollar thresholds per plan;
    - a retention term for offboarding export bundles;
    - how many superseded document versions to keep.
- **Platform:**
    - backfill ADRs with a status (`docs/agents/domain.md`): 46 citations of
      ADR-001..003 point at documents this repo never had.
- **Sales:**
    - the interim defaults listed in `sales.md` Open;
    - whether pausing DW1 also stops rendering drafts and files.

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
