# Plan — index

`.claude/hooks/session-start.sh` reads this file whole at session start and
warns past 80 lines, because an index that grows stops being read. It holds
four things: where each area stands, what is next, what Đạt still owes, and
how a feature is checked. Detail lives in the area file. History lives in
git: every slice's commit message, and the pre-split narrative at
`git show 84e3f6a:.claude/PLAN.md`.

## Areas

| Area                               | File                                | State                       |
| ---------------------------------- | ----------------------------------- | --------------------------- |
| Ops hardening, on premises         | `.claude/plans/ops-hardening.md`    | + SSE chat, warm 11-06      |
| Agent runtime and memory (Mốc 0–6) | `.claude/plans/platform-runtime.md` | Done but for named gaps     |
| Web UI shell (Ant Design v6)       | `.claude/plans/web-ui.md`           | antd, React Flow, AntD X    |
| Sales — Proterial DW1              | `.claude/plans/sales.md`            | 03,05½,06,07,09-11,14,16-22,24-38,40,41,42½,43-48; 11-21: 59 (SO, YCBG offline), 62 (orders, quotes), 56 (flag + Bravo write in chat), 57 (chat step + bar + labels), 43 (examples as readings: 3/8 → 8/8 on Strata; PO-in-mail examples, no gain; body PO now storable; examples seen stamped 11-23; only the plant's attests left), tester pass 11-22 (roundabout chat 6/6 on question_intent 1.4.0, mail 7/8), 61 step 1 + step 2's first slice (write Bravo pinned per case, 11-23), 39 (two levels with an order, 11-23), 63 (gateway, offline + test SQL Server), 65 (watch, no nightly replay), 64 (links; AD pending), 53 (date/qty end to end offline), 51 (read-back via gateway; create pending 03c), 50 (copy by rowversion; checks pending) |
| Chat channels (Zalo)               | `.claude/plans/channels.md`         | No Zalo at Proterial 11-11  |
| Purchasing — Proterial DW2         | `.claude/plans/purchasing.md`       | rebuild spec 11-13 (T2–T24) |

After working in an area, update its file. Update this index only when an
area's state, the next step or a decision owed changes. A new area gets its
own file and a row here.

## Now (2026-10-19)

- **Proterial product repo** (`Datpt0205/dw-proterial`): DW1 on mock data,
  `sales.md`, tickets under `sales/dw1-portal-demo/`, runbook `demo.md`.
- **On premises** (Đạt, 2026-10-18), DW1 and DW2: Qwen3.5-9B, bge-m3 and
  bge-reranker-v2-m3 on the plant's host, no API called;
  `infra/onprem/README.md` (`make onprem-models`, `make onprem-up`).
- **2026-10-19, local Docker** (`sales.md` State): all suites pass per
  package; two defects fixed (`89bcd0d49ea6`, route walks); six live evals
  PASS on Qwen3.5-9B; on-prem compose ran (README); scope vs Proterial's
  process in `sales/dw1-scope.md`; deny-list secret set.
- 10-19..30: rules, master data, follow-ups, mail drop, DW1 learns PO forms,
  Q&A and reminders (contract gaps closed). `sales.md` State.
- **Now:** onsite survey since 11-09 (DW1 90%, DW2 60%; daily status in the
  rollout `.xlsx`, kept out of commits); then UAT (`.claude/plans/hitl-review.md`).
- **CRITICAL, parked (Đạt, 11-16): RAG on premises** has no PDF/Word/Excel
  parser and cuts tables (`platform-runtime.md` Open). Infrastructure first;
  then ask Đạt and do it with the code tickets.

## Decisions Đạt owes

- **Platform:** upstream `953086f`, `5452299`+`26d97dd` and this batch to
  `Datpt0205/codebase`; 46 citations of ADR-001..003 point at documents this
  repo never had; renumbering duplicate ADRs.
- **Runtime:** a plan quota on direct model calls (the runner's only).
- **Ops:** push only when Đạt asks; repo private since 11-23, so the main/dev ruleset is not enforced until GitHub Pro; history rewritten 11-23 (commit ids in plans are pre-rewrite; backup branch + bundle), 5 CI jobs red; the rollout `.xlsx` restored from the 11-10 Teams copy (check); ClamAV bump off (ticket 25).
- **On premises:** Proterial's AD details for LDAP federation, and whether
  the plant keeps internet (M365, Exchange Online) or none; Bravo is on its
  own Windows Server, DW on Ubuntu; support without VPN (11-09,
  `ops-hardening.md`); host: Windows Server 2025 with UI (11-16), DW in an Ubuntu Hyper-V VM; Strata on Windows, Q2 with vision (decided 11-16; host set up over Tailscale, boot on SSD, Hyper-V, GPU driver: `ops-hardening.md`); Strata settled (ticket 01 closed by Đạt 11-16); Tailscale expiry off (11-16); mail flows Tue/Wed 11-17/18 evening with ticket 23; Bravo API waits on a three-party meeting, Đạt exports screens meanwhile; Bravo through one gateway over its database (ADR 0027, 11-21, supersedes 0026: `apps/bravo-gateway` the only credential holder, nothing created in Bravo's DB, column grants, writes as the PIC checked by token + live identity + Bravo's own rights + screen rules; identity anchored on the employee code, Keycloak federated to the AD; tickets 63 gateway, 64 identity, 65 change watch (notify, pause only what depends), 50/51/53 ready-for-agent; owed on site: scripts 05, 03c, 06, 07 and IT's AD answers (ticket 52); the 11-20 design docx needs a new version before IT and the vendor review); DW1 tickets 49–64 (DW performs Import itself; Bravo's XML rules run by DW, 59: SO screen runs offline, create/split wait on script 03c; 61: design confirmed 11-23, step 2 on write-Bravo first; vendor asked for an automatic path, 60; stages as versioned lanes, no new services, 61); pending on Proterial's host: scripts 05 and 03c, UAT saves (52); the BA owes which field marks a special item: `sales.md` 11-20); mail via Teams (11-12), customers writing only to the shared box?; api/worker off `dw-edge`; iPhone push: built (ticket 48); owed: the iPhone trusting the portal's certificate, the host reaching `web.push.apple.com`, the push contact (`DW_WEB_PUSH_SUBJECT`).
- **DW1 scope** (`sales/dw1-scope.md`): agent-proposed bars t29–t33; new flow 11-13 (`dw1-production` 17–35, conversation designed: dw_sales ADRs 0009–0012): Proterial owes contacts, mail templates, LME bands, PC stock, NOC records, which customers take silence as agreement and after how many days; Đạt owes an M365 mailbox to measure the sent-mail export (ticket 23), Strata access for the tool-calling eval (30), the BA's two `.drawio` originals (gone from Downloads), and confirming ADR 0009's sender-ledger amendment; two calls from the hardcode audit (`.claude/plans/hardcode-audit-2026-11-13.md`): ambiguous numbers/dates now go to a person, so RFQ and hand-off reading sit under their live bar until ticket 37 (keep, or settle by language), and every value of a locked PO is flagged (ticket 17; 225 lines to confirm); from the 11-14 Box files: ticket 39 (quote approval levels), each customer's PRV Sales PIC; from B41: does Bravo convert the customer code on import, is "người lập" the PIC's Bravo code; from ticket 36's run (TAISEI 293, PCS 225, FBHP 50 lines all exact): a lead time per real item (B13's groups do not match B06's categories), units "PC"/"Pcs" vs m, PCA's customer row and convert codes; from ticket 38: one real pair (PO + the PIC's SalesOrder file) per customer for the replay proof; from 19/22: which of two disagreeing files of a PO wins, and whether a mail's other POs open when one cannot; from 25/26: does a PIC's forward of a PO open a case, do Design/PC get DW sign-ins; the thread-intent step at 0.816 < 0.85 stays off; from 27: may an order be prepared with a change request open, quantities in a change table, km→m per customer; from 07: PC's request form, reminder interval (24 h now), first confirmed date on a re-split; from 29: PC earlier than asked = can do?, Bravo update approved by PIC or head; from 28: holidays for business days, the "processed Excel" (B11) and the paste sheet's internal sheet going to a customer; from 30/31: the thread agent's bar (0.85, local proxy met it, 2 tool calls in 72) and turn ceiling; dw_sales ADR 0014 accepted 11-16 (deep agent, tenant-edited AGENT.md/SKILL.md, code only guards; ticket 40, then 41 (SalesOrder as a skill with tools, every cell traced; amends ADR 0013), 42 (18 hard-coded readings to skills; a pc_dates day-first bug first), 43-44 (ADR 0015, accepted 11-16: corrections become examples and re-optimise prompts; reversible steps apply themselves under a measured error rate with audits, Bravo and anything sent stay approved; defaults decided 11-16: T0 5%, T1 2%, T2 never, 3% audit, shadow mode until labelled, skill picked by one scored call; owed: the latency budget per step), 46 (one conversation per case on its page, one general per person) 47+48 ("Việc của tôi": brief, reminders and every decision inline in one place, pushed to the iPhone, ordered by SLA; first after 43a, for 11-18), the Qdrant review (a cross-tenant delete fixed `3fbb0db6`; ticket 45 done: hybrid search on v1.20.1, measured eval), 33/34; measured on Giang's home-lab Strata first, reachable with its key since 11-16); from 42 (families 1, 3, 5 done, all off): a tenant's own hand-off kind in its own words (key `sales_handoffs` by kind?), the reply-drafts skill 0.833 < 0.85; from 16: `sales-demo.spec.ts`'s old YCBG numbers; from 02: where Bravo keeps a customer's delivery term; from 41: which PCS PO column is the PRS number (none is so titled), and where PCS's price and unit come from (its PO grid prints neither); from 10: a cancelled line in Bravo's "Thay đổi chi tiết" (0 row or deleted), a blank paste date over the first confirmed date; from 14: B43 filled for one PO; from 03: Q-B6 (B02 has POs under 2-4 SOs); from 11: the full Base price list (B21 has the latest 100), (an anchor kind is not needed: B16 holds BP, spec and copper in one file, 11-17); from 05: SGA/loyalty/profit fixed per pcs order?, is JP & HQ the GM at PRV?, the assembly-cable variant, one example of the mail to the GM; from 32: the reply-draft bar, Japanese thousands separators, prices in an AI confirmation; from 35: export control's owner, silence days in master data, three settings' meaning, the BA's words for 0-KH/6-PC; from Strata (11-16, all 23 sets, 3 bars missed: reply 0.796, RFQ 0.833, thread agent's one false accept): bge-m3's host, prompts vs steps off, CI re-recorded from Strata 11-23 (plant attests owed).
- **Model:** Qwen3.8 only (11-10); Strata settled 11-16 (ticket 01); scans by its vision, else PaddleOCR-VL/small CPU model + Tesseract boxes (11-12; Giang: Strata vision, WAF).
- **Sales:** real data replaces the mock; HIGH: 9B accuracy by code around
  the model, decided on Proterial's server (`sales.md` State 2026-10-21);
  retention of `sales.step_outcomes` (365 days, 10-23) and of stored mail;
  the IP-indemnity clause's wording (carve-outs, cap) with FPT legal;
  DW2 go-live week 4 vs 6; rollout `.xlsx` out of git (repo public);
  `sales/dw1-production` tickets 08, 15.
- **Purchasing:** Proterial list (`docs/proterial/`). **Roles:** ~7 for both DWs (`sales.md` Open).

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
