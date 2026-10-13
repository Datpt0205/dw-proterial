# 22 — FPT support reads Sales cases without prices (G20)

Status: done (2026-10-12; adversarially reviewed; not committed)
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

- Decided by the agent (Đạt away), 2026-10-12: **the set is for the whole
  workspace** (`resource_type` `workspace` only, key `sales.case_support`,
  label "Xem hồ sơ Sales (không xem giá)"). Narrowing to one case would need
  a `SupportResourcePort` and every list filtered to that case; nothing in
  the ticket or ADR 0003 asks for it, and the platform names `workspace`
  itself. Adding `order_case`/`quote_case` later is a new registration plus
  the filter, not a change to this one.
- Decided by the agent (Đạt away), 2026-10-12: **"FPT identity" is a person
  in `platform.support_staff`** (ADR 0024's list of the operators' staff;
  the spec's actor table: "Đội hỗ trợ FPT … not seeded"). The test checks the
  whole demo seed, every tenant, roles and permission sets. **Open for Đạt:**
  the platform seed's operator `dev|chi.le` (a tenant-alpha persona, "Quản
  trị nền tảng") holds `platform_admin` in tenant-alpha, the Sales demo
  tenant. If platform operators count as FPT identities too, that row
  breaks ADR 0003 §5 as written; changing it is a platform-seed change (the
  web e2e `platform-pages.spec.ts` and `feedback.spec.ts` sign in as her),
  not this ticket's. A pilot on real data waits on ADR 0024 open points
  anyway.
- Decided by the agent (Đạt away), 2026-10-12: **evidence, the source view
  and downloads** are the routes outside the five: `/source/*`, the
  artifacts list and files, `/quotes/screening` and `/master-data/*` (the
  price evidence's sources). Inside the quote detail the evidence is not
  even gathered for a caller without `sales.price.read` (`evidence: null`),
  and each priced line's amount is `{"hidden": true}`.

### As built (2026-10-12)

1. `dw_sales.application.access`: `SUPPORT_SCOPE_SET_KEY`,
   `SUPPORT_SCOPES = {sales.overview.read, sales.case.read}`,
   `SUPPORT_RESOURCE_TYPES = {workspace}`. `wiring.register_sales_support`
   registers it at the seam, after `build_sales`. Migration `7c8ba908575f`:
   `sales_head` gains `support.grant`; no other role or permission set holds
   it (`test_sales_roles.py`), so only the head can issue it (and decide an
   `org_admin`'s request).
2. `SUPPORT_ALLOWED_ROUTES` (`wiring.py`): `GET /api/v1/sales/overview`,
   `/orders`, `/orders/{case_id}`, `/quotes`, `/quotes/{case_id}`. The Sales
   router takes a `support_access_context` dependency for exactly those
   five (`ReadCtx`/`ReadSvc`); every other route keeps
   `get_access_context`, which refuses the support header.
3. No new mapper: a support context holds no `sales.price.read`, so
   `PriceView` hides every amount, as for any caller without it.
4. Tests. Unit `apps/api/tests/unit/test_sales_support.py` (the set, its
   registration, the five routes, every other Sales route → 403
   `support_context_not_allowed` under a grant header). Integration
   `apps/api/tests/integration/test_sales_api_support.py`, with a real grant
   (the head grants on `/api/v1/support/grants`, `ProvisioningService` lists
   and assigns a staff member, second factor in the token): who may issue it
   (PIC, viewer, purchasing → 403; tenant IT → `pending_approval` and cannot
   approve; the head approves and grants); the five reads answer with no
   known price anywhere while the same reads as An find them; every other
   Sales route (≥ 40) → 403 with the grant in force; one `support.access`
   row per read with the grant id, route template and path ids, none for a
   refused call; the staff member without the grant is refused, and
   tenant-beta headers next to the grant change nothing. Acceptance 5:
   `test_sales_personas.py::test_no_fpt_identity_holds_a_sales_role_or_platform_admin`
   over the whole demo seed, which first shows its query finds the head once
   listed as staff (rolled back): the membership trigger refuses a
   membership to someone listed, not listing someone who holds one.
5. **Found on the way (failure-modes #0):** the platform's route-table test
   (`test_support_routes.py`) compared two empty sets. FastAPI 0.141 keeps
   an included router as one `_IncludedRouter` in `app.routes`, so the walk
   saw no included route at all. It now walks FastAPI's
   `iter_route_contexts` (`api_routes`; review item 3 below) and asserts it
   read the mounted app (≥ 80 paths, Sales' included). Measured: `request.scope["route"].path` is the route's own
   path, with its router's prefix (`/api/v1/sales/...`) but without an
   `include_router(prefix=...)` one, so a platform route opened to support
   later must be listed as `/support/...`, not `/api/v1/support/...` (noted
   on platform support-access 02).

### Mutation checks (each red, then restored)

- `sales.price.read` added to `SUPPORT_SCOPES` → unit
  `test_the_support_set_is_…` red, and the integration read test red with
  real leaked prices (acceptance 6).
- `/quotes/{case_id}` removed from `SUPPORT_ALLOWED_ROUTES` → the platform
  route-table test and `test_the_composition_root_opens_exactly_the_five_reads`
  red.
- `/my-work` given the support context → the route-table test and
  `test_every_other_sales_route_takes_the_member_only_context` red.
- The old walker (`app.routes` only) → both walker tests red.
- Migration's upgrade skipped → `test_sales_roles` (two tests) red and every
  API support test red or erroring (no grant can be issued).
- The `support.access` append removed from the dependency → the trail test
  red.
- Not mutated: the tenant-beta-headers case (it guards the platform's
  `SupportAccessContextFactory`, which takes no header to mutate).

### Adversarial review (2026-10-12)

Re-run by the reviewer against a passing baseline, each red and restored:
`sales.price.read` in `SUPPORT_SCOPES` (unit set test, both integration read
tests); `/quotes/{case_id}` out of `SUPPORT_ALLOWED_ROUTES` (both route-table
tests); the old `app.routes`-only walker (five tests). What changed:

1. **The leak search walked two cases.** No persona holds `sales.case.read`
   without `sales.price.read` (`test_sales_api_prices.py` says so), so
   support is the first real caller of the case mappers without prices, and
   the read test looked at M04 and M10 only.
   `test_every_case_the_inbox_opens_reads_without_a_price` processes the
   whole mock inbox and reads both lists and every case in them as support.
   Mutation: `CURRENCY_MISMATCH`, `LME_BAND_MISMATCH` and
   `LINE_TOTAL_MISMATCH` taken out of `PRICE_BEARING_ORDER_CODES` → the new
   test red with a leaked amount, the two-case test still green.
2. **Revocation was tested on fakes only** (`test_support_context.py`):
   these five reads are the first routes a grant opens, so nothing exercised
   the SQL adapters' "grant ended". `test_the_head_revokes_and_the_next_read_is_refused`:
   the head revokes on `/api/v1/support/grants/{id}/revoke`, the next read
   is 403 `support_grant_ended`, and the trail holds only the read before.
   Mutation: the state check in `SupportAccessContextFactory._context`
   skipped → red (200).
3. **The walker read a private attribute and missed include-level
   dependencies.** `api_routes` walked `_IncludedRouter.original_router`,
   whose routes do not carry `include_router(dependencies=...)` (measured),
   so a route opted in at the include was invisible to the route-table test.
   It now uses FastAPI's public `iter_route_contexts` (as
   `test_platform_endpoint.py` already does) with the effective dependant,
   and `template()` reads the route's own path, the one the dependency
   matches at request time. The walker test has a route opted in at the
   include. Mutation: the route's own dependant only → red.

Checked and left as built: the five reads write nothing (the pending
decision is read, not touched); every other route refuses before any grant
is read; the head's grant stays effective only while the head holds both
scopes and `support.grant`; nothing depends on the environment
(reviewing-deployment-security §1–§6 not reached beyond the response shape,
which is the platform's taxonomy). Tenant isolation rests on the grant
naming the tenant (tested with tenant-beta headers) and on Sales' RLS reads,
the same path members take.
