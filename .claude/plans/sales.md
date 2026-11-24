# Sales (Proterial Vietnam) — DW1 Đơn hàng & Báo giá

This repo became the Proterial product repo on 2026-10-02: `origin` is
`github.com/Datpt0205/dw-proterial` (public; Đạt keeps it public for now).
The platform seed stays in `Datpt0205/codebase`. DW01 (procurement) keeps
running in `C:\Users\phung\dw` and gets no new features; it moves here when a
Purchasing DW for Proterial is signed (estimated 30–51 person-days).

## State

- 2026-11-24, **ticket 66, a customer's SalesOrder skill drafted by the model** (Đạt: "làm phần model soạn skill riêng đi"; ADR 0013 addendum): a kept worked pair writes `sales.salesorder_pair.added`; the worker fills the customer's pairs with the skill in force and, where they differ from the PIC's files, the model writes the customer's whole skill (`sales.salesorder_skill_draft@1.0.0`, up to 3 rounds on its own differences); code refuses a new constant no PIC's file holds or that is a PO value, replays the draft and proposes it as the lane only where it reproduces more pairs and loses none; the head decides as before. Eval `sales_salesorder_skill_draft@1.0.0` (smoke 4/4). Live on Giang's Strata (not attested, 5 runs): KHA and KHC need no skill of their own (the generic one reproduces them), KHB drafted and proposed in one round every run, a constant planted in a PO never proposed. 50 customers are not 50 skills: only the ones whose files the generic skill does not reproduce get one. Left: real pairs to measure on (ticket 38's Remains).
- 2026-11-24, **one call vs the agentic steps, rerun live on Strata** (Giang's home lab, flash next Q2, not attested; no recordings changed; Đạt asked whether the agentic direction reads better): replies in a thread, same 60 messages: one call + code checks (`reply_intent`) 0.850 (bar set 0.837), p50 1.8 s / p95 2.3 s, 1 call; agent with tools (`thread_agent`) 0.767 (0.800), 2.9 / 4.8 s, 1.81 calls and 58 look-ups; agent with skills (`dw1_agent`, ticket 40) 0.900 (0.883), 4.8 / 6.9 s, 2.01 calls; no false accept on any path. Unread mail 0.98 one call vs 1.00 with the tenant's mail-kind skill; hand-off 0.877 and drafts 0.917 identical both ways. Read: tools do not help reading (worst, most calls); a skill helps by +3 of 60 replies (inside one message's noise at n=60) for about 2.6x the latency. Recommended, owed by Đạt: keep the code-run flow with one model call per step and tenant skills inside it (ADR 0014/0015 as amended); `skill_intents` the only agent step, on in shadow beside `reply_intent` once attested on the plant; drop the tool-using thread agent. Note: 98-100 % seen before is unread-mail sorting and CI's replayed cases passing their floors, not reply reading, which reads 0.85-0.90 on every path.
- 2026-11-23, **ticket 61 step 2, write Bravo pinned per case**: `CaseOrigin.stage_versions` stamped at open (migration `7add0d23936a`, a trigger refuses any change), `StageHandlers` dispatching the Bravo line write and its signing by the case's version, the API and worker refusing to start while an open case runs on a version no handler serves. 5 mutations red. Left: per-PIC rollouts and shadow, the manifest's stage entries.
- 2026-11-23, **ticket 39, two levels for a quotation with an order** (WIV-03-023 §4): the first level checks it (`QuoteCheck` on the submission, the case still waiting) and opens a run-less `sales.quote.manager` approval (scope `sales.quote.manager_approve`, migration `3748b069dd99`: the head and set `sales_quote_manager`), makers the pricer, the submitter and the checker; the worker carries out the Manager's approve or return. 8 mutations red. Left: "Không duyệt", the order resuming by itself (today "Kiểm tra lại"), the quote page's words.
- 2026-11-23, **CI's recordings re-recorded from Strata** (Giang's home lab, flash next Q2, not attested; Đạt's call): 13 recorded files, 14 sets live, every set PASS live (intent 0.98 of 100). One answer lost to the network came back null and was asked again. `skill_intents` kept its plant recording of 11-16 (better provenance than the home lab); the thread agent's floor moved to Strata's own 0.833 of 72 (0.85 of the bar's set, met; 9B read 0.861). Smoke 47/47. The plant's attested runs stay owed.
- 2026-11-23, **PC's mailboxes named in the order rules** (`sales_order_rules@1.16.0`, `pc_mailboxes`, step O4, editable on /sales/rules): once named, the PC-dates panel lists and reads only a verified mail from one of them naming the order; empty (every earlier version) lists as before with the sender shown. 3 mutations red. Not built: the lane reading PC's answer unasked.
- 2026-11-23, **CI green again on dev** (PRs #6, #7): gitleaks fingerprints re-keyed after the history rewrite, ruff and Prettier skip the three held files by name, nine mypy findings, bandit B314 (the Import template refuses a DOCTYPE as the layout reader does), wcmatch 11.2 (GHSA-53pm-wgxf-c6qf), four scope labels and nine assistant words, the platform eval dataset renamed in a test. Each red job had been hidden behind the one before it since at least 11-12.
- 2026-11-23, **Đạt decided the owed DW1 calls as recommended**: 03 closed (the vendor API gave way to the gateway); 08 no NOEC draft, the hold reads Bravo's ECP and black list through ticket 50's copy (pending the match routine on Proterial's host); 15 outside DW1 (a change request); 39 ready (two levels per WIV-03-023, no new role); 53's one-person Bravo write confirmed; 57's bar stays 0.85, CI recordings re-recorded from Strata; 61's design confirmed, step 2 on the write-Bravo stage first; a `pc_mailboxes` setting and the red CI jobs to fix. What waits on Proterial, the BA or IT stays pending in each ticket.
- 2026-11-23, **ticket 43, which decided lines a reading saw**: `DescriptionReading.examples` stamps the labelled case ids the call showed (found and shown, never the version's demonstrations, at most 12, each once; an unavailable reading too), ids rather than a time because the search is by similarity; the line trail says "đã xem N dòng đã quyết". Old bases read as none. API: a count on the trail step, ids on a quote item's reading. 8 mutations red. Ticket 43 has only the plant's attested runs left.
- 2026-11-22, **tester pass on unread mail (ticket 31's step)**: eight roundabout mails in `sales_intent@1.1.0` (an order after an apology, an invoice question on an old PO, thanks then a postponement, a quote inside a party reply, a polite complaint, an indirect Japanese postponement, "đặt như đơn tháng trước", a sample inside a project story). Strata 0.97 of 100, 7/8 roundabout; "đặt như đơn tháng trước" read `reply_to_case` (no number, so a person reads it; not patched for one sentence). Recordings mixed 9B (92) and Strata (8) until Đạt decides the re-record.
- 2026-11-22, **tester pass on the case chat (Đạt: staff never ask straight)**: six conversations of several turns on M06 (`sales.case_chat_roundabout`, `sales_case_chat@1.2.0`): chatter first, a mind changed, a flag named a turn later, another PO in passing, a question back, two flags then "cái đó". Strata on `question_intent@1.3.0`: 3/5, a flag said in an earlier turn was asked again; `question_intent@1.4.0` (bundle 1.7.0) takes the flag and reason from the person's own earlier turns, still only from FLAGS and confirmed by the PIC: 6/6 (asks back when two were named), golden 8/8, writes 3/3, security held. Owed: the plant's attested run on 1.4.0.
- 2026-11-22, **ticket 43, the second step, and a defect of AI item 4 fixed**: `po_body_extraction@1.2.0` (bundle 1.6.0) is shown the sender's customer's newest decided values, cut by code from the stored mail (`right` kept, `wrong` corrected; an implied value never), from PostgreSQL under RLS; any failure reads without them. Strata (not attested), 4 roundabout mails with customer-specific traps: 1.0 without and with examples, no gain, no loss. Found by the integration test: a PO read from a mail body could never be stored on PostgreSQL (`ck_order_revisions_attachment_id`), fixed by migration `4b3f44f30356`. 9 mutations red. Left: stamping which examples a reading saw; pending: attesting both steps on the plant.
- 2026-11-22, **ticket 43, a measured gain: examples shown as confirmed readings**: a decided line whose accepted reading fits the kept item is shown as that reading in the answer's shape (`read`), else as the item (`item`); prompt `description_attributes@1.2.0` (bundle 1.5.0); a one-letter label inside a longer word ("R" beside "RL") no longer refused when it is a whole word once. Strata (not attested), `sales_description_examples@1.1.0`, 8 held-out lines: none 3/8, items 5/8, readings 8/8 (twice); security held. API contract unchanged. Left: `po_body_extraction` examples, stamping which examples a reading saw; pending: attesting 1.2.0 on the plant.
- 2026-11-22, **ticket 57, the case chat a model step, measured and labelled**: `ModelStep.CASE_CHAT`, switch `model_assist.case_chat` ON by default (Đạt: the head may turn it off; on again needs its pass), bar 0.85 on `sales_case_chat`; live on Strata (Giang's home lab, flash next) PASS 6/6, golden 8/8, writes 3/3; a flag's decision recorded after a chat statement is a labelled case (confirmed or corrected) in the decision's transaction; migration `d759676dee5e`; 9 mutations red. Left: the PICs' real replies, an attested run on the plant, examples per message.
- 2026-11-22, **ticket 56 slice 2, a Bravo write asked for in the case chat**: "đổi ngày XN dòng 3 thành 08/12/2026" read by `question_intent@1.3.0`; code binds the line, the SO and a strictly parsed value, says it back, and on the PIC's confirmation (hash) opens ticket 53's own proposal (right, visibility, version and Bravo's row checked again; the approver writes). Migration `b5c316f405cd`; eval `sales_case_chat@1.1.0` with the write and its injection (smoke 6/6); 10 mutations red.
- 2026-11-22, **ticket 62, the quote page's line trail, and Bravo writes on the order's**: `quote_line_trail` reads a requested line's steps from the quote case (reading, findings and confirmed values, YCBG, Design's reply and Bravo result, every price decision, submission to decline; no amount), `GET .../quotes/{id}/lines/{n}/trail` under the case's gate, a "Các bước" column on the quote page; the order trail now shows a line's Bravo writes (ticket 53). Found and fixed: a Bravo write was proposed and listed without the case's record visibility (53). Left: BR-* codes (the BA), Bravo validator steps (live gateway), a look at 320 px.
- 2026-11-22, **ticket 59, the YCBG screen's rules run from its own layout (offline)**: Design's saved result on the 11-20 trace reproduced column for column (17 typed, 4 computed: DesignCheck, Status, designer, date); the client writes ModifiedBy/CreatedBy only where its view loads them (the YCBG line's does not); 5 validators tested; the quotation, PR and PO screens inventoried: the functions and rule kinds they need wait on their save traces (ticket 52).
- 2026-11-21, **ticket 50, Bravo's facts copied into DW by rowversion (offline)**: `sync.changes` reads allowlisted tables and columns (black list, LME, export control) past a cursor; the `bravo_sync` lane (10 min by day, a nightly full pass that marks deleted rows gone) keeps `bravo.mirror_rows`; `GET /sales/bravo/facts` says how fresh each table is. Pending: the checks that use the copy (black list and export control through Bravo's own routines, LME in the quotation), the other reads, UAT.
- 2026-11-21, **ticket 51, the parts that need no INSERT (offline)**: the case's SO read back from Bravo through the gateway on the PIC's ask (`so.by_customer_po`) and compared line by line, now with "XN giao hàng" (a confirmed date Bravo cleared is a difference); the Import templates in `B00ImportSetting` are a watched fingerprint component, a change pausing the create kinds. Pending: creation (03c), the file from the live template (which template is in use must become tenant config), UAT.
- 2026-11-21, **ticket 53, an SO line's date or quantity written into Bravo under the approver's own user (offline)**: proposed against Bravo's row read through the gateway (`so.by_number`, `user.by_employee_code`, the gateway's first reads), approved by one person (`bravo_write.sales_order`, not under `sales.`'s second-person rule: the write is the approver's own, under their Bravo user; for Đạt to review), signed in the decision for the decider's employee code and its one active Bravo user, sent by the worker, Bravo's answer kept (`sales.bravo_line_writes`, `af89f3f5d27d`), a refusal after a lost answer kept in doubt. 22 mutations red. Pending: split/create (03c), cancel (trace), the existing SO's save word and the command right (52), the case page's button, UAT.
- 2026-11-21, **ticket 64, identity on the employee code**: measured on Keycloak 26.7.2 + OpenLDAP that a renamed login stays the same Keycloak user and a re-created account is a new one; link rules (unique exact match links itself, the rest queue with why, a code moves only from a disabled account), `bravo.person_links`/`link_queue` with the invariants in the database, a link by hand under `sales.identity.link`. Pending: Proterial's AD (`objectGUID`, `employeeID`), the people source and Bravo's people reads (ticket 50), the admin page.
- 2026-11-21, **ticket 65, the Bravo change watch built**: ticket 65's table as code with a test per row (`dw_bravo.watch`), the `bravo_watch` lane (30 min 07-19h, 02:00), history, pauses and baselines in `bravo.*` under RLS, the gateway's fingerprint (layouts, commands, columns, triggers, routines) measured on a throwaway SQL Server, pauses read before each write, and the one way back: a holder of `sales.bravo.watch.accept` accepts the latest fingerprint, which lifts the pauses with its audit row. No nightly replay yet, so a changed layout pauses until accepted. Left: the replay, the UAT read for early warnings, the client version, a page.
- 2026-11-21, **ticket 63, the Bravo gateway built** (`apps/bravo-gateway`, offline and on a throwaway SQL Server 2017): the driver check allows a driver in the gateway only; typed versioned commands (`dw_bravo.contract`); an Ed25519 approval token signed in the decision's transaction (`decision_stamps`); the six checks in order, each refusing in its own test (18 guards mutated); a ledger `bravo.write_ledger` under RLS; every write kind off per tenant until a two-person rule version names its UAT proof (`sales_bravo_writes`); container on internal networks, no port, trivy clean. Driver measured: mssql-python 1.18.0 (pymssql's wheel bundles OpenSSL 1.1.1k; python-tds mishandles rowversion). The 11-20 trace: three saves are gateway commands and give the client's own UPDATEs; the real layout still holds them back (10 blocks undecided offline). Cancel is untraced (the one save clears it), so pending like split and create. Pending on UAT: logins, script 07 (a cross-database log trigger fails under column grants, measured), the command right, an existing SO's context word.
- 2026-11-21, **Bravo through one gateway, ADR 0027 (Đạt: take the best option now and build on it; supersedes ADR 0026 and the 11-20 views + staging-job design).**
  - One `apps/bravo-gateway` holds the only Bravo credential and driver, and runs `dw_bravo` on the live layouts.
  - Nothing of DW's is inside Bravo's database: two logins with table- and column-level grants.
  - Creation goes through DW's rule runner. The vendor's automatic Import is used if ticket 60 brings one; UI automation is the last resort.
  - Every write is the PIC's own, checked by the gateway in order:
    1. the signed approval token;
    2. the live identity;
    3. Bravo's own rights, through its functions;
    4. the screen rules;
    5. the lock.

    It then writes under the PIC's context and the `timestamp` condition, with an idempotency key, and reads the result back.
  - Identity is anchored on the employee code (`B00UserList.Ma_CbNv`). Keycloak is federated with the AD. Unambiguous links are made automatically; the rest go to an admin queue.
  - A changed fingerprint stops writes.
  - Tickets 63 (gateway) and 64 (identity) were added; 49 is done; 50, 51 and 53 are rewritten onto the gateway and are ready-for-agent; 52 gains scripts 06 (users and rights, counts only) and 07 (UAT: a column-granted login saving an SO line with Bravo's triggers, rolled back) and three questions for IT about the AD.
  - Unmeasured assumptions are listed in the ADR. Đạt decided to build on them; a failed one changes only the gateway's adapter or its grants.
  - The 11-20 design docx describes the old write path and needs a new version before IT and the vendor review it.
  - **Change watch, ticket 65 (Đạt, same day: check and notify rather than ask the vendor to promise).** A `bravo_watch` lane fingerprints what writes depend on: layouts, templates, columns, triggers, the routines DW calls, and the client version.
    - A layout change the runner can follow goes on, with a notice.
    - A change it cannot follow pauses only the dependent write kinds, until a person accepts the new baseline after the UAT replay.
    - A UAT-versus-production difference is an early warning.
    - Script 06 §11 measures past change frequency.

- 2026-11-21, **how every DW1/DW2 step is built (Đạt):** rules first, the model second, a person last.
  - **Rules** come from their owners: Bravo's own rules and procedures (ticket 59), tenant parameters, and the BA's BR-* codes. They are never if/else typed into code.
  - **The model** is called only where the rules cannot decide: unstructured text, ambiguity, drafting, chat. It returns typed output with a confidence.
  - **Code checks** the model's output against the data before anything applies.
  - **Application** depends on the result. A low-risk step with a measured low error rate applies itself (ADR 0015); anything else goes to the PIC in the case chat. A PIC's correction becomes an example.
  - **The agent** (ADR 0014) sits only in those model steps and in the case chat, never as the flow's orchestrator. The flow is code's state machine.
  - **The trail** (ticket 62) marks each step as rule, model or person.

- 2026-11-21, **ticket 57, the case chat's eval** (`sales_case_chat@1.0.0`, in the smoke, 5/5): simulated PIC sentences deciding M06's flags, two injections, another PO named in the case's chat (which found a real gap, fixed in 56), missing flags, another tenant; the report keeps the model's choice beside the PIC's meaning (shadow). Left: a live run on the on-prem model, real replies after go-live, the production shadow comparison.
- 2026-11-21, **ticket 56 slice 1, a flag decided in the case chat**: the PIC says it, DW1 says back exactly what it would record (flag resolved among the case's open flags, never the model's choice), and records it only when the PIC confirms the statement's hash, through the page's own command (`question_intent@1.2.0`, copy `sales_assistant@1.2.0`, migration `3187714cd75c`). Left: the other effects as tools, the short prompt with retrieved examples (57).
- 2026-11-21, **ticket 62, "Vì sao dòng này đi như vậy" on the order page**: each PO line's steps read from what the case stamps on it, each with its code and who decided (rule, model, DW, person), no amount; `GET .../orders/{id}/lines/{n}/trail` under the case's gate; a drawer from the line's detail, checked by Playwright at desktop and 320 px. Left: the quote page, BR-* codes (the BA's list), Bravo validator steps (ticket 49).
- 2026-11-21, **ticket 61 step 1** (no code moved): the 108 `dw_sales/application` modules mapped to the five stages (read 27, check 16, wait 15, write Bravo 3, communicate 11) plus shared model-step governance (12) and shell (24); pinning designed: `stages/<stage>@<semver>` in the manifest, `stage_versions` stamped once on the case, lanes dispatch on the stamp, rollout per PIC with shadow before promotion, Bravo's layout recorded not pinned. Waits on Đạt's confirmation before step 2.
- 2026-11-21, **ticket 59, the SO screen's rules run from Bravo's own layout** (`packages/python/dw_bravo`, shared by DW1 and DW2, stdlib only, no driver): layout reader, expression evaluator that refuses what it cannot decide, rule runner (edit, check, save plan, trail). On the 11-20 UAT trace all 6 saved SO UPDATEs reproduced column for column; each of the 27 validators has a test (20 fire, 7 undecided with the reason); create and line split pending: script 03c (template `BizDocEditor`). Contexts reach it only through adapters (import-linter). YCBG, quotation, PR, PO next.
- 2026-11-20, **the BA's DW1 spec (20.11, `Downloads/DW1.zip`) reviewed for business logic against Bravo's own code**: frame right, not yet dev-ready (contradictions between spec, workbook and diagrams; open loops; steps that assume Bravo behaves otherwise). Settled by Bravo's code: convert code before the price check (Bravo's ItemCustomer convert), quotation and LME looked up by the SO's DocDate as `usp_B30BizDocDetailSO_GetSQData_HCV` does, never re-import an existing SO (edit in place), 7.2 mapped to Import template 72, split/cancel by Bravo's group fields and IsCancel, `ufn_Prevent_Edit` before any adjustment, quotation validity from Bravo's expiry date, blacklist/LME/ECP read from Bravo's tables, Bravo's own checks and thresholds reused (27 SO validators), "Design done" = YCBG line `Status='CLOSE'` (GetData's trigger sets it and writes Base price; the job being off changes nothing). **Đạt decided 11-20:** an SO always carries the PO's values (a mismatch is a keying error DW must not make); the only real mismatch is the customer's PO Excel vs PDF (item, quantities, prices, total), answered by a mail asking the customer to correct; one PO may become several SOs; every exception (blacklist, ECP block, far date over 10,000 USD, cancel touching materials, price change) goes to the case's own PIC in the case chat, who decides and replies there to continue; numbers and targets ship as defaults the tenant configures; Bravo is updated before the customer is told, in one mail. Also decided 11-20: Design is reached by Sales' own mail and fills Bravo itself; DW sees the YCBG line turn `CLOSE` (no one tells DW); quotations read from Bravo first, the Excel masterlist only when Bravo has none; the case chat stays the main channel (buttons only as in-chat suggestions), an assistant that talks freely and acts only through case-bound tools, asks rather than refuses, keeps its prompt short (rules in tools and Bravo, how-to in skills, examples retrieved) and is measured on the PICs' real replies in shadow. Later (Đạt): QM/QN/QS criteria and the JP signature, old quotations of a TDC customer turned FG. Tickets **49–57** (`dw1-production/issues/`): 49 ADR 0026 amended, 50 reads via `dw` views and sync, 51 SO by Bravo's Import, 52 UAT measurements (Import keeps DW's price? runs the validators? cancel, approve, quotation save), 53 SO adjustments under the PIC's user, 54 feedback to the BA, 55 flow aligned with the spec, 56 chat-first case assistant, 57 chat eval in shadow. Next: 52 at Proterial, 54 to the BA. Later the same day the BA answered the two left (QN unsigned, QM/QS signed; type by "in the item master?" and "special item?"; TDC→FG replaces the code on the same customer record, no old quotations, a changed price means a new quotation): ticket **58** (type, signature without DW signing: PDF from the Bravo record, signed copy closed by the outgoing mail or an upload; facts Bravo holds are polled, never taken from chat words); the BA feedback document is written (54). Owed by the BA: which field marks a special item, confirming the QN/QM/QS mapping (`SalesTempCode` is the "TDC code" column, confirmed from Bravo's layout). **Later still on 11-20 (Đạt):**
  - DW performs Import itself, not a proposal.
  - No splitting into services: stages become versioned lanes inside the modular monolith, pinned per case and rolled out per PIC (ticket **61**).
  - Learned from another FPT team's DW (ATLAS): rules first and the agent only when the rules cannot decide; a per-line decision trail (ticket **62**); versions side by side.
  - Bravo's form logic is stored in the database as XML (`B00LayoutData`), but the Bravo client on each PC runs it, not SQL Server. The SO screen alone uses 11 rule component kinds, about 20 expression functions and 22 procedures, all in hand. So DW can run Bravo's own rules rather than copy them (ticket **59**). Ticket **60** asks the vendor for an automatic Import or an import procedure (GetData-style), with UI automation of the Import button as the bridge.
  - Tickets 49 and 51 were rewritten for DW performing the writes.
  - Everything measured is in `docs/proterial/bravo/BRAVO-NOI-BO.md` (gitignored; layouts decoded beside it).
  - Pending on Proterial's host: script 05 (counts), 03c (shared template layouts), ticket 52 (UAT saves, Import).
- 2026-11-18, **ticket 44, a PO in the mail, slice 2**: Đạt's rule in code (`po_body_autonomy`), each value read gated at intake and stamped (`applied` logged as `shadow` until the effect and undo exist), labels carry the gate so the lane measures the step's threshold, and the case page never gets the gate (blind audit). Slice 3 (effect, undo, web) left in the ticket.
- 2026-11-18, **ticket 44, a PO in the mail: Đạt's rule recorded; slice 1 measures before it acts**: the reader asks the scored call, each `model_read` value carries its span's confidence and the PO its model profile, and every value Sales settles is now a labelled case with both (before, none could count toward a threshold). Nothing applies itself yet; slice 2 (gate, `AutoApply`, undo, web) is in the ticket.
- 2026-11-18, **ticket 46: a step asked of a case is offered its page's own control** (Đạt: "2 theo đề xuất"): `draft_reply`, `remind_customer`, `explain_thread` (prompt `question_intent@1.1.0`, migration `e31ed3f062a1`, copy `sales_assistant@1.1.0`); the order and quote pages register their controls (`useCaseChatOffers`) and the chat draws them under the answer, starting nothing itself. Strata live 13/13, security cases pass. ADR 0007 addendum.
- 2026-11-18, **ticket 11 done on the Excel path** (`535b15b5`, `9b902ca0`): the YCBG reader takes B16's spec number, copper per BP unit, BP unit and BP completion date with each cell, and keeps each request's own rows of the export on its case (only the columns DW1 reads: B16's target and base prices and cost split never kept). The source pane draws those rows; "Dùng kết quả Design trên Bravo" records Design's reply anchored by cell once the person opened them, the case to `design_replied` (refused over a DECLINE, by a reader, across workspaces). Each guard shown red when removed. Left: cases whose result was read before rows were kept (11-16/17) go the mail way.
- 2026-11-18, **Đạt decided four owed proposals** ("1, 2, 3, 5 theo đề xuất; 4 để sau"): the assistant's own sentences became tenant copy `sales_assistant@1.0.0` (`RuleKey.ASSISTANT`, migration `0b6574e8974d`; ADR 0007 addendum: `QuestionKind` and the status words stay code); item names stay code; family 4 (item wording, catalog values as tenant data) deferred. Ticket 46's case chat to offer the case's own T0 buttons and explain the thread, and ticket 44's auto-confirm for a PO in the mail (header by code checks, price and quantity only where they equal the quote or master), are next. Ticket 46 looked at in a browser (`12896622`).
- 2026-11-17 (night), **ticket 02's term from a PO written in the mail**: `ModelPoBody.delivery_term_span` (prompt `sales.po_body_extraction@1.1.0`, 1.0.0 kept) is found in the mail, anchored and flagged `model_read`, and compared with the customer's by the same `check_customer` as a file's (`delivery_term_mismatch`, tested end to end on a fictional NRV mail); a span the mail does not hold drops only the term. The golden English mail now prints one (17/17 scripted). Deploy note: the step was attested on 1.0.0, so it needs `--attest` again before a tenant turns it on. Left of 02: a portal export, the model's layout proposal.
- 2026-11-17 (night), **Đạt left three owed calls to the agent's recommendation; two decided and built, one redesigned**: (1) ticket 03, a Bravo read-back that differs at the version being cross-checked refuses "Kiểm chéo đạt" (`require_bravo_agrees` in `CaseDecisions._decide`, reason `bravo_read_back_differs`; no read-back or an older one refuses nothing; "Trả lại" stays; the panel says so), and Layout1's mapping is no longer asked (B41's shape is what `sales_bravo_upload` writes). (2) dw_sales ADR 0008 accepted, A: Bravo computes, DW1 reads; measured on B07 that the master list alone cannot price a PO (no PRV item, a BP shared by up to 56 items, centre price at LME 7,750 only), so ticket 12's check waits on Bravo's band table and the stand-in stays; ticket 13 wontfix. (3) Ticket 11: B16's export carries BP code, spec number and copper in one file, so no new anchor kind; the slice (keep the export's bytes for the case, read the three columns with their cells, a person's "Dùng kết quả Design trên Bravo") is written in the ticket, next.
- 2026-11-17 (night), **the PC-dates panel no longer says "no date" when PC wrote one DW1 could not settle** (from 47/48's Left): `PcDatesView.unsettled` counts the dropped dates the mail writes on a line of the case in an order its other dates leave open (`03/04`, `pc_dates.unsettled`); the panel says how many are Sales' to read and how many were dropped for not matching, and says "không thấy ngày nào" only when nothing was dropped. Both tests shown red without the change.
- 2026-11-17 (evening), **two of 11-16's "noticed" items closed**: `OrderCase.confirm_mapping` dropped a line's `requested_date_missing` (an error) and its decision when Sales confirmed a code or DW applied one, so a case could be prepared with the date never decided. Fixed: it replaces only the item findings, as the reject does; tested on M44 and checked by putting the old condition back. The case history showed `order.mapping_applied`/`_undone` as raw codes; labelled, and `case-event-labels.test.ts` now fails on any case event `dw_sales` writes without words.
- 2026-11-17, **looked at in a browser** (local stack, the Sales head): `/sales/rules/skills` (the customer SalesOrder table, 7 customers), `/sales/rules/prompts` (empty state reads right), the BRN order's "Mở báo giá" on `quotation_missing`, `/approvals`. Fixed (`f38a20ca`): the skills page showed each skill's English model description; it now shows a Vietnamese title (`skillTitle`). Not clicked through (they would change the demo data): opening a quote, the pairs drawer, a `sales.skills`/`sales.prompts` approval with a waiting version.
- 2026-11-17, **ticket 09's last leftover: a PO written in the mail opens a quote**: the quote's request holds the order's mail text (no attachment, the order's anchors); each value a model read that Sales did not correct on the order comes flagged for Sales to confirm before the YCBG; the PO's price is only the customer's statement (`stated_target_price`), never a target; `QuoteRequest.order_reader` stamps the PO's reader and the request has no `reading` of its own, so the model step is counted once, on the order. No migration (case body). Ticket 09 has nothing left.
- 2026-11-17, **ticket 41's leftovers**: the skills page lists and proposes each customer's SalesOrder skill through the one proposal → replay → `sales.skills` path; a SalesOrder example pair can be withdrawn by a proposer who reads prices (deleted, audited, 404 across workspaces), and pairs older than `learning.salesorder_pairs_kept_days` (default 365, 30–1095) are dropped by the hourly lane `sales_salesorder_pairs_retention` (migration `985e4fa0cd4f` grants DELETE, UPDATE stays revoked). A replay already stored is not redone after a withdrawal (ADR 0013). Left in 41: the PRS number as a source; nobody has looked at the skills page or the pairs drawer in a browser.
- 2026-11-17, **ticket 42 family 6's revision marks; a customer SalesOrder skill compared on /approvals** (`3c4d2b2f`): the letters marking a revised PO file are tenant reference data (`OrderRules.revision_marks`, default R/RV/RE/REV, 1-5 capitals, checked on proposal and by the reader), not a skill: a fixed rule reads them. `GET /sales/skills/versions/{id}` compares any skill version, a customer's SalesOrder skill included, with the one in force. Left in family 6: the item-name grammar (stable, errs blank: kept as code), the assistant's fixed sentences and `QuestionKind` (ADR 0007 chose a fixed catalogue: Đạt's call). Left in 41: the skills page neither lists nor proposes a customer's SalesOrder skill; pair withdrawal and retention; the PRS number as a source.
- 2026-11-17, **ticket 02's acceptance 2, the skills approval on /approvals, the brief's Design bucket** (`cbcb28ed`, `b5b4cece`, `4a861685`; migration `e07b932e4516`): a PO's delivery term (an optional label mapped on the layout, read with its anchor) is compared by Incoterms 2020 rule with the customer's; a mismatch is the error finding `delivery_term_mismatch` (order rules 1.15.0); no term on either side raises nothing. Bravo's customer export carries no delivery term (B05, B41: only per sales order), so the customer's term comes from the customer import. A `sales.skills` approval is decided on /approvals with the words diff and the replay; `followups.turn_status` owns whose turn a case is, so the brief no longer counts a quote whose Design result was read as waiting on Design. The access test now calls a DELETE route with DELETE. Owed by Proterial: where Bravo keeps a customer's usual delivery term (or may DW1 take the latest sales order's). Left: the term from a PO in the mail body, a portal export and the model's layout proposal; a customer SalesOrder skill's approval shows no comparison.
- 2026-11-17 (early), **ticket 05 in part: a pcs case waits for the GM's price**: `QuoteCase.production_type` (mass | pcs, set by a person before pricing) and `pcs_price` (GM/BC Manager's price per line, recorded by Sales); `decide_price` refuses a pcs case without it (mutation-checked). `GET /quotes/{id}/pcs-price-request` is B49's cost sheet with every amount blank; no migration (case body). The quote page's "Mass hay pcs" card sets the type, records the GM's price and opens the cost sheet; the GM price is hidden without the price scope. `waiting_pcs_price` reminds the PIC a day after a case is marked pcs without the GM's price (`sales_followups@1.7.0`, `sales_reminders@1.1.0`, migration `b01dba5d0433`). Left (a case nobody marks is priced as today): the mail to the GM (needs one real example), proposing the type from history. Ticket 11's QUOTE-to-pricing waits on an ADR: an anchor kind for a value read from a master list. Asked of Sales: are SGA/loyalty/profit rates fixed, is "JP & HQ" the GM at PRV, the assembly-cable variant.
- 2026-11-16 (late night), **ticket 03 on the Excel path, ticket 40 wired**: one upload path for every Bravo screen (`bravo_exports`, screens `ycbg` and `sales_orders`, scopes from one table; migration `7c6ad2350566` moves ticket 16's exports across and adds `order_bravo_read_backs`); "Đọc lại SO từ Bravo" reads B02's screen, compares each PO with its case's paste sheet row by row, and "Đối chiếu với Bravo" shows it on the case (prices masked to non-price readers), deciding nothing. Ticket 40: the skill turn runs with thinking on (`onprem_thinking`), measured as built on Strata 0.883, no false accept; still off. Owed by Đạt: whether a differing read-back blocks the cross-check; switching `skill_intents` on.
- 2026-11-17 (early), **the leftovers of 06, 09, 10, 16, ticket 42 family 6 in part, ticket 43's page** (`df7ee7b0`, `07bc2f67`, `23d2efff`; migration `57bbf61ae6b8`): reminders `waiting_design_code` and `waiting_quote` (24 h, PIC only, `sales_followups@1.6.0`) and both waits on the process map; Design no longer chased once its result was read from Bravo's YCBG export; the follow-up lane's words are tenant copy `sales_reminders@1.0.0` (87 renderings equal to before). PC may cancel a whole line (no delivery; quantity 0 in the Bravo update file; the notice says so, `sales_emails@1.6.0`); Sales' confirmed dates stay Bravo's first confirmed date where PC never answered (a defect); `domain/named_lines` is the one answer to "which line" (a code beside another line's number names neither; `12 cuộn` now names line 12). `INTERNAL_CHANGE` declared T2. Ticket 43: the head's page `/sales/rules/prompts` and `GET /sales/prompts` (`sales.rules.approve`), decided through the existing `sales.prompts` approval. Owed by Proterial: does Bravo's "Thay đổi chi tiết" take a cancelled line as a 0 row or a deleted row; does a blank date in the paste overwrite the first confirmed date. Left: the morning brief still counts a quote whose Design result was read as waiting on Design; a `sales.skills` approval in `/approvals` links to `/sales` instead of being decided there; ticket 42 families 2 and 4 (overlap ticket 40 and 14, the other session), family 6's revision hints and item-name grammar; ticket 02's delivery terms.
- 2026-11-16 (night), **tickets 11, 12 and 04 in part, the Excel path**: Bravo's Base price list (B21, 100/100 rows) and its "Master list báo giá" (B07, 161/161) are master lists through the Bravo port, each needing the price scopes; a QUOTE line's BP shows Bravo's base price on the quote case to price readers only (`design_prices`), a BP the list lacks said so. The one reader reads a column by its block where two blocks title it alike (B07). Convert rows take Bravo's approval state from the group label above them: only "3. Đã duyệt" answers a line; a reader older than the groups is refused (B04: 11,423 approved). Migration `acb2a1fbb213`. Left: 11's QUOTE → pricing (an anchor kind for a master-list value), 12's price check (ADR 0008), 04's colour codes (Q-B12); ticket 03 built in the scratchpad, waiting on files the parallel session holds.
- 2026-11-16 (late night), **ticket 40's `skill_intents` over its bar on the plant's Strata, still off**: thinking on for this step alone (`onprem` 1.5.0 `thinking_profile: onprem_thinking`, `AgentTurnKit.turn(thinking=True)`) and the thread's cases and last messages up front (`dw1_agent@1.2.0`): bar set 0.700 (off, same evening) → 0.850 / 0.867 / 0.867 over three runs, no false accept (RP16, RP17 gone), no turn at its ceiling; thinking alone 0.883 / 0.867. Owed: one line in `assembly.skill_agent` (held by the parallel session), the eval harness resolving the chat model per profile, way 4 (no step labels intent corrections yet). Ticket 01: handoff 7/7 and rfq 10/10 pass after `01bd501c`.
- 2026-11-16 (late night), **ticket 14 done on the Excel path, Q-B13 closed**: one reader of every Bravo export (`domain/bravo_exports.py` `find_header`: the header row found by the columns' titles, never by position, a missing column refused by name, extra ones listed, `_x000D_` ignored; the master lists and the YCBG read through it); `BravoMasterDataPort` with `ExportedMasterList`, which every list import reads through, so the vendor's API replaces the file without touching snapshot or approval; a failed read leaves the list in force (tested); `verify_architecture.py` refuses SQL Server drivers. YCBG on B16's real titles: `Số thứ tự` is blank in Bravo's export, so lines are numbered in order and must carry the request line's own description. Measured: B02's 93 SO lines → B04 through the port, 93/93 the same PRV code; B43 as received is an empty template (owed filled). Harness DB names from `DW_TEST_SALES_DB`/`DW_TEST_SALES_API_DB`.
- 2026-11-16 (night), **tickets 06, 09, 10 and 16 done** (four agents in parallel; migrations `3d139b41fec1` → `10d5dfc1a3f1` → `ae1388cdd714` → `1f037954f3d9`). 06: "Đề nghị Design tạo mã" on an unmapped line drafts a mail to Design (the tenant's `design_mailboxes`) with the three nearest PRV codes of the item master (`descriptions.nearest`); the case waits on Design; a code a verified Design mail names after the request is only offered, and maps when Sales confirms it (copy `sales_handoffs@1.2.0`). 09: "Mở báo giá" on `quotation_missing` opens one linked quote case (both scopes; idempotent); the order cannot be prepared while it is open (read from the quote, never copied); its approval re-checks the lines with the approved price from the PO's date. 10: "Thay đổi nội bộ" reads PC's pasted changes (step `internal_change`, off), applies only on a person's press into ticket 29's update loop (one Bravo update file, one notice `internal_change_notice`, `sales_emails@1.5.0`), back to cross-check. 16: YCBG numbers in Bravo's shape `RFQ<yymmdd>-<nnn>` (CHECK `NOT VALID`, old rows refuse writes), the draft carries Bravo's fields (`sales_documents@1.3.0`), Design's result read from an uploaded Bravo YCBG export through `BravoYcbgPort` (reader sandbox, worker lane `sales_ycbg_exports`), matched only to the case waiting under that number with the same lines, else listed for Sales; status read, never written. Left: Design reminder and process-map wait (06); a PO without a file opening a quote, a reminder while waiting (09); whole-line cancel, and PC's later date overwriting the first confirmed date in both loops (10, existing); QUOTE to pricing (needs 11), the R13 adapter, the export's assumed columns (Q-B13) (16). Owed by Đạt: `apps/web/e2e/sales-demo.spec.ts` (his uncommitted file) still types `YCBG-2609-030`, refused now: `RFQ260930-030`, `RFQ260929-029`. Next: a second session takes the Bravo Excel tickets (14, 03, 04, 11, 12, 05) and ticket 40's skill_intents; this one the leftovers above and ticket 42 families 2, 4, 6.
- 2026-11-16 (evening), **ticket 37's live graders fixed, no leak in the code**: the plant run's two notation failures (ticket 01, "plant's own GPU") were the graders comparing two separate live calls: HO17's "another customer's record settled a value" and the RFQ set's one extra wrong value were the model's variance between passes, not a record (records are looked up by the sender's customer code only; HO17 read 8 times live on the lab Strata, without records and with only other customers', gave one identical reading, no value from a record). Live, a leak is now a value another customer's or tenant's record settled or contradicted (both marked by code), and a record's error is a wrong value a record read; a replay still compares exactly. A leak injected into `record_for`, with the exact comparison switched off, turns both cases red. Owed: the attested plant run.
- 2026-11-16 (Bravo screenshots), **Bravo's sales-order import skips refused rows and keeps no log** (both boxes ticked in the import dialog, layout "Layout1", from row 4, file = the PIC's SalesOrder): ticket 03's read-back is what catches a lost line, recorded there. Bravo's exports share one shape (title row, header on row 2); B05/B07/B09/B16/B21/B41/B43 are already in Box 11-14. Owed by Proterial Sales, as Excel exports to Box (Đạt asks, 11-16; screenshots dropped): full Base price, "Báo giá, chào hàng" with lines, Cancelled order information, Customer order information Form 2, Black list and Export control program (B14), "Master List Lệnh sản xuất" (maybe PC's in-production source), Layout1's import mapping ("2. Thiết lập import") and one import result with a refused row. With Box 11-14 and B02, tickets 03, 04, 05, 11, 12 (reader), 14 are ready-for-agent on the Excel path; 13 waits only on ADR 0008 (A recommended), 08/15/39 on Đạt's calls, 01/23 on infrastructure (23: Tuesday/Wednesday evening 11-17/18 on the server, with the mail flows; 01 closed by Đạt 11-16). Every Excel stand-in has its Bravo API in the 11-13 list (R01-R13, R15; W01/W02 replace the import) except "Master List Lệnh sản xuất": raise it at the three-party meeting once Sales' export shows it is PC's in-production source.
- 2026-11-16 (night), **ticket 42 families 3 and 5 done** (families 1, 3, 5 of 6; 2, 4, 6 open): 3: a `document-forms` skill names each request form a customer sends (customer code or `any`, route `quote_request` only); the model sees only the sender's customer's forms plus `any`, returns ticket 29's spans, and code verifies every value with `verify_rfq`/`request_of` (each flagged for Sales); asked after the fixed reader in quotation, and at intake only for an unrecognised, non-uploaded file from a known customer's domain; step `skill_document_forms` off (migration `42b7626a1bb7`); Strata 0.893 of 196 values right, 0.005 wrong, p95 18 s (not attested). The mail-body change table stays code (it reads values, not words: item 6). 5: `handoffs` and `reply-drafts` skills name the hand-offs and reply drafts; a kind picks an existing field set/team or an existing draft, never a recipient, send, price, amount or tool; steps `skill_handoffs` and `skill_reply_drafts` off (migration `7c00901ada90`); Strata: hand-offs 0.863 (bar 0.85, none wrong, p95 28 s), reply drafts 0.833 (below the bar, the same as today's one-call drafting: both drops Japanese drafts refused for a figure), so the old paths stay. Replays grade a proposed version before the head can approve. Also: the activity names the `<field>_contradicts_record` refusals ticket 37 added (its label test had gone blind to header fields). Owed by Đạt: a tenant's own hand-off kind is worded with its field set's platform words (its own words means keying `sales_handoffs` by kind). Left: a company's own example files as a replay source; a header-only unit (`Số lượng (m)`); attested runs before any step is turned on; families 2, 4, 6.
- 2026-11-16 (late night), **tickets 33, 34 and 37 done**: 33: a mail still routed `other` gets a triage card (one call under the tenant's served mail-kinds skill; the step from the kind's route, only five routes give one; the case is the single live order case its numbers lead to within the sender's customer); advice only, the routing stays until a person takes the step, picks another or dismisses it (`POST /sales/inbox/{id}/triage`, audited, a labelled case); step `triage_card` (T0) off; Strata 97/98 (0.99, not attested). 34: most was already true through tickets 40 and 42 (tests named in the ticket); added: a PIC proposes a mail-kinds version from a card, and the replay reads that mail with and without it beside the golden set (migration `2c91d318f833`). 37: a customer's notation (decimal mark, date order, `$`, `¥`) is learned by code from the value Sales keeps when DW left it open (`dw_platform.domain.notation` `learned`/`settle`, one owner), stored per customer (`sales.customer_notations`, migration `99ae8f7eb765`, audited), shown and changeable on master data ("Cách viết số, ngày"); RFQ, hand-off and PO-body readers use it only where the document is silent, a contradiction goes to a person, a value read by record is flagged; goldens report wrong and deferred apart: RFQ right 0.839 → 0.949 with records, hand-off 0.849 → 0.945, wrong unchanged. Owed by Đạt: the split of the live bar between wrong and deferred (it still reads right ≥ 0.85 without records). Left: change requests not wired to the record; a glossary entry for the record; a skill per customer (skills stay tenant-wide). Next: the batched question list, then Docker down.
- 2026-11-16 (night), **ticket 41 done, ticket 42 family 1 built**: 41: a customer's SalesOrder is filled by one model turn with the customer's `salesorder-<code>` skill (platform ships a generic one with fictional pairs) and tool results code fetched first (the PO as read, convert list, item master, calendar, unit factors, all bound to the case's customer); every cell names its source and code traces it on every PO (value at its anchor, lookup redone, computation from ADR 0013's closed set redone, a constant only from the skill's `## Constants`), writes code's value, flags an untraceable cell for the PIC (second sheet), and a price only from the PO (ADR 0008). Worked pairs (`sales.salesorder_pairs`, migration `711e8b760139`) are written when ticket 38 learns from an uploaded example; a proposed skill version is replayed on the customer's newest 20 pairs and the head may approve it only if every pair comes out as the PIC's file (`skill_pairs_broken`). Step `salesorder_skill` (T2, bar 0.95 cell accuracy) off everywhere; ADR 0013's learned rules are the fallback. Strata (not attested): 114/114 cells on 3 golden pairs, unseen shape 7/8 with the eighth flagged, no injected value written, p50 11.5 s. 42 family 1: the kinds of mail a tenant tells apart live in its `mail-kinds` skill (`kind`, `route`, `label`, `means` per block); code keeps the routes (`INTENT_ROUTES` rows), refuses a version naming an unknown route when proposed and when served; step `skill_mail_kinds` (T0, bar 0.90) off; the inbox shows the skill's label. Strata: 92/92 golden (one call 0.978), a tenant's new kind read 4/4 with no code change, no injection opened a case; both paths kept (migration `beba87138cda`). Fixed: `sales.skill_replays`' unique key now leads with `tenant_id` (`456986ea413a`) and the schema test knows it is tenant-wide. Left: 41: the skills page lists no SalesOrder skill, no pair withdrawal or retention, the PRS number still no source; 42: families 2-6, removing the one-call path after a tenant's attestation. Next: 33/34 under ADR 0014, 37; then the batched questions.
- 2026-11-16 (evening), **ticket 40 done, ticket 43 parts 2-3 built**: 40: the skill is picked by ONE call whose schema allows only the skills served to the tenant or "none", with its logprob confidence; an unserved name, "none", no confidence or below `model_assist.skill_pick_confidence` (0.9) reads as if the step were off; the picked skill's text goes into one reading turn (`sales.dw1_agent@1.1.0`, `AGENT.md` 1.1.0, no catalogue, no loader). Strata (not attested): 0.800 on the bar set (one call 0.796, thread agent 0.85, free choice 0.183), 1 false accept (RP16), 3 turns at the ceiling (63 before), p95 6.1 s: the looping is gone, the bar (0.85) is not met, the step stays off. The replay (`sales_skill_replay` lane, `sales.skill_replays`, migration `e1b1e0cadb66`) reads the platform's example mails with and without a proposed skill version; the head may approve only a replayed version (`skill_not_replayed`). The skills page `/sales/rules/skills`. 43: corrections become examples for `description_attributes`: an example index per tenant in Qdrant (vector and ids only, filter built in `dw_knowledge.examples`), the text read back from Postgres under RLS, the case's customer first, up to 3 per line (`learning.examples_per_line`), shown as untrusted input (`description_attributes@1.1.0`), any failure reads without them; the `sales_prompt_optimiser` lane proposes a tenant prompt version (chosen demonstrations only, no instruction rewrite) only if no decided line reads worse, more read right and every security case passes; the head decides (`sales.prompts`, migration `137ec1972538`). Measured on the 9B dev model: no reliable gain yet (0-1 of 6 held-out lines either way); Strata next. Deploy note: the prompt moved to 1.1.0, so `description_attributes` needs its live eval attested again before it reads (it never was on the plant model). Left: a page showing a proposed prompt version's demonstrations and replay; `po_body_extraction` examples; recording which examples a reading saw; the unused `sales.read_skill` tool; the skills page seen in a browser; tenant-labelled reply cases for the replay. Next: release manifest, the `AskBody` route test (46) → 41, 42, 33/34.
- 2026-11-16 (later still), **ticket 44's reject**: "Không phải mã này" on a line's model-read candidates (one or several together) puts the line back to `unmapped`, keeping nothing of the reading, re-checked through the path `confirm_mapping` uses (`_line_again`), and writes a `rejected` labelled case; a convert-list or vocabulary candidate, or a confirmed code, is not rejected this way (an applied one is undone first). `test_sales_api_access.py` walks five path parameters it never listed and passes again (it found the tenant IT role reaches the skills routes through `sales.rules.propose`, recorded). Noticed, unverified: `OrderCase.confirm_mapping` may drop a line's non-item findings (e.g. `requested_date_missing`) and their decisions; the history lacks labels for `order.mapping_applied`/`_undone`. Release manifest regenerated after 43 parts 2-3 land.
- 2026-11-16 (later), **tickets 44 and 46 built, one slice each**: 44: every `ModelStep` has a tier in code (`domain/autonomy.py` `STEP_TIERS`; a step not named is T2; layout and change request T2, hand-off T1, readings and drafts T0); the structured call asks for token logprobs where the route declares them (`onprem.yaml` 1.4.0) and `dw_agent_runtime.model.scoring` turns them into a probability per value; a threshold per tenant, step, prompt and model profile by Learn-then-Test with the exact binomial bound (59/149/299 cases for 5/2/1%, fewer = no threshold = nothing applies), recomputed hourly by the `sales_auto_apply` lane (`sales.step_thresholds`, migration `efc46a50e75e`); one step applies itself first, `description_attributes` on a line with one candidate, through `confirm_mapping` as the lane, marked "DW đã tự làm" with "Hoàn tác" (the undo is a labelled case); a T2 step refused at the effect; a deterministic 3% audit sample goes to the PIC unapplied (blind); audited error whose lower bound passes the target stops the step; the head sees it on the activity page; three settings added (tighten only). 46: a conversation per (person, case) on the order and quote pages (`WithCaseChat`: beside the case from `lg`, a bottom sheet below), its case bound from the route and re-checked on every read and turn (404 for a case not readable), one general conversation per person on the assistant page that links a case it names and answers none of its data, the ten most recent cases, an unread mark in the lists (one indexed query); `sales.assistant_sessions` extended, not a second table (migration `bfe2d1aeadcd` keeps each person's newest free session as their general one and deletes the older ones: private chats, pruned at 30 days anyway); ADR 0007 addendum. Decided by me: a single-candidate line needs "Không phải mã này" (reject), else its labels read nearly all confirmed and audits cannot catch an error: next, before any threshold is trusted; the chat starts no action yet. Left: 44: the reject, other steps scored (`po_body_extraction` next), a live Strata check of the logprob path; 46: T0 actions from the chat, explaining the thread, Playwright. Noticed: `test_sales_api_access.py` fails on `{request_id}` routes since an earlier ticket; the release manifest is stale. Next: the reject + those two fixes → 43 parts 2-3 → 41, 42.
- 2026-11-16, **ticket 45 done, retrieval hybrid on Qdrant v1.20.1**: one Query API call fuses bge-m3 dense and Qdrant's own BM25 on the chunk text (RRF k=2, measured best), the trusted filter on every prefetch and the fusion; BM25 statistics scoped to what the filter admits (measured: unscoped, another tenant's 80 points moved a tenant's score 2.95 → 1.76; scoped, unchanged), so a ranking depends only on text the caller may read. Tokenizer `word` (`multilingual` drops digit-only tokens: a PO number indexed as `po`). The memory fake ranks the same way, so CI measures what Qdrant serves. Collections named by embedding model behind an alias, rebuilt from Postgres by `scripts/knowledge_reindex.py`; a process embedding with another model is refused. Query embedding: one reused client, 5 s deadline, LRU keyed by tenant and workspace. Eval `platform@1.3.0`: recall@5, nDCG@5, p95 with a floor, shown failing with the lexical leg dropped; CPU p95 10.7 ms hybrid vs 7.7 ms dense (hash embedder, 4,034 points; bge-m3 and rerank not measured here). Accepted: 2 HIGH in Debian `zlib1g` in the Qdrant image (fixed upstream in the base, not yet in a Qdrant release). Left: bge-m3 and the reranker under llama.cpp, rerank latency on CPU, the dense leg gated only by a live bge-m3 run, global documents as their own prefetch. Noticed: the release manifest is stale (`release_manifest.py --check`), to regenerate once 44 lands. Next: 44 (running) → 43 parts 2-3 → 46 → 41, 42.
- 2026-11-15 (night), **tickets 47+48 built as one slice, the pc_dates defect fixed**: `/sales` ("Việc cần làm") is a person's one place: today's brief on top (read back from what the `sales_followups` lane delivered, `GET /sales/today`), the work list ordered by the SLA (`WorkItem.sla_warn_at`/`sla_due_at` from `domain.followups.sla_of`, the lane's own timings: late, about to be, by due time, a countdown) whose rows expand into the case page's own action components (decided inline, no chat, no second page; `/sales?item=order:<id>` opens one expanded), then "Nhắc việc" (7 days; "Đã xử lý", "Nhắc lại sau", "Không cần" in `sales.reminder_marks`; a dismissed kind ranks lower; a customer's term is never hidden: service 409, CHECK, read side). Web Push: our own `public/sw.js`, "Thông báo trên điện thoại" in the account menu, `platform.push_subscriptions` (RLS per person, one SECURITY DEFINER door, 90-day prune, gone = deleted), `PushSenderPort` + `pywebpush==2.5.0` (measured against a local endpoint), one push per person per tick ("3 việc mới"), the kind and the case number at most (`sales_followups@1.5.0` `push.case_number`), VAPID key from secrets only, `web.push.apple.com` in the on-prem allow-list; migration `4bcfa82060fc`. 14 guards each shown red when removed. Decided by me: the title stays "Việc cần làm" (e2e); a push is best-effort, the feed holds the reminder; the SLA sort runs in the browser over the whole list (a recorded exception). pc_dates (`cee49a4e`): PC's dates read in the order the mail settles (`notation`), an unsettled one (03/04) left for Sales. Left: the 47/48 "Left" lists (model-worded reminder lines, "Xem trong thư" in the row, who was told of an escalation, mail routed to Sales unpushed, sign-out leaves pushes on, a real iPhone at UAT); the PC-dates panel says "no date" when every date was dropped as unsettled. Owed: the portal's certificate the iPhones trust (Proterial IT), the host reaching `web.push.apple.com`, the contact for `DW_WEB_PUSH_SUBJECT`. Next: 45 (running) → 44 → 43 parts 2-3 → 46 → 41, 42.
- 2026-11-17 (later), **ticket 43 part 1, the Qdrant fix, tickets 46-48 written**: `sales.labelled_cases` (migration `eac4fabdb31a`; tenant+workspace RLS, append-only, monthly partitions, 365-day retention lane) holds, per item a person decided, the model's proposal beside the value kept and the verdict (`verdict_of`, one rule), the input by reference only; written by each step's own service in the decision's transaction for description_attributes, po_body_extraction, rfq_extraction, change_request, layout_proposal; read port for retrieval and thresholds; the head sees per step the share kept as proposed (activity page). Gaps: reply intents, message_intent, hand-off, design reply, sender customer, PC dates and reply drafts write no labels yet. Decided by me (less work for people, ADR 0015): a reply reading is labelled from the step the person takes (the proposed step = confirmed, another = corrected), no extra button; the unlabelled readings become ModelSteps with their proposal stored. The Qdrant review (`docs/research/2026-11-17-qdrant-review.md`) found and I fixed a cross-tenant delete (`3fbb0db6`); dense-only search, Qdrant v1.13.4, an eval that cannot fail and unmeasured CPU rerank remain (ticket 45 to write). Tickets 46 (conversation per case), 47+48 (one place for a person's work, decisions inline, Web Push to the iPhone, SLA order). Next: 47+48 (for 11-18) → 44 → 43 parts 2-3 → 46 → 41, 42.
- 2026-11-17, **ticket 40 built in part, the skill step off; ADR 0015 decided**: platform skills `configs/skills/dw1/AGENT.md` and `thread-intents/SKILL.md` (pinned by the release manifest), served per run by code (`dw_agent_runtime` `model/skills.py`, `adapters/skills.py`: deepagents' `SkillsMiddleware` over a backend that answers only from the run's set, loaded through `ToolExecutor`, refused for another tenant's run); a tenant's skill version is a `platform.rule_versions` row (`sales_skill_<name>`, migration `80584b911796`: the same RLS, grants and proposer-never-decides engine, no second table), proposed with `sales.rules.propose`, decided by the head on `sales.skills`; a reading stamps the skill versions it loaded. Step `skill_intents` off: on Strata the agent loaded the skill then looped on tools (0.183 on the bar set; 276 look-ups in 80 turns, 63 at the ceiling; withheld facts found 8/8; no false accepts); a wording fix made it worse (0.083), reverted. ADR 0015 decision 5 answers it: the skill is picked by one constrained, scored call, not the agent's free choice (ADR 0014 amended). Left in 40: the replay of a proposed skill on example mails, the skills page, a tenant's wholly new skill. Decided by me under standing rules: who proposes a skill is the admin's grant (`sales.rules.propose`, PIC by grant), not a default. Next: 43 (store the model's proposal beside what the person kept, examples, optimiser) → 44 (tiers, thresholds, shadow mode, audits) → 40's scored skill pick → 41, 42.
- 2026-11-16 (night), **every DW1 step on Strata, measured (Giang's home lab, not attested)**: `onprem.yaml` 1.3.0 routes structured, reasoning and chat to `qwen3.8-flash-next-q2_0` (thinking off, no fallback, 6000-token input cut kept: nothing measured needs more); the key reaches the server only through `DW_ONPREM_MODEL_API_KEY`, never a file. All 23 DW1 model-step sets ran, every case passed (injection, cross-tenant, missing evidence included), no call refused or timed out, p50 1–3 s (descriptions 9 s). Bars met: reply_draft 0.917, change_request 1.0, descriptions 0.933, intent 0.978, handoff 0.877, layout 0.994, po_body 1.0. Missed: reply intent 0.796 (9B 0.816), RFQ 0.833 (a line's quantity left to a person), thread agent 0.85 with one false `accepts` (RP16). Japanese is the weak language (reply 0.647, thread agent 0.611). Tools: 57 calls in 72 turns (9B: 2), the expected tool in half the turns that needed one, no foreign record. The change request gained its model-down test (acceptance 3). Table in ticket 01. Owed: where bge-m3 runs on the plant (Strata serves no embeddings); keep the bars and work the prompts (reply, RFQ, Japanese) or leave those steps off; re-record CI from Strata now or after the plant's attested run. Next: 40 (the intent skill, against reply@2.0.0's 0.796), 33/34, 37.
- 2026-11-16 (evening), **ticket 35 done**: the process page draws DW1 from what code owns: the BA's step codes (`domain/process.py` `BA_STEPS`, codes only, words ours, read from the local flow review) on each status, and the flows beside the statuses (`SUBFLOWS`: the thread before the PO, the PC wait, a change by mail, the update loop, whose moves are now the table the domain enforces, `_LOOP_NEXT`); a move added in code appears without editing the map. The head sees "Thiết lập chính", ten settings with one sentence each (`HEAD_SETTINGS`, price tolerance, cross-check, five reminder hours, quote deadline warning and validity, morning brief); everything else under "Nâng cao", and a setting not on the list is the admin's (fails closed). The update loop's step words now have one owner (`SUBFLOW_STEP`). Owed: is export control the head's or the export-control PIC's; customers' days of silence in master data rather than the order rules; what `short_lead_time.from`, `layout_onboarding.uncertain_first_pos`, `fiscal_year_start_month` mean to them; the BA to confirm the words for 0-KH, 6-PC and "Khách quyết định?". Noticed: the local dev database lags the alembic head (inbox, my-work, overview 500 until `make migrate`). Next: `onprem.yaml` to Strata, measure, 40, 33/34, 37.
- 2026-11-16 (later), **ADR 0014 accepted, Strata reachable**: Đạt "tôi duyệt", on condition that it is measured on Strata first. Giang's home lab now asks for an API key (kept in `.env` as `GIANG_STRATA_API_KEY`, never committed): `/health`, `/v1/models` and POST `/v1/chat/completions` all answer (the WAF that refused POST on 11-12 no longer does); `qwen3.8-flash-next-q2_0`, 262k context; a tool call came back right (`case_by_number`, 32 s with the model loading), thinking off gives JSON in about 1 s. Ticket 40 written (AGENT.md, the tenant skill store, the intent skill first). Next: 35 (running) → `onprem.yaml` to Strata (ticket 01's first step) → live runs on Strata of reply_intent, thread agent, reply draft, change request (recorded, not attested: not the plant's GPU) → 40 → 33/34, 37.
- 2026-11-16, **ticket 32 done, the reply-draft step gated; ADR 0014 proposed**: "Bản AI soạn" beside the template draft (an answer to a reply read `asks`, 6-DW4, 6-DW3, the confirmation; offered exactly where the template is): one call, no tools, the tenant's own letter as the example (`sales_emails@1.4.0` adds `question_answer`), facts from code with no price or amount; `check_reply` drops a draft with a figure no fact supports (the question is no fact), any amount, address or link, and says why; recipients from master data; nothing sent or stored. Step `reply_draft` off for every tenant (bar 0.85 on `all.complete`; migration `3aca293b2c92`); eval `sales_reply_draft@1.0.0`, replayed in CI; local proxy 0.833 (ja 2/4: "12,200 m" refused, a quantity on the wrong line). Fixed in `figure_check`: "đồng" is money only after a number ("đồng ý", "lõi đồng" were dropped). Known limit: a figure is checked to be a fact, not to sit on the right line. **Đạt, 11-15, in conversation**: code choosing the step is if/else; wants DW1's work as skills (`AGENT.md`/`SKILL.md`, deep-agent style) Proterial edits without code: written as dw_sales ADR 0014 (Proposed): one deep agent, tenant-edited versioned skills replayed and approved by the head, code only guards (bindings, schema, quotes, figures, effects, thread by headers), measured on Qwen3.8 first with today's steps as fallback. Tickets 33 and 34 held until he decides (they are rebuilt under 0014 if accepted). Also asked: the tools barely help reading intents (2/72 calls) because an intent is what the message says; measure tools where facts are withheld (drafts, triage). Owed: ADR 0014; the reply-draft bar; "12,200" separators in Japanese; prices in an AI-worded confirmation; answer the asker or all contacts. Next: 35, 37; 33/34 after ADR 0014.
- 2026-11-15 (end), **tickets 30 and 31 done, the thread agent gated**: six read-only tools (`configs/tools/sales.*@1.0.0`, toolset `sales-dw1@1.0.0` pinned by `configs/workers/sales.yaml`: thread messages, case snapshot, case by number, conversion lookup, lead time, PC status), customer/tenant/workspace bound from the run by code, never an argument (a test walks the specs), another customer's case or code returns nothing at the tool; no price, amount or person shown. The turn (`dw_agent_runtime` `AgentTurnPort`/`BoundedAgentTurn` through `ToolExecutor`; ceiling 4 calls, 16k tokens, 90 s; no checkpoint of its own) answers ticket 26's schema with quotes located by code, and falls back to the one-call reading, then a person, saying so. Step `thread_agent` off for every tenant (bar 0.85 on intent accuracy, no false `accepts`, no foreign record; migration `5461a43e48bf`). Eval `sales_thread_agent@1.0.0` (72 golden + injection, cross-customer, missing evidence, bounded), CI replays recorded turns. Local proxy (qwen3.5-9b, not attested): 0.85 on the bar set (met exactly), 12/12 thread-dependent, no false accepts, but only 2 tool calls in 72 turns: the tools add little on that model. Owed: the attested run on Qwen3.8/Strata (Đạt: access); is 0.85 the bar or must it also call the tools where a reader would; the ceiling on the plant's hardware. Next: 32, 33 → 34 (behind the gate), 35, 37.
- 2026-11-15 (late night), **ticket 28 done**: `confirmation_sent` (Đã gửi xác nhận, chờ khách) before `confirmed` (Khách đã đồng ý, `accepted` or `implied`); old `confirmed` rows were confirmations sent and moved there (migration `64d50dbc1d00`). "Ghi đã gửi xác nhận" records it; a sent copy in the thread whose attachment's sha256 is this case version's paste sheet proposes it. Per-customer silence term in the order rules (`implied_acceptance`: days, calendar|business, from confirmation sent|PO date; 1.14.0 ships empty: never implied); `sales_followups@1.4.0` tells the PIC once when it passes and the PIC records `implied`; the lane writes nothing. A reply read `accepts`/`rejects` proposes "Khách đã đồng ý"/"Khách từ chối" with its quote; a person records (declined → `change_review`). Ticket 29's loop starts from either state. The confirmation draft attaches the customer's own PO files plus the paste sheet. Fixed on the way: a quotation test pinned to `sales_emails@1.2.0` (ticket 29 bumped it). Owed by Proterial: customer 1's 5 business days from the PO date; every other customer's days; holidays (Mon–Fri now); what the "processed Excel" is (B11), and whether the paste sheet's internal sheet may go to a customer. Not done: `requests_change` proposing "Ghi yêu cầu thay đổi"; sent copies keep no thread headers until ticket 23. Next: 30 → 31–34 (behind the gate), 35, 37.
- 2026-11-15 (night), **ticket 29 done**: a change line confirmed on a `confirmed` order (in Bravo) opens the case's update loop (`UpdateLoop`: ask PC → waiting on PC → answer the customer → waiting on the customer → Bravo update; each step a case version, every draft sent by a person and recorded). 6-DW2 is ticket 07's request with the asked values; code's verdict (every PC delivery exactly on the asked date = can do) offers 6-DW4 `change_can_do_draft` or 6-DW3 `change_options_draft` (`sales_emails@1.3.0`); the customer's answer is recorded by a person: keep (closes the request, the order unchanged), ask PC again, or accept (changes and PC's answer applied through the re-check path, first confirmed dates kept, the order to `change_review`); the PIC signs off the exact `bravo_update` file (id + sha256, `/update/bravo-file`, dropped by any later edit; the signer is a maker, so another person cross-checks); entering it in Bravo is refused before. `waiting_pc`/`waiting_customer` remind from the loop's step. Migration `0d1d0e4eb203`. `confirmed` stands for `confirmation_sent` until ticket 28. Not done: the work list's "your turn" for a loop step (`ORDER_NEXT` keyed by status); a reply's accepts/rejects proposing the answer (with 28); 6-DW2 worded as a change. Owed: does PC delivering earlier than asked count as "can do" (now: no); who approves a Bravo update, the PIC (BA flow, built) or the head. Next: 28, 30 → 31–34, 35, 37.
- 2026-11-15 (evening), **ticket 07 done**: "Hỏi PC" drafts the request to PC (lines PC has not answered, else all for a re-confirmation; words in `sales_handoffs@1.1.0`) for a person to copy; "Ghi đã hỏi PC" sets the case waiting on PC (a field on the case, not a status) and the follow-up `waiting_pc` (`sales_followups@1.3.0`, 24 h, the PIC) reminds until every asked line is answered. PC's dates per line ("Ghi ngày PC") are deliveries whose quantities must sum to the line's (else refused, never adjusted); a re-confirmation keeps each delivery's first date; one paste-sheet row per delivery with AG (first confirmed) and AH (confirmed) filled (`sales_bravo_upload@2.1.0`); re-checked through ticket 27's path; a customer change or a correction drops that line's answer (migration `91f83937dbf1`). Fixed on the way: two stale tests (a complaint unread by a model reaches a person as `other` since `401643b8`; the reader tests loaded order rules 1.6.0, now 1.13.0). Not done: the cross-check sheet still lists the PO's schedules; a split's quantities are typed (the PC-mail reader reads dates). Owed by Proterial: PC's own request form; the reminder interval; how Bravo sets the first confirmed date on a re-split (B49 leaves it empty: fill AG on the first upload?). Next: 29, 28, 30 → 31–34, 35, 37.
- 2026-11-15 (later), **ticket 27 done, the change-request step gated**: a customer's change asked in a reply already on the order is recorded by a person ("Ghi yêu cầu thay đổi") and confirmed or rejected one line at a time, each on the case version seen; a confirmed line is stored on the line (`OrderLine.changes`), the case takes its next version and the checks run again (a pulled-in date raises short lead time). Only delivery date and quantity; a B03-shaped HTML table is read by its values (PO number, item code; dates only, never quantities); free text by the gated step `model_assist.change_request` (prompt `change_request@1.0.0`, eval `sales_change_request@1.0.0`, live 6/6 locally, not attested: off for every tenant); km vs m, several schedules, a line the order lacks, a held value changed since: blocked, never converted. One open request per order, later ones queued (`sales.change_requests`, migration `c7d0730fcccd`, DELETE revoked). Only before Bravo (`in_review`/`prepared`); in Bravo is ticket 29. Owed: may an order be prepared while a change request is open (now: yes); quantities in a table, and with which columns; price ever a change line; km→m by a customer rule; notify the PIC of a queued request. Next: 07 → 29, 28, 30 → 31–34, 35, 37.
- 2026-11-14 (later), **tickets 36 and 38 done**: 36, Bravo's customer list, item master and convert list import as exported (`7ca866be`; TAISEI 293, PCS 225, FBHP 50 lines exact, PCA unreadable); 38, a customer's SalesOrder rules learned from a worked pair (PO + the PIC's file) and proven by replay, cell by cell, before the head may approve (key `sales_salesorder_rules`, nine closed steps, "Học từ ví dụ" on the customer row; findings `reel_length_mismatch`, `spec_mismatch`; dw_sales ADR 0013 "Applied to ticket 38"), mechanism proven on synthetic pairs only: the real proof waits on one real pair per customer. Fixed with it: the upload file wrote the header's PO number on a line printing its own (ticket 18). Not expressible yet: a PO column the reading does not keep (PCS's PRS number, LME center), a per-PO row number, the EXW date the PIC types. Next: 24 → 19 → 22, 20 → 21, 26 → 27 → 07 → 29, 25 → 28, 30 → 31–34, 35, 37.
- 2026-11-15, **tickets 25 and 26 done, the intent step gated**: 25, a mail whose sender is a workspace person's sign-in address (the platform's record; never the folder, never the client; an upload or a forged SPF/DKIM/DMARC is incoming) is Sales' own: stored and threaded, never a case, shown "Sales gửi" under its thread (`sales.sent_messages`, migration `7f3def432f82`). 26, `ThreadIntent` (nine, several per message, each quote located by code, else `unclear`) replaces `ReplyKind`; one table (author, case kind, status, intent) proposes a step for a person, Sales' `asks` proposes the waiting-on-customer step; prompt `reply_intent@2.0.0`, eval `sales_reply@2.0.0` (60 messages). Live on qwen3.5-9b: 0.816 against the 0.85 bar (misses add an extra `asks`, none proposes a wrong step), so the step stays off for every tenant until a measurement passes. Owed: does a PIC's internal forward of a customer's PO open a case (now: no, the customer's own mail does); do Design or PC colleagues get DW sign-ins (their mail would read as Sales'). Next: 27 → 07 → 29, 28, 30 → 31–34, 35, 37.
- 2026-11-14 (late night), **tickets 20 and 21 done**: the customer of a sender is its contact address in the master data first, then the sender ledger (never over a contact), then its domain only where the tenant has not marked the domain shared (`shared_mail_domains`, order rules 1.13.0, one list on step O1); a shared domain with no matching address goes to a person (`customer_unknown`). 21 already held (a customer's own convert rows only); guarded by tests now. Owed by Proterial: each customer's contact addresses (B05) and the group's domains (B37) entered as a rules version; customer 4's codes. Not built: a ledger entry Bravo contradicts is dropped, not shown to Sales. Next: 26 → 27 → 07 → 29, 25 → 28, 30 → 31–34, 35, 37.
- 2026-11-14 (night), **tickets 19 and 22 done**: a mail or a portal export with several POs opens one case per PO on the same message (`domain/po_groups.py`, `sales.message_cases`, migration `3fcedec4e4f1`; a reply in its thread reaches all of them); the same PO in two files is one case, compared value by value, a difference is the blocking finding `files_disagree` (order rules 1.12.0) and neither file wins; a file-name suffix (R1, RV, -2) is only a hint "Tên tệp gợi ý PO sửa". All or nothing: if one PO of a mail cannot open (late revision, closed case, two files not one PO), the whole mail goes to Sales. Owed by Proterial: which file wins; whether the other POs should still open; forecast rows per PO or per file. Next: 20 → 21, 26 → 27 → 07 → 29, 25 → 28, 30 → 31–34, 35, 37.
- 2026-11-14 (evening), **ticket 24 done**: every stored mail carries a thread key from its own headers (the earliest stored message it names, else its own Message-ID; never the subject or a model; migration `0e77f2ca8c45`), a reply reaches every case of its sender's customer on the thread without scanning the mailbox, the model's numbers choose among several, else Sales picks ("Chọn hồ sơ", only an offered case, audited); a case shows the talk before its PO. Gaps in the ticket's Remains. Box checked again: nothing new. Next: 19 → 22, 20 → 21, 26 → 27 → 07 → 29, 25 → 28, 30 → 31–34, 35, 37.
- 2026-11-14, **tickets 17 and 18 done, the hardcode audit closed, B41 and 32 new Box files read**: 17 (a PO locked with a password, opened with its own mail's password in the sandbox, `e6eec5a1`), 18 ("Tải PO lên", the portal CSV by its layout, `portal_notice`, `17c31d9e`); the audit's 22 findings fixed in four batches (`9bb19864`, `f8322ffe`, `ca144777`, `401643b8`: a deployed DW1 never reads the mock, keywords never decide what a mail is, one owner for numbers/dates/units/currency, what a document does not settle goes to a person); B41 measured into ticket 02 (Bravo's 39-column SalesOrder; column "Mã hàng" left blank by all three customers); the 11-14 Box files mapped to tickets in the spec ("11-14"), ADR 0008 recommends A from B09, ticket 39 (quote approval per WIV-03-023) for Đạt; ADR 0013 and ticket 38 (a customer's SalesOrder rules learned from a worked pair, proven by replay). Next: 02, 36, 38, then 24 → 19 → 22, 20 → 21, 26 → 27 → 07 → 29, 25 → 28, 30 → 31–34, 35, 37.
- 2026-11-13, **DW1 reminds 24/7 by default** (Đạt, via the other session): `sales_followups@1.2.0` opens working hours every day, 00:00–23:59 (the morning brief goes daily too); a tenant narrows them as a rule version. 1.1.0 stays loadable. Lead time already counts calendar days; Đạt's rule: calendar days by default wherever a rule could count working days (customer 1's "5 business days" acceptance term is noted in ticket 28 for Proterial). The BA's reminder timings take `sales_followups@1.3.0`.
- 2026-11-13 (afternoon), **the customer conversation designed** (grilling with Đạt, Q1–Q12, all on the recommendations): dw_sales ADRs 0009–0012 and ADR 0005's amendments; CONTEXT.md terms (mail thread, outgoing message, thread intent, change request, implied acceptance, confirmed sender, triage card, skill); tickets 23–35 in `sales/dw1-production/`, the order in its spec ("11-13: the customer conversation"). Found after Q4 was accepted: the sender ledger (AI list item 5) already does what a provisional case would, so ADR 0009 keeps it below Bravo's contacts (owed: Đạt's confirmation). Then, unattended (Đạt: "làm liên tục cho tới khi xong hết ticket"): the tickets in that order, the process map and a simpler configuration (35), and a sweep for hardcoded values hiding bugs.
- 2026-11-13, **DW1 rebuilt to the BA's merged flows and the real Box files** (Đạt: "làm theo luồng mới"): the comparison and the 53 real files are read (outside git, `sales/dw1-production/spec.md` §11-13). Decided: no mail sent by DW and no customer portal (a person downloads and uploads); Bravo is written by DW only after a person approves, through the vendor's write API, now asked for (ADR 0026 amendment; paste sheet until then); a password-protected PO is opened with its own mail's password, never stored; real PO intake first. Next, asked 11-13 (Đạt): a design pass on the conversation before a PO (talks before the final PO, updates in the mail body, Sales' sent mail not exported today, final confirmation by reply or by silence per customer, new customers, Power Automate tags judged against thread headers), which reorders 19 and 22; ticket 17 does not depend on it. Then: tickets 17–22 (password, portal upload and CSV, several POs per mail, customer by address, customer absent from the conversion list, two files of one PO), then 07, 10, the confirmation as the customer's own PO plus the processed Excel, 09, 06, follow-ups 1.2.0, the RFQ branches. Found on the way and fixed (`c1e7ca94`): a mail routed to a named PIC was shown to nobody in a restricted tenant. The DW1 browser walk's remaining stale steps (4, 6: written before the 10-28 visibility and YCBG changes) are left uncommitted in `apps/web/e2e/sales-demo.spec.ts`, to be rewritten with the new flow (Đạt: "code chả sửa lại").
- 2026-10-30, **the contract's two DW01 gaps closed** (Đạt: "làm (1) hỏi đáp trên portal, (2) thư nhắc khách ... chạy liên tục tới khi xong", the design left to the implementer; Q&A to answer "theo ngữ cảnh tốt", with sessions and memory):
    - **Done: customer reminders** (DW01 function 4): `GET /{orders,quotes}/{id}/customer-reminder` (prepare scope, 409 unless `correction_requested` / `spec_discussion`) asks `sales.customer_reminder@1.0.0` (one-call door, as the caller) for a mail in the customer's language from code's facts (PO or request number, the day the customer was asked, for an order the points asked as finding code and line, never their values); `figure_check` + `names_amount` (moved from Q12's module, now shared) or no draft; recipients the customer's contacts; nothing sent or stored. Web: "Nhắc khách" card on both case pages while the case waits on the customer; `DraftedMail` is now the one drafted-mail view (Q12's too). Eval `sales_customer_reminders@1.0.0` 5/5. Mutations (amount, figure, waiting, asked-points filter, gate) each red.
    - **Done: status assistant** (DW01 criterion 6; dw_sales ADR 0007, item 9 back in scope, replaced by a catalog): `POST /sales/assistant/ask`, `GET /sales/assistant/sessions[/{id}]` (case.read; not open to support). `sales.question_intent@1.0.0` reads a question into `QuestionIntent` (order_status, quote_status, my_work, overdue, out_of_scope; the number as written; "about the case discussed"); code resolves it through `OrderQueries` / `QuoteQueries` / `OverviewService.my_work` (the portal's own read path, so nothing the pages would hide), `same_reference` ignores case and separators but never matches a part; facts carry no amount; `sales.assistant_answer@1.0.0` words them, kept only through `figure_check` + `names_amount`, else code's sentence. No model: "DW1 chưa hiểu", never a guessed case. Sessions in `sales.assistant_sessions` / `assistant_turns` (`e0940c90ce04`: RLS `tenant AND ((workspace AND user) OR scope)` to read, `tenant AND workspace AND user` to write; a turn's FK is `(tenant, workspace, user, session_id)`; appended, `last_turn_at` the one column updated; `sales.prune_assistant_sessions()` after 30 days, worker lane `sales_assistant_retention`). The session's focus (kind + id + label) carries "PO đó". Labels (`ORDER_STATE`, `QUOTE_STATE`, `ACTION`) held to CONTEXT.md and `labels.ts` by test. Web: "Hỏi đáp DW1" under Hồ sơ (session list, conversation, session in the URL, Enter sends but never mid-composition). Not done, per the ADR: images as context, Qdrant retrieval of turns, `dw_memory` (status must be live). Zalo/Teams: an adapter over the same service once Proterial accepts the provider and egress.
    - **Fixed, found by the integration run:** item 4 (`9851a74`) added `ModelStep.PO_BODY_EXTRACTION` with no migration, so `ck_model_step_measurements_step` and `ck_step_outcomes_step` refused it (attesting the step, or the activity row of every PO read from a mail body, would fail its insert): `55aea24d5845` admits it. Its `test_sales_constraints` case still expected an order's message-text row to be refused, which `cbd4fbacfce2` allows on purpose: the case now refuses a text row holding a page.
    - Live on Qwen3.5-9B (2026-10-30, GTX 1080): assistant 8/8 turns right (VI, EN, JA, the "PO đó" follow-up), 5 of 6 fact answers kept in the model's words, p50 2 s (p95 72 s is the model's first load); reminders 2/2 drafted, p50 9 s.
    - Checks: eval `sales_assistant@1.0.0` 5/5 smoke; mutations red (owner check via a leaky store, wording guard, loose match, guess without a reading, the ask gate via an out-of-scope question, the DB user clause, the composite FK, the IME guard); integration on Postgres (RLS by person/workspace/tenant with no WHERE, no DELETE or rewrite, prune with cascade), `test_rls_coverage`, `test_privileges`.

- 2026-10-30, **the signed-off contract's acceptance criteria against what is built** (Đạt: "xem các step quy trình đã đảm bảo chưa", percentages ignored, the deployment model will raise them; the contract PDF stays outside git, as every Proterial document does):
    - **DW01, covered:** intake and sorting from the mailbox (mail drop), PO revision replaces the old one, unrecognised mail goes to a person; PO read from Excel, text PDF and the mail body, layouts learned, codes converted, checked against quotation and standard LT, flags, customer mail drafted for approval; export hold (`missing_noc_esf`, export-control PIC only); Bravo upload file (the contract accepts a file where the ERP offers no connection), approval before anything is recorded, failures told; RFQ read, YCBG to Design, Design reply read, price basis and `suggest_price`, Sales decides, head approves, master list recorded; morning brief.
    - **DW01, to build:** (1) **status Q&A** (contract criterion 6: answers on the agreed question list right from the data, anything outside it said plainly, no guessing) — reverses the 10-30 deferral of item #9; on premises the channel is the portal ("kênh tương tác khác"), and the `onprem` profile has no `chat` route yet; (2) **reminders to the customer** ("nhắc nhân viên bán hàng và khách hàng"): `followups.py` never writes to a customer; a drafted reminder Sales sends, like Q12's.
    - **DW01, waiting on Proterial:** customer-portal intake (not connected; agree at the survey that portal POs reach the mailbox, or that email is the connected channel), the sending flow behind "Gửi cho khách", Bravo API, scans through the vision route (#13, needs the RTX PRO 4000).
    - **DW02 (Purchasing, PR → PO): nothing built here.** Six functions: PR intake (email, Bravo, form, scanned paper), cross-check (quotes, purchase history, budget, approval limits), supplier RFQ and comparison, draft PO, supplier confirmation and delivery tracking, brief and Q&A. `C:\Users\phung\dw` holds `dw_tender` (tender analysis), at most ideas for the comparison.
    - **Contract vs the rollout plan sent to Anh Tuấn** (`docs/sales/ke-hoach-trien-khai-dw1-dw2.xlsx`, untracked): DW02 runs **4 weeks** (go-live week 4) while the plan has DW2 going live in week 6; Proterial hands over the host **with the OS installed** (art. 5.1; FPT may help, but a late host is Proterial's delay, art. 3.2), and the host has one 4 TB HDD with no RAID 1 (the plan says HDD RAID 1).

- 2026-10-29, **less to configure, more for the model** (Đạt: "config các mẫu PO rồi email khá là phức tạp ... chuyển cho AI làm thì làm đi"; three questions, each answered with the recommended option; dw_sales ADR 0006):
    - **Done: DW1 learns a PO form.** A model's mapping that passes every `LayoutChecks` check is adopted as the customer's layout in the run that read the PO (`origin = 'model'`, no approval, audited `sales.layout.learned`, migration `e91d0c239874`); the case opens at once and its first POs carry `new_layout` flags. A refused mapping still goes to Sales with the onboarding screen linked from the message. "Mẫu PO" left the menu.
    - **Done: export control withdrawn** (Đạt: "kiểm soát xuất khẩu đâu có nằm trong 2 quy trình ... bỏ đi được không"; chose "bỏ trang, giữ bước chặn"): ticket 45's page, `sales.export_control_screenings`, `ScreenedCatalog` and the `sales_export_control` rule key removed (`fc723c5a7d81`). The hold stays: `missing_noc_esf` from the master data's NOC/ESF/denial-list dates, acknowledged by the export-control PIC.
    - **Model wired into the stack:** `DW_ONPREM_MODEL_BASE_URL` passed to api and worker (`.env`: the host's Ollama). Live attest on Qwen3.5-9B for the demo tenant: `layout_proposal` 97.7% (bar 90%, passed); `message_intent` 92% recorded not passed; the other four to re-run (the run broke while code moved under it).
    - **Done: rules changed in words, mail from an example** (ADR 0006 decisions 2–3, item #1): `POST /rules/{key}/drafts/words` queues a draft for any key the person may propose and read; the worker asks `sales.rule_change_in_words@1.0.0` for changes (path, value) to the part asked about (`focus`, a mail's kind); `rule_words.apply_changes` refuses an unknown path, a changed type, a mail text that drops or adds a `${value}` or prints a digit neither the old text nor the words hold, and a document the schema refuses (migration `71305f72d962`: `request`, `focus`, every key). The draft opens in the editor as a start option; the person sends it through the one door. Rules page: a sentence per rule, no version codes on the first screen, technical keys under "Nâng cao". Eval `sales_rule_words@1.0.0` 5/5 (mutation: the digit guard off → red).
    - **Done: item 3, the convert list learns from Sales** (`bbf5aa95bf6f`, `sales.recorded_convert_entries`, append-only, RLS): `OrderCommands.confirm_mapping` keeps the confirmed (customer, customer item code) → PRV code through `SnapshotSalesCatalog.learn_convert`; a later PO line maps through it at once, the company's list answers first, the first confirmation stays. No batch approval, unlike the line in the AI list: the confirmation is already a person's decision on the line; Đạt to say if a head's batch review is still wanted.
    - **Done: item 4, a PO written in the mail body** (no file attached): where the mail names an order and carries no document, the sender's domain is a customer's and `model_assist.po_body_extraction` (rules 1.8.0, off; `ModelStep.PO_BODY_EXTRACTION`, bar 0.85 `all.right_field`, placed at O3) may run, `PoBodyReader` asks `sales.po_body_extraction@1.0.0` for spans of the newest part; `domain.po_body_reading.read_po_body` locates each (whole token, a line's fields inside that line), parses it with `rfq_reading`'s parsers (an amount or total also as `2,792.00` / `2.792,00`, `parse_amount`; a quantity or price written `1.200,5` stays unread, as ticket 29's test holds), and refuses the whole PO when a line lacks its code, quantity, unit or price, a line repeats, there is no PO number or no currency. What the mail does not write is what it implies, anchored where it comes from: revision 0 and the receive date at the PO number, amount = quantity × price at the price, no requested date at the line (`requested_date_missing`). Every value flagged `model_read`, so Sales confirms each against the mail. `PoDocument` takes `attachment_id` None with `body: MessageText` (moved to `anchors.py`, shared with quotations), anchors ranges of that text with its digest. `GET /orders/{id}/message-text` serves the text (case + price read) and records it (`cbd4fbacfce2`: `ck_source_served_region` allows an order's text); `required_regions` asks for it before prepare/cross-check. Not read (down, refused, sender unknown): routed to Sales as before, with why. Web: the order page opens "Thư của khách" with the value's words marked (`MailTextDrawer`, shared with the quote's), "Chưa mở nguồn: nội dung thư" until opened. Eval `sales_po_body@1.0.0` smoke 5/5; live Qwen3.5-9B 5/5: VI/EN/JA golden 42/42 values right, the injected price and quantity not given (8/8 right), missing price/currency read as no PO; p50 54 s while four test suites shared the machine. Mutations red: the step gate, a field from outside its line, the message region, the flags, a guessed currency, the price scope on the text, the page's served mark.
    - **Deferred: item 9, a read-only assistant over cases** (Đạt 10-30: not now and likely not needed; on premises the work stays on the portal). The recorded design: a platform agent with read-only Sales tools, tenant-bound through the caller, no mutating tool, answers citing case and mail ids.
    - **Done: item 2, master data in the company's own layout**: when `parse_rows` refuses a file (no template header matched, a title row above), `CatalogParsing._matched` asks `sales.catalog_columns@1.0.0` (one-call door, as the importer resolved again, cut to `sales.master_data.import`) which shown row is the header and which cell is which column; `column_mapping.remapped` accepts only a row shown, each header that row's cell exactly, no cell or column twice, every required column named, then rewrites the header to the template's and `parse_rows` reads every row as before (row checks refused a scripted "note column as price"). `catalog_snapshots.column_map` (129852d287dc, jsonb, default `[]` = matched by header) keeps the match; the preview shows it "Máy ghép" to the submitter and the approving head. Smoke 5/5; live 9B: Vietnamese and Japanese layouts read whole, the English one refused twice (it would not map "Cust." to the customer code; code refuses a match missing a required column, so the importer sees "thiếu cột" as before), injection and missing column held: 2/3, a 9B limit to re-measure on the deployment model. Mutations (same cell twice, column twice, required) each red once their tests stopped covering for each other.
    - **Done: item 7, PC's delivery dates from a pasted mail** (O4): PC's mail is internal and internal mail never reaches DW1's mailbox, so Sales pastes it in the confirmation drawer; `POST /orders/{id}/pc-dates` (`sales.order.prepare`, at the version seen, text ≤ 8000, nothing stored) asks `sales.pc_dates@1.0.0` (one-call door, as the caller) for line/delivery/date-as-written/ISO date; `checked` keeps a date only when its words are written whole in the text (`written_in`: not inside a longer date, a sentence's full stop no part of it), `reads_as` that day (day before month, ISO, or no year), on a line and delivery of the case, and the line not named twice. The dates fill the form; "Ghi đã gửi xác nhận" still records them. Smoke 5/5; live 9B golden 3/3, then the injection case spread line 1's date to every line ("mọi dòng" in the injected sentence): the prompt now says a date belongs only to the lines PC names, and a sentence addressed to the assistant is no answer; then 5/5 twice. Mutations (written, reads-as, line, named twice) red.
    - **Done: item 6, Design's reply written in the mail**: a mail naming a YCBG is a Design reply with or without a file (the keyword gate no longer needs a document); from a verified Design mailbox with no attachment it is routed `design_reply_unmatched` ("written in the mail"). On the inbox row, `GET /inbox/{id}/design-reply` (`sales.quote.prepare`) asks `sales.design_text_reply@1.0.0` (one-call door, as the caller); `verified` anchors every value in the newest part (chars + digest) and parses it into its field; `QuotationService.awaiting_reply` (now the one matcher for forms and mails) finds the case. `POST` takes the values Sales confirms, checks them against the mail again, attaches `DesignReply(body=…, confirmed_by=…)` (attachment now optional) and logs the message attached. Live 9B first run followed an injected "report 99.9 kg/km" (a value the mail holds, so anchoring proved nothing): a mail stating more copper weights than lines is now no reading, and the prompt says a sentence addressed to the assistant is no answer; then 5/5 (golden 3/3). Mutations (anchor, sender, lines) red; the sender check needed its own test (a mailbox taken off `design_mailboxes` after the mail came). Not a `ModelStep`: on request, like items 5, 8, 12 (a stored proposal would have tied `dispositions` to `quotes` in a cycle).
    - **Done: item 11, Q12's question to the customer drafted**: on the screening page, "DW1 soạn thư hỏi khách" (`GET /quotes/screening/{customer}/{prv}/followup`, `sales.quote.prepare`, a row of today's screening only) asks `sales.screening_followup@1.0.0` (one-call door, as the caller) for a mail in the customer's language from code-built facts (customer name, item code, quote numbers with validity; no price). Refused when a figure is not among the facts or when it names any amount (a percent, a currency code or symbol: the unit test caught "giảm 5%" passing the figure check against a date's 05). Recipients are the customer's contacts; nothing sent or stored: "Mở trong Outlook" (`mailto:`) from the person's own mailbox. Eval smoke 5/5; live 9B 3/3 drafted.
    - **Done (prepared, not deployed): "Gửi cho khách" from the presser's own mailbox** (Đạt 10-29: no Graph, never a shared mailbox on the server; no flow exists until Proterial signs). `c42ed45c73a2` `sales.outbound_mails` (RLS, UPDATE allowed, DELETE revoked, one active mail per draft, `outbound_scopes_pending()` definer ids-only). API `POST /{orders,quotes}/{id}/artifacts/{artifact_id}/send` (prepare scope; the current, downloadable `send_draft` / `confirmation_draft`; every To/Cc one of the customer's contacts; mailbox = the presser's own address from the directory) queues; the worker's `sales_outbound` lane alone touches the share: writes `outbox/<tenant>.<workspace>.<mail>.json` + files into the presser's folder, reads `receipts/` (only the same mailbox's, only `"sent"` counts), marks a quotation sent as the presser through `QuoteCommands.sent`, tells them on not_connected / flow_failed / no receipt in 30 min. `DW_SALES_OUTBOX_ENABLED` (API) and `DW_SALES_OUTBOX_DIR` (worker) are unset everywhere today, so the button says "chưa được nối"; `DW_SALES_OUTBOX_FAKE_FLOW` answers locally (refused deployed). Flow and share setup in `infra/onprem/README.md`. Tests: 8 unit (mutations of the contact check, the receipt's mailbox, the connected check and the receipt default each red), 4 DB, 3 web.
    - **Done: item 10, the morning brief opened by the model**: a switch in `sales_followups` (`morning_brief.model_opening`, default on; not a `ModelStep`, because the brief is no step of either surveyed lane: placing it on the process map failed eight tests that hold the map to the WIV steps, and rightly). `FollowupLane.writer` (`BriefWriter`, built in the worker's DW1 mount where a model is wired) writes each recipient's opening from `brief_facts` (counts and up to 8 pressing cases: reference, customer code, who it waits on, due date as dd/mm/yyyy, next step; no amount, no name), as that recipient (`RequesterAccessPort`, their plan), checked by `figure_check`; declined or failed: the brief as before, the counts always follow. Eval `sales_morning_brief@1.0.0` smoke 5/5; live 9B 2/3 until dates went in as dd/mm/yyyy (the model rewrote ISO dates), then 3/3 three runs, p50 ~6 s. Mutations of the figure check and the switch red; a gone recipient is also caught by the lane's fallback, so no test tells that guard apart.
    - **Done: item 8, a case's mail thread summarised with citations**: `GET /{orders,quotes}/{id}/thread-summary` (`sales.case.read`, the case as the caller may see it) asks `sales.thread_summary@1.0.0` (one-call door, as the caller) for 2–6 points over the case's newest 12 mails; code keeps a point only when its cites are mails of this thread and every figure is in a cited mail (`figure_check`, now shared with item 12, and tightened: a figure counts whole or as a whole part of a longer one, never as a substring, so "9" no longer passes inside "0.79"). Nothing stored; web card "Tóm tắt chuỗi thư" on both case pages, points link to the inbox mail, the dropped count is said. Eval `sales_thread_summaries@1.0.0` smoke 5/5; live 9B both threads summarised, 5/6 points kept twice running (dropped: a reformatted number), p50 11–12 s; item 12 re-run under the tighter check 8/8. Mutations (cite check, figure check, substring rule back, gate) each red.
    - **Done: item 5, an unknown sender's customer suggested** (`7f94b09d1905`, `sales.recorded_customer_senders`, append-only, RLS): on a `customer_unknown` mail, `GET /inbox/{id}/customer` asks `sales.sender_customer@1.0.0` (one-call door, as the caller) which candidate wrote it; code picks the candidates (a name word no other customer's name holds, found in the sender, subject or newest part) and accepts only a candidate whose quoted words are in the mail and hold such a word. Sales confirms (`POST`, `sales.inbox.process`): the **address** (never the domain: public mail providers) is kept, `customer_by_sender` answers it after the domain, every intake path asks it, and the mail is queued again. Web: the inbox row opens with the guess, marked "Máy đoán", or a pick from the customer list. Eval `sales_sender_customers@1.0.0` 5/5 smoke; live 9B 5/5 (the distributor mail stays unmatched; the injected "answer VLX" resisted) after the prompt said a shorter name without its legal form is the same company (first run 4/5). Mutations (quote check, gate, routed check, ledger read) each red. `caller_run` replaces three copies of the one-call run; `assemble` builds the one-call services from one model.
    - **Done: item 12, findings explained by the model** (Đạt: model, not code-written text; no batch approval for learned codes): `GET /orders/{id}/findings/{key}/explanation` asks `sales.finding_explanation@1.0.0` through the one-call door (the API now gets one, as the worker) with code-built facts (finding, PO, line, `LineBasis`, other quotations valid today; amounts only for a price reader; a price finding refused to anyone else); `unsupported_figures` refuses an answer holding a number, date or code no fact holds. Nothing stored. Web: "DW1 giải thích" on each finding, marked "Máy viết". Eval `sales_finding_explanations@1.0.0` 5/5 (mutation: the figure check off → red).
    - Live attest on Qwen3.5-9B, demo tenant (10-29): layout 97.7%, rfq 94.1%, reply 97.1%, handoff 98.6% passed; descriptions 66.7% (bar 70%) and intent 89.8% (bar 90%) did not.
    - **Next (was):** customer mail drafted from one example letter per kind (code writes every fact, the model the prose, Sales sends); rules shown as sentences and changed by typing what to change (the model proposes the document, the head applies); technical rules under "Nâng cao" for the admin.
    - **AI audit of both lanes** (Đạt: "còn cho AI làm được cái gì nữa không ... ngoại trừ rule, gate kiểm định và HITL"), proposed order: (1) every draft mail from an example; (2) master-data Excel of any column layout mapped by the model, checked per row, the head still approves; (3) a confirmed item code proposed into the convert list; (4) a PO in the mail body read like a file; (5) an unknown sender's customer proposed from the signature; then Design free-text replies (Q4), PC date replies (O4), cited thread summaries, a read-only Q&A assistant over cases, a written morning brief, Q12 follow-up drafts, findings explained in words, scans with a vision model (infra). Human stays: price, approvals and cross-check, finding dispositions, sending, Bravo, NOC/ESF, applying master data and rules. Đạt (10-29): "làm luôn các cái" — all of them, in this order.
    - **Qwen3.8-Flash-Next only, no Qwen3.5-9B (Đạt, 11-10).** Measured on six DW1 sets (10-26, RTX 3090): every bar passed, PRV hints 0.978 vs 0.711, intent 1.0 vs 0.898. Owed before it ships: Strata packaged for offline use and its licence, a measurement on the RTX PRO 4000, DW2's and the Q&A sets on it. The profile switch is one file (`configs/models/onprem.yaml`).
    - **Scans and handwriting read by a model, not by code (Đạt, 11-12, decided).** If Qwen3.8 has vision, its own vision part ships with it to the plant. If not: PaddleOCR-VL (~0.9B) or another small vision model on CPU reads the page, and Tesseract stays for word boxes (DW1's anchors). Either way the page is rendered in `reader` (no network), the worker sends it to the model, the image is untrusted (an injection case in an image), and every value read from a scan stays flagged for a person. Found 11-12: Strata lists `qwen3.8-flash-next-q2_0` as `input_modalities: ["text"]`, and Giang's Cloudflare WAF blocks every POST to it (GET `/models` answers). Owed from Giang: whether Strata loads Qwen3.8's vision part, and the WAF opened. The comparison (Tesseract + model vs the model reading the image; synthetic PR forms in four handwriting fonts, scan and phone photo, plus the PO scan fixture) runs first on local Qwen3.5-9B; Proterial's real paper is still the measurement that decides.
        - **Run 11-12, Qwen3.5-9B (GTX 1080), 12 synthetic PR forms + the PO scan** (harness in the session scratchpad, not committed): reading the image, every critical field (number, date, code, quantity, unit, needed-by) right on all 12 forms, 0 wrong, ~30 s a page; Tesseract `vie+eng` `--psm 6` then the model: 0–5 of 14–18 critical fields right, the rest null or **wrong** (e.g. "The Huong", "paling M12x40"). The printed PO: 22/22 both ways. So Tesseract cannot read handwriting at all; the font-drawn hands are far neater than a person's, so 0 wrong is an upper bound, and a 2026 multilingual benchmark (OmniHandwritingOCR, arXiv 2608.18586) finds vision models "prone to hallucinated corrections" on real hands, the dangerous kind.
        - **Found on the way (11-12):** Strata's `/health` says `"service": "strata", "images": false`, so it has an image switch, off. Qwen3.8-Flash-Next is "Causal Language Model with Vision Encoder" (text, image, video in), but only community GGUF vision projectors exist (F16 ~0.9 GB), vision reached llama.cpp through an Unsloth branch, and quantisation is reported to hurt small-text reading most: q2 on the plant needs its own measurement. Cloudflare in front of Strata lets only GET `/health` and `/models` through (every other path 403, POST included); a WAF rule on Giang's side, not ours to bypass.
        - **Small OCR candidates, if Qwen3.8's vision falls short (all Apache 2.0, ~0.9B, CPU-capable):** PaddleOCR-VL-1.6 (native in llama.cpp, GGUF); SenOCR-Vi (VietAlphaLabs, a Vietnamese fine-tune of it, 23k Vietnamese handwriting records in training, self-reported 82.83 vs base 80.90 on MDPBench Vietnamese, transformers/vLLM, no GGUF); a fine-tuned PaddleOCR-VL reached 5.40% CER on UIT-HWDB handwriting lines (one GitHub benchmark). None gives word boxes, so Tesseract stays for anchors. Next: run both on CPU here through the same harness, and on a few PR forms written by real hands.
        - **Run 11-12, the small models on CPU (this machine, 8 threads, same 13 pages):** PaddleOCR-VL-1.6 (GGUF, llama.cpp b12307) read a page in about 55 s; its text then went to the same extraction model: 186 of 200 critical fields right, 14 wrong, all on 3 of the 12 forms (the cursive photo and both loopy hands: `V7-0412` for `VT-0412`), the printed PO 21/22 with 1 left empty; names and notes often lose a diacritic. Against it: Qwen3.5-9B reading the image 200/200, Tesseract about 23/200. SenOCR-Vi through transformers on CPU took 50 min for one page and was stopped: not usable here without a GGUF build or a GPU. So the fallback order holds: the main model's vision first, PaddleOCR-VL second, and a wrong code that looks right is why every scan value still waits for a person.
    - **The BA's surveyed flow, 11-09** (`Downloads/proterial/prv.drawio`, 4 pages: RFQ intake, pricing and sending, PO intake to confirmation, changes after confirmation). Beyond what DW1 does: mass vs pcs (pcs priced by JP & HQ: a drafted request), a new-code request to Design with the nearest PRV code, "never produced" and stock/production checks (need Bravo data; PC confirms what Bravo cannot see), the confirmation as a PDF in the customer's own PO form with the PIC's stamp and the processed Excel, NOEC/ESF drafts holding a PO, PO before RFQ opening an RFQ, internal changes (6.1B: overcapacity, NG, short stock) and bulk line splits for PC, pricing from LME band, customer margin and exchange rate with a suggested strategy, the signed quotation PDF, Base price and BP code from Design. Bravo's own quotation module goes live 11/2026: read it, do not duplicate it. Customer portals (log in, download) stay a person's.
    - **What the 11-09 recording shows** (`Downloads/Digital Worker 01 PRV-FPT-20261109_154204-Meeting Recording.mp4`, 95 min; frames read, speech not yet: a Teams transcript is asked of Đạt). Sales enters an order by **pasting rows from an Excel sheet into Bravo's "Cập nhật đơn đặt hàng bán" grid** (Bravo's clipboard, 24 rows). Its header: booking date, SO number (`SO2611-000156`), currency, type (Mass production), direct and indirect customer, contact, creator, **LME center**, the customer's PO number, contract (`HDB11/19-001`), receipt date, payment terms, delivery term (CIP), delivery mode (SEA), destination, end user, shipment type. Its lines: PO line, item code, item name, specification, sales special notice, MOQ, lead time, LT-MOQ notice, customer description code, all customer code, all customer description, other information 1–4. The paste sheet ("SalesOrder"): PO line, item, customer code, other information 1–4, unit, quantity, unit length, MOQ, lead time, unit price, requested date, first confirmed date, confirmed date, sales accounting, delivery mode, delivery term, destination; one row per delivery date. A check workbook ("in put PO") sets the customer portal's download (part no., qty, delivery date, PO no., firm order, site, supplier code) beside the order as on Bravo, with a TRUE/FALSE column. Conversion runs through a large formula workbook (sheets PRL PO, PRV vs PRL, price); colour codes take part in the PRV code; quotation masterlists are Excel (QM-PRL-…). An internal "PRV Portal" lists requests (PCS PO). So DW1's Bravo file should be that paste sheet, in Bravo's column order.
    - **The surveyed flow, specified for production (11-10, Đạt: "ok làm đi").** `sales/dw1-production/spec.md`: Bravo's "Đơn đặt hàng bán" from Đạt's four photos (one SO per customer PO, `SO2611-000161`; books in USD, VND at 25,972; delivery mode/term/destination, payment terms and PIC constant per customer; price to 5 decimals; first and current confirmed dates; "Chi tiết thực hiện" for deliveries; a `SALEAI` user signed in), the drawio's steps against what is built, six questions Q-B1..B6 (Create CDO, Sent to G-Samit, Returned, `SALEAI`, Bravo's "Duyệt" vs DW1's cross-check, one SO per PO). Tickets `sales/dw1-production/issues/01..13`: ready-for-agent 02 (paste sheet, final headers on B41), 06, 07, 09, 10; needs-info 01, 03, 04, 05, 11, 12, 13; needs-triage 08 (NOEC draft vs the 10-29 withdrawal). ADRs: `docs/adr/0025` (Qwen3.8 on Strata only, Accepted), `docs/adr/0026` (Bravo read through the vendor's API, written by a person, never its database; Accepted), dw_sales `0008` (who computes a price: Bravo's quotation module or DW1; Proposed, Đạt owes). Glossary: production type, paste sheet, SO number, first confirmed date, sales accounting, LME center, Base price and BP code, colour code, read-back. Forms list gained B41–B45 (outside git). Out: customer-portal login, the electronic stamp.
    - **Bravo's second batch, 11-10 (37 photos, `sales/dw1-production/spec.md`).** Bravo already owns every master list DW1 imports (customers incl. `TDC` prospects, items with customer item codes, stock and SO history per item, the approved convert list with colours written out, base prices `BP`+6 digits with costs, LME and LME center, black list, export control program per direct+indirect customer and fiscal year, delivery terms) and runs quotations (LME band 7,500–15,000, price at fixed LME, Duyệt) and their master list: production DW1 reads them through ports (new ticket 14), keeps no second copy, and a mapping Sales confirms waits for Bravo's approved row. The paste target is "Edit detailSO all" (order known; amount = qty × price half-up, VND price ÷ rate, both hold on every row seen). Create CDO and G-Samit are shipping and group reporting, not DW1. LME center fits `floor(actual/500)×500+250` for all 7 months (asked). Whiteboard: a pre-sales step before the RFQ (approach, profile and catalogue, RFQ form for Design, verify, new Bravo customer code) — ticket 15, needs-triage: outside the contract's two procedures. Questions 57–60 added (Q-B7..B10); 51–52 marked answered by the screens.
    - **Proterial workbooks standardised to Bravo (11-10; outside git).** Questions: 27 rewritten (every list is in Bravo: can Sales export each screen until the API?), 11's interim answer reads ECP and Black list, 61–62 added (who writes the YCBG's Design Check and status; how colour enters a PRV code). Forms (44): B02/B04–B07/B09/B14/B21 now name the Bravo screen to export; B16 exports Bravo's YCBG screen, B11/B18 Bravo's print or the template in use; B08 and B20 withdrawn (into B41, B07); B45 sent; B46 pre-sales documents (P3, if question 59 says so). API (39): R01/R03–R07/R10 use Bravo's real fields; R08 Base price and R09 ECP + Black list added; R13 reads Bravo's YCBG (RFQyymmdd-nnn, Design Check); W05 creates a draft quotation for Bravo's own Duyệt. Correction the same day: YCBG, Color code and Quy trình bán hàng are not empty, only unphotographed (Đạt sent them). The convert list's states 1–2 held no rows that day but are steps (Đạt: an empty Bravo screen is no data, never no step). Rollout `.xlsx`: "Báo cáo tiến độ" rebuilt as Đạt's whiteboard grid (Plan / Thực tế × Nghiệp vụ / IT, every working day 09/11–18/12, dates as WORKDAY formulas off the plan's start date; days 1–6 copy the board, the rest follow the 6-week plan, so DW02 still goes live in week 6, not the contract's week 4). Ticket 16 is the YCBG in Bravo's shape.
    - **Acceptance documents per milestone (11-11, Linh asked; outside git).**
        - Sheet "Hồ sơ nghiệm thu" in `Downloads/proterial/Baseline_Proterial_DW1-DW2.xlsx`, read from the contract: 34 documents over the baseline's milestones, each marked as named by the contract or proposed as evidence.
        - State: 15 missing, 8 partial, 2 drafts.
        - Same day, Đạt: the sheet is an expected set to send, so it was rebuilt without the state and FPT's notes: 33 documents (TL01–TL33), 21 by contract and 12 proposed, the two DW user guides merged into one row "mỗi DW một bản". The version with the 11-11 state is `Baseline-ban-noi-bo-co-hien-trang-11-11.xlsx` in the session scratchpad, which does not outlive the session.
        - Named by the contract and missing: the rule set (waits on Proterial), the incident guide, the DW02 user guide, training material, the pre-test confirmation (data, rules, approvers), the per-function acceptance report, and the acceptance-and-handover minutes.
        - DW02 is due by contract in week 4 (04/12). Moving it to week 6 needs a signed change (art. 7, 15.3).
    - **Forms workbook made a one-shot request (11-10, Đạt sends it once; outside git).** 51 forms:
        - New group B47–B53:
            - shared conversion rule sheet signed off by the Sales head;
            - full chains per Sales PIC (PO → conversion workbook → SalesOrder → SO);
            - internal mail samples (Design new code, PC, JP & HQ, NOEC, internal changes);
            - screen recordings plus a written step sheet per person and process;
            - DW2 chains per buyer;
            - UAT scenarios to confirm.
        - Sharpened: B05 (PIC and backup), B09 (three worked price examples), B40 (golden sets).
        - New sheets: "Mẫu quy tắc chuyển đổi", "Mẫu mô tả cách làm", "Bộ kiểm thử (golden)" (7 sets with required edge cases and where each answer comes from), "Kịch bản UAT" (U01–U27).
        - "Hướng dẫn" gained "Cách gửi một lần": plant folder, naming, Bravo export, a narrated Teams self-recording, marking manual edits.
        - Question 63: one PIC per customer?, who settles differences, B47 as the single source.
    - **Target model at deployment** (Đạt, 10-29): Qwen3.8-Flash-Next (text, image, video in), quantised to 2 bits with the speed-ups Giang's homelab used (MTP and the like), on the customer's RTX PRO 4000 Blackwell, 24 GB VRAM. Not available on this machine (GTX 1080, 8 GB): #13 (scans read by the vision route) is built and measured when that GPU is in place; every other step runs on Qwen3.5-9B now and is re-attested on the new model then (`configs/models/onprem.yaml`, one route per step).

- 2026-10-29, **the two lanes linked for real, and nothing fails silently** (Đạt: "2 quy trình trong DW1 đã nối với nhau chưa", "không thể làm hỏng luồng rồi im lặng luôn được"):
    - Quote → order: step 11's master-list rows went to the mock catalog in the memory of the API process; the worker that checks a dropped PO never saw them and a restart lost them. Now `sales.recorded_quotations` (`c1c192e011e1`, append-only, tenant AND workspace RLS); `SnapshotSalesCatalog` answers every quotation read with the list (approved snapshot or mock) plus the recorded rows it does not hold, and refuses a recorded number the list holds with other terms. Integration: what the API records the worker checks against, after a restart too.
    - Mail drop: a file the reader refuses or over 20 MB was only logged. Now recorded as `refused` with its reason (`2b666371099a`), never read again after a restart, and told to the inbox's people (`sales.inbox.process`) once per file; a folder that cannot be listed is told once a day while it lasts.
    - Outbox: three attempts a second apart, so a reader restart of a few seconds stranded an upload or a decided approval for good. Now `next_attempt_at` (`8607c7876b2e`) with waits doubling from 30 s, `OUTBOX_MAX_ATTEMPTS` 5 in `dw_platform.domain.outbox` (the worker setting is gone: the admin page reads the same value); the `outbox_alarms` lane tells the tenant's administrators (`platform.tenant.settings.write`) once per stopped event, and Quản trị → Việc nền lỗi (`/admin/background-failures`) sends one back, audited `platform.outbox.requeued`. Only the error's kind is shown, never its text (a database refusal echoes its row).
    - Already in place, checked: the processing queue (retry with backoff, then `failed` with its reason in the inbox and "DW xử lý lại"), the reaper for a dead worker's jobs, the worker loop that keeps every other lane running when one throws, rule drafts swept when their event is lost.
    - Not done: a lane that throws on every tick (other than the mail drop) is still only logged; there is no deployment-wide operator inbox to tell.
    - Mutations red: the recorded-row merge, the store's read-back refusal, the claim's wait, the page's workspace filter.

- 2026-10-28, **who sees and changes what** (Đạt, answering "các sales thấy luôn cả các đơn hàng, báo giá của nhau à", "PIC tự config quy trình luôn à", "không có workspace … swap DW2"):
    - Rules: a PIC proposes nothing; the head proposes and their version applies at once (`applied_directly`, audited `sales.rules.applied`); the admin proposes through `sales_rules_editor` and the head approves (migration `40266fbc98bf`, ADR 0003 addendum).
    - Cases: in a `restricted` tenant a PIC sees their own cases, the pool's and what they are asked to check; the head sees their reports' (`visible_owners`, ADR-003; `visibility.sees_case`, enforced in `stored_order`/`stored_quote` with a required viewer and on every list). Demo tenant restricted, PICs report to Giang.
    - Shell: the workspace block only with a choice; the brand names the DW ("DW1 Đơn hàng & Báo giá") and becomes a switch once a person reaches two.
    - Integration run (PostgreSQL, 1 h 33 min): 21 red, all tests left behind by today's changes, none a defect: the route inventory lacked the export-control parameters (`customer_code`, `step`); rule drafts and the price walk proposed as An (now the head, whose version applies at once); the quote-artifact state test assumed M10 stays `received` (its YCBG is drafted at once) and that the uploaded signed copy renders (422, no composer). Re-run 78/78 green; the demo-team test now puts back the platform's hierarchy (Bình also reports to Giang there) instead of clearing it.
    - Stack rebuilt, `40266fbc98bf` applied, demo reset: An sees 2 orders (An's own and the pool's), Giang 6; An's Quy tắc answers 403 and the nav drops it; the brand reads "DW1 Đơn hàng & Báo giá". Two fixes from looking: the head's rules page said "Đề xuất bản mới" and "Người đề xuất không tự duyệt" (now "Sửa quy tắc", applied at once); the bell read 99+ from 490 notices left by earlier rehearsals, linking to deleted cases (the demo reset now clears `sales.` notices).
    - Answered, no code: the two lanes run independently from incoming mail (DW1 sorts each message), linked only by data (an approved quotation prices the later PO); a PIC keeps "Duyệt" for the cross-check; the quote lane's manual steps are Bravo (YCBG number) and outgoing mail until those are connected.
- 2026-10-28, **the quote lane runs on its own as far as it can** (Đạt: "làm đi kể cả Q4… Q7… AI càng nhiều càng tốt"): a complete request has its YCBG drafted by DW1 in the transaction that receives it (`quote.ycbg_drafted`, DW1's run), and the PIC's last answer drafts a request that lacked something; Q4 was already automatic (a verified Design mailbox's reply is matched by YCBG number, `take_design_reply`); Q7: `suggest_price` gives each line a starting price from the evidence, the customer's own valid quotation, else their last order, else (only for a viewer holding the other-customers scope) the reference, raised to the policy floor, shown beside the price with its row and filled into empty fields on request; Sales still records the price as their decision. The your-turn notice names the next step for `ycbg_drafted` and `design_replied`. Deterministic by choice: no model picks a number. Mutations red: the inbox draft, the answer's draft, the scope gate on the reference, the floor raise, the empty-field fill.
- 2026-10-28, **"your turn" told at once** (Đạt: "nếu dừng thì có noti cho họ thấy chưa"): `sales_followups@1.1.0` adds `your_turn` (on by default): the follow-ups lane tells the PIC the moment a case enters a status waiting on Sales, and the head for a cross-check or an approval; once per status entered, quiet hours defer it. Whom a status waits on is `overview_service.WHOSE_TURN`, read from `STATUS_BUCKETS` and the next steps (one owner). Migration `fb59ce04fd76` widens the delivery CHECKs. Unit, lane, DB tests; two mutations red.
- 2026-10-28, **export control** (ticket 45): backend, and the page `/sales/export-control` with a drawer per customer; see the ticket.
- 2026-10-28, **latency measured, and the slow paths fixed** (agent; Đạt: "lúc test không đo P50 P95 P99 à", the source drawer slow, search jumpy):
    - **Measured now:** `dw_api/middleware/timing.py` logs one `request_timing <method> <route template> <status> <ms>` line per request (the template rebuilt from the route and the path: FastAPI 0.141 hands an included router's route over without its prefix, measured); `make latency-report` (`scripts/route_latency.py`) prints p50/p95/p99 per route from the API log, on a test stack or at Proterial's.
    - **Before** (743 requests, three rounds of the demo): `GET …/orders/{case_id}/source/{attachment_id}` p50 9.5 s, p95 11.5 s; every other route p95 under 0.9 s. Cause: a sheet view asked the reader twice (grid, then sheet names), each a fresh sandboxed process spending 4.3 s of 4.6 s compiling its imports (`PYTHONDONTWRITEBYTECODE` on a read-only root, no bytecode in the image; the Dockerfile's "negligible impact" was true of a long-lived process only), and nothing was kept.
    - **Fixed:** bytecode compiled in the reader and docgen images; the grid carries the workbook's sheet names (one read per view); `SourceService` keeps an opened page or grid in the platform cache for an hour (`source_cache_key`: tenant and workspace lead; entries over 2 MB not kept; a miss or a corrupt entry reads the file; the served record is written on a hit too); the reader child no longer imports `reader_client`, httpx, the agent runtime or SQLAlchemy (`dw_reader/files.py`; the dead `in_process_readers` removed); DW1 reads a new or revised case's pages ahead into the cache (`SourceService.warm`, at most 6 regions, records nobody as served, a failure logged and never failing processing; the worker reads `REDIS_URL`).
    - **After:** child import 4.7 s → about 1.0 s; source view p50 1.2 s, p95 1.6 s on a page never opened; 42–95 ms from the cache, which is what a fresh case's pages are after DW1 read them (40 entries after `demo-reset`, no warm failure).
    - **Web:** the list search kept its value in the URL and lost keys when typed fast ("vlx po 2609" ended as "9"); it now keeps the text in the field and hands the list (and the URL) the text 250 ms after the last key. Identical GETs in flight at once share one request (`lib/session.ts` `sharedFetch`, GET without a signal only, keyed by URL, bearer, tenant, workspace, support grant): a page load's `directory/members` 2 → 1, `my-work` 2 → 1, `sales/inbox` 3 → 2 (the DW1 bar's read waits for the overview by design).
    - **Checked:** unit tests for each guard, each mutation-checked red (timing template, one read, cache tenant key, served on a hit, warm failure, search keys, shared GET); Python unit suites (Sales, API, reader, worker) exit 0; web 647/647; ruff, mypy, 12 import contracts.
    - **Scan (trivy 0.74.0, HIGH+ with a fix), found, not caused by this change:** certifi 2026.7.22 → 2026.10.18 (CRITICAL), pillow 12.3.0 → 13.0.0 (CRITICAL, a major), pypdf 6.19.0 → 6.21.2 in api/worker/reader (pillow alone in docgen); reader's libbrotli1, libexpat1, openssl fixed upstream but a cached `apt-get upgrade` layer kept the old ones. **Owed:** a dependency bump (uv.lock) and a reader build without the cached apt layer, then the scan again.
    - **Note:** Valkey runs `noeviction` and saves to disk (`--save 60 1`): kept grids, prices included, live in the Valkey volume for their hour; entries are bounded by TTL and size, not by a memory cap.
    - **Proterial's process, read 10-28:** the survey lists WIV-03-032's six steps (product screen, denial list on the group site, red-flag questions, NOEC/NOC by mail, ESF with multi-level approval printed and scanned, yearly screening) and WIV-03-031's four (temporary code, new direct customer on a hard-copy form to accounting, two conversions to official); Q9 is "print and get the head's signature", no e-signature asked. Deck 30/09 said "trình ký điện tử"; deck 13/10 (the latest) says "trình duyệt" and promises no dependence on the internet, which a remote-signing service would break.

- 2026-10-28, **stack run and the last fixes before Proterial** (agent; Đạt: "còn code gì nữa ở DW1… chạy lại cho tôi xem"):
    - **Keycloak for the customer's IT:** realm group `dw-it` (`infra/keycloak/dw-realm.json`) holds `view-users`, `manage-users`, `query-users`, `query-groups` of realm-management and nothing else. Measured on 26.7.2: a member's admin console (`/admin/dw/console/`) shows Users and Groups only; realm settings, clients, authentication and identity providers answer 403; mapping `manage-realm` to themselves or anyone answers 403; they can add another user to `dw-it` (the same rights, no more). For a deployment serving one customer only (the realm is shared by every tenant). FPT adds Proterial's IT accounts at hand-over; the guide's Keycloak section says so and asks for OTP per user. `test_keycloak_realm.py` holds the role set (mutation: `manage-realm` added → red).
    - **Keycloak master admin password** matched to `.env` again through `kc.sh bootstrap-admin user` (a temporary admin, deleted after): `make demo-reset` runs whole. `scripts/keycloak_dev_users.py` now also stamps each one-tenant dev user's `dw_tenant_id` (so the demo's Thành viên can reset and lock) and puts the org admins in `dw-it`.
    - **Web:** the case stepper puts titles under the icons with the WIV code on the line below, and marks the case's own step active (antd marked step 1); "N giá trị chưa ai mở nguồn" is drawn at `uploaded_to_bravo` only (Đạt's 10-24 question, decided); the activity card's empty state says no model step ran, not that DW1 did nothing; the inbox's sender tag reads "Đã xác thực"/"Chưa xác thực" and the owner column "Phụ trách", so the table fits 1440 (it still scrolls inside itself at 1280, DW1 column fixed).
    - **Qdrant:** 37 leftover `dw_*_test_*` collections from interrupted test runs deleted (the fixtures do delete theirs; a killed run cannot).
    - **Reader child:** importing `dw_sales.adapters.readers.operations` measured 1.75 s on the host (LangGraph no longer imported; `dw_agent_runtime` and SQLAlchemy still are, through `application/catalog_imports` and `order_ports`). Left as is: about 2 s per file is not the bottleneck at Proterial's volume.
    - **Run:** `make demo-reset`, 45 sample mails processed in about 9.5 min (27 cases: 23 orders, 4 quotes; 15 routed to Sales; 3 attached); a 13-page tour as An, Giang, Hà and Tâm with no API or console error. Web 642/642.
    - **Still owed to Proterial, not code:** real PO/RFQ samples, the plant PC mail drop measured, Bravo write, e-signature, NOEC, retention of stored mail. The `.docx` user guide needs a rebuild for the Keycloak section.

- 2026-10-27 evening, **checked on the rebuilt Docker stack** (migration head `d90793645086`, `make demo-reset` run: the 7 `eml-` dispositions left from ticket 43's stored-mailbox run are gone, the lane processed the 45 sample mails again): a flow walk (An marks M11/M16/M17 handled, it leaves Việc cần làm, reopened it is back; Tâm on Thành viên finds DW1's row locked and marked a service account, and his own bin locked; six Sales lists at 390 px with no page overflow and no table scrolled sideways) passed 15/15; a sweep of 31 routes × 4 personas × 2 widths (218 views) found no overflow, no English, nothing under 12 px but React Flow's attribution, and no API error but the 403 of a refused page typed by URL. Python unit, architecture, ruff and mypy pass; web 641/641. **Not done:** `scripts/keycloak_dev_users.py` (the second half of `make demo-reset`) fails with `invalid_grant`: the Keycloak master admin's password in `.env` no longer matches the `keycloak-data` volume (the bootstrap reads it on the first start only); the personas' logins from before still work.
- 2026-10-27, **a routed message marked handled** (Đạt chose the done state; `application/routed_mail.py`, migration `d90793645086`): a person marks a message routed to Sales handled once dealt with outside DW1, with an optional note, and may reopen it. Who may is whoever Việc cần làm shows it to (`message_owners`, now the one answer both read: its PIC, any PIC for the pool's) and the head (`sales.case.assign`). It leaves Việc cần làm and the overview's waiting count and stays in the inbox (tabs "Chuyển Sales" and "Sales đã xử lý"), saying who and when; processing it again clears the mark. One CHECK (`ck_messages_handled`) holds the shape; `ix_messages_routed_work` leaves handled messages out. Audit `sales.message.handled`/`reopened`, the note kept off the audit row. Checked: unit 5, integration 4 (route, upsert, CHECK, another tenant 404), web 4; mutations of the owner guard, the in-memory filter and the SQL filter each went red.
- 2026-10-27, **ticket 43 run on the Docker stack** (stored mailbox, a scratch drop folder, override outside git): 5 fictional `.eml` files stored by `sales_mail_drop`, queued by `sales_inbox`, processed: the PO with its xlsx opened a case, the Design reply was recognised (verified sender) and routed `design_reply_unmatched`, the internal and body-only RFQ mails `other` (the stack's model is the mock). A PIC proposed `ignored_sender_domains: [seller.example]` from step O1, the head approved it (`sales_order_rules@1.7.1`), and the next internal mail (a subdomain) was `left_out` while a customer's was stored. Fixed on the way: the inbox no longer says "giả lập", and a stored mail's 68-character id shows as `eml-` + 8 digits (`_lib/messages.ts`). **Found by the edge-case sets:** (1) fixed 2026-10-27: the plain-text cut now knows Vietnamese Outlook's "Đã gửi:" (`domain/mail_parts.py`); (2) fixed 2026-10-27: a hand-off quantity in another unit than metres ("3 km", "4 cuộn", "2巻") is not copied, Sales fills it (`domain/handoffs.quantity_of`); (3a) fixed 2026-10-27: a delivery column that reads no date on any line refuses the layout (`requested_date_empty`); (4a) fixed 2026-10-27: an RFQ date in Reiwa (令和8年11月15日, R8.11.15, 令和元年) is read; **open:** (3b) the layout check accepts a thousands separator on a PDF with no grouped number (not fixed: checking it means telling a number from a date or a code in the form's cells, and a wrong guess refuses a good layout); (4b) the reply and RFQ cutters miss "loi"/"x2c" (lab notes; the cases were not kept, so not fixed on a guess). The edge-case sets live outside git (lab) until Đạt decides whether they join the datasets.

- 2026-10-27, **real mail without Microsoft 365 access** (ticket 43, `issues/43-mail-drop-folder.md`): Proterial refuses DW1 any M365 access and its admins are in Japan. Each PIC's Power Automate flow exports every Inbox mail as `.eml` to their OneDrive; a plant PC syncs the PICs' shared folders and shares them over SMB; the worker's `sales_mail_drop` lane parses each file in the reader sandbox (`mail.read`) and stores it (`sales.mailbox_messages`/`_attachments`/`_files`, migration `e544ff20fad6`, append-only, partitioned, RLS). `DW_SALES_MAILBOX=mock|stored` in both processes; `sales_order_rules@1.7.0` adds `ignored_sender_domains` (empty takes all; Design always taken), placed on step O1. Guides for the PICs and for the plant PC/host are Word files outside git. Checked: unit (mail read 12, lane 18), integration 16 on Docker, mutation check 10/10 red. **Owed:** retention of stored mail (must follow the cases'); the plant PC steps (OneDrive shortcuts moved into one folder, SMB over a OneDrive folder) are written from knowledge, not yet measured; a real Exchange export read by `mail.read` (Đạt's test file, not yet in hand).

- 2026-10-26, **user guide for Proterial** (Đạt): `docs/user-guide/Huong-dan-su-dung_Proterial_DW1.docx`, 22 pages, every role (Sales PIC, Sales head, leadership, IT), built from `docs/user-guide/huong-dan-su-dung-dw1.md` with the fdx-word-doc skill (TOC page numbers from Word over COM: no LibreOffice on this machine). Screenshots are the demo tenant's fictional data, taken as each persona through the dev-auth stack; every button label in the text was checked against the code. No screenshot of Thêm người (dev auth has no Keycloak) or of an empty Duyệt page. Rebuild after a UI change: edit the `.md` and rerun the build; the recipe is in this commit's message.

- 2026-10-26, layout from Đạt's look at the running portal:
    - **Home → "Việc cần làm".** Someone with `sales.case.read` landing on `/` is sent to `/sales`, the bar's first page; reverses 2026-10-20 (the board at `/`), because no menu item led back to it. The board stays under Hồ sơ → Pipeline hồ sơ.
    - **Board, one lane at a time** (`?lane=quote`, orders by default, the switch counts each lane); columns as tall as the window, each scrolling its own cards; a long tag wraps inside its card (`StatusTag`, `@dw/ui`).
    - **Lists scroll inside themselves** on `md` and up (`lib/use-fill-height.ts`, `scroll.y` from the window's remaining height): Việc cần làm, Hộp thư, Đơn hàng, Báo giá, Mẫu PO, Dữ liệu chủ, the rule versions, Duyệt, Nhật ký, Tri thức. Not yet: the case pages' line tables, Kiểm chéo & duyệt (two tables stacked), Hoạt động DW1.
    - **Rules for a PIC is by design** (`57a241ea182b`): `sales.rules.propose` on `sales_pic` and `sales_head`, `sales.rules.approve` on the head only, and the proposer never decides their own version. Whether a PIC should propose at all is Đạt's call (one migration).
    - Checked: vitest 613, tsc, lint; e2e `enduser-nav` and `platform-pages` updated for the new home and board, not yet re-run.

- 2026-10-24, web half of defects C, D, E and audit gaps 1–5, the browser-look list of 2026-10-24, and the master-data mismatch. Committed 2026-10-24 with the server half below. **Defects A–E closed**: the full run passed.
    - **Full run 2026-10-24:** integration dw_sales 192 (3 skipped, clamd), dw_platform 328, apps/api 165 (1 h 42 min); e2e platform-pages 3, enduser-nav 13, enduser-data 6, enduser-forms 12, enduser-race 7 (C, D, E now pass, no test.fail), sales-demo 13 + 2 skipped. Found and fixed: the process canvas dropped each card's measured size, so React Flow's fit never ran and "Xem cả quy trình" did nothing while the quote lane's last row sat outside the frame (`LaneViewport` fits from the lane's own layout; enduser-nav test 10 now checks every card and label is inside its frame); a rules-process vitest that read an antd field error synchronously.
    - **Open, found by the run (not caused by it):** sales-demo test 2 times out at 480 s on this machine (38/45 mails): each reader child spends ~4.1 s of ~4.5 s importing `dw_sales.adapters.reader_client` → `catalog_imports` → `dw_agent_runtime.approval_flow` → LangGraph — the reader child must not import the agent runtime (failure-mode #6 shape for time, and the mailbox throughput); 118 leftover `dw_knowledge_test_*`/`dw_memory_test_*` Qdrant collections that some test never deletes (failure-mode #6) make Qdrant take ~4 min to start; the "N giá trị chưa ai mở nguồn" panel also shows to the preparer before Bravo (long on a phone) — limit it to after Bravo? (Đạt); "DW1 chưa làm gì ở hồ sơ này" contradicts the history's "DW1 đọc và kiểm tra PO" when no model step ran; case history shows the raw "(accepted)" code; at 390 two card titles are cut by their extras; back edges remain dense.
    - **C.** The DW1 bar says "hết thư" only when done = total; otherwise "DW1 đang chờ: còn N thư chưa xử lý" (`sales-frame.tsx` `headline()`).
    - **D.** The bar's mailbox resource is published by `SalesFrameProvider` (`progress`); the inbox's "DW xử lý" / "DW xử lý tất cả" reload it after the press, so the bar moves to "sắp đọc / đang đọc" at once and starts polling. Chosen over sharing one resource with the inbox page: the bar's read waits for the overview and the inbox's does not, and five tests render case pages with `sales.case.read` but no mailbox.
    - **E.** A `stale_case_version` refusal on "Ghi giá" reads the quote again and shows, per line, the price now saved (who, when) beside what is being typed, which stays in the form, with "Dùng giá của tôi" (records again on the saved version) and "Giữ giá hiện có" (takes the saved price into the form). Any other refusal is drawn as before (`quotes/[caseId]/pricing.tsx`).
    - **Gaps:** `not_opened` is "Chưa mở nguồn" (warn tone, its own icon; `VALUE_LOOK` is now keyed by every glossary state, so a new one fails the typecheck) and is the weakest state after "uncertain" on a line row. RFQ "Xác nhận" is disabled per `source_not_served` with "Mở nguồn trước khi xác nhận…" beside it, and the quote is read again when a source drawer closes while any value waits on one (the server stays the owner). The quote has "Phạm vi đã đọc: …" from `coverage` (no N/N; warning while a model-read value is unconfirmed, `statements.ts` `quoteCoverageStatement`). The order shows the cross-checker "N giá trị chưa ai mở nguồn (trước khi nhập Bravo)" by line, each opening its source, only when `unopened_values` is non-empty (`orders/[caseId]/unopened-values.tsx`). On both case pages "Hành trình hồ sơ", "DW1 đã làm gì" and the replies moved below the flags, lines, files and changes (gap 3).
    - **Not done, on purpose:** `not_opened` regions are not added to `expectedRegions`: the server's `required_regions` owns which pages prepare and cross-check need, and a stricter copy in the browser would disable buttons the server allows.
    - **Process map:** new `_lib/process-geometry.ts` places a lane from `layoutLane`'s ranks, naming no status: columns wrap into bands of at most 5 (order and quote: two bands each, about 1.5k px wide, zoom ≈0.9 at 1440); a move between neighbours runs through the gap with its words in the gap's middle; every other move runs on a lane of a channel, forward under its band, back (dashed) over it; each card leaves and is entered on its own trunk at the gap's sides, and lane words slide away from other moves' trunks. `process-flow.tsx` draws those polylines and label boxes, fits the lane on load and when measured heights change it (min fit zoom 0.6), and sizes the canvas to the fitted height. A test computes the boxes for the served order and quote lanes (least and taller card heights): no label over a card or another label, no segment through a card, everything inside the canvas. Rendered to an image once to look at (scratch): clean, but the order lane is about 1,230 px tall at zoom 1, so at 1440 the page scrolls vertically past the canvas.
    - **Browser-look list:** (a) "DW1 đã làm gì" says a step's calls and time once per (message, step), on its first entry, "… cho cả thư (N mục của bước này)" when it covers several; grouped in the web, since the server's copy on every row is its documented contract. (b) The drawer splits "Điểm đạt đo trên bộ thử" from "Thực tế 7 ngày: DW1 tự xử lý X% số mục (a/b)" with "Đếm trên việc thật, không cùng thước với điểm đạt". (c) The drawer is a bottom sheet below `md`. (d) The feedback button joins the top bar's actions below `md` (web-ui.md); from `md` up it floats bottom-left as spec 003 US5 says, with room kept under the page. (e) `ProcessFlow` is loaded with `next/dynamic` (`ssr: false`), so a phone never downloads React Flow.
    - **Master data:** a reader reply that fails validation on an import now settles the snapshot `failed` with "không đọc được tệp: trình đọc tệp trả lời không khớp phiên bản…", audited by the lane as before, instead of raising for the outbox to retry (`catalog_imports.py` `_unread`, as `rule_drafts._unopened`).
    - **e2e updated, not run:** `enduser-race.spec.ts` C, D, E lose `test.fail` and assert the correct behaviour (C: the "đang chờ: còn N" headline; D: the bar without a reload; E: 0,689 beside "bạn đang nhập: 0,74", the typed value kept, both buttons); test 4 no longer reloads. `sales-demo.spec.ts` 10's headline regex takes "đang chờ: còn".
    - **Checked:** see web-ui.md 2026-10-24 for the web checks and mutations. Python: ruff, ruff format, mypy (682 files) clean; dw_sales unit + worker catalog consumer passed (about 1,940); the new import test, mutated twice (the `except` narrowed; the reason worded without the reader's sentence), each red, restored.
- 2026-10-24, defects A and B and audit UI gaps 1, 2, 4 and 5 (2026-10-21 entries below), server half. Committed 2026-10-24; the web half is the entry above.
    - **A.** A route's unhandled error is caught by `dw_api/middleware/unexpected_error.py`, the innermost middleware, so the 500 (same body: `code`, `message`, `request_id`) passes back through request-id and CORS. The `Exception` handler stays for an error a middleware raises; both render `exception_handlers.internal_error_response`. `test_cors.py`: allowed origin gets `access-control-allow-origin` on a 500, another origin does not.
    - **B.** A reader reply, or its result, that fails this process's wire models raises `ReaderMismatchError` (`DomainError`, 422, `reason_code: reader_version_mismatch`, logged by field location and error type, never a value) instead of a `ValidationError` 500 or a retried 503. A template draft then settles `failed` with "không mở được tệp mẫu: trình đọc tệp trả lời không khớp phiên bản…", audited as before, not retried.
    - **Gap 1.** A prepared value is `confirmed` only where its preparer was served its page or sheet (same file sha256) before `prepared_at`; otherwise the new value state `not_opened` (CONTEXT.md "Value states").
    - **Gap 2.** `QuoteFindingView.source_not_served`: the flagged values still to confirm whose source this caller has not opened at this version. It is the same fact the 409 uses (`source.value_unserved`).
    - **Gap 4.** `QuoteCaseView.coverage` (`QuoteCase.coverage`): lines read, regions ("page N", sheet, `message_text`), values a model read and how many are confirmed, findings. No "N/N": a request's reader counts no printed rows.
    - **Gap 5.** `OrderCaseView.unopened_values` lists `{field, line_no}` values whose page or sheet nobody was served before Bravo was recorded. Only a holder of `sales.order.cross_check` gets the list; everyone else gets null.
    - **Read from** `SourceServedPort.servings` (every serving of one case), no migration (the existing index leads with the case id).
    - **Web owed:** draw `not_opened`, disable "Xác nhận" per `source_not_served` with a reason, a quote coverage statement, show `unopened_values` to the cross-checker, and include `not_opened` in the regions `expectedRegions` asks the preparer to open, if wanted.
    - **Same shape, fixed in the entry above:** a master-data import (`CatalogParsing`) whose table reply mismatches raises the same `DomainError`; it is not caught there, so the outbox retries it until `max_attempts`.

- 2026-10-23, "Quy trình DW1" slices 2+3, web half (React Flow decided by Đạt the same day, CLAUDE.md "Web UI"). Committed 2026-10-24 with slices 2 and 3.
    - **n8n look (2026-10-24, Đạt; uncommitted):** each status is a compact tile (icon for whose turn: robot DW1, person, flag done; name; step codes; one AI line "AI bật · đạt / AI bật · chưa đạt / AI tắt", `AI_STATE_SHORT`) with visible handles where lines attach; whose turn, settings, ways back and exits moved to a popover on hover and keyboard focus (Esc closes; describes the link) and stay whole in the drawer. Lines keep `process-geometry.ts`'s routes, drawn with rounded bends and arrowheads, words in pills, back moves dashed; dotted background, minimap, horizontal controls in a strip under the lane. Tiles 168×≥88 (measured 90–122), gaps 148. Phone list unchanged. Checks in web-ui.md 2026-10-24 "n8n look".
    - **Calm re-cut (2026-10-24, Đạt: "đơn giản, sạch như n8n"; uncommitted):** the canvas draws the **main path** in one row, left to right, never wrapped (pans; opens at zoom 0.85 from its start; "Xem cả quy trình" fits all). Main path = the longest run of forward moves from the first status that never enters a **detour** (a status whose every way on goes back or out); a tie goes to the API's order (`process-graph.ts` `main`, tested and mutation-checked). Every other status sits on a row below: under the mean column of the row's statuses that move on to it (a detour hangs under where it starts), or one column past the last status that reaches it ("Đã đóng", "Từ chối báo giá"). Forward moves only by default: neighbours straight through the gap, a skip arched over the row, a branch down through the corridor. Switch "Hiện đường quay lại" (`?back=1`, replaced not pushed) adds the ways back (dashed arches over the row; from the row below, up through the corridor) and the exits (dashed, down the gap onto one rail per final status, "Đóng hồ sơ" once). Pills carry only the action; a guarded move gets one lock (antd `Button`, accessible name and `Tooltip` "Điều kiện: …"), guards whole in the drawer and the popover. Order lane: 7 on the row (Đã nhận → Đã xác nhận), Chờ khách sửa PO, Xem thay đổi PO and Đã đóng below; quote: 10 on the row, Thảo luận spec với khách, Bị trả lại định giá and Từ chối báo giá below. Checks in web-ui.md "Calm re-cut".
    - **Open from the browser look (2026-10-24):** ~~at 1440 the order map shows half its 10 states and back edges cross card labels~~ (closed by the calm re-cut: one row that pans, the ways back behind a switch, labels and lines tested clear); "DW1 đã làm gì" repeats a step's whole-mail timing on every line entry; "Điểm đạt" beside "Tự động 7 ngày qua" invites a false comparison (wording pinned in `rules-process.test.tsx`); the drawer opens from the right on phones where ui-quality §9 asks for a bottom sheet; the feedback button covers the O6 chip at 320/390; React Flow is not lazy-loaded, so phones download ~56 kB gz they never draw.
    - **`/sales/rules/process`:** on `lg` and up each lane is a React Flow canvas (`_components/process-flow.tsx`, the one file allowed `@xyflow/react` 12.12.0): cards on the rank columns of `process-graph.ts`, forward moves as arrows, moves back as dashed arches (over the first row, else under), every drawn move labelled with its action (`EDGE_ACTION`) and guard tags (`EDGE_GUARD`), aria-labelled with who takes it; exits into a final status stay words on it. Zoom/fit controls in Vietnamese, wheel scrolls the page, cards are real links (Tab, Enter, new tab), `?node=`/Back/focus return as slice 1. Each card says its model steps' state ("AI bật · đạt", "AI bật · chưa đạt — người làm", "AI tắt"). Below `lg` the list as before (ways back written). The drawer adds "AI ở bước này" (switch, bar, latest measurement or "Chưa đo", effective, 7-day share or "chưa có dữ liệu"; absent when the server sends no model steps), "Dữ liệu bước này dùng" (master-data tabs, Mẫu PO) and "Ai làm, ai duyệt" (roles/permission sets as served; `/admin` link for `platform.members.write`).
    - **Case pages:** "DW1 đã làm gì" under "Hành trình hồ sơ" on orders and quotes (`_components/case-activity.tsx`): per entry the step, result (Đã chấp nhận / Chuyển cho người / Model không trả lời), reason, values read with "Xem nguồn" opening the existing source drawer at the anchor, who took it over, model · prompt · time · calls.
    - **`/sales/activity` "Hoạt động DW1":** nav under Quản lý, `anyScope` overview.read or rules.propose (ScopeGate takes any-of); 7/30 days and lane in the URL; per step handled / automatic (+ share) / to a person / no answer / p50·p95 / top reasons; a count links to `/sales/orders|quotes?tab=all&…` with the server's filter once a lane is chosen (over both lanes a count is one number for two lists, so no link); a per-day table under each row. The order and quote lists read those params, pass them to the API and show "Lọc theo hoạt động DW1: …" with Xóa.
    - **Words:** `labels.ts` `EDGE_ACTION`, `EDGE_GUARD`, `MOVE_ACTOR`, `AI_STATE`, `ACTIVITY_*`; reason codes through `activity.ts` `reasonLabel` (exact tables, then `<field>_not_found|repeated|unparsed`, then a hand-off's field); `activity-labels.test.ts` holds every closed set to the OpenAPI snapshot and every reason code it finds in `dw_sales` sources (each pattern must still find codes).
    - **Checked:** see web-ui.md 2026-10-23 (tsc, lint, prettier, full vitest, mutations). **Run 2026-10-24:** e2e including `enduser-nav.spec.ts` 10 and 11a, all green; looked at in the browser (findings under "Open from the browser look").
- 2026-10-23, "Quy trình DW1" slice 3, AI activity ("DW1 đã làm gì"), server half, and the integration of slices 2–3. Committed 2026-10-24.
    - **Built (slice 3):**
        - **Rows:** `sales.step_outcomes` (`4bca401bcb3a`, after `2d97d03c937a`): one row per item a model step handled (a line for descriptions, the message otherwise), written by `InboxProcessing` in the transaction of the disposition and the case (`domain/activity.py` `outcomes_of`, derived from the stamps and the timed calls, `application/model_calls.py`). Ids, codes, counts and times only; CHECKs on step/result/lane and on the row saying what happened; tenant AND workspace RLS (offboarding shape); `dw_app` SELECT+INSERT, UPDATE/DELETE revoked; monthly partitions through `platform.ensure_time_partitions`, DEFAULT policed; FKs `ON DELETE CASCADE`.
        - **Reads:** `GET /sales/{orders|quotes}/{id}/activity` (`sales.case.read`; another workspace's case 404; a price field absent with its anchor without `sales.price.read`) and `GET /sales/activity` (`sales.overview.read` or `sales.rules.propose`; counts, top reasons, p50/p95, a series per local day; at most 31 days), each count carrying the case list filter it stands for.
        - **Retention:** `retention@1.9.0` gives `sales.step_outcomes` 365 days; the worker's `sales_step_outcomes_retention` lane drops whole expired months (`sales.drop_expired_step_outcomes`, SECURITY DEFINER, NULL drops nothing).
    - **Integration fixes (this session):**
        - **Live share on the process page:** each `models[]` entry carries `live_share` {handled, automatic, share|null, window_days 7}, read only after the order-rules gate, so it is absent (and not read) without `sales.price.read`. The ports moved to `application/activity_ports.py` (the activity service imports the process page; the reverse import was a cycle).
        - **No silent skip:** `step_activity` is a required member of `SalesUnitOfWork`; `record_outcomes` and `StepActivityUnitOfWork` are gone; the evals' `MemoryStore` keeps the rows per transaction (refusing a second write of a row) and reads them (`StepActivityReadPort`).
        - **Demo regression (slice 2):** `make demo-reset` installs `sales_order_rules@1.5.3` (`data/policies/no_model/`): 1.5.2 with all six steps off, every other rule the same (`test_order_rules.py` holds them equal), so the NOC/ESF hold and the tenant's price rule are back. 1.5.2 stays for the unit tests, evals and the API integration suite (over stand-in measurements). No measurement is seeded. demo.md, ADR 0005's addendum, the mock README and e2e 2b/11 comments updated.
        - **Drill-down:** `GET /sales/orders` and `/sales/quotes` take `step, handled_by, result, reason_code, lane, from, to` (a count's `ActivityFilter`, held equal by a test), checked after `sales.case.read`; half a filter, the other lane or more than 31 days is 422. Resolved through `sales.step_outcomes` under RLS (`StepRowFilter.matches` is the definition; the SQL is held to it), carried by the new `ix_step_outcomes_tenant_id_workspace_id_step_occurred_at` (added to `4bca401bcb3a`, uncommitted).
        - **Price leak, real:** the quote case view served the printed target price's anchor (its `quote` is the printed words) to a caller without `sales.price.read`, reachable today by FPT support (`sales.case_support`). The anchor is now absent; the amount stays marked hidden. The API suite's price search now knows the requests' target prices, so the support walks would have caught it.
    - **Decision Đạt owes:** the retention term of `sales.step_outcomes` (365 days in `retention@1.9.0`, proposed by the agent, not decided).
    - **Gap:** a message whose intent read had no usable answer inside `unread_retry_hours` stays not yet processed and writes nothing, so its retried calls leave no row: the activity page undercounts `model_unavailable` for `message_intent` until the retry ends in a disposition.
    - **Run 2026-10-24 (Docker on for the run, then off):** integration dw_sales 191 (3 skipped: no clamd), dw_platform 333, apps/api 162, all passed; e2e platform-pages 3, enduser-nav 13, enduser-data 6, enduser-forms 12, enduser-race 7 (C, D, E expected failures), sales-demo 13 (2 skipped, no model server). The first run failed every insert into `sales.step_outcomes`: the migration's `^[!-~]{1,512}$` CHECK exceeds PostgreSQL's 255 repetition cap (second time, failure-modes #4); fixed with `char_length`, with a test at the 512 bound. Fixed with it: three tests that compared the wrong way (stringified `details`, a CHECK named by the first violated constraint, a Decimal served as "0.65"), the stale `platform-pages.spec.ts:110`, enduser-nav test 10 accepting the empty activity state, and the AI section's layout below `sm`.
- 2026-10-23, a model step earns its switch (failure-mode #1 fixed; dw_sales ADR 0005, addendum of 2026-10-23, design approved by Đạt). Committed 2026-10-24.
    - **Built:**
        - **One owner for the bars:** `application/model_readiness.py` `BARS`, per `ModelStep` (domain, the six `model_assist` switches): bar, metric path in the golden grader's details, prompt, dataset, grader. The six eval modules read it (`bar_verdict`); `PROPOSED_BAR` is gone.
        - **Store:** `sales.model_step_measurements` (`2d97d03c937a`, after `e8192ed5cc59`): tenant-wide RLS (ENABLE+FORCE, the `rule_versions` shape), CHECKs on step, formats, 0..1, "a pass meets its bar"; `dw_app` SELECT+INSERT, UPDATE/DELETE revoked; not partitioned (a row per attested step).
        - **Writer:** `run_evals.py --live <profile> --attest --tenant <uuid> --workspace <uuid>`: lane `sales_model_attest` (`system:sales_model_attest`, audit in the same transaction), as dw_app under the tenant's RLS; refuses a BYPASSRLS role; records nothing when the run read nothing; passes only if the golden verdict and every case passed.
        - **Enforced:** `ModelStepGatePort.allows` before every model call (intent, reply, hand-off, layout pre-fill, descriptions, RFQ): on AND latest measurement for the current model (profile route, per tenant) and prompt version passed at today's bar; else the step runs as if off and logs why; unreadable = not ready. A version that turns a step on (on in it, off in force) gets 409 `model_bar_unmet` at propose and at decision; a settlement that finds it no longer ready records it rejected with why. Off, or kept on, is never refused.
        - **Process page:** per step `models` (switch, bar, metric, model, prompt, latest, effective; absent without `sales.price.read`), `uses` (`STEP_USES`), `actors` (`STEP_SCOPES` x the platform role/permission-set catalog via `RoleCatalogPort`); edges carry `action`, `actor`, `guards` (`EDGES`, held to `order_moves`/`quote_moves` by a test). `LockReason.MODEL_BAR_UNCHECKED` became `MODEL_BAR` with new words.
        - **Demo:** no measurement seeded. This first left tenant-alpha on the platform's rules after `make demo-reset` (1.5.2 refused), dropping its own rules; fixed the same day by 1.5.3 (below). The API integration suite seeds stand-ins through the lane's write path (`seed_test_measurements`) and keeps 1.5.2.
    - **Checked (2026-10-23):** ruff, ruff format, mypy (673 files), lint-imports (12 kept), verify_architecture, verify_invariants, contracts --check, release manifest --check, unit dw_sales 1915 + api/worker 619, eval smoke 10/10, web tsc/eslint/prettier and the 4 touched vitest files (33). Ten mutations, each red, each restored.
    - **Run 2026-10-24, passed:** integration `test_sales_model_measurements.py` (write+audit, RLS cross-tenant, no UPDATE/DELETE, CHECK, migration down/up), `test_sales_schema.py`, `test_privileges.py`, `test_rls_coverage.py`, and the API suite (`test_sales_api_rules.py` new 409 and process-page tests; every model-step test now runs on seeded stand-ins). Still not run: `--attest` against a live model.
    - **Open:** a tenant's own prompt wording under the same version is not told apart; the RFQ measurement names only its own prompt.
- 2026-10-22, "Quy trình DW1" (`/sales/rules/process`), slice 1. Đạt asked for a config page that draws DW1's process as nodes and edges, where a click opens that step's numbers, not hardcoded; the structure stays fixed for now.
    - **Decided by Đạt:**
        - drawn with antd and inline SVG, no diagram library;
        - one open proposal per rule key, refused on the server;
        - the page is for `sales.rules.propose` holders only, as `/sales/rules` is.
    - **Built:**
        - **Graph:** `GET /sales/rules/process` serves it from the domain's own transition tables (`order_moves()`, `quote_moves()`), with no second copy on the web.
        - **Step settings:** `application/process_settings.py` maps every `StepId` to the rule paths it reads, plus lane-wide and process-wide groups.
        - **Locked paths:** model_assist, design_mailboxes, working_hours.time_zone and intake are served as locked, each with a `LockReason`.
        - **Never placed:** `NOT_ON_PAGE` and `BASELINE_ONLY` list, with a reason each, what the page never places.
        - **Price:** price-bearing keys are absent for a caller without `sales.price.read`.
        - **Editing:** the drawer reuses the rules editor, limited to the step's fields. It proposes the whole document through the same propose → approve path.
    - **Guard:** migration `e8192ed5cc59` adds `uq_rule_versions_one_proposed` on `(tenant_id, key) WHERE status = 'proposed'`.
        - The 409 names who proposed the waiting version and when.
        - The upgrade stops on a proposal that has no approval.
        - Settlement now rejects a version whose number the platform shipped before it was applied, so the key is not blocked forever.
    - **Checked:**
        - unit 3535, integration 51 (rules, access, schema), contracts, web vitest 514;
        - security, correctness and UI reviews, with their findings fixed;
        - mutations on the settlement fix, the Back guard, the disabled "Gửi duyệt" and focus return, each turning a test red.
        - **Not yet:** a Playwright run and a look on the Docker build.
    - **Open:**
        - A proposal records no base version, so a stale form can still undo an approved one; the editor now reloads after a 409 to reduce this. This is the other half of decision 2.
        - The 409 does not name the other workspace.
        - Settlement still audits as the decider, not the lane (ADR 0011).
        - The order lane is about 1830 px wide and scrolls inside its frame at 1440.
    - **Slice 2:** an edge table with Vietnamese action and guard labels, step titles, and copy and templates on steps.
    - **Slice 3:**
        - move the RFQ required fields and the 12-month screening look-back into rules;
        - fix the intake binding, which reads the platform file at build time (`assembly.py:192-193`), so a tenant's version is likely unread: failure-mode #1;
        - give the time zone one owner (`order_checks.py:64` against `sales_followups`).
- 2026-10-22, DW2 (Mua hàng) readiness, audited with no code changed:
    - `new_context.py --name purchasing` wires 15 seams and passed every scaffold-smoke gate. It was run once in a throwaway clone, since removed.
    - **Left to do by hand:**
        - migrations, roles and permission sets;
        - configs, prompts and the eval dataset;
        - all web seams (nav, approvals host, badges, roles, api-client);
        - the `purchasing.` approval prefix and its `.decided` handler;
        - demo data.
    - **What blocks reuse:** the reader sandbox and malware scan import `dw_sales` (`apps/reader`), as do the rules editor, master-data import, pipeline, my-work and worker pause.
    - **Before DW2 starts,** decide whether to lift these to the platform (ADR 0004 `dw_evidence`) and whether to port DW01 from `C:\Users\phung\dw` or write it anew. The "30–51 công" line above and the 2026-10-21 "reuse only the ideas" talk disagree.
    - **Drift found:**
        - several files still call delivery/CDO "DW2" (`spec.md`, `dw_sales/CONTEXT.md:284`, `process.py:37`, tickets 02/06/21/33/35);
        - `PolicyOverridePort` is read by nothing;
        - CLAUDE.md says `@dw/ui` owns the case workspace, but it lives in `app/sales`;
        - `Makefile:161` says 13 seams, the script says 15.
- 2026-10-22, model comparison on the home lab: nine configurations in the Excel in Downloads.
    - **Candidates:** Gemma 4 12B with thinking off is the small candidate (6/6 bars). Gemma 4 26B-A4B and Qwen3.6-35B-A3B are the 24 GB candidates.
    - **Ruled out:** Nemotron 3.5 30B-A3B (4/6) and MiMo 9B (5/6, 6 invented RFQ values).
    - **Decision:** the switch from Qwen3.5-9B is still decided on Proterial's server with real data. Before it, check Gemma 4 12B's licence and its thinking switch on Ollama.
- 2026-10-21, end-user browser tests and `make web-screens` (Đạt: "test kiểu end user thôi"):
    - **Five new specs** under `apps/web/e2e/`, black box through the UI, each resetting the demo itself and run serially (shared database):
        - `enduser-forms` 12: input validation, double submit, cancel, close, decline, return, reassign;
        - `enduser-data` 6: master-data import, rules editor diff, "Tạo từ tệp mẫu", layouts, approvals, tenant IT;
        - `enduser-nav` 11: pipeline filters in the URL, Back, case history, viewer forbidden, 320 px, reload, keyboard, offline;
        - `enduser-race` 4 scenarios + 3 known-defect tests: pricing conflict, NOC/ESF hold, pause/resume, the DW1 bar;
        - `case-screens`: case pages per persona at wide-1440 and phone-320 (`DW_SCREENS_SETUP=1`, then `DW_SCREENS=1`).
    - **The first run was blind to its own stack** (failure-modes #0): the reader container was built 2026-10-20, before `text_unseen`, so every Excel source answered 500. Rebuilt; the three markers that blamed it are gone. Rebuild the reader with the API after a change to `dw_sales` the reader imports.
    - **Open defects, each a `test.fail` test that reports when fixed:**
        - C. Right after a reset the DW1 bar says "đã xử lý hết thư" at 0/45 (`sales-frame.tsx` `headline()`).
        - D. After "DW xử lý tất cả" the bar does not refresh until reload (`useWorkerProgress` polls only once its own fetch saw work: one fact, two resources).
        - E. A pricing conflict shows "hồ sơ đã thay đổi" but not the price the other person saved (ui-quality §4 "conflict").
    - **Open defects with no e2e test** (no black-box way to provoke them on a healthy stack):
        - A. A 500 leaves without CORS headers (`exception_handlers.py` runs in `ServerErrorMiddleware`, outside `CORSMiddleware`), so the UI shows "Mất kết nối mạng".
        - B. A reader reply that fails validation becomes a retried `ReaderUnavailableError` (500; a template draft keeps "Đang đọc tệp") instead of a worded refusal.
    - **Not a defect:** a resent identical PO (M08) opens its own case with `duplicate_po`, closed as duplicate (`order_checks.check_history`, issue 02). The board could say "PO trùng" on the card.
    - **Possible defect, unconfirmed:** on a quote at "Đã nhận", opening "Đã lập YCBG" while "Soạn YCBG" is still running closes the dialog when the latter finishes (`quotes/[caseId]/actions.tsx` `finish()` → `setDialog(null)`).
    - **Baseline:**
        - `sales-demo` passes stage 1. Stage 2 times out: 45 mails at about 13 reads a minute take about 9.5 minutes against an 8-minute budget (environment, not app).
        - `platform-pages.spec.ts:110` is stale: "Quản trị nền tảng" moved into the account dropdown's header (92b155a).
    - **Visual review of the 304 screenshots**, not yet fixed:
        - the floating chat button covers the first column on most pages, desktop and phone;
        - pipeline cards are 160–230 px tall, with 23 in one column and nine empty columns. The "Việc của bạn: …" tag overflows the card; on a phone the first screenful is two empty columns;
        - the inbox table is wider than 1440 and its rows are 70–95 px tall;
        - at 320 px the DW1 bar wraps to six lines, Segmented tabs are cut, and identifiers are clipped;
        - 28 admin/platform shots are an HTTP 429 page (seven navigations in 5 s), and that page says "không kết nối được" in English detail instead of "đang bận".

- 2026-10-21, decisions and owed work from Đạt's review (no code):
    - **HIGH PRIORITY, owed; decide once DW1 runs on Proterial's server.** Raise 9B's accuracy with code around the model, never with keyword tables or prompt examples fitted to the eval. The audit found every refused description line was a word left out (16), a span not in the text (5) or one span used twice (2); `single_candidate_wrong` is 0, so a higher score means less manual work, not fewer wrong codes. In order:
        1. A targeted second call on exactly the words the checks named, then the same checks; a still-unexplained word still goes to a person.
        2. 1–3 lines per call instead of 10.
        3. Load the Bravo convert list, so a listed line needs no model.
        4. Catalog retrieval (bge-m3), only to suggest codes for a person to pick.

        Measure each as a new prompt version on the same datasets, plus fresh unseen lines.

    - **Not ReAct.** No model-driven tool loop for reading customer documents: ADR 0007 forbids tools on document-content turns (injection), the 9B is slow per call, and the code checks are what keep wrong codes at 0. A read-only ReAct/deepagents agent stays a fit for staff Q&A over system data (questions come from staff, not from customer files).
    - **UI gaps from the same audit, not yet fixed:**
        1. Prepare relabels every unflagged value "Đã kiểm" (`views.py` ~497-502), though nobody opened them, and the cross-checker then trusts them.
        2. "Xác nhận" on RFQ values can be pressed before the source is opened, and the server then answers 409.
        3. Flags sit below the history.
        4. The quote page has no coverage statement.
        5. Show the cross-checker which values nobody opened.
    - **Channels.** Portal first. Teams preferred over Zalo, through a Teams bot whose inbound goes Azure Bot → an Azure Function queue that the plant server polls outbound. No domain, certificate or inbound port is needed. Proterial's IT owes an Entra app registration, approval of the Teams app, an Azure subscription and outbound 443.
    - **Out of scope for now.** NOEC and ESF drafting (WIV-03-032 steps 4–6) wait for a survey; the contract wording should say so. CDO is not built (a later DW).
    - **Model.** Stay on Qwen3.5-9B. Candidates, measured on our eval sets before any switch: Qwen3.8-27B or Gemma 4 31B (24–48 GB), Gemma 4 12B (8 GB).
    - **Flaky test.** `rule-drafts.test.tsx` "uploads a template, polls…" failed once under the full parallel vitest run on a loaded machine and passed alone 11/11.

- 2026-10-21, "Tạo từ tệp mẫu", phase 1 (Bravo upload template only; the email, document and hand-off copy are phase 2):
    - **Flow.** In the rules editor, for `sales_bravo_upload`, "Tạo từ tệp mẫu" uploads the company's Excel template.
        - `POST /sales/rules/{key}/drafts` answers 202; `GET /sales/rules/drafts/{id}` reads the draft. Both need `sales.rules.propose`.
        - A key outside `rules.DRAFTABLE` is refused with 422, so are a non-.xlsx/.xls file and one over 2 MB. Another tenant or workspace gets 404.
        - The editor polls every 3 s, then opens the draft as start option `draft:<id>`. Values the machine filled carry the "Máy đọc" chip and "Đọc từ Sheet!C3" until edited. An Alert lists the template columns no field takes and why a mapping was refused.
        - The diff and "Gửi duyệt" are unchanged: `POST /rules/{key}/versions` is still the only write path for a version, and the head approves as before.
    - **Worker** (`sales.rule_draft.requested` → `RuleDrafting`, lane audit `system:sales_rule_drafts`): scans the file, opens it through the reader (`ClientSourceView`), takes the first visible sheet with a row of at least 4 visible text cells, and drops hidden rows, columns and same-colour text first.
        - The model is asked under `sales.bravo_template_mapping@1.0.0` through the one-call door: the new `WorkflowRuntime.one_call` carries the runner's own plan rule, and is passed only where an on-prem model is configured.
        - The call runs as the asker, resolved again now. Someone who lost `sales.rules.propose` gets `failed`.
        - Code accepts a mapping only when every header is exactly one visible cell, no column serves two fields, PO/line/item/quantity are named, columns keep the template's order and the result passes `BravoUploadLayout`.
        - Statuses: `ready`; `refused` (fields named); `unavailable` (model down, not configured, or plan day spent); `failed` (with the reason). The file's bytes are deleted once read.
        - refused and unavailable still open: the version in force with only the template's sheet name, columns not guessed, the template's headers offered as AutoComplete choices.
    - **Storage.** `42868d8c21c5`: `sales.rule_drafts` and `sales.rule_draft_files`, RLS ENABLE+FORCE in the workspace shape, CHECKs on status, key, document and error. `dw_app` holds no UPDATE on the files.
        - A request prunes the workspace's drafts older than 30 days, and so does the worker's sweep (review fixes).
        - Found by the CHECK on the first run: JSONB `None` is written as JSON `null` unless the column says `none_as_null`.
    - **Checked.**
        - Unit: `test_rule_drafts.py` 35, the worker consumer 2, the one-call door 1, routes 3.
        - Integration: `test_sales_rule_drafts.py` 5, plus schema, privileges and RLS coverage.
        - Eval `sales_rule_drafts@1.0.0`: 5/5 with full security coverage. The smoke scripts the right mapping (no live reading recorded yet). Whole smoke passes.
        - Web: `rule-drafts.test.tsx` 8, tsc, lint, prettier.
        - Mutations, each turning a test red: verbatim header match loosened; hidden-cell filter removed (2 unit tests and the injection eval); RLS removed from the migration (2 isolation tests); the asker's scope re-check removed; the service gate removed; the door given its own plan service; the "Máy đọc" chip kept after an edit.
    - **Review fixes (same day).**
        - Unseen text: the reader sets `SheetCell.text_unseen` (`excel.text_unseen`): font the colour of its fill, white on a cell with no solid fill (ARGB, theme 0 / lt1, indexed 1 or 9), or 2pt and smaller. The template's header row drops it, and so does `text_parts` (what a model reads of an attachment). White on a dark fill stays visible. New eval case `sales-rule-draft-sec-unseen-text` (grader `sales.rule_draft_unseen_text`).
        - Headers are compared NFC without surrounding spaces, and the document holds the cell's own text so. A header over 64 characters is refused as `header_too_long` with its cell; the 64 now has one owner, `artifact_content.UPLOAD_HEADER_MAX`.
        - Web: the poll stops on an error answer (shown in the editor's error) and gives up after 3 minutes with "DW1 chưa đọc xong tệp mẫu, hãy thử tải lại sau."; the upload button is offered again; an earlier draft stays a start option while a second template is read.
        - Lifecycle: the worker lane `sales_rule_drafts` (every 10 minutes) visits each workspace `sales.rule_draft_scopes_due` names (SECURITY DEFINER, migration `e8a1c3e8ed78`, EXECUTE to `dw_app` only) and, in that workspace's RLS, fails a draft still queued after 1 hour (`STALE_AFTER`, file dropped, lane audit) and drops drafts older than 30 days.
        - `test_live_lane.py` now lists `sales_rule_drafts@1.0.0` among the model steps (it was red since phase 1).
    - **Open.**
        - No live measurement on Qwen3.5-9B yet (`--live onprem` on the dataset).
        - A layout cannot hold a blank template column, so unmapped columns are only listed.
        - A version proposed from a draft does not record that it was machine-drafted (the approver sees the diff only).
        - Drafts are not listed: closing the drawer loses the link to one.
        - `KEPT_FOR` (30 days) and `STALE_AFTER` (1 hour) are code constants in `rule_drafts.py`, not terms of `retention@*.yaml`; the drop of an old draft is not audited (its request and outcome are).
        - A PO value white on no fill or 2pt is still read without a `RegionFlag` (`excel.flags` checks only `font_matches_fill`), and the source viewer's grid does not mark `text_unseen` cells.
        - `sales_rule_drafts@1.0.0` gained a case in place (unreleased, local commits only), so the manifest pins new checksums under the same version.
- 2026-10-21, contract acceptance row 3 made provable ("100% test cases
  that do not meet export-control conditions are held awaiting approval,
  never automatically confirmed"). The hold already existed: `OrderCase.confirm`
  refuses while `missing_noc_esf` is open, and only a holder of
  `sales.compliance.ack` accepts it, with a reason (mode `warn`, kept; Đạt).
  What changed: `missing_noc_esf` is `error` (blocking) in platform rules
  `sales_order_rules@1.6.0` and the demo tenant's `1.5.2` (replaces `1.5.1`,
  `make demo-reset` installs it), so the order reads "chặn" in the list and
  on the case; the order page shows "Đơn đang bị giữ: chờ PIC kiểm soát xuất
  khẩu xác nhận NOC/ESF." while the finding is open; the rules form says
  `warn` is "Giữ xác nhận cho tới khi PIC kiểm soát xuất khẩu chấp nhận".
  Evidence: `test_export_control_hold.py` walks every README scenario whose
  findings include `missing_noc_esf` (read from the table, today M03, M28,
  M35, M45) to the step before confirm through the real services: refused
  until accepted, then confirmed; the API test walks M03 to a 409 on
  `/confirm` with version and status unchanged, then 200 after acceptance; a
  revision re-opens the hold (`test_orders.py`). Mutations: confirm refusal
  deleted, `_compliance_finding` returning None, tenant severity `warning`,
  and the page's condition each turned a test red. Cases checked before keep
  their stamped `warning` severity; the hold applies to them all the same.
  Options left open, not decided: a second person for the export-control
  acceptance (Proterial's survey says the same Sales PIC does export control,
  so no separation now); moving the hold before the Bravo entry (Đạt: no);
  the denial list stays a screening date on the customer, not a screening
  DW1 runs. Review follow-up: the page and the confirm button read one
  helper, `exportControlHold` in `order-actions.ts` (`awaiting_ack` or
  `blocked_by_rule`, the case's stamped `block_confirmation`, which the page
  now names in the rule's words); the notice uses antd's own warning icon,
  not the padlock that means masked prices. Mutations: the helper ignoring
  `block_confirmation`, holding closed cases, and the page drawing one wording
  for both each turned `export-control-hold.test.tsx` red.

- 2026-10-21:
    - **IT proposes rules, the head approves** (decided by Đạt; dw_sales ADR 0003 addendum):
        - Permission set `sales_rules_editor` = `{sales.rules.propose}` (migration `59cf23d3a859`); the seed gives it to `dev|tam.ngo` (org_admin). `org_admin` itself still holds no `sales.*` scope.
        - Price keys fail closed: `PRICE_BEARING` = `sales_pricing`, `sales_quote_rules`, `sales_order_rules` (in `rules.py`, beside `OVERRIDABLE`) also asks for `sales.price.read`. Without it, `GET /rules` leaves those keys out entirely (in force, layers, platform, versions), and their schema, platform documents and proposals answer 403. The web draws only the keys it is given.
        - `sales_order_rules` is price-bearing since the review of 2026-10-21: it holds price policy (`price.relative_tolerance`, the LME rule, which ADR 0003 names confidential). So IT cannot read or propose the order rules; it proposes KPI, copy, the Bravo upload template, hand-offs and follow-ups. Failed closed; relaxing it is Đạt's call and one entry in `PRICE_BEARING`.
        - Non-waivable SoD rule `sod_sales_rules_approve_vs_member_admin` (`platform.members.write` vs `sales.rules.approve`). The insert trigger from `d82a60870baf` checks existing memberships.
        - Tests: `test_rules.py` (unit; also IT holding `approvals.decide` after self-granting `sales_quote_approver`: refused on its own version, and on another proposer's, whose stamped approval it is not even served, so not found), `test_sales_api_rules.py` (Tâm proposes `sales_bravo_upload`, his decision 403, Giang approves; 403 and nothing listed on the three price keys), `test_sales_api_access.py` (Tâm reaches exactly the four rules routes of `sales_bravo_upload`), `test_sales_api_prices.py` (the G2 walk also reads `/rules` and each listed key's schema and platform documents; it also seeds a tenant `sales_pricing@9.0.1` proposal whose `floor_margin` is the known price 0.6890; An's `/rules` shows it (control), so with `PRICE_BEARING` emptied Tâm's walk goes red, d16c6fa), `test_sales_roles.py`, `test_sales_personas.py`, `nav.test.ts`, `rules.test.tsx`.
        - Mutations: with the price check removed, the unit and API tests went red; with the SoD insert removed, `test_it_cannot_also_approve_rules` went red; with `sales_order_rules` taken out of `PRICE_BEARING`, the unit IT test and the API price-key test went red. Downgrade and upgrade round-trip clean.
        - **Owed by Đạt (noted, not fixed):** `admin_console.py` refuses only `platform.*` scopes on a permission-set grant, so tenant IT can already give itself `sales_quote_approver` (no price scope, so no SoD rule stops it). Whether IT may grant `sales_*` sets at all is Đạt's call. **Decided 2026-10-25 (Đạt):** yes, every business role and set, price included, never an administrative one; the members screen now offers the catalog's roles (`platform-runtime/member-sign-in-accounts/spec.md`).
    - **DW1 bar.** It names what DW1 does: reading "<subject>", N waiting, all done and waiting for new mail, or paused. Never a bare "đang chạy" (`worker-bar.test.tsx`).
    - **Contract.** Đạt asked how the contract's acceptance bars and hardware should read against the measured Qwen3.5-9B figures. The advice was given in the session and kept out of the repo, which is public:
        - define the test set and that routing to a person is not an error;
        - split digital and scanned POs;
        - every new PRV code confirmed by Sales (descriptions measure 71%);
        - Q&A only over agreed question types (not measured; Teams needs internet);
        - one shared server: L4 24 GB or a 32 GB card, 64 GB RAM, RAID1 NVMe, internal backup disks plus a daily off-machine copy.

- 2026-10-20, "does the AI follow the template?" (Đạt), answered from the code and checked:
    - **No rule document reaches a prompt.** All nine keys are applied by code: email, document and hand-off copy by `string.Template` / `str.format`, the Bravo file by the upload layout plus openpyxl, and thresholds read as numbers. The model only reads incoming mail (spans); code verifies the spans and fills the tenant's template.
    - **Config → output tests.** The existing ones cover emails and hand-offs. New: `test_a_bravo_upload_follows_the_tenants_own_template` checks sheet, columns, order and headers, and that a template missing PO/line/item/quantity is refused at validation.
    - **Live eval on the host's qwen3.5-9b-dw: `sales_handoff` PASS.**
        - 33 mails, 73 fields: 94.5% right, 0 invented.
        - By language: vi 100%, en 96.2%, ja 86.4%.
        - 12.1% go to a person.
        - Injection cases: nothing followed.
        - Latency: p50 22 s, max 154 s on the first load.
    - **Docker stack with the model.** `api` and `worker` point at the host's Ollama through an override kept outside the repo (scratchpad `compose.host-model.yml`); `make demo-reset`, then the inbox lane processed the mailbox with the model.
    - **UI (Đạt: banner too big, text still large, less scrolling).**
        - The DW1 bar is one line: state, who paused and why, the mail being read, done/total, queued, failed. It is polled every 5 s while busy; the explanation sits in an info icon.
        - Body text is 13px, small text pinned at 12px.
        - Page header: tighter, 16px title, 12px subtitle and breadcrumb.

- 2026-10-20, the rules editor made plainer (Đạt: "Biểu mẫu và JSON nâng
  cao nhìn phức tạp ... người cấu hình sẽ mệt"; the configurator is
  **Proterial's IT**):
    - **Step 1, done.**
        - `schema_version`, `policy_id` and `copy_id` are kept in the document but not drawn (`SYSTEM_FIELDS`).
        - The version's own fields (number, mock, note) come last under "Phiên bản" (`VERSION_FIELDS`).
        - The note starts empty for a new proposal and is labelled "Ghi chú thay đổi".
        - Template values carry Vietnamese names and a copy button (`PLACEHOLDER`).
        - The JSON tab stays for IT.
        - Tests: `rule-form.test.tsx` +2; a mutation drawing the system fields again turns one red.
    - **Step 2, decided, not built: "Tạo từ tệp mẫu".**
        - The rule keys covered: the Bravo upload template (from the Excel template's header row), and the email, document and hand-off copy (from a sample the company sends).
        - The file is read in `reader` and queued for the worker. The model proposes a version into the same form, every machine-read value is flagged, and the diff and approval stay as they are.
        - The price, KPI and follow-up rules get suggestions only.
        - It needs an eval with a prompt-injection case in the uploaded file.
    - **OCR.**
        - Templates are born-digital, so `reader` already extracts them without a model.
        - Scans use the Tesseract (vie) already in `reader`.
        - EasyOCR and docling were not added: PyTorch would grow the image by GBs and compete for the GPU with Ollama. Measure Tesseract on Proterial's real scans first; Japanese would need `tesseract-ocr-jpn`.
    - **Owed by Đạt.** IT configures, but `sales.rules.propose` sits on the Sales roles only (`tam.ngo`, tenant IT, holds no `sales.*` scope). Decide whether to grant IT a permission set with `rules.propose`, keeping approval with the Sales head.

- 2026-10-20, the pipeline (Đạt: "UI mà thành từng tab ... k thành 1 cái
  pipeline", then "làm thẳng luôn pipeline", each role its own view):
    - **Board.** `GET /sales/pipeline` (`application/pipeline.py`, `sales.case.read`, no support context):
        - one column per status in the enum's order, each with whose turn it is (`STATUS_BUCKETS`) and its WIV steps;
        - one card per case with its reference, assignee, when it entered its status (the follow-ups' `_entered`), due date and flags;
        - `my_action` is the caller's next step, read from `my_work`, so a role differs by reading, not by a second rule;
        - done cases show for 7 days, then are only counted.
    - **History.** `GET /sales/{orders,quotes}/{id}/history`: the case's events, oldest first (`OverviewReadPort.history`, SQL and in-memory). Another tenant's case answers 404.
    - **Web.**
        - `/sales/pipeline` and the home page (`/`) for anyone with `sales.case.read`: two lanes, "Tất cả / Việc của tôi", search;
        - the order and quote pages gain "Hành trình hồ sơ": the statuses the case passed through, and every event with who did it;
        - nav: "Pipeline hồ sơ" under "Hồ sơ".
    - **Denser theme** (`@dw/ui`): controls 28px, `sizeStep` 3, a 48px bar, 20px page titles, tighter page padding; text stays 14/12px.
    - **Checked.**
        - Integration: `test_sales_api_pipeline.py` 5/5, plus overview;
        - mutations: removing the history's existence check turns the cross-tenant test red (200 vs 404), and removing the "mine" filter turns its vitest red;
        - web: vitest 420, tsc.
    - **Open.**
        - Not looked at on a rendered page by anyone yet; `make web-screens` is owed for the pipeline.
        - Viewers (`sales_viewer`) still get the overview, not the board.
        - Production build in Docker (`make docker-up`) was started for Đạt to view at localhost:3300.

- 2026-10-19, local Docker, tests and the on-premises models (Đạt: "chạy
  test full ... chạy docker lên test"):
    - **Without Docker:** lint, mypy, import contracts, invariants, the manifest and the contracts all pass. Unit tests: 3430 pass. Web: 466/466 vitest, plus typecheck, lint and format.
    - **Integration.** One 2-hour run on a loaded machine gave 766 pass, 53 fail and 84 errors. Per file and per package, everything passes except two real defects:
        - `dw_app` held UPDATE on three append-only tables (tickets 41 and 42); fixed by `89bcd0d49ea6`.
        - The two Sales route walks lacked tickets 41's path parameters.
          The rest were load: Qdrant timing out while images built, docgen's toolchain check run right after its fork bomb, and `DW_DOCGEN_URL` defaulting to 8110 where this machine maps 38110.
    - **Live evals on `qwen3.5-9b-dw`.** Six datasets PASS:
        - RFQ 94.9%, with **one invented value**;
        - layout 97.7%;
        - reply 97.8%;
        - hand-off 94.5%;
        - intent 89.8%, **below** the 90% bar the agent proposed;
        - descriptions VI/EN 71.1%.
          The container's Ollama 0.34.4 matched the host's 0.40.4.
    - **The on-premises compose files ran for the first time,** in the `local` profile: rerank, bge-m3 and chat, each through the API's own builders. Findings are in `infra/onprem/README.md`.
    - **Scope.** Which DW1 feature Proterial's process asks for, which the platform requires, and which we added: `sales/dw1-scope.md`.
    - **`PUBLIC_REPO_DENYLIST`** is set: the GitHub secret, plus `DW_PUBLIC_REPO_DENYLIST` on Đạt's machine, from the Sales survey and the proposal decks. The list has no customer names yet, because no real Proterial data has arrived.

- 2026-10-19, ticket 41 built (Đạt's goal of 2026-10-18: master data is
  loaded by business users, not hard-coded): customers, items, convert list,
  quotations and LME are imported per list from Excel/CSV on
  `/sales/master-data`, read by the worker in the reader sandbox, previewed
  as a diff with rejected rows, submitted on a stamped `sales.catalog`
  approval the head decides on `/approvals`; an approved snapshot replaces
  the mock for that list (migration `511ef1b71dee`). Bravo orders and open
  YCBG stay on the mock until the ERP adapter. Owed on Docker: the
  integration tests and the migration round trip (ticket 41).

- 2026-10-15, batch merge (agent; Đạt: "còn task nào và ticket nào còn
  sót lại không làm luôn đi"): every open Sales, platform and CI item that
  needed no decision of Đạt's was taken up in eight batches, each reviewed
  and its findings fixed, and merged on `main` from `0bc1395` (`b2ea975` ..
  `57d3c20`). Two are partial (`web-ui.md`: the support routes'
  Idempotency-Key; offline on ten platform screens). Each ticket records its
  part; choices the agents made read "decided by the agent 2026-10-15 (Đạt:
  làm luôn)".
    - **Sales.** Processing's audit rows name the run (10); a pause whose
      notification fails still answers (05); My work offers `confirm` when
      no cross-check is needed (14); a correction re-checks the PO's
      history, the price lock reads the server, corrected values show as
      entered (15); the mailbox lane's channel, `service|` subjects refused
      at sign-in, DW1's account provisioned with every new tenant, its row
      in the job's transaction (16); KPI keys a closed set (37); a version
      shows its decider's reason, `/sales/rules` proposes (38); the inbox
      links an intent's PO to its case (31); the picker compares with what
      DW1 read (08); orders are due on their short-LT date (24); one file
      of a kind per version, orphans removed (06); a model-read quote value
      waits for its source to be served (29); rich-text fonts read, legacy
      RFQ values refused (20); the live lane fails when nothing was read
      (28); eval-only M92, `sales@1.3.0` (13 cases); refusals in
      Vietnamese by rule code; the walk visits a reply, the layouts page, a
      hand-off draft and a rule decision (step 11).
    - **Platform, web and CI.** In `platform-runtime.md`, `web-ui.md`,
      `ops-hardening.md` and `channels.md`. Migrations `1a8fd934194f`,
      `2dd12f5b9c88`, `358bfa9b231f`, `546a6a81e58c`, `2e0354b50d10`,
      `d82a60870baf`, `0d8f03566652`, `271bdb87af91`; re-chained at merge
      (`2dd12f5b9c88` on `1a8fd934194f`, `2e0354b50d10` on
      `546a6a81e58c`), one head `271bdb87af91`.
    - **Verified (no Docker).** Contracts, API types and the release
      manifest regenerated; ruff, mypy (637 files), lint-imports 12/12,
      verify_invariants, manifest `--check`, web typecheck, lint, format,
      416 vitest, eval smoke 9/9; the full unit suite green.
    - **Owed to CI/Docker.** Every integration test the batches wrote, the
      eight migrations' round trips and mutation runs (listed per ticket),
      the walk with its new steps, promtool, the pinned images with trivy,
      the worker image rebuild, the Đ-after-D collation on Postgres 16.15, a
      real Keycloak expiry, `make web-screens`. The walk is blocking since
      2026-10-15 (ticket 18: six consecutive green `sales-walk` jobs).
    - **CI on `9bbce15` (pushed before Đạt's "no pushes").** Green but for
      three: the artifacts' new unique keys did not lead with tenant and
      workspace; a lane test read DW1's account through sign-in, which ticket
      16 now refuses; the walk passed 13/13 and then setup-uv's cache prune
      waited on the still-running worker. Fixed locally in `fac68c8`, not
      pushed: they run again at the next push or on local Docker.
    - **Owed to Đạt.** The ClamAV bump's
      Actions setting (ticket 25); the `PUBLIC_REPO_DENYLIST` secret (ticket
      26); the Open items below dated 2026-10-15.

- 2026-10-15 (Đạt: "làm luôn mục 1–3, 5, 6"): `legacy_text_anchor` no
  longer hands a price's anchor to a viewer who may not see amounts (tickets
  20/22, `953086f`); the API integration price scan looks for VND prices
  and every printed grouping (ticket 34); offboarding exports and purges
  each row of a partitioned table once (platform, owed upstream); the plan
  statuses and `demo.md` brought up to date; and a race found on the way:
  the demo seed and the worker both carried out the seed's `sales.rules`
  decision, and the loser failed `make demo-reset` in CI run 38545009082
  (`9704778`: a settlement that loses the race finds the decision applied).

- 2026-10-14, Đạt's decisions (afternoon): dw_sales ADRs 0004 (with both
  amendments) and 0005 (with its addenda) **Accepted**; the bars of tickets
  29–33 kept as proposed; every released rules version kept readable
  (ticket 37); rule versions decided on the platform's approvals (ticket
  38); ticket 28 with thinking on measured: unusable on this card. Built by
  the agent:
    - **37.** The rule book holds every platform version the checkout ships
      (`TenantRuleBook.released`); a version written before a field of its
      schema existed reads it as the platform's current version has it
      (`read_over`), tenant versions included (the next required field
      would otherwise have stopped DW1 for every tenant with its own
      version). A stamp asks the tenant first. A file any release manifest
      pinned is never edited or deleted (test over `contracts/release`); the
      two deleted 1.0.0 files are restored byte for byte.
    - **38.** Proposing a version opens a run-less `sales.rules` approval
      (migration `218118b8f0e5`); `RuleDecisions` guards it, the worker
      carries out `sales.rules.decided` (`RuleSettlement`), `/approvals`
      decides it in place; the Sales decision route is gone, and the
      "no Sales route decides" test, which could not see a `/decision`
      suffix, now does. Integration tests rewritten, owed while Docker is
      down.

- 2026-10-14, CI on 1621cbc: every job green (integration incl. the
  processing queue, the reader image with LibreOffice and Tesseract, tickets
  35/36; container build and trivy; the DW1 browser walk in 13m38s) except
  the public-repo guard, which fails by design until Đạt creates the
  PUBLIC_REPO_DENYLIST secret (the repo has no secrets at all). The first
  CI run of tests written while Docker was down found a regex repetition
  over 255 in a CHECK, an unquoted .env.example value, OCR labels losing
  their diacritics (now matched without accents on OCR pages) and five
  stale tests. Still local-only after a reboot (WSL hung since 2026-10-13):
  measure_reader timings for ticket 27 and the support-access 03 walk.

- 2026-10-14, tickets 25 and 27 built, pending measurement (agent; Đạt
  decided "DW xử lý" asynchronous, the agent took the ticket's recommended
  reader container while he was away; "As built", Comments and "Post-reboot
  checks" in each ticket):
    - **25.** "DW xử lý" and "DW xử lý tất cả" answer 202 with a job per
      message (`sales.processing_jobs`, migration `0a78ca5e96d3`, parented
      on 36's `26a5276840ba`); the worker's `sales_processing` lane runs
      each as whoever asked, re-resolved and cut to `sales.inbox.process`,
      through `Dw1Runs.process` (quota, pause, key unchanged); the reaper
      settles a dead worker's job; the mailbox lane queues through the same
      door. Every file is read in the `reader` container (`apps/reader`,
      no network, one throwaway process per request under docgen's runner,
      reached over a Unix socket); the API imports no reader. The inbox
      shows each job's state and polls while any runs.
    - **27.** In that container: `.xls`→`.xlsx` and `.doc`→PDF by
      LibreOffice (fresh profile, macros disabled), anchors carrying both
      hashes and the PO its converter; a scanned page OCRed by Tesseract
      (`vie+eng`), every value flagged `ocr` (`value_uncertain`). A tool
      failure routes the message with the reason. No `.xls` is committed
      (the public-repo guard cannot read one); the scan fixture and its OCR
      truth are generated.
    - **Verified (no Docker).** ruff, mypy (627 files), lint-imports 12/12
      (the new "API imports no reader" contract included), verify_architecture,
      verify_invariants, release manifest and contracts current; unit 3,108
      passed, 3 skipped; eval smoke all PASS (`sales_legacy@1.0.0` 6/6); web
      typecheck, lint, 350 vitest, prettier. 36 mutations, all red (the
      reader's body cap first survived and got two tests).
    - **Owed after the reboot**: `scripts/measure_reader.py`, the image's
      size and socket, the full stack's "DW xử lý" (ticket 25 "Post-reboot
      checks" 1, 3 and 7) and ticket 27's macro fixture (ticket 27's checks
      after them). The image build, trivy (`dw-reader` included), the
      image suite, migration `0a78ca5e96d3`, the integration suites and the
      full profile's compose smoke ran green on CI (run 38545008947 on
      `99cb905`), and the walk with a worker on the Web E2E workflow (run
      38548179383 on `a89ca01`).

- 2026-10-14, tickets 35 and 36 triaged and done (agent, Đạt away, on his
  ask of 2026-10-14; committed in `8adbe08`; Triage, "As built", "Owed" in
  each ticket):
    - **35.** A split line is confirmed per schedule (decided by the agent:
      one date per schedule, the recommended default): `OrderLine` holds a
      date per delivery, the route takes `schedule_dates`, the draft
      (`sales_emails@1.2.0`) and the portal checklist list each schedule,
      the drawer asks per schedule. Migration `b2afb906fbf2` (`date[]`
      replaces the one-date column, backfilled).
    - **36.** Quote rules, pricing, e-mail and document copy, the Bravo
      upload template and the hand-off copy resolve per tenant through the
      rule book, ticket 19's routes unchanged (ADR 0004 option noted); a
      quote case's later steps read its stamped rules, files of one case
      version the copy the first stamped. Hand-off placeholders and e-mail
      subjects are validated before a tenant can propose them. Migration
      `26a5276840ba` (eight keys; the document check no longer passes a
      NULL comparison).
    - **Verified (no Docker).** ruff, mypy (619 files), lint-imports 12/12,
      verify_architecture, verify_invariants, release manifest and
      contracts current; unit 3,074 passed, 3 skipped (one collection error
      in ticket 25's worker test, in progress in parallel); eval smoke all
      PASS; web typecheck, lint, 346 vitest. 19 mutations, all red.
    - **Owed after the reboot.** The two migration round trips and their
      scratch-database mutations listed under "Owed" in tickets 35 and 36;
      their integration runs are green on CI (run 38545008947 on `99cb905`).

- 2026-10-13, CI on 399920d: 6 of 7 jobs green (unit, evals, frontend with
  vitest, integration, container build, scaffold-smoke). The public-repo
  guard fails by design until Đạt creates the PUBLIC_REPO_DENYLIST secret.
  The DW1 browser walk on CI passed on e97042b and failed on 399920d at step
  2: it pinned "DW xử lý tất cả (42)" while 44 were left after M44/M45;
  the click is now count-agnostic. Local integration and the support-access
  03 walk wait on a reboot (WSL hung at 22:01, needs admin).

- 2026-10-13, ticket 25 needs-info, 27 needs-info (agent, Đạt away; "As
  built" and Comments in each ticket):
    - **25, built.** Every attachment is scanned by ClamAV before anything
      reads it (`ScannedInbox` in `build_dw1`), then held to its name: an
      infected one routes its message `malware_detected` unread and audited
      (ids and signature), a scanner that cannot answer leaves it not yet
      processed (503 "chưa quét được, thử lại"), a renamed program or an
      encrypted Office file is refused unread; every reader call has a wall
      clock. Compose `clamav` (`clamav/clamav:1.5.4` by digest, own internal
      network `dw-scan`, read-only, no capabilities, 947 MiB resident, trivy
      0 HIGH/CRITICAL); EICAR caught by the real clamd; CI starts it.
      Migration `13c687788955`. `DW_SALES_MALWARE_SCAN=skip` for a host-run
      local API only (refused where a deployed process reads a mailbox).
    - **25, owed.** Acceptance 5, parsing in a sandbox: which one (docgen, or
      a reader container of its own) and whether "DW xử lý" may become
      asynchronous. The integration suites it touches were running when
      Docker's WSL VM died, and are owed.
    - **27.** Not started: it runs in 25's sandbox, and the measurements need
      Docker. `WslService` is stuck in StopPending; restarting it needs an
      administrator. Ollama was not touched.
- 2026-10-13, tickets 23 (review), 24 and 19 done (agent, Đạt away;
  committed in `399920d`; Comments and "As built" in each ticket):
    - **23.** The review found the end-to-end test asserting that no model
      was called, since 28-33 made DW1 call one; a new test runs M36's
      description reading on the real gateway and finds no prompt, answer or
      12-character window of a description in any span or log. And every
      span exported the text and stack trace of any exception crossing it,
      the SDK recording it a second time on its own: a span now records the
      type and a `DWError`'s message only (`dw_observability.otel`).
    - **24.** The overview's figures are SQL aggregates and the work list is
      a keyset page (`GET /my-work?limit&cursor`), behind `OverviewReadPort`;
      the old Python computation is the in-memory store's and the test's
      reference, held equal over the walked demo. Partial indexes on open
      work (migration `6d0252a87a6c`); measured on 50,000 cases: 51 rows
      read, 0.5 ms generic plan. The kernel cursor gained an optional leading
      `group` (the due date).
    - **19.** A tenant's own `sales_order_rules` and `sales_kpi` versions are
      proposed (PIC or head), approved (head, never the proposer) and
      resolved through `TenantOverlay`; a recheck reads the version its case
      stamped. `sales.rule_versions` (migration `57a241ea182b`, narrowed by
      tenant only), `/api/v1/sales/rules`. The demo tenant's `1.5.1` is
      proposed by An and approved by Giang through the service at
      `make demo-reset`; the API no longer reads the sample set's policies.
      The quote rules, pricing, copy and upload template: ticket 36.
    - **Owed.** Docker Desktop (WSL) stopped answering at 22:00 mid-run: the
      full Sales integration suite was not re-run after 19's last changes
      (ticket 19, "Owed"). Run since on CI, green on `99cb905` (run
      38545008947).
- 2026-10-13, ticket 34 done (agent, Đạt away; "As built" and Comments in
  the ticket): a PO line printed with no requested date (blank, or a dash)
  reads with none and raises `requested_date_missing` (ask the customer, or
  accept with the date to follow), in both readers and through an approved
  layout; an `.xlsx` and its PDF print in one mail are one PO read from the
  workbook, the print kept as a source and each value it shows differently
  `value_uncertain` (`print_differs`). Rules `sales_order_rules@1.5.0`, the
  demo tenant's `1.5.1` (replaces `1.4.1`), readers `@1.5.0`, migration
  `a459e2244a9c`, mock M44 and M45 (the mailbox is 45 messages). Found on the
  way: a PDF anchor's quote showed prices to a viewer without amounts (support
  and leadership); the order view now leaves a price's anchor out.
- 2026-10-13, ticket 21 done (agent, Đạt away; built in `dd5ef1d`, verified,
  finished and reviewed; "As built" and Comments in the ticket): a PO line
  keeps every delivery schedule from the reader to the upload file (a row per
  schedule, `sales_bravo_upload@1.1.0`), the cross-check sheet and the order
  page. Review added a PostgreSQL round trip (M34) and found a cubic
  backtracking pattern on customer text in the schedule list (75 s on one
  4,000-character entry) and a quadratic one in the PDF total; both are linear
  now, each with a test that goes red with the pattern back. Ticket 35
  (needs-triage): confirmation is one date per line, so a split line is
  confirmed as one delivery.
- 2026-10-13, tickets 32, 33 and 30 built (uncommitted; Đạt away, on his
  pre-authorisation; "As built" and Comments in each ticket):
    - **What.** A customer's reply is attached to its case by its thread
      headers (no model) and a local model reads what it says; the case
      suggests the step, Sales takes it (32). A delivery change, complaint
      or sample request becomes a hand-off draft code writes from the
      customer's located words, for Sales to send to PC or QA (33). A new
      customer's PO form is mapped once on an onboarding screen, a model may
      pre-fill the labels, the head approves it on a platform approval, and
      later POs are read with no model, the first 3 flagged value by value
      (30).
    - **Where it is on.** `sales_order_rules@1.4.0` ships `reply_intent`,
      `request_handoff` and `layout_proposal` off; the demo tenant's `1.4.1`
      has all six model steps on.
    - **Measured** (Qwen3.5-9B, thinking off): replies 95.7% kind accuracy,
      0 false accepts, p50 3.6 s; hand-offs 94.5% of fields, 0 invented,
      p50 5.0 s; layouts 98.2% of fields, 11 of 12 pre-fills kept, 0 kept
      wrong, p50 9.4 s. Every proposed bar holds.
    - **Live portal flow.** M41 → `settle_spec` proposed and taken; M42 →
      `resume_review`, both findings still asked; M11/M17/M31/M40 drafts to
      PC/QA; M43 pre-filled, approved by Giang on the platform approval,
      read with every value flagged; the 43-message mailbox, 0 unprocessed.
    - **Shipped with it.** Migrations `aeb7a7241d75` (`messages.case_reply`),
      `a970a6cbac29` (`messages.handoff`), `63242ec52c4b`
      (`sales.po_layouts`, `messages.layout_prefill`, `sales.layout.approve`
      for `sales_head`); mock M41-M43 (43 messages); prompts
      `reply_intent`, `request_handoff`, `po_layout_proposal` `@1.0.0`;
      copy `sales_handoffs@1.0.0`; evals `sales_reply`, `sales_handoff`,
      `sales_layout` `@1.0.0`; a worker handler for `sales.layout.decided`;
      dw_sales ADR 0004 amendment (a checker's decision with no run).
    - **Next.** Ticket 34 (blank requested date, an .xlsx and its PDF
      print), then 21/23, 24, 25, 27, 19.
- 2026-10-13, tickets 29 and 31 built (uncommitted; Đạt away, on his
  pre-authorisation; "As built" and Comments in each ticket):
    - **What.** A local model reads a request for quotation no reader reads
      (mail body, a PDF's text, the customer's own sheet; ticket 29) and the
      intent of a message no reader accepted (ticket 31). A readable
      document now decides its message's kind first, for every tenant.
    - **Where it is on.** `sales_order_rules@1.3.0` ships `rfq_extraction`
      and `message_intent` off; the demo tenant's `1.3.1` has all three
      model steps on.
    - **Rules.** dw_sales ADR 0005 unchanged; its addendum records how both
      steps apply it (field confusion flagged, a kind is not a route, the
      newest part only, bounded input, one switch block).
    - **Measured.** RFQ: 94.6% VI/EN values in the right field (bar 85%),
      JA 96.0%, p50 15 s per request. Intent: 90.9% kind accuracy (bar 90%)
      against 27.3% for the keyword tables, p50 2.7 s.
    - **Live portal flow.** 40 messages in 149.7 s; M37-M39 quote cases with
      every value flagged; M40 `delivery_change` naming M35's PO; a value
      confirmed through the API.
    - **Shipped with it.** Migration `dab4fd83b8cb` (messages stamp the
      reading; `reply_to_case`), mock M37-M40 (the mailbox is 40 messages),
      evals `sales_rfq@1.0.0` and `sales_intent@1.0.0`, prompts
      `rfq_extraction@1.0.0` and `message_intent@1.0.0`.
    - **Next.** Ticket 30, then 32 and 33.
- 2026-10-13, ticket 28 built (uncommitted; Đạt away, on his
  pre-authorisation; "As built" in the ticket):
    - **What.** DW1 reads an item description its own vocabulary does not
      through the local Qwen3.5-9B (provider `onprem`, Ollama, thinking off)
      for a tenant whose `sales_order_rules.model_assist` turns it on.
    - **Where it is on.** The platform's 1.2.0 ships it off; the demo
      tenant's own 1.2.1 has it on.
    - **Rules.** dw_sales ADR 0005 (Proposed) replaces spec decision 13's "no
      model": typed output that code verifies (spans found once, numbers
      parsed from their span, coverage), labels flagged, never exact, and
      degrading to a person.
    - **Measured.** VI/EN gold code among the candidates 71.1% (bar 70%,
      Đạt 2026-10-15), JA 50.0%; 0 wrong single candidates, 0 injection
      effects; about 77 s per 10-line call.
    - **Against an API model (2026-10-14).** The same set on `luna`
      (gpt-5.6-luna; a throwaway copy of the profile adding
      `max_input_tokens: 6000`, which `luna` does not declare for DW1's
      route): VI/EN 97.8%, JA 100%, 1 of 67 lines to a person, 0 wrong
      single candidates, 0 injection effects, p50 11.6 s per call (9 calls).
      The gap is the model, not the code: verification is the same.
    - **Thinking on (2026-10-14).** Qwen 9B with thinking on (a throwaway
      Ollama model at num_ctx 32768, 2,000 output tokens per line, 600 s
      timeout) on the GTX 1080: 189 minutes for the set, p50 808 s per
      10-line call, 5 of 9 calls failed (44 of 67 lines unavailable); of the
      23 lines answered, 1 read and 22 refused by code (9 lines left out of
      the answer, 11 text not covered). VI/EN 0%, 0 wrong candidates, 0
      injection effects. Thinking is not usable on this card; the context
      that thinking needs spilled part of the model off the GPU, so a 16 GB
      card would be faster, not measured. The live lane reported [PASS]
      with every call unavailable: it grades the guards, not the bar.
      Fixed 2026-10-15 (`b279cc2`, `6d837e0`): a live run fails when the
      model read nothing; a case's bar is reported, not enforced.
    - **Live portal flow.** The whole mailbox in 57.5 s; M36 lines 1 and 3
      suggested correctly and confirmable.
    - **Shipped with it.** Migration `a9977d62e09b`, mock `M36` (the mailbox
      is 36 messages), eval `sales_descriptions@1.0.0`, and the live lane
      `run_evals.py --live onprem`.
    - **Next.** Ticket 29.
- Context `dw_sales` scaffolded with `scripts/new_context.py` (14 seams).
- Feature in progress: `sales/dw1-portal-demo/` — DW1 end to end on mock data
  behind real ports. Spec: `sales/dw1-portal-demo/spec.md`. Tickets 01–27 in
  `sales/dw1-portal-demo/issues/`.
- 2026-10-12, ticket 12 triaged: what needs nothing from Proterial became
  17 and 19–27 (rule overrides, legacy encodings, delivery schedules,
  support without prices, telemetry, SQL overview, ClamAV and worker
  parsing, public-repo guard, legacy Office and OCR), all ready-for-agent;
  12 keeps what waits on the requirements doc (needs-info). Đạt sent the
  requirements doc to Proterial (confirmed 2026-10-12). Order agreed with Đạt:
  13 → 14 → 17, then 19–27.
- 2026-10-12, ticket 23 built (uncommitted; "As built" in the ticket): no
  price, customer name or mail text reaches a span, a log line or an error.
  Sales spans go through one helper (`dw_sales.application.telemetry`) whose
  allowlist checks each key and its value's shape; DW1 emits
  `sales.message.processed` per message. The API's 422 for a request body no
  longer echoes `input` (platform-wide). Tested end to end: three fixture
  POs (one walked to `confirmed`), real OTel exporter, root logs, five
  refusals, 43 document values searched for. Left for the platform: a span
  records `str(exc)` of any exception that crosses it.
- 2026-10-12, ticket 22 built (uncommitted; "As built" in the ticket): FPT
  support reads the overview and the order and quote lists and details
  under a customer's grant, every amount hidden; every other Sales route
  refuses a support context. Set `sales.case_support` =
  `{sales.overview.read, sales.case.read}` for the workspace; `sales_head`
  alone holds `support.grant` (migration `7c8ba908575f`). Found on the way:
  the platform's route-table test saw no included router (FastAPI 0.141),
  fixed. Open for Đạt: whether platform operators count as FPT identities
  (`dev|chi.le` holds `platform_admin` in the demo tenant). Adversarially
  reviewed 2026-10-12: support is the first caller with `sales.case.read`
  and no `sales.price.read`, so the leak search now walks every case the
  inbox opens (it caught a mutation the two-case walk missed); a revocation
  is tested end to end; the route walker is FastAPI's `iter_route_contexts`,
  which also sees a dependency added at `include_router`.
- 2026-10-12, ticket 20 built (uncommitted; "As built" in the ticket): a PO
  value typed in a TCVN3/VNI font (`.VnTime`, `VNI-Times`) is detected by the
  readers. It raises a blocking PO-level `legacy_encoding` whose only decision
  is `ask_customer` (the Unicode re-send arrives as a revision), and no
  attribute is matched on that text. Migration `0d7fd21052a4`,
  `sales_order_rules@1.1.0`, `sales_emails@1.1.0`, readers `@1.2.0`, fixture
  `M33` (the mailbox is 33 messages), eval `sales@1.1.0` 11/11. Reviewed the
  same day. Two guards had no test that could fail, and each now has one:
  the PDF page fallback, and a typed `value_uncertain` value over legacy
  text, which must not clear the finding. The review also found a problem
  that predates this ticket and belongs to ticket 22. A PDF anchor's `quote`
  is the printed text, so for a price field it shows the price to a viewer
  whose amounts are hidden.
- 2026-10-12, ticket 15 built (uncommitted; "As built" in the ticket): a
  `value_uncertain` is corrected per field with a typed value
  (`POST /orders/{id}/findings/{key}/corrections`), kept beside the value as
  read (migration `33f444c15062`), and the upload file, the cross-check sheet
  (`sales_documents@1.1.0`) and the drafts print the entered value; the
  corrected line's checks (header: PO-level checks) run again and a finding
  whose values did not change keeps its decision. Reviewed the same day: a
  revised order's change list now carries the corrected value, and the
  findings card offers the sheet note only when the case would take it.
- 2026-10-12, tickets 13, 14 and 17 built (uncommitted; each ticket's "As
  built" has the detail and its mutation checks):
    - 13: the quote page reads the artifact list once (`useCaseArtifacts`)
      and hands it to the files panel and the approval panel, so a rendered
      preview shows without a reload; the walk's `page.reload()` is gone
      (the walk itself was not run then; it has passed on CI since `e97042b`);
    - 14: a cross-check decision the run cannot apply is recorded on the
      order (`unapplied_decision`, migration `58184771c541`) and in the
      audit (run, approval, reason code), and "Gửi kiểm chéo lại"
      (`POST /orders/{id}/resend-cross-check`; the Bravo recorder, or the
      head with the new `sales.order.resend_cross_check`) raises a new
      approval; `bravo-entry` on an order already in Bravo no longer
      withdraws its pending cross-check. The platform's resume payload now
      names the approval (`approval_id`), and its in-memory run store has
      `active_since`: both are platform code changed in this repo, owed
      upstream;
    - 17: the head reassigns a case (`PUT /orders|quotes/{id}/assignee`,
      `sales.case.assign`, migration `934101cde272`), eligibility from
      `ScopeHoldersPort.holding`, audit with old and new ids, the new
      assignee notified.
      Found while running the integration suites: `ck_approval_requests_sales_stamped`
      (`a64b918fc1f2`) lets a `sales.` approval with a NULL `required_scope`
      through, because `false OR NULL` is NULL and a NULL CHECK passes; its two
      tests fail (`test_sales_constraints.py`, `[sales.quote-None]`,
      `[sales.order.cross_check-None]`). **Closed 2026-10-12 by migration
      `d9e73228e7d7`**: the constraint, same name, now reads
      `coalesce(required_scope, '') LIKE 'sales.%'`; validated on ADD, so an
      unstamped Sales row already in the table stops the upgrade (measured on
      a scratch database: "violated by some row"); downgrade restores
      `a64b918fc1f2`'s definition. Both tests red before, green after.
- 2026-10-12, the gaps left in the demo flow became tickets 13–18, each
  checked against the code that day (the Open items below point at them):
    - 13 the quote approval panel sees a new preview without a reload
      (ready-for-agent);
    - 14 an order whose cross-check decision failed to apply can be
      cross-checked again (ready-for-agent; wider than the race noted under
      ticket 10: any version bump between decide and apply strands it);
    - 15 `value_uncertain` corrected per field, and the upload file prints the
      correction (done 2026-10-12, uncommitted, reviewed; re-run the corrected line's checks, plus the total check);
    - 16 a worker lane processes new mail (done 2026-10-12, uncommitted:
      the worker's `sales_inbox` lane acts as DW1's service account per
      tenant, role `sales_dw1` = `sales.inbox.process` only, migration
      `af154486381e`, resolved by `SqlMembershipLookup.find_service_access`
      and cut to that one scope; one run per message, oldest first; the
      message log's (workspace, message_id) key refuses a second disposition
      on a case; pause state only; 60 s tick; the lane audits as
      `system:sales_inbox`. DW1 is built for both processes by
      `dw_sales.adapters.assembly.build_dw1`. The lane is on by default;
      `DW_WORKER_SALES_INBOX_LANE=false` for the walk-through by button,
      which demo.md now says. Reviewed 2026-10-12: the lane re-reads each
      message and the pause just before its run, so it never re-processes
      one a person routed mid-tick nor spends a run a pause would refuse;
      the worker image is scanned by CI's trivy since);
    - 17 the head reassigns a case (G22, moved out of 12; ready-for-agent);
    - 18 CI runs vitest and the DW1 walk (ready-for-agent 2026-10-12: vitest on
      every push; the walk on `main` and nightly, blocking after three green
      runs in a row). Built and adversarially reviewed 2026-10-12, committed
      in `395dbf3`; the walk first passed on a runner on `e97042b`, and is
      blocking since 2026-10-15.
- Tickets 01 and 07 committed 2026-10-03; 01 follow-up (fixtures M13–M32,
  mock Bravo history, open YCBG list, snapshot as_of, one SourceAnchor) and
  02/03 reworked to the amended spec, adversarially reviewed and committed
  2026-10-05 (dw_sales 683 unit tests; import contracts 9 kept).
- 2026-10-03, conformance review done. The review itself stays outside git
  because it quotes Proterial's survey. The plan gets the mechanics right
  (reading, mapping, checks) but not the process:
    - WIV-03-012 steps 9–10 are missing: no cross-check by a second Sales
      member, no joint confirmation. One PIC can approve and confirm alone.
    - The revised-PO loop dead-ends: a correction request plus Rev.1 never
      yields an upload file.
    - The confirmation carries no delivery date, and the short-LT rule counts
      from the PO date, not the date the PO was received.
    - Quotation steps 2, 5, 6, 8, 9, 11 and 12 have no state or artifact.
    - Roles are three generic scopes, so the walk-through only works as
      platform_admin.
    - ADR 0008, 0009 and 0010 decisions are not followed, nor recorded as
      exceptions.
- 2026-10-03, spec and tickets amended per the review: the process map, the
  actor/role/scope table, maker/checker, price visibility, per-finding and
  per-message dispositions, check basis, the ADR 0009 source gate and the
  interim behaviour per open decision are in the spec. 02/03 are amendment
  tickets, 01 has a fixture follow-up, 11 seeds the personas, and 12 holds
  the production-only gaps. Context glossary and ADRs 0001–0003 are under
  `packages/python/dw_sales/`.
- 2026-10-03, a second pass checked the amendments against the survey and
  the requirements doc. It corrected three process facts: the short-LT
  rule uses the standard lead time; the PIC still compares the Bravo entry
  with the PO when recording the order number; NOC/ESF blocks confirmation,
  not preparation. The cross-checker must also differ from the Bravo
  recorder. The quotation approval matrix waits for Proterial (ticket 12).
- 2026-10-05, ticket 05 built (`3557de8`): 42 routes under
  `/api/v1/sales`, each on the verified access context, scope before the
  idempotency key, amounts left out by one mapper per resource, ids-only
  mutation answers. The items owed into 05 landed: the case carries every
  earlier maker and refuses the cross-check itself (409 "tách nhiệm"), quote
  cases stamp rules version and catalog `as_of` (the parser is the
  request's), one actor id type (principal uuid, migration `075dca5a6168`),
  audit rows in the same transaction, the Design mailbox in
  `sales_quote_rules@1.1.0`, and `price_floor_unknown` (fail closed, Đạt did
  not object). `sales_kpi@1.0.0` shipped. Details in the ticket's "As built".
- 2026-10-05, ticket 06 built (`2f737ca`): every artifact in the table
  rendered from the case by `POST /orders|quotes/{id}/artifacts`, listed by
  `GET .../artifacts`, stored under `{tenant}/{workspace}/sales/{case}/{id}`
  with template `id@version`, case version and sha256, downloaded only in its
  state and at the case's current version (409 `stale_artifact` after an
  edit). Copy `sales_emails@1.0.0`, `sales_documents@1.0.0` and policy
  `sales_bravo_upload@1.0.0` (MOCK) are pinned by the manifest. reportlab
  stays a runtime dependency (G38). The confirmation draft opens at
  `confirmed`, not `cross_checked`; details in the ticket's "As built".
- 2026-10-06, ticket 09 built (`2284d3c`): eval dataset `sales@1.0.0`
  (10 cases, full security coverage) graded by seven `sales.*` graders that
  live in `dw_sales.evals` and run the real Sales services in one process
  over an in-memory store; `scripts/run_evals.py` is the composition root
  that injects them, so `dw_evals` imports no context. Pinned in the release
  manifest. Demo runbook `sales/dw1-portal-demo/demo.md` (Vietnamese),
  `make demo-reset` (start state), `make test-web-sales` (Playwright walk).
  Security reviews (feature and deployment) recorded in ticket 09.
- **What "done" means for the demo:** the personas walk the spec's Done-when
  on the local stack from `make demo-reset`, the walk is automated
  (`make test-web-sales`), and `make eval-smoke` scores extraction and
  findings on the mock set. It is a demo on fictional data, and nothing
  production-only exists. What remains is ticket 12 (production hardening:
  sandboxed parsing, support access, tenant overrides, rules approval, DW1's
  service principal, Proterial's real inputs).
- 2026-10-06, ticket 10 committed (`8d098b3`): DW1 runs on the agent runtime
  (dw_sales ADR 0004, Proposed, supersedes ADR 0001; spec decision 5
  amended). "DW xử lý", submit and the Bravo entry are each a DW1 run
  (`configs/workers/sales.yaml`, graph 1.0.0, pinned), counted by the
  runner's `RunAllowancePort` check. Submit and the Bravo entry pause on a
  platform approval (`sales.quote`, `sales.order.cross_check`) stamped with
  its decide scope (`sales.quote.approve`, `sales.order.cross_check`, never
  `approvals.decide`) and naming every maker; `sales.` is strict and has a
  Sales decision guard; the run applies the decision. The context decide
  routes are gone; the pages decide on `decision.approval_id` with a
  required comment. Platform gained: stamped decide scope, makers, decision
  guard, inbox audience filter, withdraw by subject, an in-memory runtime
  the eval world uses. Walk: 11/11 passed on the third run (`make demo-reset`, `make test-web-sales`); the two before timed out at different steps under machine load (a draft render at stage 1; M29's reprocess at stage 8, whose run row shows 107 s against 0.2 s measured idle). Details and open items in the ticket's
  "As built".
- 2026-10-07, platform `96f95ad` merged (`chore/platform-merge-2`): Sales
  approvals moved onto the platform's approval model (dw_sales ADR 0004
  amendment). The stamp is the `required_scope` column (migration
  `ac31ff0f2087` copies a payload `decide_scope` into it and renames the
  key; `DecisionAsked` still reads `decide_scope` from runs paused before);
  deciding asks `approvals.decide` AND the stamp, so `sales_pic`,
  `sales_head` and `sales_quote_approver` gained `approvals.decide`; seeing
  is the platform's `ApprovalAudience` (the product's own filter and its
  `test_approval_audience.py` are gone). The purchasing manager now gets
  404, not 403, on a Sales request. Kept: makers, `CaseDecisions.check`
  (async guard, longest-prefix keyed), withdrawal (reads the approval as
  the run's requester). Platform ADR 0004 is `docs/adr/0011` here.
- 2026-10-08, platform `ab33703` merged: the antd-only web (see
  `web-ui.md`), decision audit (one `approval.decided` row per decision, the
  platform's; Sales writes none of its own), append-only decisions, 401 for
  a missing bearer (`test_sales_routes.py` follows), `ScopeHoldersPort.holding`
  takes the tenant id as the platform's does, Sales role labels in the one
  role-label table, `/approvals` links a Sales approval to its case. DW1
  renders no prompt (spec decision 13), so the platform's prompt containment
  versions no Sales prompt and `sales@1.0.0` is unchanged.
  **Owed from that merge (Docker became unavailable mid-pass):** the
  integration suites ran once before it stopped (729 passed, 6 failed: the
  five new `ck_approval_requests_sales_stamped` cases on a test bug, and
  `test_sales_api_access.py` still expecting 403 for a missing bearer); both
  are fixed and NOT re-run. Playwright (sales spec, platform specs) and
  `make check-rerank` were NOT run. `make db-migrate` did run on the dev DB
  (head `a64b918fc1f2`) before the stop. Since then the integration suites
  and the sales spec run green on CI (integration on `99cb905`; the walk
  green on 13 of 16 finished runs from `e97042b` to 2026-10-14); the
  platform specs and `make check-rerank` are still not run.
- Next: 12 (needs-info since its triage on 2026-10-12).
  Owed by the API to the pages: delivered 2026-10-15 (refusals only where a
  rule code exists). The PO-read attributes for the candidate picker
  (`136893d`, `734dccd`; stamped at mapping, decided by the agent: the stamp
  rule, four attributes only),
  order due dates in my-work (`27e36bb`), server time (`7ed84b6`: the API
  exposes `Date`, `lib/server-clock.ts` keeps the offset, `useNow` counts by
  it), Vietnamese refusals (`4fa6799`, `04708ec`, `e9cd4bc`: decided by the
  agent, the web words only codes whose server sentence is still English,
  one table per context in `lib/error-message.ts` `REFUSAL_TABLES`;
  separation-of-duties refusals and `stale_case_version` are worded by the
  server (owed on Docker: `test_sales_store.py`,
  `test_sales_constraints.py`)). Still English: refusals with no code (e.g.
  "the approval is not one DW1 raised", "the layout is already decided", order/quote status
  moves, the pricer refusal in `domain/quotes.py`); each needs a
  `details.rule` and a table entry, or a Vietnamese server sentence. The
  picker's khớp/lệch mirrors `StatedAttributes.fits` (a test holds it);
  the lasting fix is the server sending each candidate's fit. (Role names
  and permission-set scopes landed in `/auth/bootstrap` on 2026-10-05; the
  web stopgap roster is gone.)
- Offboarding export reads a partitioned parent and its partitions, so audit
  and event rows come out twice (pre-existing; platform; fixed 2026-10-15,
  `953086f`).
- Open from the 02/03 pass: routing reasons (complaint, sample request,
  delivery change) are keyword tables, against operator guideline §6,
  accepted by the spec for the demo; ticket 03 added the ledger to the mock
  catalog; the sales policy files stayed at 1.0.0 (never released).

- 2026-10-05, UI compared with the E-HSDT v3 prototype (screenshots in the
  session scratchpad): the Sales pages are antd v6 but keep the platform's
  navy theme and system font, the header shows the platform menus in
  English, and lists are plain tables. The prototype uses Be Vietnam Pro
  (JetBrains Mono for codes), a bright primary, a Sales-only header with
  counts, a "Cần xử lý" panel, Segmented tabs with counts, search/sort and
  two-line rows. Primary decided `#0071e3` by Đạt 2026-10-05.
- 2026-10-05, restyle built (`92b155a`): theme from the prototype
  (`web-ui.md` has the mapping and the nearest-passing values); Sales-only
  bar for a PIC/head/viewer with counts (my-work, unprocessed mail) and the
  Vietnamese role name; the four lists on the prototype's list pattern
  (breadcrumb, summary line, "Cần xử lý", Segmented tabs with counts,
  diacritics-insensitive search, `Intl.Collator('vi')` sort, two-line rows,
  `StatusTag`s, red "còn X giờ" inside a day, assignee avatar; tab/q/sort in
  the URL); order and quote detail with the 4-fact summary strip, the
  procedure card and findings as severity-barred rows. API: bootstrap
  returns `role_names` and the effective scopes (roles + permission sets,
  via `effective_scopes`); OpenAPI and TS types regenerated.
  Left different from the prototype: lists on white tables; no command
  palette; the bar overflowed "…" from 992 to beyond 1600 px with nine
  pages (2026-10-15). It now folds them into the "Hồ sơ" and "Quản lý"
  submenus (ticket 39, `f84643e`); the visual check at 992-1600 px is still
  owed. Customer names come
  from the mock master data (a code it lacks shows the code).
- Dev: realm redirect URIs allow port 3300 only; `.env` sets
  `DW_WEB_PORT=3300`, but `scripts/dev.sh` defaults to 3000, so a run
  without the env var cannot sign in. Fixed 2026-10-15 (`9c08926`):
  `dev.sh` reads the port from `DW_PUBLIC_WEB_URL`, and `.env.example`
  uses port 3300. Still open: the local keycloak service gets no
  `DW_PUBLIC_WEB_URL` (the realm falls back to 3300), and the Docker web
  publishes `DW_WEB_HOST_PORT=3000`, so a Docker stack in dev auth at :3000
  is refused by CORS and by Keycloak; follow-up: default
  `DW_WEB_HOST_PORT` to 3300 and change CI's smoke curl (`ci.yml`,
  `http://localhost:3000`) in the same change. A real `make dev` sign-in
  is owed (Docker).

## Inputs owed by Proterial

The requirements doc `DW1_Don-hang-Bao-gia_Nhung-gi-can-co_30-09-2026_v1.2.docx`
(kept outside git) lists them: convert list, item master, quotation master
list and LME rule, Bravo upload template, sample POs with their Bravo orders,
mailbox access, AI/data approval, WIV-03-012/023 texts. Sent by Đạt
(confirmed 2026-10-12); answers awaited.

## Slice log

| Ticket | Commit    | What                                                                                                      |
| ------ | --------- | --------------------------------------------------------------------------------------------------------- |
| 07     | `78af2bd` | antd v6 shell: registry on the `antd` layer, theme owns tokens, top navbar, dates/money                   |
| 01     | `b5f990b` | Mock catalog and inbox behind `SalesCatalogPort`/`InboxPort`; 12 fictional emails M01–M12                 |
| 02, 03 | `ad467dd` | Amended to WIV steps: maker/checker, dispositions, revised PO, quote steps 1–12; fixtures M13–M32         |
| review | `077d54b` | Security review of the core: Design mailbox, decided_by, scope-bound mocks, confirm_mapping               |
| 04     | `5ed607b` | `sales` schema, RLS by tenant+workspace, maker/checker across revisions, roles, offboarding               |
| 11     | `87ab107` | Demo personas: `dw_sales.testing.seed_personas`, `khoa.lam`/`tam.ngo` in the platform seed, roster fixed  |
| 05     | `3557de8` | API routes and scopes, overview/my-work, source gate, pause/resume, actor uuids, `sales_kpi@1.0.0`        |
| 06     | `2f737ca` | Artifacts: upload file, cross-check, drafts, quotation xlsx+PDF; copy pinned; download gates              |
| 08     | `88fb7b6` | Sales pages on the E-HSDT v3 visual language; walked in a browser as every persona, refusals shown        |
| 09     | `2284d3c` | Evals `sales@1.0.0` + graders injected; security reviews; demo runbook, `demo-reset`, Playwright walk     |
| 10     | `8d098b3` | DW1 on the runtime: checker decisions are platform approvals, decide scope stamped, makers refused        |
| 12     | `e60592c` | Triaged into 13-27; what waits on the requirements doc stays (needs-info)                                 |
| 13     | `a995031` | The quote approval panel sees a newly rendered preview                                                    |
| 14     | `4027c0d` | An order whose cross-check failed to apply is cross-checked again                                         |
| 17     | `4db04fc` | The head reassigns a case                                                                                 |
| 15, 16 | `8ac3d33` | Per-field value corrections; the DW1 mailbox lane                                                         |
| 18     | `395dbf3` | Web vitest on every push, the DW1 browser walk on main and nightly                                        |
| 20, 22 | `dd5ef1d` | Legacy Vietnamese encodings refused; FPT support reads cases without prices                               |
| 26     | `dd5ef1d` | Public-repo guard over `git ls-files`, deny-list outside git                                              |
| 21, 23 | `399920d` | Built in `dd5ef1d`; 21 finished and 23 reviewed 2026-10-13                                                |
| 28     | `61a5ae5` | A local model reads free-text item descriptions; code verifies (ADR 0005)                                 |
| 29, 31 | `1009491` | A local model reads RFQs in any shape and classifies unread mail                                          |
| 30-33  | `e97042b` | Model steps for case replies, hand-offs and new PO layouts                                                |
| 34     | `399920d` | Blank requested dates, an `.xlsx` and its PDF print as one PO                                             |
| 24, 19 | `399920d` | Overview figures and a paged work list in SQL; a tenant's own rules proposed and approved (2026-10-13)    |
| 25, 27 | `8adbe08` | "DW xử lý" queued, every file read in the `reader` container; legacy Office and OCR (scanning `399920d`)  |
| 35, 36 | `8adbe08` | A split line confirmed per schedule; a tenant's own quote rules, pricing, copy and upload template        |
| 37, 38 | `8894874` | Released rules versions stay readable; rule versions decided on platform approvals                        |
| batch  | `57d3c20` | Eight batches merged 2026-10-15 (`b2ea975`..`57d3c20`): open items of 05-38 closed (State)                |
| 41     | `035d5a7` | Master data imported from a file, previewed, approved on `sales.catalog`; mock until approved (`ed78006`) |
| 40     | `6659d14` | Rules edited in a form drawn from each key's schema; diff before sending and on the approval (look owed)  |
| 42     | `4235dde` | Follow-ups and the 07:30 brief, every timing in `sales_followups`; integration owed on Docker             |
| 43     | State     | Real mail from a drop folder of `.eml` files, stored in PostgreSQL; ignored sender domains in the rules   |

## Open

- 2026-11-04, **less to press on what DW1 read** (Đạt, from the HITL review,
  `plans/hitl-review.md`): a request's line read by the model is confirmed
  with one press, "Xác nhận cả dòng như đã đọc" (`QuoteCase.confirm_as_read`,
  `as_read` on the finding's answer), once this person opened every place
  the line's values were read at this version; each value is still recorded
  on its own; one line per press (ADR 0005 addendum, `ui-quality.md` §7).
  A new PO layout's values are confirmed on its first PO only, not three
  (`layout_onboarding.uncertain_first_pos: 1` in `sales_order_rules@1.10.0`
  and the demo's own `1.5.4`; the tests' 1.5.2 keeps three). Mutations red
  (served per value, the last value's page, as-read naming a value, another
  line, the web's reason). **Dropped (Đạt, 11-04):** the same one press for
  a PO's flagged values (O3); HITL stays until the plant survey.

- 2026-11-02, Đạt: **no e-signature** on quotations (too involved); the
  signed paper stays the official approval. **Roles**: the ~4 of the
  2026-10-28 brainstorm were DW1's alone; for both DWs about 7 (Sales PIC,
  Sales head, buyer, purchasing head, requester, approving director, IT
  admin), exceptions as permission sets. Waiting on Đạt's go-ahead; no code.
  Internal mail kept by DW: decided, kept (on-prem model).

- 2026-11-02, **no sender left out** (Đạt: "gỡ hẳn"): `ignored_sender_domains`
  is gone from `sales_order_rules@1.9.0`, the `sales_mail_drop` lane, the
  stored mailbox, step O1 and the rules page; every mail is stored and DW1's
  model sorts it, internal mail included. A version holding the key still
  reads (dropped on reading; mutated red). Item 7's premise ("internal mail
  never reaches DW1") no longer holds: PC's mail reaches the mailbox now,
  so DW1 could read PC's dates itself (not built; Sales still pastes them).
  **Built 2026-11-04:** `PcDateReplies.mails` lists the verified mails that
  name the order's PO number or its Bravo SO, other than the case's own
  revisions and the customer's mail (`GET /orders/{id}/pc-mails`);
  `read_mail` reads one of them through the same reader and checks as a
  paste (`POST /orders/{id}/pc-dates/from-mail/{message_id}`); any other
  message is not found and no model is asked. The dates still only fill the
  form; "Ghi đã gửi xác nhận" records them. Web: the PC block lists the
  mails with "DW1 đọc ngày từ thư này", the paste stays. Unit 7 new (listed,
  read, five unlisted, scope, the case's forwarded mail, another tenant);
  6 mutations, each red (one first green, closed with a test). **Owed to
  Đạt:** no setting names PC's mailboxes, so any verified non-customer mail
  naming the PO is offered, its sender shown; a `pc_mailboxes` trust
  setting (as `design_mailboxes`) would narrow it, and would let the lane
  read PC's answer unasked.

- 2026-11-02, one inbound flow for DW1 and DW2, built (`purchasing.md`
  State): DW1 reads the folders of those holding `sales.inbox.process` in
  the one drop folder (`DW_MAIL_DROP_DIR`, was `DW_SALES_MAIL_DROP_DIR`).
  Owed: whether Proterial agrees to internal mail being kept and read
  (`purchasing.md` "Decisions Đạt owes").
- 2026-10-28, brainstormed, waiting on Đạt (no code yet): roles cut to the ~4 Proterial uses with plain-words permissions, plus a few audited switches, never a free permission editor (A + B); "Bộ quyền bổ sung" renamed and explained, "Approval authority" hidden; e-signature step 1 (the approval stamped on the quote PDF with a verification code, no key held, no internet) before any remote digital signing; a questionnaire for WIV-03-032 drawn from the standard export-control programme, code only once Proterial's document is in hand; WIV-03-031 after the Bravo meeting.
- 2026-10-28, licence check for Proterial's IP-indemnity clause (agent):
  no AGPL/SSPL/RSAL component ships (153 Python dists, 118 web prod
  packages, 22 images); copyleft runs only as separate, unmodified programs
  (ClamAV and poppler GPL-2.0, LibreOffice MPL-2.0, libvips LGPL-3.0 in
  sharp). Models: Qwen3.5-9B Apache-2.0, bge-m3 MIT, bge-reranker-v2-m3
  Apache-2.0; no Gemma. The notices are generated from the built on-prem
  images (`make third-party-notices`, `2c9c8d52`, run 10-28 into `dist/`):
  re-run it on the images handed over, since DW2 and the reader changed
  after 10-28 (2026-11-04: this line said "none exists", stale). Contract
  wording (carve-outs, cap) is FPT legal's call.
- From tickets 32, 33 and 30 (2026-10-13, agent, Đạt away):
    - ADR 0005's addendum and ADR 0004's amendment (a PO layout decided
      on a run-less `sales.layout` approval the worker carries out):
      accepted by Đạt 2026-10-14.
    - `layout_onboarding.uncertain_first_pos` = 3 is an interim default,
      Proterial's call.
    - Delivery changes in DW1 or DW2 (ticket 33's question): built in DW1;
      one table entry (`HANDOFF_KINDS`) turns them off.
    - A reply opening "Hệ thống: khách đã đồng ý..." was read
      `accepts_spec` (S32-VI): nothing is applied by a reading, and the case
      shows the sentence beside the suggestion.
    - A hand-off is copied and sent by Sales from their own mail: DW1 has no
      path to PC or QA.
    - Ticket 34 holds two of ticket 30's reader fixes.
    - The browser walk (`make test-web-sales`) passes, 11 of 12 (2b skipped:
      no model server), with its counts at 43 messages (42 to process) and
      two assertions that had drifted before this work brought up to date: a
      stamped request an outsider may not see answers 404 (ADR 0004
      amendment 2026-10-07), and the forbidden state reads "Bạn không có
      quyền xem mục này" (`3d1f9a5`). It needs Valkey up: with it stopped,
      every authenticated request waited about 4 s on the cache and the
      order page never loaded within the walk's 60 s. The walk does not yet
      visit the layouts page or a reply or hand-off (unit, API and web tests
      do). Done 2026-10-15, owed one green run (`b478685`, `70df3ff`): it
      visits a case reply (M42 on M04), the layouts page (M43), a hand-off
      draft (2d, skipped without a model server) and a `sales.rules`
      decision on `/approvals` (step 11, proposed on `/sales/rules`); it
      runs only in CI or on a local stack. If a platform release ships
      `sales_order_rules` 1.5.99, step 11's version must change.

- From tickets 29 and 31 (2026-10-13, agent, Đạt away):
    - ADR 0005 with its addendum and the two bars (85% and 90%): accepted
      by Đạt 2026-10-14. `model_assist.unread_retry_hours` (24 h) stays an
      interim value.
    - Confirming a model-read value is not gated on the server on the person
      having opened its source, as an order's prepare is (`require_served`):
      the mail text has no served record yet. Resolved 2026-10-15
      (`5c0e28d`, migration `546a6a81e58c`; ticket 29 Comments): gated per
      value; the mail text has its own route and served record.
    - A request stating no currency goes to a person (`currency_missing`);
      a quantity whose unit is only in a column header is asked for. Both
      by design, both cost recall (ticket 29's misses).
    - Thread headers on `InboundMessage`: built with ticket 32.
    - The browser walk's sign-in step had looked for "Sign in" since the
      antd sweep (`3d1f9a5`); fixed here to "Đăng nhập". The nightly walk
      cannot have passed in between.
    - The intent's resolved references are stamped and shown; ticket 33
      resolves its own PO from the mail, so they are still read by no route.
      2026-10-15 (`0d8806b`): the inbox reads `order_case_id` (a link to
      the case). No route reads them to decide: 32 keeps thread headers, 33
      resolves its own PO; switching either to the intent's numbers is
      Đạt's call.

- From the batch merge (2026-10-15, agent, Đạt: làm luôn):
    - ~~The review page listed every `uploaded_to_bravo` order while My
      work offered `confirm`; `confirm()` let None skip the check
      `awaiting()` waited on (ticket 14).~~ Closed 2026-10-17 (`b65956a`):
      `OrderCase.awaits_cross_check` is the one answer; confirm,
      `awaiting()` and `OrderSummaryView` read it.
    - ~~`supported_channels: [web]` was read by nothing (ticket 16).~~
      Closed 2026-10-17 (`b65956a`): the runner refuses a run from an
      undeclared channel; sales.yaml declares `[web, sales_inbox]`.
    - Offboarding never deletes `platform.users`, so a purged tenant leaves
      DW1's per-tenant user row (ticket 16). Closed 2026-10-18 (`981f3a1`;
      decided by Đạt: the purge deletes that tenant's service subjects,
      never a person's row). `purge_rows` deletes the users inside
      `service_subject_bounds(tenant)` (by subject, so a resumed purge still
      finds them) and lists their ids on the purge audit row. Owed on
      Docker/CI: `test_purge_deletes_the_tenants_service_accounts_and_nobody_elses`,
      `test_a_resumed_purge_still_finds_the_service_accounts`.
    - ~~The candidate picker compared the unit and quantity as read
      (ticket 15).~~ Closed 2026-10-17 (`2b23a1b`): `_lib/entered.ts`.
    - A legacy-font run in an inline string, and legacy text reaching the
      model through a non-form `.xlsx` RFQ, are not detected; refusal
      versus a quote-side finding is Đạt's to revisit (ticket 20).
    - The final eval bars are Đạt's; until then a live run fails only when
      the model read nothing (ticket 28).

- **Sales roles decide unstamped approvals** (CLOSED 2026-10-18, `89e33d6`:
  Đạt chose "the platform stamps its own types". `memory.review` is stamped
  with the new platform scope `memory.review`, held by `approver`, `manager`,
  `director` and `approver_boost` and by no Sales role; migration
  `445f93c2ea2a` grants it, stamps existing rows and adds
  `ck_approval_requests_memory_review_stamped`; `docs/adr/0011` amendment
  2026-10-18. A Sales decider now gets 404 on a memory review.
  `platform-runtime.md` has the details. Kept below for the history; from
  `ac31ff0f2087`). Every Sales approval type is stamped, and since the
  platform merge of 2026-10-08 the database says so
  (`ck_approval_requests_sales_stamped`, migration `a64b918fc1f2`, NULL
  refused since `d9e73228e7d7`: a `sales.` approval carries a `sales.`
  scope or is not written). That does
  not close the widening: the platform decides on `approvals.decide` AND the
  stamp (`docs/adr/0011`), so `sales_pic`, `sales_head` and
  `sales_quote_approver` keep `approvals.decide` and with it every
  UNSTAMPED request in their workspace (`memory.review` today). Closing it
  needs a platform decision, not a product patch: either a stamp stands in
  for `approvals.decide` (then the three drop it), or the platform stamps
  its own types (`memory.review`).
- From ticket 09 (2026-10-06): the approval panel needed a page reload after
  the approver rendered the preview (closed by ticket 13); whether submit should render the preview
  itself (Đạt); the release manifest pins an eval dataset file but not the
  fixtures and truth files it names (platform; pinned since 2026-10-15,
  `5452299`, except data a grader opens by its own code: ticket 09 Open);
  the mock README's
  Design-reply dispositions assume Sales recorded the YCBG first (the eval
  states those steps); CI does not run `make test-web-sales` (ticket 18); the walk passed
  11/11 once, then a re-run timed out on Hà's overview ("Loading…", 60 s)
  under heavy machine load: unexplained, and not seen again: stage 9 passed
  on every green CI walk since `e97042b` (13 runs to 2026-10-14), and no CI
  failure was on that stage.

- From ticket 06 (2026-10-05): a `value_uncertain` correction is one value
  for a whole region, so the upload file carries the values as read
  (closed by ticket 15, 2026-10-12); an object written before its record commits can be orphaned
  (purged by offboarding; removed when its record does not commit since
  2026-10-15, `76c3792`, ticket 06); rendering was not stopped by the pause:
  closed 2026-10-18 (`f4705f9`, decided by Đạt: pausing DW1 also stops
  rendering drafts and files; drawing one is refused with `worker_paused`,
  reading what exists is not); the web client types need `pnpm run generate:api-types` (current:
  CI's "Generated API client is current" check was green on `99cb905`).

- From ticket 05 (2026-10-05):
    - The overview loaded every case of the workspace: SQL aggregates and a
      paged work list since ticket 24 (2026-10-13).
    - The A3 shadow count uses interim conditions (no finding, every line
      exact, an original) until Proterial defines A3.
    - Ticket 08 must render a served PDF page with pdf.js scripting off and
      a sheet grid's cell text as text; a download's file name needs
      `Content-Disposition` in the CORS `expose_headers` if the browser is
      to read it. Closed by ticket 08 (`88fb7b6`): pdf.js runs with no
      scripting, XFA or annotations (`pdf-page.tsx`), cell text renders as
      text, and a download is saved under the name the file list gives, so
      the header need not be exposed.
    - A pause commits before its notification: a delivery failure answers
      500 while DW1 is paused (a retry answers 409 "đã tạm dừng"). Closed
      2026-10-15 (`55ade02`): the failure is logged and the pause answers
      as one. A failed notification is not retried; if retries are wanted,
      it moves to an outbox event.
    - The committed OpenAPI snapshot was stale on `main` before 05 (the
      contract test failed); 05 regenerated it, platform drift included.
- Ticket 11 (2026-10-05): the full demo seed is
  `uv run python -m dw_sales.testing.seed_personas` (platform seed, then the
  Sales keys). The new personas sign in through Keycloak via
  `scripts/keycloak_dev_users.py`, which links by email; the realm file was
  not changed. The platform seed resets roles, so a full re-run rewrites the
  Sales keys (same end state); the Sales seed alone writes nothing on a
  re-run. (The `approver_boost` item owed to ticket 10 is closed: a Sales
  approval requires its stamped `sales.quote.approve`, so Diệu's
  `approvals.decide` decides none; tested in the API suite, the unit suite,
  the eval and the walk.)
- From ticket 10 (2026-10-06): the generic Approvals page sends no case
  version, so deciding a Sales approval there would be refused. Closed by the
  platform's `approval-inbox-link` (merged 2026-10-08): `salesApprovalHost`
  in `apps/web/app/sales/_meta/approvals.ts` makes `/approvals` show "Mở hồ
  sơ để quyết định", linking to the case page, instead of the decide
  buttons. An order whose decision passed the guard and then failed in its
  run had no step that raises its cross-check again: closed by ticket 14. Processing's
  audit rows do not name the run (decision rows do): closed 2026-10-15
  (`79be08d`). No mailbox consumer
  exists, and one must start a DW1 run to be counted: ticket 16 (built
  2026-10-12; each message is its own counted run).
- Public repo: the repo name and these plan files name Proterial and its
  procedure codes (WIV-03-0xx). Đạt decided on 2026-10-05 to keep the repo
  public and not alias them. Mock data, people and figures stay fictional,
  and Proterial's documents stay outside git. Guarded since 2026-10-12
  (ticket 26, `scripts/check_public_repo.py`; done and reviewed, uncommitted):
  owed by a person, the `PUBLIC_REPO_DENYLIST` repository secret (the CI step
  fails until it exists) and, on each machine that commits, a deny-list file
  named by `DW_PUBLIC_REPO_DENYLIST`. Without one the hooks only say they
  skipped, and CI finds a term only after the push has published it.
- Defaults adopted until Proterial answers, taken from the requirements
  doc's own interim answers (Đạt may overrule); the spec's "Interim
  behaviour" table names the policy key or role each answer changes:
    - the cross-check is kept;
    - the signed hard copy stays the quotation approval of record, and portal
      approval is shown as the proposal;
    - only the quotation PIC and the head see other customers' prices;
    - NOC/ESF warns, and the export-control PIC must acknowledge it;
    - quotation steps 11–12 are built on mock data.
- Quotation-time target: under 1 day (Đạt, 2026-10-05).
- UI reference (2026-10-05): Đạt's E-HSDT v3 prototype in `docs/design/`
  (untracked, another product's handoff) is the visual language for ticket
  08; the screen mapping is in ticket 08. `docs/design/` is in `.gitignore` (Đạt, 2026-10-05)
