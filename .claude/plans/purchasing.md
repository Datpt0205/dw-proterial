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

- 2026-11-01, **slice 2 — cross-check + approval limits (DW02 function 2), done**:
    - `GET /requests/{id}/check` (read) and `POST /requests/{id}/submit`
      (`purchasing.request.submit`, `case_version`, Idempotency-Key).
      `domain.checks.cross_check` over master data behind `MasterDataPort`
      (mock `data/master.json`, demo scope only): reference price = lowest
      valid quotation, else last price paid, else the estimate; amount
      unknown when a line has none; findings as codes.
    - `purchasing_rules@1.1.0` adds `approval`: bands (`up_to` inclusive, the
      last open), the scope each is decided by
      (`purchasing.approve.tier1..3`, the migration's), a label, the price
      tolerance and the findings that escalate to the last tier. Unknown
      amount or another currency → the last tier. Rules without `approval`
      send nothing (409 `no_limits`).
    - Sending stamps the check and `ApprovalAsked` (approval id, scope,
      label, version, sender) on the case and opens a run-less platform
      approval `purchasing.request` in the same transaction, `required_scope`
      the tier's, makers = receiver + sender. The API makes `purchasing.`
      strict and registers `RequestDecisions` (refuses another approval of
      the case or a stale `subject_version`); the worker settles
      `purchasing.request.decided` (`RequestSettlement`: outcome from the
      approval row, read with the stamped scope, idempotent).
    - Migration `911fdfb96d5e`: statuses, generated `approval_id` (unique per
      tenant), `ck_cases_sent`; buyer + submit; role `purchasing_head`
      (tier1, tier2); permission set `purchasing_director_approver` (tier3).
    - Checks: unit 75 + API routes 14 + worker handler; integration 10 (the
      platform's own approval flow: maker refused, empty reason refused,
      another tier's holder finds nothing, stale version refused by the
      guard, outbox event, settlement idempotent, another tenant finds
      nothing; `ck_cases_sent`; roles and permission sets cover every
      approve scope); eval `purchasing_pr_approval@1.0.0` 4/4 (red with
      escalation off). Mutations, each red: expired quote, highest quote,
      partial-sum amount, other-currency price, tolerance, over budget,
      unknown-amount escalation, escalation, inclusive limit, tier shape,
      submit gate, stale version, sent twice, tier scope stamp, makers, guard
      version, guard approval id, idempotent settle, pending settle, stamp
      not rules at settle, master-data scope, API strict prefix, API guard,
      worker handler. One guard (status beside version) was redundant and
      removed: every write moves the version.

- 2026-11-01, **slice 3 — RFQ + offers + comparison + choice (DW02 function 3), done**:
    - `POST /requests/{id}/rfq` (approved only): suppliers per line from the
      master data (`suppliers_for`: supplies it, quoted it, was paid for it;
      known suppliers only; at most `rfq.max_suppliers_per_line`, rules
      `1.2.0`), reply date `rfq.reply_days`, recipients the supplier's
      contacts. `purchasing.rfq_mail@1.0.0` words it from code's facts (dates
      day first, as the mail writes them); kept only when `figure_check`
      finds no figure outside the facts and `names_amount` none, else the
      template. Nothing is sent.
    - Offers: `POST /requests/{id}/offers` (typed; known supplier, a line of
      the request) and `/offers/from-mail/{message_id}` (verified sender of an
      asked supplier's domain; `purchasing.supplier_quote_reading@1.0.0`
      spans; tied by item code to the lines asked; an unasked item is left
      out; read once).
    - `GET /requests/{id}/comparison`: valid offers in the request's
      currency, cheapest first, totals, need-by met. `POST /selection`: one
      offer per line, total held to the stamped tier `limit` (409
      `exceeds_approved_limit`).
    - Migration `0e9a49b7a6f8`: statuses `rfq_drafted`,
      `supplier_selected`; `ck_cases_sent` rewritten; `ck_cases_sourced`
      (absent jsonb keys read as absent, not NULL); buyer gets
      `purchasing.rfq.prepare`.
    - Checks: unit 95 + API routes 15; integration 11 (the whole flow on the
      SQL store, `ck_cases_sourced` refusals, another workspace finds
      nothing); eval `purchasing_sourcing@1.0.0` 4/4 (red with the comparison
      reversed or unasked items kept). Mutations, each red: supplier cap,
      unknown supplier, RFQ figure check, RFQ amount check, RFQ before
      approval, rfq gate, reply read twice, unverified reply, any sender,
      unknown typed supplier, unknown line, one per line, choice without
      offer, approved limit, expired and foreign offers compared, dearest
      first, offer price span, unasked item recorded, sourcing-state
      validator.

## Next

1. Slice 4 — draft PO + Bravo import file (function 4). Stop and report.
3. Then: confirmation/delivery tracking (5), brief + Q&A (6), the web pages.

## Not done, on purpose

- No web page yet: the API first, the pages after slice 4.
- A purchase approval is decided on the web only: no subject version is
  registered for the Zalo decision command.
- A sent request cannot be withdrawn or edited yet; a rejected one stays
  rejected (a new request is a new case).
- RFQ drafts are not sent: the outbox folder (`dw_platform`) can carry them
  from the buyer's mailbox, as DW1's mails go; wiring it is the next step
  after the pages.
- A supplier's reply is not linked to its RFQ by thread headers yet: the
  buyer picks the case and the mail.
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
