# 22 — FPT support reads Sales cases without prices (G20)

Status: ready-for-agent
Blocked by: platform-runtime/support-access 02 (core done; step 10 left, not blocking the API part)
Category: enhancement

Split from ticket 12 on 2026-10-12.

## What

The platform has support grants (ADR 0024): a support staff member works in
a customer's tenant under a grant the customer issued, with only the scopes
stamped on it, and every route not listed in `SUPPORT_ALLOWED_ROUTES` refuses
a support context (empty today, so all of Sales refuses support). dw_sales
ADR 0003 says support may see cases but never a price.

## Acceptance

1. Sales registers its support scope set at the composition-root seam:
   `{sales.overview.read, sales.case.read}`, never a price or write scope.
   Only a `sales_head` may issue a grant carrying it.
2. The read routes support needs are added to `SUPPORT_ALLOWED_ROUTES`, each
   in the same change as its negative test: the overview, the order and quote
   lists and details. Evidence, the source view and downloads stay closed
   (they carry prices or the customer's own file).
3. Under a support context, every amount is absent from every response,
   by the same mapper that hides it from a holder without
   `sales.price.read` (one owner of "who sees a price").
4. Negative tests under a support context: every Sales mutation → 403; the
   source view, evidence, downloads → 403; the audit log shows the support
   grant id on each read.
5. A test that no seeded FPT identity holds a `sales_*` role or
   `platform_admin` in the customer's tenant.
6. Mutation check: add a price scope to the support set and watch a test go
   red.

## Out of scope

- The web session and banner (platform support-access 03).

## Sources (as of 2026-10-12)

- `apps/api/src/dw_api/bootstrap/wiring.py` (`SUPPORT_ALLOWED_ROUTES`,
  support catalog), `test_support_routes.py`,
  `dw_platform/application/access_context.py` (`support`),
  `dw_sales/docs/adr/0003-roles-and-price-visibility.md`,
  `.claude/plans/platform-runtime/support-access/`.

## Comments
