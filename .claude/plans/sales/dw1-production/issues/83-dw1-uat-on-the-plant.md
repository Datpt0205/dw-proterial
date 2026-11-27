# 83 — DW1 on the plant's machine for UAT

Status: ready-for-human (Đạt, Proterial IT)
Blocked by: 52, 63, 70–75 for Bravo writes; nothing for a read-only UAT
Category: deployment

## What

1. DW in the Ubuntu VM on the plant's Windows Server 2025 host
   (`infra/onprem/README.md`, `ops-hardening.md`); Strata reachable from it.
2. Live evals `--attest` on the plant's model for every step the rules turn on
   (tickets 01, 43, 57, 67); only attested steps are switched on.
3. Mail: a receiving flow per PIC (SharePoint → sync PC → share) and a sending
   flow per PIC (ticket 23); the folder watchdog (shared parts, mail section).
4. iPhone push: a certificate the iPhones trust, the host reaching
   `web.push.apple.com`, `DW_WEB_PUSH_SUBJECT`.
5. Identity: Keycloak federated to the AD once IT answers (ticket 64).
6. The UAT walk rewritten for today's flow (`apps/web/e2e/sales-demo.spec.ts`
   is Đạt's uncommitted file: he rewrites it or hands it over).

## Acceptance

- A PIC receives a real customer mail, prepares an order, and sends the
  confirmation from their own mailbox, all inside DW, on the plant's machine.

## Comments

### 2026-11-27 — full review (functions), fixes that belong to no other ticket

- **Two current steps.** An order at `uploaded_to_bravo` read "Hồ sơ đang ở
  bước này" on O3 and on O7: `WIV_STEPS` lists the state under both, and the
  timeline marked every step holding it. The later step is now current and
  the earlier one reads "Đã qua bước này" (the state says the entry
  happened). `WIV_STEPS` is unchanged: the overview's per-step figures read
  it. `case-timeline.test.tsx`'s fixture now has O3 as the server does (it
  had only O7, so it could not see this); red on the old component.
- **The rules page for someone who reads no price.** Tâm (IT,
  `sales_rules_editor` without price scopes) read "Công ty chưa có phiên bản
  riêng nào: mọi quy tắc đang theo bản của nền tảng" while the company's own
  `sales_order_rules@1.5.4` was in force, only hidden from her for its
  prices. Without `sales.price.read` the empty table now says no version is
  among the rules she may see, and that price rules show only to whoever
  reads prices; the subtitle reads "quy tắc bạn được xem". Test in
  `rules.test.tsx` (both personas), red with the scope check forced true.
- **A reply no model read, and "DW1 đã làm gì" beside it.** The reply line
  always said "Chưa đọc: bước mô hình đang tắt", but `outcome` is null also
  when the reader is on and not yet at its bar (`model_steps.allows`); it
  now says "Chưa đọc: bước AI tắt hoặc chưa đạt" (the AI state words), and
  the trial reading that may have run stays in "DW1 đã làm gì". There the
  result tag read "Model không trả lời" beside the kind "Mô hình không trả
  lời": the tag is Vietnamese now and the kind line is not repeated. A
  model step's `process_steps` name both procedures' steps, so a quote
  showed the reply reader's "O1": a case's entries now name only their own
  procedure's steps. Tests in `case-activity.test.tsx` and
  `case-replies.test.tsx`, red under each mutation (no procedure filter, the
  kind line always drawn, the old reply wording).
- **Flag values in machine words and English.** "Mong đợi: lme_band ·
  Thực tế: fixed", "<= 0.65" beside "0,705 USD", "floor" with factor
  names, "official"/"temporary", and the NOC/ESF hold's English sentence.
  The server's values stay as stored: `orders._carried` keeps a decision
  only while `expected`/`actual` are unchanged, so rewording them on the
  server would reopen every decided flag (an acknowledged NOC/ESF hold
  among them) on the next re-check. `findingValueWords` (web,
  `_lib/finding-values.ts`) puts them into words at display, by finding
  code, for the shapes `order_checks._compliance_finding`,
  `quotes._basis_mismatch`, `quotes._unknown_floor_factors` and the two
  price comparisons write; any other shape shows as written. Tests:
  `finding-values.test.ts` (server strings copied from
  `test_order_intake.py`), the order page (`export-control-hold.test.tsx`)
  and the quote page (`case-audit.test.tsx`), red with the code dropped at
  each of the three call sites and with the price-only number rule removed.
  Not done: the pricing form still starts a line on "Cố định" and does not
  show the prescribed band, because the quote view carries neither the
  quote rules' `copper_basis` nor the month's band; that needs a view field.
  English values of other order flags (`customer_unknown`,
  `revision_without_base`, `duplicate_po`) are left as written.

### 2026-11-27 — full review (config)

- **The source view opened a PO under the platform's caps.** Reading a PO
  and the manual upload took the tenant's `intake` caps per call
  (`order_intake._order`, `po_uploads`); the source view, the rule-draft
  template and the learned SalesOrder file used the platform file's caps,
  bound when the process started (`client_readers(reader,
  policies.order_rules.intake)`). A company that raised `max_pages` got POs
  read that Sales could not open, so "Xác nhận" stayed off. Now
  `ClientSourceView` takes the caps per call, and `SourceService`,
  `RuleDrafting` and `SalesOrderLearning` pass the tenant's
  (`SourceService.rules` is new). DW2's workbook reader passes its own, as
  before. Tests: `test_source_caps.py` (the view asks with the company's
  raised caps; the company's lowered caps refuse a file read earlier),
  `test_rule_drafts.py` and `test_salesorder_learning.py` (one each); all
  four red with the platform caps put back in each service.
  The table reader (a master list or a Bravo screen Sales uploads) keeps the
  platform file's caps: those are not a sender's file, and changing them
  would also move DW2's master import. The `bound_at_build` lock now says
  that in words instead of "may not take effect". Not done: whether staff
  uploads should follow the company's caps too is Đạt's call. The review
  also said the lock is not enforced; that is by design: the lock only
  decides where the field is edited, and a rules version still goes
  through proposal and approval.
- **`autonomy_level: A1` read like DW1's bound and was not.** The comment in
  `configs/workers/sales.yaml` said a person makes every decision; since
  tickets 44, 81 and 82, `sales_auto_apply`, `sales_cross_check_on_match`
  and implied acceptance act by themselves, outside the runner, and none
  reads the worker's level. The comment now says what the level bounds (a
  tool call of a run through the runner; every DW1 tool is `none`, held by
  `test_dw1_runtime.py`) and what bounds each lane instead (`STEP_TIERS`,
  `sales_order_rules.autonomy`, `implied_acceptance.record`). Comment only,
  so no test of its own. Left as found: the background lanes' run contexts
  stamp `autonomy_level="A1"` by hand (`salesorder_pairs.lane_run`,
  `skill_replay`), and `domain/followups.py`'s docstring still says "DW1
  never records" implied acceptance.

### 2026-11-27 — full review (authz)

- **A sent mail whose presser lost the scope stopped the outbound tick.**
  The lane records "Đã gửi KH", "Ghi đã gửi khách" and "Ghi đã hỏi PC" as
  the person who pressed, re-resolved at the receipt. A person still a
  member but without `sales.quote.prepare` / `sales.order.prepare` by then
  got a `PermissionDeniedError` from the service, which the lane did not
  catch (only `ConflictError`, `NotFoundError`): the rest of that tick's
  receipts and queued mails waited an interval, and the PIC of a request
  to PC was not told it went unrecorded. Now all three marks catch it too;
  the PC one tells the PIC (`pc_not_recorded`), as for a case that moved
  on. Nothing was ever recorded without the scope (fail closed). Tests:
  three in `test_outbound_mail.py`, red with `PermissionDeniedError` before
  the change. Left as found: a lost scope on the quote and change-answer
  receipts is logged only, nobody told, the same as a case marked by hand.
- **No test held the service's own check on eleven mutations.** The route
  checks first, but the outbound lane reaches `QuoteCommands.sent` /
  `design_sent` and `UpdateLoops.answer_sent` with no route, so there the
  service is the only check (failure-modes #5). `test_service_scopes.py`'s
  table now calls `WorkerService.pause`, `upload_signed_quote`,
  `OrderQuotes.recheck`, `Confirmations.sent` / `implied_undone`,
  `ChangeRequests.add_line`, `UpdateLoops.pc_answer` / `answer_sent`,
  `QuoteCommands.master_list`, `sent` and `design_sent`; the signed upload
  also needs `sales.quote.prepare` besides reading. Each one red with its
  `Gate.require` made a no-op (a pytest plugin, the tree untouched), and
  the upload red with `sales.quote.prepare` alone dropped.
- **The route test "scope before the Idempotency-Key" looked at POST only.**
  The three PUT and two DELETE Sales routes were outside it (all correct
  today). It now takes every method that is not a read; red when a PUT or
  a DELETE route claims the key before its guard.

### 2026-11-27 — full review (ui)

- **A Bravo write's reason in machine words.** "Ghi vào Bravo" showed the
  gateway's codes as "Bravo trả lời: write_kind_off", which every approved
  write gets until UAT; only the three target reasons had words. The
  reason is kept as the gateway answers it (the audit and the ledger read
  it); `bravoWriteReason` (`_lib/bravo-write.ts`) puts every code the
  gateway, its token and target checks and DW's settlement answer with into
  words (`BRAVO_WRITE_REASON`, the f-string families by their Literals, the
  unmeasured cases, DW's "after a lost answer" suffix), and an unknown code
  reads as a sentence for IT with the code. `bravoWriteWarning` words the
  read-back differences; a screen rule's warning keeps the rule's own name.
  The line reads "Lý do:", not "Bravo trả lời" (the gateway refuses, not
  Bravo); the switch step reads "Loại ghi chưa được bật" (not "cho đơn vị",
  which on this panel reads as a unit of measure); the decider's notice
  says to see the reason on the order instead of the code. Tests:
  `bravo-write-words.test.ts` reads the reason literals from the gateway's,
  the token's, the targets' and the settlement's source, so a new code
  without words goes red (red with one entry removed);
  `bravo-writes.test.tsx` red with the panel back on the raw reason;
  `test_bravo_line_writes.py` red with the code back in the notice.
- **DW1's own implied agreement read "Người dùng 1a2b3c4d".** The lane
  stamps the agreement with its system actor (a uuid5 no roster holds), and
  `usePeople` knows DW1 only by a `dw1|worker|service:` prefix. Telling a
  lane's id by its uuid version on the web was rejected: the demo seed's
  people are uuid5 too. `AgreementView.recorded_by_dw` now says it (the
  view compares `by` with `system_actor(SALES_FOLLOWUPS_LANE)`, as
  `applied_by_dw` does for a code), and the card reads "DW1 ghi lúc …".
  Tests: `test_confirmation_agreement.py` (the lane's agreement true, a
  person's false; each red with the flag forced the other way) and
  `agreement.test.tsx` (red with the card back on `name(by)`). Contracts and
  api types regenerated.
- **"Dạy DW1 loại thư này" was hidden from every PIC.** Since 40266fbc98bf
  a PIC holds no `sales.rules.propose`, so a PIC triaging mail never met the
  control. It is now shown disabled with who can, "Chỉ Trưởng bộ phận Sales
  hoặc Người đề xuất quy tắc dạy được DW1 loại thư." (names from
  `SALES_ROLE`), in its tooltip only, not under every card. The server
  refuses as before. Test in `triage-card.test.tsx`, red with the button
  hidden again.
- **The head called "trưởng nhóm".** The two inbox reasons now name the head
  from `SALES_ROLE`; the assistant's `assign_not_yours` is reworded in copy
  `sales_assistant@1.7.0` (pinned; 1.6.0 kept; release manifest
  regenerated). Tests: the inbox tests hold the new sentences;
  `test_sales_policies.py` reads every copy DW1 runs for "trưởng nhóm" and
  the head's name, red with the pin back on 1.6.0.
- **Mẫu PO had no way in for a PIC, and opened a 403 for tenant IT.** The
  list is now under "Quản lý" beside "Dữ liệu chủ" (`sales.case.read`, as
  its page). In "Quy trình DW1", "Dữ liệu bước này dùng" links the lists and
  the layouts only for a viewer holding `sales.case.read`; tenant IT with
  `sales_rules_editor` alone reads their names and one line saying why.
  "Chưa có vai trò hay bộ quyền nào…" gets its verb. Tests: `nav.test.ts`
  and `app-frame.test.tsx` (red with the entry removed);
  `rules-process.test.tsx` (red with the links always on, and with the old
  sentence).
