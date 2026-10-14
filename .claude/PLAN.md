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
| Sales — Proterial DW1              | `.claude/plans/sales.md`            | 13–24, 26, 28–34 done         |
| Chat channels (Zalo)               | `.claude/plans/channels.md`         | Upstreamed; live run owed     |

After working in an area, update its file. Update this index only when an
area's state, the next step or a decision owed changes. A new area gets its
own file and a row here.

## Now (2026-10-13)

- **Proterial product repo** (`origin` `Datpt0205/dw-proterial`; platform
  seed in `Datpt0205/codebase`). DW1 (Đơn hàng & Báo giá) on mock data:
  `sales.md`, spec and tickets under `sales/dw1-portal-demo/`; demo runbook
  `demo.md`, `make demo-reset`, `make test-web-sales`, eval `sales@1.2.0`.
- dw_sales ADR 0004 (checker decisions on the runtime) is Proposed, Đạt to
  review. Platform pieces waiting for a first caller: `platform-runtime.md`.
- 2026-10-13/14 (agent, Đạt away): sales 19, 21, 23, 24, 34, 35, 36 done;
  25 ("DW xử lý" queued, files read in the `reader` container) and 27
  (LibreOffice, Tesseract there) built, owing the post-reboot checks.
- **Next:** CI green on 1621cbc but for the public-repo guard (Đạt: create
  the PUBLIC_REPO_DENYLIST secret). After a reboot: ticket 27's reader
  timings and the support-access 03 walk. Đạt reviews 28–33 and ADR 0005.

## Decisions Đạt owes

- **Runtime:**
    - sales roles decide UNSTAMPED approvals via `approvals.decide`
      (`sales.md` Open: a stamp standing in for it, or stamped platform types);
    - a plan quota on direct model calls (`runs_per_day`/`spend_usd_per_day`
      are enforced only in the runner);
    - the model profile and key for uat/production (local runs on `luna`,
      gpt-5.6-luna, `make check-model`; the key is only in local `.env`);
    - the rerank key for uat/production (FPT Cloud locally, `make check-rerank`);
- **Ops:**
    - spend guard dollar thresholds per plan;
    - a retention term for offboarding export bundles;
    - how many superseded document versions to keep.
- **Platform:**
    - backfill ADRs with a status (`docs/agents/domain.md`): 46 citations of
      ADR-001..003 point at documents this repo never had.
- **Sales:**
    - dw_sales ADR 0005, bars 28 71%, 29 94.6%, 31 90.9%, 32 95.7%, 33
      94.5%, 30 98.2%; ADR 0004's amendment (run-less layout approval);
    - the interim defaults listed in `sales.md` Open;
    - whether pausing DW1 also stops rendering drafts and files.
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
