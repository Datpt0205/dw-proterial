# Plan — index

`.claude/hooks/session-start.sh` reads this file whole at session start and
warns past 80 lines, because an index that grows stops being read. It holds
four things: where each area stands, what is next, what Đạt still owes, and
how a feature is checked. Detail lives in the area file. History lives in
git: every slice's commit message, and the pre-split narrative at
`git show 84e3f6a:.claude/PLAN.md`.

## Areas

| Area                               | File                                | State                    |
| ---------------------------------- | ----------------------------------- | ------------------------ |
| Ops hardening                      | `.claude/plans/ops-hardening.md`    | Done; numbers owed       |
| Agent runtime and memory (Mốc 0–6) | `.claude/plans/platform-runtime.md` | Done but for named gaps  |
| Web UI shell (Ant Design v6)       | `.claude/plans/web-ui.md`           | Shell landed; pages next |
| Sales — Proterial DW1              | `.claude/plans/sales.md`            | Spec + tickets; building |

After working in an area, update its file. Update this index only when an
area's state, the next step or a decision owed changes. A new area gets its
own file and a row here.

## Now (2026-10-03)

- **This repo is now the Proterial product repo** (`origin`
  `Datpt0205/dw-proterial`; the platform seed stays in `Datpt0205/codebase`).
  Context `dw_sales` is scaffolded; DW1 (Đơn hàng & Báo giá) is being built
  end to end on mock data: `sales.md`, spec and tickets under
  `sales/dw1-portal-demo/`.
- A conformance review found the plan misses process steps (cross-check,
  revised PO, quotation steps) and roles; `sales.md` lists the amendments.
- Platform pieces still waiting for a first caller: `platform-runtime.md`.
- **Next:** finish tickets 01–03 and 07, amend the spec and tickets per the
  review, then 04/05/06/08.

## Decisions Đạt owes

- **Runtime:**
    - a plan quota on direct model calls (`runs_per_day`/`spend_usd_per_day`
      are enforced only in the runner);
    - the model profile and key for uat/production (local runs on `luna`,
      gpt-5.6-luna, `make check-model`; the key is only in local `.env`);
    - whether CI runs the web vitest suite.
- **Ops:**
    - spend guard dollar thresholds per plan;
    - a retention term for offboarding export bundles;
    - how many superseded document versions to keep.
- **Platform:**
    - backfill ADRs with a status (`docs/agents/domain.md`): 46 citations of
      ADR-001..003 point at documents this repo never had.
- **Sales:**
    - alias Proterial and its procedure codes in the public repo, or not;
    - the quotation-time target the demo measures;
    - the interim defaults listed in `sales.md` Open.

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
