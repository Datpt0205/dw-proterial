# Purchasing (Proterial Vietnam) — DW2 Mua hàng

DW02 (the contract's Phụ lục 02, `sales.md` State 2026-10-30): six functions,
PR intake (email, Bravo, form, scanned paper) → cross-check (quotes, purchase
history, budget, approval limits) → supplier RFQ and comparison → draft PO
(Bravo import file) → supplier confirmation and delivery tracking → brief and
Q&A. Built per `docs/adr/0013` on mock data until Proterial's purchasing
samples arrive. The model on premises only reads and writes; code checks and
decides (dw_sales ADR 0005/0006/0007, as DW2 applies them).

## State

- 2026-11-01, **ADR 0013 decision 1 done**, one commit each, behaviour unchanged,
  unit suite green after the five (4037 passed), lint-imports kept:
  malware port + clamd → `dw_platform` (`0c75ddb`); figure/amount check →
  `dw_agent_runtime.model.figure_check`, the names `DW1`/`DW2` now the
  caller's (`a5f75ac`); the one-call model door (`caller_run`,
  `InterpretationPort`, `GatewayInterpretation`) → `dw_agent_runtime`
  (`9485f97`); `InboundMessage`/`AttachmentContent`/`mail_parts` →
  `dw_platform.domain` (`a0be24d`); outbox folder → `dw_platform` (`43908c2`).
- 2026-11-01, **scaffold** (`e0fb115`): `make new-context NAME=purchasing`, all
  generated seams; the first `independence` contract (Sales ↔ Purchasing).
- 2026-11-01, **slice 1 — PR intake (DW02 function 1), done**:
    - Form: `POST /api/v1/purchasing/requests` (`purchasing.request.intake`,
      Idempotency-Key) held to the tenant's form rules (422 naming
      `missing:<field>`, `too_many_lines`, `currency_not_allowed`), a case
      `received`, stamped `rules_ref`, audited `purchasing.request.received`.
    - Mail: `POST /mail/{id}/read` — the sender must be one of the rules'
      `internal_domains` and pass SPF/DKIM/DMARC, else a person reads it
      unread by any model; then `purchasing.pr_mail_reading@1.0.0` returns
      spans only, code finds each as a whole token run in the newest part,
      parses quantity/date/currency, refuses the whole request on any span it
      cannot find; requester = the verified sender. Settled once
      (`purchasing.mail_outcomes`, append-only). No model / no answer: 503,
      nothing recorded.
    - Reads: `GET /requests` (keyset), `/requests/{id}`, `/mail`
      (`purchasing.request.read`).
    - Rules: `configs/policies/purchasing_rules@1.0.0.yaml` (platform layer);
      a tenant's version from the platform's `PolicyOverridePort`, validated,
      refused (409) when unreadable or reusing a platform version — never a
      fallback.
    - Data: migration `2d0c58dc3806` (schema `purchasing`, `cases` with the
      aggregate in `body`, `mail_outcomes`; RLS tenant AND (workspace OR
      scope); roles `purchasing_buyer`, `purchasing_viewer`).
    - Checks: unit 50 + API routes 11; integration 8 on Postgres (RLS by
      tenant/workspace with no WHERE, unscoped session reads 0, no
      UPDATE/DELETE on outcomes, CHECKs = enums, roles, service end to end
      with a tenant override); `test_rls_coverage`, `test_privileges`,
      offboarding, migration round trip green. Eval
      `purchasing_pr_intake@1.0.0` 5/5 with full security coverage (red with
      the span check off). Mutations, each red: internal sender, verified
      sender, form rules, mail rules, intake gate, read gate, route guards,
      settled-once, requester from sender, header spans, line quantity,
      token boundary, duplicate line, tenant-rules fallback, platform-version
      reuse, mock inbox scope.
    - Found on the way: the date parser read `20/11/2026` as 2020 (unit
      test); the outcome was written before its case (FK, integration test;
      the in-memory store now refuses it too); Sales' route walks lacked
      `session_id` since `22da090` (`4031bc8`).

## Next

1. Slice 2 — cross-check + approval limits (function 2): purchase history,
   quotes on file and budget from mock master data behind a port; findings;
   the approval tier from `purchasing_rules` (limits and the scope that
   decides each), stamped on the case; a run-less `purchasing.request`
   approval, strict, maker excluded; `purchasing.request.decided` settled in
   the worker.
2. Slice 3 — RFQ to suppliers + comparison table (function 3).
3. Slice 4 — draft PO + Bravo import file (function 4). Stop and report.
4. Then: confirmation/delivery tracking (5), brief + Q&A (6), the web pages.

## Not done, on purpose

- No web page yet: the API first, the pages after slice 4.
- The Excel PR form and scanned paper: the reader's registry is Sales' until
  it is split (ADR 0013 decision 2). Bravo as a source: no connection.
- No offsets kept for a mail's spans (DW1 keeps anchors): the mailbox is the
  mock; anchors come with the mail drop's move (ADR 0013 decision 3).

## Decisions Đạt owes (Purchasing)

- **Tenant rule editor**: a tenant's `purchasing_rules` is stored through the
  platform's policy overrides, which has no route; a maker/checker editor
  means lifting Sales' rule-version engine (ADR 0013 decision 3).
  Recommended when Proterial's real limits arrive.
- **Retention** of `purchasing.cases` and `mail_outcomes` (none set).
- **Who requests**: today a buyer enters a department's form; whether
  departments get their own `purchasing_requester` role (and see only their
  own requests) is Proterial's process.
