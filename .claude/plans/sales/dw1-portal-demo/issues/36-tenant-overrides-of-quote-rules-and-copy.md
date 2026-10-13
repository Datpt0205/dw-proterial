# 36 — A tenant's own quote rules, pricing, copy and upload template

Status: ready-for-agent
Blocked by: —
Category: enhancement

Split from ticket 19 on 2026-10-13 (agent, Đạt away).

## What

Ticket 19 built the mechanism: `sales.rule_versions`, the propose and
approve routes, `TenantRuleBook` resolving through `TenantOverlay`, and the
stamp read back by a recheck. It made two keys overridable, `sales_order_rules`
and `sales_kpi`, because their readers already took the tenant's scope. The
other Sales policy and copy files are still read as one platform object at the
composition root, so a tenant version of them would be stored and applied by
nothing:

- `sales_quote_rules` and `sales_pricing`: `QuotationService.rules` and
  `.pricing`; the Design mailboxes are also copied into `ArtifactCopy` from
  the platform's quote rules (`load_artifact_copy`), so the drafting of a
  YCBG must read the tenant's too, or the two disagree.
- `sales_emails`, `sales_documents`, `sales_bravo_upload`: `ArtifactCopy` in
  `ArtifactService` and the drafting.
- `sales_handoffs`: `InboxQueries` and the hand-off drafts.

## Acceptance

1. Each reader resolves its key per tenant through `TenantRuleBook` (the
   service asks with the scope it already has); the composition root hands
   the book, not the loaded object.
2. Each key is added to `RuleKey`, `OVERRIDABLE` and the migration's
   `ck_rule_versions_key` in one change, with its reader.
3. Where a case or an artifact stamps the version it used (a quotation's
   `rules_version` and pricing version, an artifact's `template_ref`), a later
   read uses the stamp, as ticket 19 does for order rules.
4. Tests as ticket 19's: another tenant never sees the version; a stamped
   version is read back; a mutation making resolution fall back to any tenant
   goes red.

## Sources (as of 2026-10-13)

- `dw_sales/application/rules.py`, `adapters/policy_files.py`
  (`load_artifact_copy`, `rule_book`), `application/quotation.py`,
  `application/drafting.py`, `application/artifacts_service.py`,
  `application/inbox_service.py`; ticket 19's Comments.

## Comments
