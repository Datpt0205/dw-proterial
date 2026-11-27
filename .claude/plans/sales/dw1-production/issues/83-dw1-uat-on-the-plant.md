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
