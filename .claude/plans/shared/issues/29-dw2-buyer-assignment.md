# 29 — DW2: a buyer per purchase request, given, reassigned or claimed

Status: ready-for-agent (the automatic rule is needs-info)
Blocked by: 08
Category: assignment / DW2

## What

§3: "DW2: thêm người phụ trách hồ sơ (buyer), luật giao, API và nút giao
lại" (M–L). Checked 2026-11-27: DW2 cases have no assignee; the buyers' work
is by scope (`purchasing.rfq.prepare`, `purchasing.po.prepare`,
`dw_purchasing/domain/brief.py:7`), so every buyer sees every case.

This ticket is the assignee, claim and reassign; the rule that assigns a PR
by itself waits on Proterial's answer (below).

## Design

- `purchasing.cases.assigned_to` (nullable, FK users `ON DELETE SET NULL`,
  indexed with `tenant_id` first for the list's filter; migration). New
  cases start unassigned.
- Using ticket 08's platform pieces: candidates = holders of
  `purchasing.rfq.prepare` in the workspace; "Nhận việc" by a holder on an
  unassigned case; reassign by a new scope `purchasing.case.assign` granted
  to `purchasing_head` (migration and role seed); version-checked, audited,
  the new buyer told.
- DW2's "Việc của tôi" filters "của tôi" / "chưa ai nhận"; the brief
  (`brief.py`) counts a buyer's own cases plus the unassigned.
- Nothing about who may *act* changes: any buyer may still act on any case,
  as today, until Đạt says otherwise.

## Acceptance

- API: claim twice at one version → 409 once; reassign without the scope
  refused; a non-buyer not a candidate; another tenant's case 404
  (PostgreSQL).
- The brief counts per assignee.

## Owed

- Proterial / Đạt: the rule for a PR's buyer (by item group, by requester's
  department, by supplier?), and whether only the assigned buyer may act.
