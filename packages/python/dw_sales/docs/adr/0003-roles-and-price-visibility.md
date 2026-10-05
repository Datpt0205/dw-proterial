---
status: Proposed
date: 2026-10-03
---

# Sales roles are the context's own, and prices fail closed

## Context

The first plan granted three generic scopes to unnamed "seeded roles". The
platform's rungs (member, approver, manager, director, executive) span
departments. Putting Sales scopes on them would let a purchasing manager
approve a quotation, and would let every member read every price. The
customer's procedure has distinct actors:

- a PIC per process, and a cross-checker other than the PIC;
- the head, who approves quotations;
- a deputy;
- the export-control PIC;
- management, who read aggregates only.

Who may see prices given to other customers is still owed by the customer
(requirements doc §3.2). ui-quality.md §6 requires a hidden value never to
reach the browser.

## Decision

1. **Context roles.** `sales_pic`, `sales_head` and `sales_viewer` are rows
   the sales migration inserts. So are three permission sets:
   `sales_price_evidence`, `sales_quote_approver` and
   `sales_export_control`. No `sales.*` scope is added to a platform role;
   a migration test asserts this. The scope list per role is the spec's
   actor table.
2. **Prices fail closed.**
    - An amount reaches a caller only with `sales.price.read`.
    - Another customer's price also needs
      `sales.price.other_customers.read`, held by `sales_price_evidence`
      (the quotation PIC) and `sales_head` only, until the customer answers.
    - One DTO mapper per resource omits the value. A hidden value is marked
      hidden, never zeroed.
3. **No amounts in side channels.** Audit events, case events,
   notifications, logs, traces and error messages carry ids, codes,
   transitions, versions and counts, never a price, a target price or an
   input-echoing validation message. Prices, quotations and the LME rule are
   confidential; contacts are personal data.
4. **IT is not Sales.** `org_admin` holds no `sales.*` scope. A
   `platform.sod_rules` row keeps `platform.members.write` and
   `sales.price.read` off one membership.
5. **Support sees no prices.** The support scope list dw_sales declares for
   ADR 0008 is `{sales.overview.read, sales.case.read}`. No price or write
   scope can ever be granted to support. A `sales_head` is the grantor. No
   FPT identity holds a `sales_*` role or `platform_admin` in the customer's
   tenant, and a pilot on real data waits for ADR 0008 open point 5.
6. **DW1's own principal** holds `sales.inbox.process` only.

## Consequences

- When the customer answers, the answer changes role and permission-set
  assignments, not code. An example is splitting the cross-check into a
  `sales_order_reviewer` set.
- `platform_admin` still passes every check (ADR 0008 open point 2).
  Walk-throughs never use it, and ticket 12 tests the support context.
- The demo personas (ticket 11) exercise each role, and each one's refusals.
