# 05 — API routes and scopes

Status: ready-for-agent
Blocked by: 04, 11

## What

`/api/v1/sales/...`. The tenant and workspace come from the verified access
context only. Every mutation carries `case_version` (409 on mismatch),
honours `Idempotency-Key`, and is audited without amounts (decision 8). DW1's
own writes are recorded with `actor_kind='worker'` and `initiated_by`.

| Route                                                                                                                  | Scope                                                                                                               |
| ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `GET /overview`                                                                                                        | `sales.overview.read`                                                                                               |
| `GET /my-work`                                                                                                         | `sales.case.read`, filtered by the caller's scopes; cases assigned to the caller, and unassigned cases to every PIC |
| `GET /inbox`                                                                                                           | `sales.case.read`                                                                                                   |
| `POST /inbox/{message_id}/process`, `POST /inbox/process-all`                                                          | `sales.inbox.process`; refused while paused, naming who paused and when                                             |
| `GET /orders`, `GET /orders/{id}`                                                                                      | `sales.case.read`; amounts only with `sales.price.read`                                                             |
| `GET /orders/{id}/source/{attachment_id}?page=\|sheet=`, the same under `/quotes/{id}`                                 | `sales.case.read` + `sales.price.read`; records a served row                                                        |
| `GET /orders/{id}/artifacts/{artifact_id}`, the same under `/quotes/{id}`                                              | `sales.case.read`, plus `sales.price.read` for a price-bearing artifact, plus the state gate in ticket 06           |
| `POST /orders/{id}/findings/{finding_id}/disposition`                                                                  | `sales.order.prepare`; accepting `missing_noc_esf` needs `sales.compliance.ack`                                     |
| `POST /orders/{id}/lines/{no}/mapping`, `POST /orders/{id}/lines/{no}/delivery-date`                                   | `sales.order.prepare`                                                                                               |
| `POST /orders/{id}/prepare`, `/bravo-entry`, `/confirm`, `/close`                                                      | `sales.order.prepare`                                                                                               |
| `POST /orders/{id}/cross-check {accept\|return, reason}`                                                               | `sales.order.cross_check`                                                                                           |
| `GET /quotes`, `GET /quotes/{id}`                                                                                      | `sales.case.read`; evidence needs `sales.price.read`; other customers' rows need `sales.price.other_customers.read` |
| `POST /quotes/{id}/ycbg`, `/design-sent`, `/spec-discussion`, `/price`, `/submit`, `/sent`, `/master-list`, `/decline` | `sales.quote.prepare`                                                                                               |
| `POST /quotes/{id}/approval {approve\|return, comment}`                                                                | `sales.quote.approve`; the approver is not the pricer                                                               |
| `GET /quotes/screening`                                                                                                | `sales.case.read`                                                                                                   |
| `GET /master-data/...` (read-only, mock)                                                                               | `sales.case.read`; quotation prices need both price scopes                                                          |
| `POST /worker/pause`                                                                                                   | `sales.worker.pause`; notifies holders of `sales.worker.resume` (who paused, when), with no amounts                 |
| `POST /worker/resume {reason}`                                                                                         | `sales.worker.resume`; audited with the reason                                                                      |

## Amendments (2026-10-03)

- **Price omission (G2, decision 8).** One DTO mapper per resource omits
  amounts unless the caller holds the price scopes. That covers findings'
  expected/actual for the price-bearing codes, evidence, the source view and
  master-data quotations. A hidden amount comes back as
  `{"hidden": true}`, never as zero. The currency enum (USD, VND, JPY) is in
  OpenAPI (G38).
- **Source gate (G12, G23, decision 12).** The source route serves the
  original:
    - PDF bytes for the browser to render (pdf.js), with the anchor boxes
      beside them;
    - for Excel, the sheet grid as cells with their hidden and colour flags.

    The route is read through the API with a scope check, never through
    presigned links, and never runs a native rasteriser in the API process. It
    records `(principal, case_id, case_version, attachment_id, page or
sheet, served_at)`. `prepare` and `cross-check` answer 409 "chưa mở
    nguồn" unless the same principal was served the current version's source,
    plus every page or sheet holding a flagged or hand-entered value. The
    checker needs their own record.

- **Overview (G14, G21).** It returns:
    - counts per WIV step, read from `WIV_STEPS`;
    - messages without a disposition, and the age of the oldest waiting
      message;
    - the median and max of DW time (ingest → draft ready) and Sales
      decision time, separate from waits on Design, the approver and PC;
    - lines printed vs read;
    - lines mapped by convert list, confirmed candidate, or unresolved;
    - findings by code;
    - orders prepared with no corrected value;
    - drafts sent unedited;
    - the A3 shadow count;
    - an export per surveyed step and month.

    Targets come from `sales_kpi@1.0.0`, which this ticket ships in
    `configs/policies/` with a Pydantic schema in dw_sales and fictional
    values: the order-confirmation and quotation-time targets and the manual
    baseline per surveyed step. Which quotation-time target the demo
    measures is owed by Đạt; the key holds a fictional default and says so
    in a comment. No key is added that the overview does not read. The
    response holds no amounts.

- **Mocks bound and gated (G31).**
    - The mocks are bound to one configured demo `(tenant_id, workspace_id)`
      and return empty/None for any other scope. Test: tenant B sees an
      empty inbox and no customers, shown going red when the binding is
      removed.
    - The mocks, and `SimulatedDesign`, are wired only when not
      `settings.is_deployed`, or when `SALES_DEMO_TENANT_ID` names the demo
      tenant. Otherwise the sales routes answer "chưa cấu hình nguồn dữ
      liệu".
- **Delete the scaffold slice (G31)** in the same change: `SalesRequest`,
  `SalesSinkPort`, `InMemorySalesSink`, `HandleSales`, `POST /requests` and
  `test_sales_slice.py`. A route-inventory test asserts that every
  `/api/v1/sales/*` route depends on the verified access context.
- Run `reviewing-deployment-security` on this change.

## Acceptance

API tests on the authorized path for every route, plus these negative tests,
each one a persona from ticket 11:

- **Missing scope or wrong caller:**
    - any route without its scope → 403;
    - a tenant-beta id from tenant-alpha → 404;
    - `dev|binh.tran` → 403 on every `/api/v1/sales/*` route;
    - the viewer → 403 on case detail.
- **Separation of duties:**
    - the preparer, or the Bravo recorder, cross-checks → 409 "tách nhiệm";
    - the pricer approves → 409;
    - `dev|dieu.hoang` (holding `approver_boost`) approves → 403.
- **Order flow:**
    - stale `case_version` → 409;
    - confirm before `cross_checked` → 409;
    - prepare with one open blocking finding → 409 naming it;
    - deciding a superseded revision → 409;
    - a mapping to a non-candidate code → 409.
- **Permission sets:**
    - a PIC without `sales_export_control` accepting `missing_noc_esf` → 403;
    - a PIC resuming the worker → 403;
    - process while paused → 409;
    - pausing notifies `dev|giang.do` and nobody without
      `sales.worker.resume`.
- **Downloads:** per artifact kind, before its state → 409; as the viewer
  → 403.
- **Source gate:** prepare and cross-check without a served source → 409,
  with the UI's disabled attribute removed. A checker relying on the
  preparer's served record → 409.
- **Price leakage:**
    - as the viewer, as `dev|tam.ngo` (org_admin) and as a member without
      sales scopes, no known price string in any `/api/v1/sales` response or
      in `GET /audit/events` after M04 is decided and M10 approved;
    - a PIC without `sales_price_evidence` sees no other customer's price on
      M10.
