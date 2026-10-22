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
| Ops hardening, on premises         | `.claude/plans/ops-hardening.md`    | Done; on-prem ran locally     |
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
- 2026-10-19, users change DW1 themselves: rules form (40), master data
  from Excel (41), follow-ups and the 07:30 brief (42).
- **2026-10-19, local Docker** (`sales.md` State): all suites pass per
  package; two defects fixed (`89bcd0d49ea6`, route walks); six live evals
  PASS on Qwen3.5-9B; on-prem compose ran (README); scope vs Proterial's
  process in `sales/dw1-scope.md`; deny-list secret set.
- 2026-10-20: pipeline board as the Sales home, a history per case, denser
  theme (`sales.md` State).
- **Next:** "Quy trình DW1" slices 2–3, defects A–E, the screenshot review (`sales.md` State 2026-10-21/22);
  `onprem-up` in `uat` behind Caddy; DW2 (Mua hàng) when its survey arrives, after the reuse decisions in `sales.md`.

## Decisions Đạt owes

- **Platform:** upstream `953086f`, `5452299`+`26d97dd` and this batch to
  `Datpt0205/codebase`; 46 citations of ADR-001..003 point at documents this
  repo never had; renumbering duplicate ADRs (left as they are).
- **Runtime:** a plan quota on direct model calls (the runner's only).
- **Ops:** the ClamAV bump is disabled on GitHub and nothing is pushed
  until Đạt says so (ticket 25); the deny-list grows once real data arrives.
- **On premises:** Proterial's AD details for LDAP federation, and whether
  the plant keeps internet (M365, Exchange Online) or none; whether the
  on-prem overlay takes api/worker off `dw-edge` (egress blocked by network,
  not only by configuration).
- **DW1 scope** (`sales/dw1-scope.md`): the agent-proposed bars of
  t29–t33 (t31 at 89.8% of 90%). Whether tenant IT may grant `sales_*`
  sets in the admin console at all (`sales.md` State, 2026-10-21).
- **Sales:** real data replaces the mock; HIGH: 9B accuracy by code around
  the model, decided on Proterial's server (`sales.md` State 2026-10-21).

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
