# 19 — Tenant overrides of Sales rules and templates, proposed and approved (G15)

Status: ready-for-agent
Blocked by: —
Category: enhancement

Split from ticket 12 on 2026-10-12.

## What

Sales rules and templates ship as platform-layer files:
`configs/policies/sales_order_rules`, `sales_quote_rules`, `sales_pricing`,
`sales_kpi`, `sales_bravo_upload`, and `configs/copy/sales_emails`,
`sales_documents`. Proterial's own values (lead-time table, LME rule, email
wording, upload template) must arrive as a tenant override at runtime, not as
an edit to the checkout (`CLAUDE.md`, "Per-tenant artifacts").

`dw_kernel.overlay.TenantOverlay` and `dw_platform`'s `PolicyOverridePort`
exist; Sales does not use them yet (verified 2026-10-12).

## Acceptance

1. Every Sales policy and copy file resolves through `TenantOverlay`: the
   tenant's approved version if one exists, the platform's otherwise. The
   tenant comes from the run or the access context, never from the request.
2. A case keeps stamping the `id@version` it was processed under, and the
   stamp says which layer it came from; later reads use the stamp, not a
   fresh lookup.
3. Routes under `/api/v1/sales/rules`:
    - propose a new version of one key (body validated by that key's schema;
      a schema failure → 422), needs `sales.rules.propose`, granted to
      `sales_pic` and `sales_head` (maker/checker, as in the rest of DW1);
    - approve or reject a proposal, needs `sales.rules.approve`, granted to
      `sales_head` only;
    - both scopes declared in one new migration, with this route;
    - the proposer cannot approve their own proposal (409);
    - list versions, with who proposed and approved each.
4. Each proposal and decision is audited in its transaction.
5. Inventory answers (the release manifest) still read the platform layer
   only.
6. Negative tests: an override never resolves for another tenant; a
   `sales_pic` cannot approve; a support context cannot propose or approve;
   a proposal for an unknown key → 422.
7. Mutation check: make resolution fall back to any tenant's override and
   watch the cross-tenant test go red.

## Out of scope

- A web editor for rule files (the API and an audit trail are the slice);
  a read-only "rules in force" view is welcome if small.
- Proterial's actual values (they wait on the requirements doc).

## Sources (as of 2026-10-12)

- `dw_kernel/overlay.py`, `dw_platform/application/ports.py`
  (`PolicyOverridePort`), `test_tenant_overlay.py`.
- Spec decision 14; `configs/policies/sales_*`, `configs/copy/sales_*`.

## Comments
