# 11 — Demo personas

Status: ready-for-agent
Blocked by: 04

## What

A `dw_sales` seed module (for example `dw_sales.testing.seed_personas`) that
attaches the context's roles and permission sets to the seeded dev users, per
the spec's actor table. It uses uuid5 ids under the seed namespace and
upserts with ON CONFLICT, so re-running is a no-op.

Who owns which row: a user and their platform membership are platform rows,
so the two new users (`dev|khoa.lam`, `dev|tam.ngo`) are added to
`dw_platform.testing.seed_env.USERS` with platform roles only (`member`,
`org_admin`), and to the Keycloak realm if they must sign in through it. The
platform seed names no `sales_*` key, because it must not depend on a
context. The dw_sales module only adds the `sales_*` roles and permission
sets to existing memberships; the SoD trigger checks each write.

| Subject           | Display name    | Tenant / department | Gets                                                                        |
| ----------------- | --------------- | ------------------- | --------------------------------------------------------------------------- |
| `dev\|an.nguyen`  | Nguyễn Văn An   | alpha / kinh-doanh  | `sales_pic`, `sales_export_control`                                         |
| `dev\|dieu.hoang` | Hoàng Thị Diệu  | alpha / kinh-doanh  | `sales_pic`, `sales_price_evidence` (keeps the platform's `approver_boost`) |
| `dev\|giang.do`   | Đỗ Trường Giang | alpha / kinh-doanh  | `sales_head`                                                                |
| `dev\|khoa.lam`   | Lâm Minh Khoa   | alpha / kinh-doanh  | new platform user (`member`); `sales_pic`, `sales_quote_approver`           |
| `dev\|ha.vu`      | Vũ Thanh Hà     | alpha / dieu-hanh   | `sales_viewer`                                                              |
| `dev\|tam.ngo`    | Ngô Minh Tâm    | alpha / dieu-hanh   | new platform user (`org_admin`); no `sales_*`                               |
| `dev\|binh.tran`  | (as seeded)     | alpha / mua-hang    | nothing: the negative persona                                               |
| `dev\|bao.pham`   | (as seeded)     | beta / kinh-doanh   | `sales_pic` (cross-tenant tests)                                            |

The names are fictional. Never use a name from the customer's survey.
`dev|chi.le` (`platform_admin`) gets nothing and is not used in any
walk-through.

`Customer.sales_pic` in the mock data names these personas' emails, so the
case's `assigned_to` resolves to them (ticket 04).

## Fix `configs/demo/demo_users.yaml`

- Replace the labels `[sales]`, `[am]` and `[sales_admin]` with roles that
  exist.
- Drop users the seed never creates (`tung.pham.duc`, `duong.do.ngan`), or
  seed them.
- Align display names with the seed: today `binh.tran` differs.
- Add the two new personas, each with a description stating what they may
  and may not do.

## Acceptance

- A test asserts that every user in `demo_users.yaml` exists in the seed,
  with the same display name and roles.
- An integration test signs in as each persona and checks the scopes they
  resolve to against the spec's actor table.
