---
status: Accepted
date: 2026-10-03
accepted: 2026-10-18 (Đạt, on review)
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
- Decision 5 as built (ticket 22, 2026-10-12): the set `sales.case_support`
  is granted for the workspace; `sales_head` alone holds `support.grant`
  (migration `7c8ba908575f`); five reads are open to it (the overview, the
  order and quote lists and details) and every other Sales route refuses a
  support context. The support ADR is platform ADR 0024 (it was 0008 when
  this was written).

## Addendum, 2026-10-21: IT proposes rules, the head approves

Decided by Đạt. The customer's IT may propose a version of a Sales rule
(ticket 19); approving one stays with the Sales head.

- A permission set `sales_rules_editor` = `{sales.rules.propose}` goes on an
  IT membership (migration `59cf23d3a859`). `org_admin` itself still holds no
  `sales.*` scope, so decision 4 stands for the role.
- A key whose documents hold prices or price policy (`sales_pricing`,
  `sales_quote_rules`, and `sales_order_rules` for its price tolerance and
  the LME rule: `PRICE_BEARING` in `dw_sales.application.rules`) also
  asks for `sales.price.read`, which decision 4's rule keeps off IT. The rules
  list leaves such a key out for a caller without it, and its schema, its
  platform documents and a proposal of it answer 403. Decision 2 extended to
  policy documents: fail closed.
- A second non-waivable rule, `sod_sales_rules_approve_vs_member_admin`,
  keeps `platform.members.write` and `sales.rules.approve` off one
  membership: whoever can grant roles cannot become the checker of a rule
  they proposed.
- The demo's tenant IT (`dev|tam.ngo`) holds the set and every other Sales
  route still refuses him.

Open: the admin console refuses only `platform.*` scopes on a grant, so a
tenant IT member can grant a `sales_*` set without a price scope to anyone,
themselves included (`sales_quote_approver`, for one). Whether IT may hand
out Sales sets at all is owed by Đạt.

## Addendum, 2026-10-28: the admin and the head change the rules, not a PIC

Decided by Đạt: "các sales PIC chỉ nên theo config chung ... chỉ có role admin
và IT đổi", then "giao hết cho admin cũng như sale trưởng, không cần IT", and
"Trưởng bộ phận tự áp dụng luôn".

- `sales_pic` loses `sales.rules.propose` (migration `40266fbc98bf`): a PIC
  works to the settings, and the rules pages leave their navigation.
- The head keeps `sales.rules.propose` with `sales.rules.approve`, and a
  version the head proposes is **applied directly**: no approval is opened,
  the row is decided by its proposer and marked `applied_directly`
  (`ck_rule_versions_applied_directly` holds its shape), and the audit trail
  says `sales.rules.applied`. A proposal already waiting on the key is
  decided first. The maker-checker rule still holds for every other
  proposer: the head approves what the admin proposes.
- The admin (the demo's `dev|tam.ngo`, `org_admin`) proposes through
  `sales_rules_editor`, as before; the 2026-10-21 rules above stand, so a
  price-bearing key is the head's alone to change.
- The set may still be given to a PIC by the admin; nothing does by default.

## Addendum, 2026-10-28: a PIC sees their own cases, the head sees the team's

Decided by Đạt ("các sales thấy luôn cả các đơn hàng, báo giá của nhau à,
đáng lẽ chỉ có trưởng phòng thấy thôi"), choosing: own cases, the pool's, and
the ones they are asked to check.

- **No new scope.** The platform already owns whose records a person sees
  (ADR-003 roll-up): a tenant set to `restricted` resolves `visible_owners`
  (the person and everyone reporting to them, `memberships.manager_user_id`)
  on the context; an open tenant, an admin and a support context carry no
  limit. The tenant's admin sets both on the admin pages.
- `dw_sales.application.visibility.sees_case` applies it to a case, whose
  owner is its assignee: unassigned (the pool), an assignee among
  `visible_owners`, or a case waiting on a checker step the caller may take
  (`next_steps.checker_scope`: a cross-check, a quotation's approval).
- Enforced where a case is read: `stored_order`/`stored_quote` take a
  required `viewer` (None only for DW1's lanes and carrying out a decision
  already taken), so a write is refused the same way; the order and quote
  lists, the board and the inbox filter on it. Outside it, a case reads as
  not found, never forbidden.
- The demo tenant is restricted, its PICs reporting to the head
  (`seed_personas.seed_demo_team`); the API suite's tenant stays open.
