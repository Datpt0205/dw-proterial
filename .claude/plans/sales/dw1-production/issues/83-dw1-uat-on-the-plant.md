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
